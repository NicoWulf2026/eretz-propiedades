#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Un paro cuya firma ya se diagnosticó a mano no necesita diagnosticarse otra vez.

Dry-run por defecto. No escribe en produccion, no cambia extractores, no cambia
huellas. `database_writes: 0`. Nunca convierte un defecto en un exito.

Por que existe
--------------
La cola se detiene ante un defecto de radio transversal y no vuelve a arrancar
hasta que alguien escribe una diferida firmada. Eso es correcto -relanzar sobre
un paro sin diagnosticar produce certificaciones con codigo sospechado- y tiene
un costo: **cada paro necesita una persona**. El 2026-09-20 la cola paro cuatro
veces en cinco horas y las cuatro esperaron a que yo mirara.

Pero la mayoria de esos paros no son diagnosticos nuevos. Medido sobre las 93
agencias en `NEEDS_FIX`:

    con diferida escrita                                   76  (82 %)
    sin diferida                                           17
    de esas, con firma YA VISTA en otra agencia diferida   13  (76 %)
    que requieren investigacion nueva de verdad             4

O sea que **tres de cada cuatro** paros pendientes son el mismo problema que
alguien ya miro contra la fuente y escribio. `ya_lo_vimos.py` los encuentra, y
hoy hay que correrlo a mano y copiar el diagnostico a mano.

Que hace, y las siete cosas que NO hace
---------------------------------------
Escribe una diferida para la agencia B cuando la agencia A tiene una diferida
**escrita por una persona** con la MISMA firma de defecto. Nada mas.

  1. Solo reutiliza firmas de diferidas previas que no sean automaticas. Una
     diferida automatica no puede justificar otra: dos saltos desde un
     diagnostico humano ya no son ese diagnostico.
  2. Nunca auto-difiere un radio FAMILIA o COMPARTIDO **salvo** que el
     precedente humano sea de ese mismo radio y esa misma firma. No se
     extrapola de un radio chico a uno grande.
  3. Nunca toca `variante_no_soportada`. Su firma se arma con conector,
     estrategia, componente y razones, y para "no reconoci la forma del sitio"
     esas cuatro cosas son identicas siempre: agrupa causas que no tienen nada
     que ver. Medido: una sola firma junta una SPA de React, jQuery contra la
     API de SOM, un 200 con cuerpo vacio, una url desconocida y un /buscador.
  4. No convierte `NEEDS_FIX` en `CERTIFIED`. Una diferida dice "esto ya se
     miro", no "esto esta bien".
  5. Guarda la procedencia: que agencia y que fecha justifican la diferida.
  6. Si la firma cambia, la diferida vieja deja de aplicar y hace falta
     analisis nuevo. La firma incluye la huella de estrategia, asi que un
     cambio de codigo la invalida sola.
  7. Una firma PARECIDA no alcanza. Solo la identica.

Uso:
    python scripts/diferir_por_precedente.py
    python scripts/diferir_por_precedente.py --aplicar
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DIFERIDAS = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
COLA_DE_DEFECTOS = CERT / "AGENCY_DEFECT_QUEUE.jsonl"

COMPONENTE_PROHIBIDO = "variante_no_soportada"
RADIOS_TRANSVERSALES = ("FAMILIA", "COMPARTIDO")
MARCA_AUTOMATICA = "diferida_por_precedente"


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def firma_de(fila: dict[str, Any]) -> tuple[str, str, str] | None:
    """Lo que hace a dos defectos EL MISMO defecto, en agencias distintas.

    Componente, radio y firma del patron. La firma del patron ya incluye
    conector, estrategia, huella y razones, asi que un cambio de codigo
    produce una firma distinta y el precedente deja de aplicar solo.
    """
    componente = fila.get("componente") or fila.get("componente_sospechoso")
    radio = fila.get("radio") or fila.get("radio_estimado")
    patron = fila.get("firma_del_patron") or fila.get("firma")
    if not componente or not radio or not patron:
        return None
    return (str(componente), str(radio), str(patron))


def precedentes_humanos() -> dict[tuple[str, str, str], dict[str, Any]]:
    """Firmas diagnosticadas POR UNA PERSONA, con su diagnostico.

    Se excluyen las automaticas: una diferida escrita por este mismo guion no
    puede justificar otra. Dos saltos desde un diagnostico humano ya no son
    ese diagnostico, y encadenarlos convierte una decision en una cadena de
    suposiciones.
    """
    # La cola de defectos es la que trae `firma_del_patron`; las diferidas
    # traen el diagnostico. Se cruzan por (agencia, componente, radio).
    firmas: dict[tuple[str, str, str], tuple[str, str]] = {}
    for fila in _jsonl(COLA_DE_DEFECTOS):
        clave = firma_de(fila)
        agencia = fila.get("canonical_agency_id")
        if clave and agencia:
            firmas[(agencia, clave[0], clave[1])] = (clave[2], "")
    salida: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fila in _jsonl(DIFERIDAS):
        if fila.get(MARCA_AUTOMATICA):
            continue
        agencia = fila.get("canonical_agency_id")
        componente = fila.get("componente")
        radio = fila.get("radio")
        if not agencia or not componente or not radio:
            continue
        encontrada = firmas.get((agencia, componente, radio))
        if not encontrada:
            continue
        salida[(componente, radio, encontrada[0])] = {
            "agencia": agencia, "cuando": fila.get("cuando"),
            "diagnostico": fila.get("diagnostico") or ""}
    return salida


def ya_diferidas() -> set[tuple[str, str, str]]:
    return {(f.get("canonical_agency_id"), f.get("componente"), f.get("radio"))
            for f in _jsonl(DIFERIDAS)}


def abiertos_hoy() -> set[str]:
    """Agencias cuyo resultado VIGENTE sigue siendo `NEEDS_FIX`.

    La cola de defectos es un registro de eventos, no una lista de problemas
    abiertos. Sin este filtro la herramienta escribia diferidas para defectos
    YA RESUELTOS: de las seis primeras candidatas, cuatro estaban en
    `CERTIFIED_COMPLETE` -`abriola` con 263 propiedades, recertificada esa
    misma manana tras arreglar la paginacion de Tokko-.

    Cuarta vez que este proyecto confunde un rastro con un estado. Las
    anteriores: el corrector de fuentes reaplicando una propuesta retirada, el
    corte por lote repitiendose sobre si mismo, y los tests con fecha fija.
    """
    from ledger_de_certificacion import vigentes_por_agencia
    vigentes, _ = vigentes_por_agencia(
        CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl")
    return {agencia for agencia, fila in vigentes.items()
            if fila.get("status") == "NEEDS_FIX"}


def candidatas() -> list[dict[str, Any]]:
    """Defectos abiertos cuya firma exacta ya tiene precedente humano."""
    precedentes = precedentes_humanos()
    hechas = ya_diferidas()
    abiertos = abiertos_hoy()
    ultimo: dict[tuple[str, str, str], dict[str, Any]] = {}
    for fila in _jsonl(COLA_DE_DEFECTOS):
        clave = firma_de(fila)
        agencia = fila.get("canonical_agency_id")
        if not clave or not agencia:
            continue
        ultimo[(agencia, clave[0], clave[1])] = fila
    salida = []
    for (agencia, componente, radio), fila in sorted(ultimo.items()):
        if componente == COMPONENTE_PROHIBIDO:
            continue
        if agencia not in abiertos:
            continue
        if (agencia, componente, radio) in hechas:
            continue
        clave = firma_de(fila)
        if not clave:
            continue
        precedente = precedentes.get(clave)
        if not precedente:
            continue
        if precedente["agencia"] == agencia:
            continue
        salida.append({"agencia": agencia, "componente": componente,
                       "radio": radio, "firma": clave[2],
                       "precedente": precedente})
    return salida


def texto(candidata: dict[str, Any]) -> str:
    precedente = candidata["precedente"]
    ajeno = precedente["diagnostico"].strip()
    if len(ajeno) > 1500:
        ajeno = ajeno[:1500] + " [...]"
    return (
        f"DIFERIDA POR PRECEDENTE, no por investigacion nueva. La firma de "
        f"este defecto -{candidata['componente']}, radio {candidata['radio']}, "
        f"patron {candidata['firma']}- es IDENTICA a la de "
        f"`{precedente['agencia']}`, diagnosticada a mano el "
        f"{precedente['cuando']}. No es una firma parecida: es la misma, y la "
        f"firma incluye conector, estrategia, huella de codigo y razones, asi "
        f"que un cambio en cualquiera de esas cosas la habria roto. "
        f"Esto NO afirma que la agencia este bien: afirma que este defecto ya "
        f"se miro contra una fuente y se escribio. Sigue en NEEDS_FIX y sigue "
        f"en la cola de defectos. "
        f"DIAGNOSTICO HEREDADO, textual: {ajeno}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    lista = candidatas()
    precedentes = precedentes_humanos()
    print(f"firmas con diagnostico humano disponibles: {len(precedentes)}")
    if not lista:
        print("no hay defectos abiertos cuya firma exacta tenga precedente")
        print("\ndatabase_writes: 0")
        return 0

    print(f"defectos que se pueden diferir por precedente: {len(lista)}\n")
    print(f"  {'AGENCIA':34} {'COMPONENTE':32} {'RADIO':11} PRECEDENTE")
    print(f"  {'-' * 34} {'-' * 32} {'-' * 11} {'-' * 26}")
    for c in lista:
        print(f"  {c['agencia'].split(':')[-1][:34]:34} "
              f"{c['componente'][:32]:32} {c['radio']:11} "
              f"{c['precedente']['agencia'].split(':')[-1][:26]}")

    transversales = [c for c in lista if c["radio"] in RADIOS_TRANSVERSALES]
    print(f"\n  de radio transversal: {len(transversales)} "
          f"(se difieren solo porque el precedente humano es del MISMO radio "
          f"y la MISMA firma)")

    if not args.aplicar:
        print("\n  DRY-RUN: nada escrito. Para aplicar: --aplicar")
        print("\ndatabase_writes: 0")
        return 0

    marca = time.strftime("%Y-%m-%dT%H:%M:%S")
    with DIFERIDAS.open("a", encoding="utf-8") as fh:
        for c in lista:
            fh.write(json.dumps({
                "canonical_agency_id": c["agencia"],
                "componente": c["componente"], "radio": c["radio"],
                "diagnostico": texto(c), "cuando": marca,
                MARCA_AUTOMATICA: True,
                "precedente_agencia": c["precedente"]["agencia"],
                "precedente_cuando": c["precedente"]["cuando"],
                "firma_del_patron": c["firma"],
                "database_writes": 0}, ensure_ascii=False) + "\n")
    print(f"\nescritas: {len(lista)} diferidas por precedente")
    print("  Ninguna cambia un estado de certificacion: siguen en NEEDS_FIX.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

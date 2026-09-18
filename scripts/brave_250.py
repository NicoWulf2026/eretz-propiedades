#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Brave a 250 inmobiliarias, elegidas por impacto. §10–§12.

No escribe en la base. `database_writes: 0`. No persiste payload de Brave:
sólo la conclusión propia, verificada contra el sitio real.

El resolutor no se copia: se importa de `canario_brave_50_v2`, que es el que se
midió en el A/B. Duplicar esa lógica fue exactamente como se coló el defecto
del TTL —el replay medía una copia y la copia leía un campo que producción
descartaba—, así que acá la única forma de que el canario y la corrida grande
difieran es que alguien las separe a propósito.

La selección NO es "las 250 más fáciles". Se ordena por avisos, que es lo que
se recupera si la web aparece, y después se le ponen dos frenos:

  - un tope por zona, para que no queden 250 agencias de Capital y ninguna del
    interior. Sin el tope, las 250 primeras por volumen serían casi todas de
    CABA y GBA, y el resultado no diría nada sobre el resto del país;
  - los nombres de una sola palabra corta entran igual, pero marcados
    `IDENTIDAD_DEBIL`. Son las que más falsos positivos dieron en el canario,
    y sacarlas de la muestra inflaría la precisión sin mejorar nada.

Uso:
    python scripts/brave_250.py --seleccionar        # sin gastar una query
    python scripts/brave_250.py --correr
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts import canario_brave_50_v2 as canario, search_provider as sp  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PADRON = DATOS / "roomix_agency_directory.jsonl"
VERIFICADAS = DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
YA_CORRIDAS = DATOS / "BRAVE_CANARIO_50.jsonl"
SELECCION = DATOS / "BRAVE_250_SELECCION.jsonl"
SALIDA = DATOS / "BRAVE_250.jsonl"

OBJETIVO = 250
TOPE_POR_ZONA = 18
# Las oficinas de red son el 3 % de las agencias sin web, pero publican mucho:
# ordenar por avisos sin este tope llenaba 137 de los 250 lugares con ellas.
# Eso no mide lo que hay que medir. Su desenlace ya lo conocemos -el
# verificador encuentra una `NETWORK_OFFICE_PAGE`, que no es una web propia- y
# gastar la mitad de las consultas en reconfirmarlo no enseña nada sobre las
# 8.600 restantes. Se las deja entrar por encima de su peso real, para poder
# medirlas, pero no que dominen la muestra.
TOPE_DE_RED = 40
USD_POR_MIL = 5.0

# Un nombre de una sola palabra corta -"Yacoub", "Alba"- no distingue a la
# inmobiliaria de una persona, un barrio o un comercio cualquiera. No se
# excluye: se marca, y su precisión se informa por separado.
NOMBRE_DEBIL = re.compile(r"^\s*\S{1,9}\s*$")


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    fuera = []
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            try:
                fuera.append(json.loads(linea))
            except ValueError:
                continue
    return fuera


def sin_web_resuelta() -> list[dict]:
    """El padrón menos lo ya resuelto y menos lo ya corrido en el canario."""
    resueltas = {f.get("canonical_agency_id") for f in leer(VERIFICADAS)}
    corridas = {f.get("agency_id") for f in leer(YA_CORRIDAS)}
    fuera = []
    for f in leer(PADRON):
        sid = f.get("stable_id")
        if not sid or sid in resueltas or sid in corridas:
            continue
        if f.get("official_web") or f.get("official_office_page"):
            continue
        fuera.append(f)
    return fuera


def zona_de(fila: dict) -> str:
    zonas = [z for z in (fila.get("zonas_observadas") or []) if z]
    return zonas[0] if zonas else "SIN_ZONA"


def seleccionar() -> list[dict]:
    """Por avisos, con tope por zona. El tope es el que hace la diversidad."""
    pool = sin_web_resuelta()
    pool.sort(key=lambda f: -(f.get("avisos_observados") or 0))
    por_zona: Counter = Counter()
    de_red = 0
    elegidas = []
    for f in pool:
        if len(elegidas) >= OBJETIVO:
            break
        zona = zona_de(f)
        if por_zona[zona] >= TOPE_POR_ZONA:
            continue
        if f.get("red_franquicia"):
            if de_red >= TOPE_DE_RED:
                continue
            de_red += 1
        por_zona[zona] += 1
        nombre = f.get("nombre_original") or ""
        elegidas.append({
            "agency_id": f.get("stable_id"),
            "nombre": nombre,
            "avisos_observados": f.get("avisos_observados") or 0,
            "zona": zona,
            "red_franquicia": f.get("red_franquicia"),
            "estrato_nombre": ("IDENTIDAD_DEBIL" if NOMBRE_DEBIL.match(nombre)
                               else "IDENTIDAD_NORMAL"),
            "tiene_matricula": bool(f.get("matricula")),
        })
    return elegidas


def informe_seleccion(elegidas: list[dict]) -> None:
    avisos = sum(e["avisos_observados"] for e in elegidas)
    zonas = Counter(e["zona"] for e in elegidas)
    estratos = Counter(e["estrato_nombre"] for e in elegidas)
    print(f"SELECCIONADAS           {len(elegidas)}")
    print(f"AVISOS_EN_JUEGO         {avisos:,}")
    print(f"ZONAS_DISTINTAS         {len(zonas)}")
    print(f"TOPE_POR_ZONA           {TOPE_POR_ZONA}")
    print(f"TOPE_DE_RED             {TOPE_DE_RED}")
    print(f"CON_RED_FRANQUICIA      {sum(1 for e in elegidas if e['red_franquicia'])}")
    print(f"CON_MATRICULA           {sum(1 for e in elegidas if e['tiene_matricula'])}")
    for k, n in estratos.most_common():
        print(f"   {k:20} {n}")
    print("\nzonas mas representadas:")
    for z, n in zonas.most_common(10):
        print(f"   {z[:32]:34} {n}")
    techo = OBJETIVO * canario.CONSULTAS_MAXIMAS
    print(f"\nCOSTO_MAXIMO_SI_NINGUNA_RESUELVE_GRATIS  "
          f"{techo} queries = USD {techo/1000*USD_POR_MIL:.2f}")
    print("   (es el techo, no la previsión: en el canario V2 la mitad se")
    print("    resolvió sin gastar una query)")


def correr(elegidas: list[dict], pausa: float) -> int:
    sp.cargar_env_local()
    buscador = sp.Brave()
    if not buscador.disponible():
        print("BRAVE_AUTH_FAILED")
        return 1
    padron = canario.padron_por_id()
    clases: Counter = Counter()
    vias: Counter = Counter()
    usadas = 0
    processed = 0
    with SALIDA.open("w", encoding="utf-8") as fh:
        for i, elegida in enumerate(elegidas, 1):
            fila = padron.get(elegida["agency_id"])
            if not fila:
                continue
            try:
                r = canario.resolver(fila, buscador, pausa)
            except RuntimeError as e:
                # El proveedor se agoto o la credencial dejo de valer. Se corta
                # sin mostrar el error crudo: puede traer la key adentro.
                print(f"   proveedor detenido en {i}/{len(elegidas)}: "
                      f"{type(e).__name__}")
                break
            ver = r["v"]
            processed += 1
            usadas += r["consultas"]
            clases[ver.clase] += 1
            vias[r["via"]] += 1
            fh.write(json.dumps({
                "agency_id": elegida["agency_id"],
                "nombre": elegida["nombre"],
                "avisos_observados": elegida["avisos_observados"],
                "zona": elegida["zona"],
                "red_franquicia": elegida["red_franquicia"],
                "estrato_nombre": elegida["estrato_nombre"],
                "verification_status": ver.clase,
                "site_type": ver.tipo_de_sitio,
                "confidence": ver.confianza,
                "official_url": ver.url,
                "evidence_summary": ver.evidencias,
                "contras": ver.contras,
                "razon": ver.razon,
                "discovery_method": r["via"],
                "queries_used": r["consultas"],
                "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "database_writes": 0,
            }, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 25 == 0:
                print(f"   {i}/{len(elegidas)}  queries={usadas}")
    print(f"\nPROCESADAS         {processed}")
    print(f"SELECCIONADAS      {len(elegidas)}")
    print(f"QUERIES_USADAS     {usadas}   (USD {usadas/1000*USD_POR_MIL:.2f})")
    for k, n in vias.most_common():
        print(f"   via {k:16} {n}")
    for k, n in clases.most_common():
        print(f"   {k:28} {n}")
    print(f"\nartefacto: {SALIDA}")
    print("\nNINGUNA de estas conclusiones vale como OFFICIAL_WEB hasta la")
    print("auditoria del §12. Brave descubre; el sitio real es el que prueba.")
    print("\ndatabase_writes: 0")
    complete = processed == len(elegidas)
    print(f"RUN_STATUS         {'COMPLETE' if complete else 'PARTIAL'}")
    return 0 if complete else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seleccionar", action="store_true")
    ap.add_argument("--correr", action="store_true")
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()

    if SELECCION.exists() and args.correr:
        elegidas = leer(SELECCION)
        print(f"selección ya fijada: {len(elegidas)} agencias\n")
    else:
        elegidas = seleccionar()
        SELECCION.write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in elegidas),
            encoding="utf-8")
        informe_seleccion(elegidas)
        print(f"\nseleccion: {SELECCION}")

    if not args.correr:
        print("\ndatabase_writes: 0")
        return 0
    return correr(elegidas, args.pausa)


if __name__ == "__main__":
    raise SystemExit(main())

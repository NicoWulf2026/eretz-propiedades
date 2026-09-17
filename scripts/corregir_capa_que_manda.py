#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aplicar las correcciones de fuente donde el certificador las mira. §6, §11.

Dry-run por defecto. No toca producción, no cambia extractores, no cambia
huellas. `database_writes: 0`.

Por qué existe: cinco correcciones que di por aplicadas no hacían nada
---------------------------------------------------------------------
El 2026-09-17 corregí la fuente de cinco agencias —tres del canario de cambio de
fuente y dos que apuntaban a una ficha en vez del catálogo— editando
`scrape_source_technology_map.jsonl`. Verifiqué que el archivo quedara bien,
verifiqué que `resolve_identity()` devolviera la URL nueva, y reporté las cinco
como aplicadas.

Ninguna tuvo efecto. `fios` se recertificó dos veces después del cambio, a las
01:07 y a las 02:54, **con la URL vieja**.

`resolve_identity()` resuelve con esta precedencia:

    1. platform.domain      <- agency_platform_directory.jsonl
    2. source.official_url  <- scrape_source_technology_map.jsonl   <- edité ESTA
    3. resolution.official_domain
    4. verificada.official_url
    5. directory.official_url

y **2.327 de las 2.330** agencias del registro de fuentes tienen también entrada
en el directorio de plataformas. La capa 1 gana siempre que exista, así que
editar la capa 2 es inerte para casi todo el padrón.

Mi verificación no lo detectó porque buscó el directorio de plataformas con un
glob —`*platform*` dentro de `ERETZ_AGENCY_DATA`— y encontró otro archivo. La
cola usa `D:\\INMO CAPITAL\\agency_platform_directory.jsonl`, que está en otro
lado. Comparé contra una capa vacía y me dio verde.

La lección, que vale más que el arreglo: **verificar el artefacto no es
verificar el efecto**. Lo que había que comprobar no era que el archivo quedara
escrito sino que la certificación siguiente usara la URL nueva.

Qué hace
--------
Lee el rastro de auditoría de las correcciones ya emitidas, las aplica sobre el
campo `domain` del directorio de plataformas —que es el que gana— y después
**verifica con las rutas reales de la cola** que `resolve_identity()` devuelva
la URL nueva. Si no la devuelve, lo dice.

Uso:
    python scripts/corregir_capa_que_manda.py
    python scripts/corregir_capa_que_manda.py --aplicar
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

# Las rutas REALES que usa `run_agency_certification_queue.py`. Están acá
# escritas y no descubiertas con un glob, que es como se coló el error.
V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

RASTROS = (CERT / "ERETZ_SOURCE_SWITCH_APLICADO.jsonl",
           CERT / "ERETZ_FUENTE_FICHA_CORREGIDA.jsonl")
AUDITORIA = CERT / "ERETZ_CAPA_QUE_MANDA_CORREGIDA.jsonl"


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


def _sin_barra(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def correcciones_pendientes() -> dict[str, dict[str, Any]]:
    """Lo que hay que aplicar, leyendo los rastros EN ORDEN.

    Un rastro de auditoría es una **historia**, no una lista de estados
    deseados, y tratarlo como lo segundo ya salió mal: una propuesta retirada
    —la raíz de `barnes`, generada por una regresión— seguía escrita ahí, y el
    corrector la reaplicó después de que yo la revirtiera a mano. Revertir el
    destino no alcanza si el origen la vuelve a emitir.

    Por eso una fila con `retirada: true` cancela lo pendiente de esa agencia.
    La fila retirada NO se borra del rastro: el §11 pide conservar evidencia, y
    una decisión equivocada que se retira es parte de la historia.
    """
    pendientes: dict[str, dict[str, Any]] = {}
    for rastro in RASTROS:
        for fila in _jsonl(rastro):
            agencia = fila.get("canonical_agency_id")
            if not agencia:
                continue
            if fila.get("retirada"):
                pendientes.pop(agencia, None)
                continue
            destino = fila.get("a")
            if destino:
                pendientes[agencia] = {
                    "a": destino, "de": fila.get("de"),
                    "porque": (fila.get("evidencia_del_canario")
                               or fila.get("porque") or ""),
                    "rastro": rastro.name,
                }
    return pendientes


def resuelto_hoy(agencia: str) -> str | None:
    """Lo que la cola usaría AHORA, con sus rutas de verdad."""
    from scripts.agency_certifier import load_catalog, resolve_identity
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    registro = catalogo.get(agencia)
    if not registro:
        return None
    return (resolve_identity(registro, agencia) or {}).get("official_url")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    pendientes = correcciones_pendientes()
    if not pendientes:
        print("no hay correcciones emitidas en los rastros de auditoria")
        return 1

    from scripts.agency_certifier import load_catalog, resolve_identity
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)

    print(f"correcciones ya emitidas: {len(pendientes)}\n")
    print(f"  {'AGENCIA':36} {'EN EL CATALOGO':16} {'EFECTO HOY':12}")
    print(f"  {'-' * 36} {'-' * 16} {'-' * 12}")

    a_aplicar, sin_entrada, ya_ok = [], [], []
    for agencia, dato in sorted(pendientes.items()):
        registro = catalogo.get(agencia)
        if not registro:
            sin_entrada.append((agencia, dato))
            print(f"  {agencia.split(':')[-1][:36]:36} {'NO ESTA':16} "
                  f"{'-':12}")
            continue
        actual = _sin_barra((resolve_identity(registro, agencia) or {}).get(
            "official_url"))
        if actual == _sin_barra(dato["a"]):
            ya_ok.append(agencia)
            estado = "YA APLICA"
        else:
            a_aplicar.append((agencia, dato, actual))
            estado = "INERTE"
        print(f"  {agencia.split(':')[-1][:36]:36} {'si':16} {estado:12}")

    print(f"\n  inertes que hay que aplicar en la capa que manda: "
          f"{len(a_aplicar)}")
    print(f"  ya vigentes: {len(ya_ok)}   sin entrada en el catalogo: "
          f"{len(sin_entrada)}")
    for agencia, dato in sin_entrada:
        print(f"     {agencia.split(':')[-1][:34]:36} no figura con esa clave; "
              f"no se inventa una")

    if not a_aplicar:
        print("\nnada que aplicar")
        return 0

    for agencia, dato, actual in a_aplicar:
        print(f"\n  {agencia.split(':')[-1]}")
        print(f"     resuelve hoy : {actual[:76]}")
        print(f"     deberia ser  : {dato['a'][:76]}")

    if not args.aplicar:
        print(f"\n  DRY-RUN: {len(a_aplicar)} cambios preparados y NO escritos.")
        print("  Para aplicar: --aplicar")
        print("\ndatabase_writes: 0")
        return 0

    respaldo = PLATAFORMAS.with_suffix(
        f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(PLATAFORMAS, respaldo)
    cambios = {a: d for a, d, _ in a_aplicar}
    lineas, escritas = [], 0
    for fila in _jsonl(PLATAFORMAS):
        agencia = fila.get("canonical_agency_id")
        if agencia in cambios:
            fila = dict(fila)
            # La url vieja se conserva: el §11 pide evidencia, no borrado.
            fila["previous_domain"] = fila.get("domain")
            fila["domain"] = cambios[agencia]["a"]
            fila["domain_corrected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            fila["domain_corrected_reason"] = cambios[agencia]["porque"][:400]
            escritas += 1
        lineas.append(json.dumps(fila, ensure_ascii=False))
    temporal = PLATAFORMAS.with_suffix(".jsonl.tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    temporal.replace(PLATAFORMAS)

    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for agencia, dato, actual in a_aplicar:
            fh.write(json.dumps({
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "canonical_agency_id": agencia,
                "capa": "agency_platform_directory.jsonl :: domain",
                "de": actual, "a": dato["a"],
                "porque_estaba_inerte": ("se habia editado "
                                         "scrape_source_technology_map.jsonl, "
                                         "que pierde contra platform.domain"),
                "respaldo": respaldo.name, "database_writes": 0},
                ensure_ascii=False) + "\n")

    # LA VERIFICACION QUE FALTABA: no que el archivo quedo escrito, sino que la
    # cola resuelve distinto. Se recarga el catalogo desde cero.
    print(f"\naplicadas: {escritas}   respaldo: {respaldo.name}")
    print("\nverificacion con las rutas REALES de la cola:")
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    fallaron = 0
    for agencia, dato, _ in a_aplicar:
        ahora = _sin_barra((resolve_identity(catalogo.get(agencia, {}),
                                             agencia) or {}).get("official_url"))
        ok = ahora == _sin_barra(dato["a"])
        fallaron += not ok
        print(f"   {'OK ' if ok else 'NO '}{agencia.split(':')[-1][:34]:36} "
              f"-> {ahora[:56]}")
    if fallaron:
        print(f"\n  {fallaron} NO resuelven a lo esperado: hay otra capa "
              f"ganando. NO dar por aplicado.")
        return 1
    print("\n  Las agencias corregidas van a recertificarse en la proxima "
          "pasada,")
    print("  porque `is_current_result` invalida cuando la fuente cambio.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

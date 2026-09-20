#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una lista de socios de un colegio no es la web de ninguno de sus socios.

Dry-run por defecto. No escribe en produccion, no cambia extractores, no cambia
huellas. `database_writes: 0`.

Que retira
----------
Solo las dos clases donde la url no es de NINGUNA de las agencias que la
comparten, segun `fuentes_compartidas.py`:

    DIRECTORIO_INSTITUCIONAL   /socios, /colegiados, /miembros, /padron...
    BUSCADOR_DE_PORTAL         /buscar, /busqueda sobre un host compartido

Son 7 grupos y 23 agencias. `https://cir.org.ar/socios` la comparten diez.

NO toca `OFICINAS_DE_RED` -ahi el sitio SI es de alguna de las oficinas y hay
que decidir de cual-, ni `POSIBLE_DUPLICADO` -el arreglo puede ser de identidad
y no de fuente-, ni los 10 `SIN_CLASIFICAR`.

Por que hay que tocar VARIAS capas
----------------------------------
`resolve_identity` resuelve con esta precedencia:

    1. platform.domain      <- agency_platform_directory.jsonl
    2. source.official_url  <- scrape_source_technology_map.jsonl
    3. resolution.official_domain
    4. verificada.official_url  <- AGENCY_OFFICIAL_WEB_VERIFIED.jsonl
    5. directory.official_url

De las 23 agencias, 4 resuelven por la capa 1 y 12 por la capa 4. Retirar solo
una capa deja que aparezca la de abajo con la MISMA url, y el trabajo queda
inerte: ya paso con cinco correcciones de fuente que di por aplicadas y no
hacian nada. Asi que se retira de TODAS las capas que la tengan, y despues se
comprueba el EFECTO, no el archivo.

Que se conserva
---------------
La url no se borra: se guarda en `url_retirada_como_fuente` con el motivo y la
fecha. Un perfil en un directorio sigue siendo prueba de que la inmobiliaria
existe; lo unico que deja de ser es fuente de inventario. El §11 pide conservar
evidencia.

Uso:
    python scripts/retirar_fuente_compartida.py
    python scripts/retirar_fuente_compartida.py --aplicar
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

V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
AUDITORIA = CERT / "ERETZ_FUENTES_RETIRADAS.jsonl"

CLASES = ("DIRECTORIO_INSTITUCIONAL", "BUSCADOR_DE_PORTAL")

# archivo -> campos que pueden traer la url de la fuente
CAPAS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (PLATAFORMAS, ("domain",)),
    (DATOS / "scrape_source_technology_map.jsonl", ("official_url",)),
    (V2 / "AGENCY_ID_RESOLUTION_FINAL.jsonl", ("official_domain",)),
    (DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl", ("official_url",)),
    (DATOS / "agency_web_directory.jsonl", ("official_url",)),
)


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


def normalizar(url: Any) -> str:
    return str(url or "").strip().rstrip("/").lower()


def a_retirar() -> dict[str, str]:
    """Agencia -> url que hay que dejar de usar como fuente."""
    from fuentes_compartidas import colisiones
    salida: dict[str, str] = {}
    for grupo in colisiones():
        if grupo["clase"] not in CLASES:
            continue
        for agencia in grupo["agencias"]:
            salida[agencia] = grupo["url"]
    return salida


def retirar_en(ruta: Path, campos: tuple[str, ...],
               objetivo: dict[str, str], aplicar: bool) -> int:
    """Quita la url de esos campos, conservandola. Devuelve cuantas filas tocó."""
    if not ruta.exists():
        return 0
    lineas, tocadas = [], 0
    marca = time.strftime("%Y-%m-%dT%H:%M:%S")
    for fila in _jsonl(ruta):
        agencia = fila.get("canonical_agency_id")
        url = objetivo.get(agencia) if agencia else None
        if url:
            cambiada = False
            for campo in campos:
                if normalizar(fila.get(campo)) == normalizar(url):
                    if not cambiada:
                        fila = dict(fila)
                        cambiada = True
                    fila["url_retirada_como_fuente"] = fila.get(campo)
                    fila["url_retirada_at"] = marca
                    fila["url_retirada_porque"] = (
                        "url compartida por varias agencias y que no es la web "
                        "de ninguna: directorio institucional o buscador de "
                        "portal")
                    fila[campo] = None
            if cambiada:
                tocadas += 1
        lineas.append(json.dumps(fila, ensure_ascii=False))
    if tocadas and aplicar:
        respaldo = ruta.with_suffix(
            ruta.suffix + f".bak_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(ruta, respaldo)
        temporal = ruta.with_suffix(ruta.suffix + ".tmp")
        temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        temporal.replace(ruta)
    return tocadas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    objetivo = a_retirar()
    if not objetivo:
        print("no hay fuentes compartidas de las clases que se retiran")
        return 0

    from scripts.agency_certifier import load_catalog, resolve_identity
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)

    print(f"agencias a las que se les retira la fuente: {len(objetivo)}\n")
    por_url: dict[str, list[str]] = {}
    for agencia, url in sorted(objetivo.items()):
        por_url.setdefault(url, []).append(agencia)
    for url, agencias in sorted(por_url.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(agencias):>2} agencias  {url[:62]}")
        for agencia in agencias[:3]:
            actual = (resolve_identity(catalogo.get(agencia, {}), agencia)
                      or {}).get("official_url")
            print(f"        {agencia.split(':')[-1][:36]:36} resuelve a "
                  f"{str(actual)[:40]}")
        if len(agencias) > 3:
            print(f"        ... y {len(agencias) - 3} mas")

    tocadas_por_capa = {}
    for ruta, campos in CAPAS:
        tocadas_por_capa[ruta.name] = retirar_en(ruta, campos, objetivo,
                                                 args.aplicar)
    print("\n  filas que contienen esa url, por capa:")
    for nombre, cuantas in tocadas_por_capa.items():
        print(f"     {nombre:46} {cuantas}")

    if not args.aplicar:
        print("\n  DRY-RUN: nada escrito. Para aplicar: --aplicar")
        print("\ndatabase_writes: 0")
        return 0

    # LA VERIFICACION QUE IMPORTA: no que los archivos quedaron escritos, sino
    # que la cola ya no resuelve a esa url. Se recarga el catalogo desde cero.
    print("\nverificacion con las rutas REALES de la cola:")
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    fallaron = 0
    for agencia, url in sorted(objetivo.items()):
        ahora = (resolve_identity(catalogo.get(agencia, {}), agencia)
                 or {}).get("official_url")
        ok = normalizar(ahora) != normalizar(url)
        fallaron += not ok
        estado = "OK " if ok else "NO "
        print(f"   {estado}{agencia.split(':')[-1][:36]:36} -> "
              f"{str(ahora)[:42]}")
    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for agencia, url in sorted(objetivo.items()):
            fh.write(json.dumps({
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "canonical_agency_id": agencia, "url_retirada": url,
                "porque": "compartida y de ninguna: directorio o buscador",
                "database_writes": 0}, ensure_ascii=False) + "\n")
    if fallaron:
        print(f"\n  {fallaron} SIGUEN resolviendo a la url retirada: hay otra "
              f"capa con el mismo valor. NO dar por aplicado.")
        return 1
    print("\n  Ninguna resuelve ya a una url compartida.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

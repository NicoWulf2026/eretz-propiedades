#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Separar la web propia de la inmobiliaria del perfil que tiene en un portal.

Una ficha en todoprops.com, un exhibidor en construex o una publicacion en
realestate.com.au no son la web de la inmobiliaria. Contarlas como tal infla
"agencias con web oficial" con paginas de terceros, y despues alguien lee ese
numero como cobertura.

Tampoco se borran: son evidencia real de que la inmobiliaria existe y opera, y
sirven para buscar su sitio propio mas adelante. Se reclasifican y se guarda de
donde salieron.

Distingue tres cosas que se confunden:

  OFFICIAL_WEB              dominio propio de la inmobiliaria
  OFFICIAL_OFFICE_PAGE      su pagina dentro de la red a la que pertenece
                            (Century 21, RE/MAX): no es un portal ajeno, es su
                            casa dentro de su franquicia
  EXTERNAL_PORTAL_PROFILE   perfil en un marketplace o directorio de terceros

Solo lee y reescribe artefactos. No pide nada a la red.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

VERSION = "portal_reclass_v1"

OFICIAL = "OFFICIAL_WEB"
OFICINA_RED = "OFFICIAL_OFFICE_PAGE"
PERFIL_PORTAL = "EXTERNAL_PORTAL_PROFILE"

# Marketplaces, directorios y agregadores. Una inmobiliaria puede tener perfil
# en cualquiera; ninguno es su web.
PORTALES = re.compile(
    r"^(www\.)?("
    r"zonaprop|argenprop|properati|inmuebles24|mercadolibre|articulo\.mercadolibre|"
    r"realestate\.com\.au|construex|todoprops|inmobusqueda|miguiaargentina|"
    r"near-place|mapaprop|proppies|liderprop|inmoclick|choza\.ai|indice-inmobiliario|"
    r"mercadoprop|emis\.com|kitepropcrm|yably|aspenbienesraices|"
    r"paginasamarillas|cylex|opendi|infoisinfo|guiaempresas|"
    r"facebook|instagram|linkedin|twitter|x\.com|youtube|linktr\.ee|"
    r"colegioinmobiliario|martilleros|cpicordoba|cir\.org)", re.I)

# Redes: la pagina de la oficina dentro de su propia franquicia. No es un portal
# ajeno, pero tampoco es un dominio propio, y conviene poder distinguirlo.
REDES = re.compile(
    r"^(www\.)?(century21|remax|remax-|kellerwilliams|coldwellbanker|"
    r"engelvoelkers|sothebysrealty)", re.I)


def host(u: str) -> str:
    return re.sub(r"^https?://", "", u or "").split("/")[0].lower()


def clasificar(url: str) -> tuple[str, str]:
    h = host(url)
    if PORTALES.match(h):
        return PERFIL_PORTAL, f"{h} es un portal, directorio o red social"
    if REDES.match(h):
        return OFICINA_RED, f"{h} es el sitio de la red, no un dominio propio"
    return OFICIAL, ""


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def escribir(ruta: Path, filas: list[dict]) -> None:
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas),
                   encoding="utf-8")
    tmp.replace(ruta)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--directorio",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\PORTAL_RECLASSIFICATION.jsonl")
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo informa, no reescribe el directorio")
    a = ap.parse_args()

    filas = leer(Path(a.directorio))
    cambios = []
    for f in filas:
        tipo, motivo = clasificar(f.get("domain") or "")
        anterior = f.get("web_kind")
        f["web_kind"] = tipo
        if tipo != OFICIAL:
            cambios.append({
                "canonical_agency_id": f["canonical_agency_id"],
                "eretz_id": f.get("eretz_id"),
                "agency_name": f.get("agency_name"),
                "url": f.get("domain"),
                "host": host(f.get("domain") or ""),
                "clasificacion_anterior": anterior or "OFFICIAL_WEB (implicita)",
                "clasificacion_nueva": tipo,
                "motivo": motivo,
                "evidencia": "clasificacion por host, sin peticiones a la red",
                "propiedades_extraidas": f.get("properties_normalized"),
                "platform": f.get("platform"),
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "classifier_version": VERSION,
            })

    escribir(Path(a.salida), cambios)
    if a.aplicar:
        escribir(Path(a.directorio), filas)

    total = len(filas)
    c = Counter(f["web_kind"] for f in filas)
    print("### RECLASIFICACION DE WEBS ###")
    print(f"  agencias en el directorio:      {total:,}")
    for k, v in c.most_common():
        print(f"    {k:26} {v:5,}  ({v/total*100:5.1f}%)")
    print(f"\n  reclasificadas: {len(cambios):,}")
    print(f"  hosts mas frecuentes entre las reclasificadas:")
    for k, v in Counter(x["host"] for x in cambios).most_common(10):
        print(f"    {k:34} {v:4}")
    propias = c.get(OFICIAL, 0)
    print(f"\n  AGENCIAS CON WEB PROPIA (corregido): {propias:,}")
    print(f"  antes se contaban:                   {total:,}")
    print(f"  diferencia:                          {total - propias:,}")
    print(f"\n  artefacto -> {a.salida}")
    if not a.aplicar:
        print("  (informe solamente; usar --aplicar para reescribir el directorio)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
import difflib
import re
import sys
import time
from collections import Counter
from pathlib import Path

VERSION = "portal_reclass_v1"

OFICIAL = "OFFICIAL_WEB"
# Ni web propia ni perfil de portal: una guia de rubros, un diario de la zona o
# una pagina de vehiculos. Se comprobo mirando QUE publica esa forma de url, no
# adivinando por el dominio. No se borra ninguna: son la evidencia de que la
# url que el padron tiene cargada no lleva a la inmobiliaria.
NO_INMOBILIARIA = "NOT_A_REAL_ESTATE_WEB"
OFICINA_RED = "OFFICIAL_OFFICE_PAGE"
PERFIL_PORTAL = "EXTERNAL_PORTAL_PROFILE"

# Marketplaces, directorios y agregadores. Una inmobiliaria puede tener perfil
# en cualquiera; ninguno es su web.
PORTALES = re.compile(
    r"^(www\.)?("
    r"zonaprop|argenprop|properati|inmuebles24|mercadolibre|articulo\.mercadolibre|"
    r"realestate\.com\.au|construex|todoprops|inmobusqueda|miguiaargentina|"
    r"near-place|mapaprop|proppies|liderprop|inmoclick|choza\.ai|indice-inmobiliario|"
    r"mercadoprop|emis\.com|yably|aspenbienesraices|"
    r"paginasamarillas|cylex|opendi|infoisinfo|guiaempresas|"
    r"facebook|instagram|linkedin|twitter|x\.com|youtube|linktr\.ee|"
    r"colegioinmobiliario|martilleros|cpicordoba|cir\.org)", re.I)

# Redes: la pagina de la oficina dentro de su propia franquicia. No es un portal
# ajeno, pero tampoco es un dominio propio, y conviene poder distinguirlo.
REDES = re.compile(
    r"^(www\.)?(century21|remax|remax-|kellerwilliams|coldwellbanker|"
    r"engelvoelkers|sothebysrealty)", re.I)


def host(u: str) -> str:
    """El host, sin www.

    Sin normalizarlo, "www.bustamantepropiedades.com" y
    "bustamantepropiedades.com" se cuentan como dos sitios distintos y el
    dominio compartido por dos inmobiliarias no se ve. Son tres casos, pero
    uno de ellos son las 3.137 propiedades en disputa mas grandes que tiene
    el proyecto.
    """
    h = re.sub(r"^https?://", "", u or "").split("/")[0].lower()
    return re.sub(r"^www\.", "", h)


def agencias_por_host(filas: list[dict]) -> dict[str, list[str]]:
    """Cuantas inmobiliarias distintas cuelgan de cada host.

    Es la senal que no depende de conocer el nombre del portal. Un portal
    aloja a muchas inmobiliarias en UN host -choza.ai figura como web de 36-;
    un SaaS marca blanca le da a cada una el suyo -kitepropcrm.com tiene 10
    hosts para 10 inmobiliarias-. La diferencia es estructural y se puede
    contar, y contarla es lo que evita tener que mantener una lista de nombres
    que siempre va a estar incompleta.

    kitepropcrm estaba en la lista de portales por su nombre y por eso 10 webs
    propias figuraban como perfiles ajenos. La cuenta lo desmiente.
    """
    c: dict[str, list[str]] = {}
    for f in filas:
        h = host(f.get("domain") or "")
        if h:
            c.setdefault(h, []).append(f.get("agency_name") or f["canonical_agency_id"])
    return c


# Dos inmobiliarias en un host no significan lo mismo que veinte. Con veinte es
# un portal; con dos suele ser el MISMO negocio cargado dos veces en el padron
# -"De Bernardis Propiedades" y "FABIANA DE BERNARDIS GESTION INMOBILIARIA"
# comparten sitio porque son la misma inmobiliaria-. Declarar portal a ese sitio
# le quitaria la web propia a quien si la tiene.
MUCHAS_AGENCIAS = 3
PARECIDO_MINIMO = 0.6
AMBIGUA = "AMBIGUOUS_WEB_ATTRIBUTION"


# Palabras que aparecen en media Argentina inmobiliaria y no distinguen a nadie.
# Compararlas hace que dos nombres se parezcan por lo que tienen en comun con
# todos los demas.
GENERICAS = {"propiedades", "propiedad", "inmobiliaria", "inmobiliarias",
             "inmobiliario", "inmobiliarios", "negocios", "gestion", "servicios",
             "bienes", "raices", "estudio", "grupo", "consultora", "desarrollos",
             "real", "estate", "sa", "srl", "sas", "y", "de", "del", "la", "el",
             "&", "-", "ii", "i"}


def distintivas(nombre: str) -> set[str]:
    palabras = re.split(r"[^0-9a-zA-Zaeiouunc]+", (nombre or "").lower())
    return {p for p in palabras if p and p not in GENERICAS and len(p) > 2}


def mismo_negocio(a: str, b: str) -> bool:
    """Dos nombres que describen a la misma inmobiliaria.

    Decide por las palabras que DISTINGUEN: "De Bernardis Propiedades" y
    "FABIANA DE BERNARDIS GESTION INMOBILIARIA" son la misma inmobiliaria
    cargada dos veces, y comparten "bernardis"; "Arquitectura Inmobiliaria" y
    "Urbano Rosario" no comparten ninguna.
    """
    x, y = (a or "").lower().strip(), (b or "").lower().strip()
    if not x or not y:
        return False
    if x in y or y in x:
        return True
    dx, dy = distintivas(x), distintivas(y)
    if dx and dy and (dx <= dy or dy <= dx or len(dx & dy) >= 1):
        return True
    return difflib.SequenceMatcher(None, x, y).ratio() >= PARECIDO_MINIMO


def clasificar(url: str, por_host: dict, nombre: str,
               observado: dict | None = None) -> tuple[str, str]:
    """Que ES esa url para esa inmobiliaria.

    `por_host` y `nombre` son obligatorios a proposito. Cuando eran opcionales,
    build_platform_directory.py llamaba con la url sola y la senal estructural
    no se evaluaba nunca: la regeneracion del directorio devolvia en silencio a
    52 perfiles de portal la condicion de web propia. Sin valor por defecto, el
    que olvide pasarlos falla en el acto.
    """
    h = host(url)
    # Lo que se vio en el sitio manda sobre cualquier regla sobre el dominio.
    if observado:
        return NO_INMOBILIARIA, observado.get("motivo") or "el sitio no publica inmuebles"
    if PORTALES.match(h):
        return PERFIL_PORTAL, f"{h} es un portal, directorio o red social"
    if REDES.match(h):
        return OFICINA_RED, f"{h} es el sitio de la red, no un dominio propio"
    vecinos = [n for n in (por_host or {}).get(h, []) if n != nombre]
    n = len(vecinos) + 1
    if n >= MUCHAS_AGENCIAS:
        return PERFIL_PORTAL, (f"{h} figura como web de {n} inmobiliarias "
                               f"distintas: no es el dominio propio de ninguna")
    if vecinos and not mismo_negocio(nombre, vecinos[0]):
        # Una de las dos es la duena y la otra tiene la url mal cargada, y desde
        # afuera no se puede saber cual. Ingerirla le atribuiria a una el
        # inventario de la otra, asi que queda marcada y sin ingerir.
        return AMBIGUA, (f"{h} figura como web de dos inmobiliarias sin relacion "
                         f"aparente ({nombre} y {vecinos[0]}): no se puede "
                         f"decidir de quien es")
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
    ap.add_argument("--no-inmobiliarias",
                    default=r"D:\INMO CAPITAL\RESIDUAL_SHAPES_FINAL.jsonl",
                    help="artefacto con las webs que se comprobo que no "
                         "publican inmuebles")
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo informa, no reescribe el directorio")
    a = ap.parse_args()

    filas = leer(Path(a.directorio))
    por_host = agencias_por_host(filas)
    observadas = {}
    for x in leer(Path(a.no_inmobiliarias)):
        if x.get("estado_final") == "WEB_NO_INMOBILIARIA":
            observadas[x["canonical_agency_id"]] = x
    cambios = []
    for f in filas:
        tipo, motivo = clasificar(f.get("domain") or "", por_host,
                                  f.get("agency_name") or f["canonical_agency_id"],
                                  observadas.get(f["canonical_agency_id"]))
        anterior = f.get("web_kind")
        f["web_kind"] = tipo
        # El motivo viaja con la clasificacion. Sin el, el directorio dice que
        # algo no es web propia y no dice por que, que es la mitad util.
        f["web_kind_reason"] = motivo or None
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

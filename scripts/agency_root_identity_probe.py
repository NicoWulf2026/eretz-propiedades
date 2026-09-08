#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Quien dice ser el sitio, preguntado en su raiz.

Hay 99 inmobiliarias cuya url cargada es una pagina adentro de un host que no
lleva su nombre. Ahi conviven dos cosas que ninguna regla sobre la URL separa:

  https://www.dbj.com.ar/Alquiler              es su propio sitio
  https://lujanprop.com.ar/inmobiliaria/arte   es su perfil en un portal ajeno

Las dos son una ruta profunda en un dominio que no dice el nombre. La primera
porque la marca es una sigla de tres letras; la segunda porque el dominio es de
otro. Se probo decidirlo por la forma de la url y el resultado fue cerrar como
ajenas a `DBJ`, `CHB`, `LEX`, `LSR`, `merprop` y veinte mas, varias con mas de
cien propiedades ya extraidas: una regla que borra inventario real.

Y la diferencia importa mas que la cobertura: dos corridas seguidas sobre el
perfil de `arte propiedades` enumeraron 17 y 18 fichas **sin una sola en
comun**, y las tres que se abrieron declaraban otras tres inmobiliarias del
portal. No es inestabilidad, es atribucion falsa: publicariamos propiedades
ajenas bajo el nombre de esa agencia.

La pregunta que si los separa es la mas simple: **abrir la RAIZ del host y ver
como se presenta**. Un sitio propio se presenta con el nombre de la
inmobiliaria; un portal se presenta con el nombre del portal, y la inmobiliaria
es una entrada mas adentro.

Se mira la raiz y no la pagina cargada a proposito. La pagina de perfil SI dice
el nombre de la inmobiliaria -para eso es-, y por eso la evidencia de nombre
leida en la pagina profunda no distingue nada: es la misma advertencia que ya
hace `agency_official_web_gate`, que midio que `waze.com` y `signalhire.com`
traen el nombre exacto igual que el sitio propio. La raiz no: ahi el portal
esta obligado a decir que es un portal.

Se exige el nombre ENTERO, no una palabra suelta. Un directorio de rubros puede
mencionar "propiedades" en su titulo; lo que no hace es titularse con el nombre
completo de una de las inmobiliarias que lista.

Solo lee. No escribe en ninguna base ni toca el directorio de plataformas: deja
la evidencia para que la reclasificacion la consuma.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import Descargador, LimitadorDeRitmo  # noqa: E402
from connectors.texto import plegar, sin_acentos  # noqa: E402
from scripts.agency_official_web_gate import (GENERICAS,  # noqa: E402
                                              nombre_en_el_dominio)

VERSION = "root_identity_probe_v1"

PROPIO = "SITIO_PROPIO"
PERFIL = "PERFIL_EN_UN_HOST_QUE_INDEXA_INMOBILIARIAS"
NO_AFIRMABLE = "NO_SE_AFIRMA_QUE_SEA_SUYO"
SIN_RESPUESTA = "LA_RAIZ_NO_RESPONDE"

# Cuanto texto de presentacion se mira. El titulo y el nombre del sitio alcanzan
# y son lo que el sitio elige decir de si mismo; el cuerpo entero traeria el pie
# de pagina, los avisos y los nombres de todas las inmobiliarias listadas, que
# es justamente lo que no se quiere leer.
LARGO_DE_PRESENTACION = 600


# Cuantas hermanas hacen falta para que la ruta sea un indice y no una pagina.
# Con una es un sitio propio con una seccion; con tres el host esta organizado
# por inmobiliaria, y la que cargamos es una entrada de esa lista.
HERMANOS_PARA_SER_INDICE = 3

# La palabra con la que el propio sitio nombra lo que indexa. Contar hermanas
# sin mirarla confunde tres cosas distintas: hermanas que son AGENCIAS -que es
# la evidencia-, hermanas que son PROPIEDADES -que tiene cualquier sitio
# propio- y hermanas que son SECCIONES del sitio.
#
# Medido sobre las 18 que la cuenta sola marcaba: `realchatia.com/sunset/
# propiedades/venta/...` y `redtuinmobiliaria.com/propiedades/...` tienen de
# hermanas otras propiedades, y `turismomardelplata.gob.ar/ASP/SP/...` tiene
# otras paginas del sitio. Ninguna de las tres prueba que el host aloje
# inmobiliarias. Exigiendo la palabra quedan cinco, y las cinco se verifican a
# mano: `micasamiento.com.ar/cordoba/inmobiliarias/kunze-asociados` es
# directamente la pagina de OTRA inmobiliaria.
#
# Es una lista, pero de las que no crecen con el mercado: son las palabras que
# significan "inmobiliaria" en una ruta, no los nombres de los portales.
COLECCION_DE_INMOBILIARIAS = re.compile(
    r"^(?:inmobiliaria|inmobiliarias|agencia|agencias|agency|agencies|"
    r"agente|agentes|agents?|corredor|corredores|corretor|empresa|empresas|"
    r"oficina|oficinas|broker|brokers)$", re.I)

# `infocasas` numera las paginas del MISMO perfil: `.../caetano.../pagina44`.
# Contadas como hermanas, el perfil se delataria a si mismo.
PAGINACION = re.compile(r"^(?:p|pag|pagina|page)[-_]?\d+$", re.I)


def indexa_inmobiliarias(ruta: str, hermanos: list[str]) -> bool:
    """El sitio dice con su propia palabra que lo que lista son inmobiliarias."""
    tramos = [s for s in ruta.split("/") if s]
    if len(tramos) < 2:
        return False
    if not COLECCION_DE_INMOBILIARIAS.match(tramos[-2]):
        return False
    reales = [h for h in hermanos if not PAGINACION.match(h)]
    return len(reales) >= HERMANOS_PARA_SER_INDICE


def hermanos_de_perfil(html: str, ruta: str) -> list[str]:
    """Otras entradas de la MISMA coleccion que la url cargada.

    `lujanprop.com.ar/inmobiliaria/arte` tiene como prefijo `/inmobiliaria`, y
    la pagina enlaza `/inmobiliaria/46`, `/27` y `/33`: el host esta organizado
    por inmobiliaria. `cuno.com.ar/Venta` no tiene prefijo -su ruta es de un
    solo tramo- y por eso no se le pregunta nada: sus hermanas serian `/Alquiler`
    y `/Contacto`, que son secciones de su propio sitio y no otras agencias.

    De ahi que se exija profundidad dos: el ultimo tramo tiene que ser un item
    ADENTRO de una coleccion nombrada, no una seccion colgada de la raiz.
    """
    tramos = [s for s in ruta.split("/") if s]
    if len(tramos) < 2:
        return []
    prefijo = "/" + "/".join(tramos[:-1])
    propio = tramos[-1].lower()
    vistos: set[str] = set()
    for m in re.finditer(r'href=["\']([^"\']{1,400})', html or "", re.I):
        camino = urllib.parse.urlparse(urllib.parse.urljoin("http://h/", m.group(1))).path
        partes = [s for s in camino.split("/") if s]
        if len(partes) != len(tramos):
            continue
        if "/" + "/".join(partes[:-1]) != prefijo:
            continue
        ultimo = partes[-1].lower()
        if ultimo and ultimo != propio:
            vistos.add(ultimo)
    return sorted(vistos)


def presentacion(html: str) -> str:
    """Como se presenta el sitio: titulo, `og:site_name` y el primer encabezado."""
    partes: list[str] = []
    for patron in (r"<title[^>]*>(.{0,300}?)</title>",
                   r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']{0,200})',
                   r'<meta[^>]+content=["\']([^"\']{0,200})["\'][^>]+property=["\']og:site_name',
                   r"<h1[^>]*>(.{0,300}?)</h1>"):
        for m in re.finditer(patron, html or "", re.I | re.S):
            partes.append(re.sub(r"<[^>]+>", " ", m.group(1)))
    return " | ".join(partes)[:LARGO_DE_PRESENTACION]


def nombre_nucleo(nombre: str) -> str:
    """El nombre sin las palabras que comparte con media Argentina inmobiliaria.

    `ARTE PROPIEDADES` sin genericas es `arte`, y `arte` suelto aparece en
    cualquier lado -`estiloarte.com` sin ir mas lejos-. Por eso el nucleo no se
    usa solo: se exige tambien que el nombre entero aparezca, y el nucleo sirve
    para el caso contrario, cuando el sitio se titula con la marca sola.
    """
    palabras = [p for p in re.sub(r"[^a-z0-9]+", " ", sin_acentos(nombre or "").lower()).split()
                if p not in GENERICAS]
    return " ".join(palabras)


def se_presenta_como(nombre: str, texto: str) -> str | None:
    """Que parte del nombre dice el sitio de si mismo, o nada.

    Devuelve la forma que coincidio para que quede escrita como evidencia: no
    alcanza con saber que hubo coincidencia, hay que poder discutirla despues.
    """
    dicho = plegar(texto or "")
    entero = plegar(nombre or "")
    if entero and len(entero) >= 4 and entero in dicho:
        return entero
    nucleo = plegar(nombre_nucleo(nombre))
    # El nucleo solo cuenta si es una marca y no una palabra cualquiera: dos
    # caracteres coinciden en todos lados, y una palabra unica y corta -"arte"-
    # aparece adentro de dominios que no tienen nada que ver.
    if nucleo and len(nucleo) >= 6 and nucleo in dicho:
        return nucleo
    return None


def candidatas(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Las que hay que preguntar: ruta profunda y el dominio no dice su nombre.

    Si el dominio SI lleva el nombre no hace falta preguntar nada, y si la url
    ya es la raiz no hay ambiguedad sobre que se cargo.
    """
    salida = []
    for f in filas:
        if f.get("web_kind") != "OFFICIAL_WEB":
            continue
        p = urllib.parse.urlparse(f.get("domain") or "")
        if not p.netloc or not p.path.strip("/"):
            continue
        if nombre_en_el_dominio(f.get("agency_name") or "", f"{p.scheme}://{p.netloc}"):
            continue
        salida.append(f)
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--directorio",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\AGENCY_ROOT_IDENTITY.jsonl")
    ap.add_argument("--intervalo", type=float, default=1.5)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()

    filas = [json.loads(l) for l in
             Path(a.directorio).read_text(encoding="utf-8").splitlines() if l.strip()]
    pendientes = candidatas(filas)
    if a.limite:
        pendientes = pendientes[:a.limite]

    descargador = Descargador(LimitadorDeRitmo(a.intervalo))
    resultados: list[dict[str, Any]] = []
    for f in pendientes:
        p = urllib.parse.urlparse(f["domain"])
        origen = f"{p.scheme}://{p.netloc}/"
        nombre = f.get("agency_name") or f["canonical_agency_id"]
        try:
            cuerpo = descargador.bajar(origen)
        except Exception as error:      # una raiz caida no decide nada
            resultados.append({
                "canonical_agency_id": f["canonical_agency_id"],
                "agency_name": nombre, "url_cargada": f["domain"],
                "origen": origen, "decision": SIN_RESPUESTA,
                "presentacion": None, "coincidencia": None,
                "motivo": f"{type(error).__name__}: {str(error)[:120]}",
                "version": VERSION, "database_writes": 0})
            continue
        dicho = presentacion(cuerpo)
        coincide = se_presenta_como(nombre, dicho)
        # Las hermanas solo se buscan si la raiz NO dijo ser de esta
        # inmobiliaria: en su propio sitio, una coleccion con muchas entradas
        # son sus propiedades, no otras agencias.
        hermanos: list[str] = []
        if not coincide:
            hermanos = hermanos_de_perfil(cuerpo, p.path)
            if not indexa_inmobiliarias(p.path, hermanos):
                try:    # la raiz puede no listar el indice; la pagina si
                    hermanos = sorted(set(hermanos) | set(
                        hermanos_de_perfil(descargador.bajar(f["domain"]), p.path)))
                except Exception:
                    pass
        es_indice = indexa_inmobiliarias(p.path, hermanos)
        resultados.append({
            "canonical_agency_id": f["canonical_agency_id"],
            "agency_name": nombre, "url_cargada": f["domain"], "origen": origen,
            "decision": PROPIO if coincide else (PERFIL if es_indice else NO_AFIRMABLE),
            "presentacion": dicho,
            "coincidencia": coincide,
            "hermanos": hermanos[:12],
            "hermanos_contados": len(hermanos),
            "motivo": (f"la raiz se presenta con '{coincide}'" if coincide else
                       (f"el host publica {len(hermanos)} entradas mas bajo "
                        f"'{p.path.strip('/').rsplit('/', 1)[0]}': lo que "
                        f"indexa son inmobiliarias y la url cargada es una de "
                        f"ellas" if es_indice else
                        "la raiz no se presenta con el nombre de esta inmobiliaria")),
            "propiedades_extraidas": f.get("properties_normalized"),
            "version": VERSION, "database_writes": 0})

    destino = Path(a.salida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in resultados),
                   encoding="utf-8")
    tmp.replace(destino)

    conteo = Counter(r["decision"] for r in resultados)
    print(json.dumps({"version": VERSION, "preguntadas": len(resultados),
                      "por_decision": dict(conteo), "database_writes": 0,
                      "artefacto": destino.name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cual de las webs descubiertas se puede AFIRMAR que es de esa inmobiliaria.

El resolver decide una entidad por vez, y esa es exactamente su limitacion: un
verificador que mira una sola entidad no puede ver que 65 entidades eligieron
el mismo host. Sobre 598 dominios descubiertos, 597 quedaron marcados
`OFFICIAL_WEB_HIGH_CONFIDENCE` -o sea que el estado no discriminaba nada- y
`buscainmueble.com` figuraba como web oficial de 65 inmobiliarias distintas.
Es la variante del riesgo que el propio modulo de discovery ya advertia: poner
`remax.com.ar` como web de las 191 oficinas de la red.

Esta compuerta corre sobre el conjunto, no sobre la entidad, y aplica cuatro
reglas:

1. La web oficial es un ORIGEN, no una pagina. Una ruta profunda dice donde la
   encontramos, no cual es el sitio. La mitad de los dominios descubiertos
   apuntaba a la ficha de una propiedad.

2. Un host reclamado por MAS DE UNA entidad no identifica a ninguna. La regla
   se demuestra sola con nuestros propios datos y no necesita una lista de
   portales mantenida a mano: cae `buscainmueble.com` y caen tambien los
   colegios y las redes de franquicia, sin haberlos enumerado.

3. Host propio y nombre de la inmobiliaria en el dominio: se puede afirmar.

4. Host propio pero sin rastro del nombre en el dominio: NO se afirma. La
   evidencia de nombre leida en la pagina no sirve para decidirlo, y esto se
   midio: `waze.com` y `signalhire.com` traen `nombre_exacto` igual que
   `ayfb.com.ar`. Un directorio que lista a una inmobiliaria menciona su nombre
   exacto, asi que esa senal no distingue el sitio propio del que lo lista.
   Adentro de este grupo hay acronimos legitimos, pero no hay forma de
   separarlos sin inventar; se prefiere la ausencia.

No escribe en ninguna base. Produce el archivo para que la certificacion lo
consuma.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.texto import sin_acentos  # noqa: E402

# Palabras que casi toda inmobiliaria comparte. Si el dominio coincide solo por
# una de estas, no probo nada.
GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "inmobiliarios",
             "inmobiliario", "negocios", "servicios", "real", "estate",
             "brokers", "broker", "srl", "sas", "grupo", "estudio",
             "consultora", "desarrollos", "emprendimientos", "propiedad"}

# Una coincidencia de tres letras dentro de una marca larga es casualidad, no
# evidencia: "sol" aparece adentro de "solucionesglobales".
LARGO_MINIMO = 4

FUENTES = ("web_identity_resolved.jsonl", "web_identity_lote2.jsonl")


def origen(url: str) -> str:
    partes = urllib.parse.urlparse(url or "")
    if not (partes.scheme and partes.netloc):
        return ""
    return f"{partes.scheme.lower()}://{partes.netloc.lower()}"


# Etiquetas que son sufijo de dominio y no marca de nadie. Es una lista, pero
# de una clase distinta a la de portales: los sufijos no crecen con el mercado
# inmobiliario argentino, y olvidarse de uno solo deja una palabra de mas en la
# comparacion, nunca una decision al reves.
SUFIJOS = {"com", "net", "org", "ar", "uy", "py", "cl", "br", "es", "info",
           "io", "co", "gob", "gov", "edu", "tur", "app", "site", "online"}


def marca_de(origen_url: str) -> str:
    """El nombre registrable, sin `www`, sin sufijos y CON los subdominios.

    Antes devolvia la primera etiqueta y nada mas. `MORESCO REAL ESTATE`
    publica en `propiedades.moresco.com.ar` -su dominio, con el catalogo en un
    subdominio- y la marca leida era "propiedades": generica, descartada, y la
    inmobiliaria quedaba sin rastro de su nombre en su propio dominio.

    Se conservan todas las etiquetas que no son sufijo porque cualquiera puede
    ser la marca: esta en la segunda en `propiedades.moresco.com.ar` y en la
    primera en `cuno.com.ar`.
    """
    host = urllib.parse.urlparse(origen_url).netloc.removeprefix("www.")
    etiquetas = [e for e in host.split(".") if e and e not in SUFIJOS]
    return "".join(etiquetas)


def palabras_del_nombre(nombre: str) -> list[str]:
    """Las palabras que distinguen, ya sin acentos.

    Sin plegar los acentos primero, la expresion parte la palabra en dos por el
    caracter que no reconoce: `Cuno Propiedades` -escrito con enie- se volvia
    ["cu", "o"], las dos por debajo del largo minimo, y `cuno.com.ar` -su
    dominio, literalmente su nombre- figuraba sin rastro. `Bertoia` era peor:
    quedaba "berto", un pedazo que puede coincidir con cualquier otra cosa.
    """
    plano = sin_acentos(nombre or "").lower()
    crudo = re.sub(r"[^a-z0-9]+", " ", plano).split()
    return [p for p in crudo if len(p) >= LARGO_MINIMO and p not in GENERICAS]


def nombre_completo_en_el_dominio(nombre: str, origen_url: str) -> str | None:
    """El nombre ENTERO, pegado, contra la marca del dominio.

    `ABP PROPIEDADES` vive en `abppropiedades.com.ar` y la compuerta lo daba
    por sin rastro: "abp" tiene tres letras y cae por el largo minimo, y
    "propiedades" es generica. Ninguna palabra sobrevivia, aunque el nombre
    completo sea EXACTAMENTE el dominio.

    La asimetria es deliberada. Una palabra generica suelta no prueba nada
    -miles de dominios dicen "propiedades"- pero el nombre entero coincidiendo
    exacto es de la evidencia mas fuerte que hay: no es que el dominio
    contenga algo del nombre, es que el dominio ES el nombre.

    Por eso se exige coincidencia EXACTA y no que uno contenga al otro:
    `Buro 2` esta contenido en `remax-buro2.com.ar`, que es el dominio de la
    franquicia y no el de la inmobiliaria.
    """
    entero = re.sub(r"[^a-z0-9]+", "", sin_acentos(nombre or "").lower())
    marca = re.sub(r"[^a-z0-9]+", "", marca_de(origen_url))
    return entero if entero and entero == marca else None


# Sufijos reservados al Estado y a las universidades. Ningun privado puede
# registrar debajo de estos, asi que el sitio es de otro por definicion y no
# hace falta mirar el nombre.
#
# La regla existe porque el arreglo de acentos y subdominios habilito una
# coincidencia que antes no pasaba de casualidad: `Estudio Inmobiliario Crespo`
# quedaba afirmado sobre `turismo.lacumbre.gob.ar` -la pagina de turismo de la
# municipalidad de La Cumbre- porque el nombre de la localidad contiene
# "cumbre". Los otros dos hosts del Estado en el universo, `santafe.gob.ar` y
# `boletinoficial.neuquen.gov.ar`, se salvaban por suerte y no por regla.
#
# Es una lista, pero de las que no crecen: los sufijos institucionales estan
# reservados y no aparecen inmobiliarias nuevas adentro.
INSTITUCIONALES = re.compile(
    r"\.(?:gob|gov|gub|mil|edu|int)(?:\.[a-z]{2,3})?$", re.I)


def dominio_institucional(origen_url: str) -> bool:
    host = urllib.parse.urlparse(origen_url).netloc.removeprefix("www.")
    return bool(INSTITUCIONALES.search(host))


def nombre_en_el_dominio(nombre: str, origen_url: str) -> str | None:
    marca = marca_de(origen_url)
    for palabra in palabras_del_nombre(nombre):
        if palabra in marca:
            return palabra
    return nombre_completo_en_el_dominio(nombre, origen_url)


def evaluar(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reclamos: Counter = Counter()
    for fila in filas:
        o = origen(fila.get("discovered_domain") or "")
        if o:
            reclamos[o] += 1

    salida = []
    for fila in filas:
        crudo = fila.get("discovered_domain") or ""
        o = origen(crudo)
        if not o:
            estado, razon, palabra = "SIN_DOMINIO", "el resolver no propuso dominio", None
        elif reclamos[o] > 1:
            estado = "AMBIGUO_HOST_COMPARTIDO"
            razon = (f"{reclamos[o]} inmobiliarias distintas apuntan a este host; "
                     f"un host compartido no identifica a ninguna")
            palabra = None
        elif dominio_institucional(o):
            estado = "DOMINIO_INSTITUCIONAL"
            razon = ("el host esta bajo un sufijo reservado al Estado o a una "
                     "universidad: no puede ser el sitio propio de una empresa")
            palabra = None
        else:
            palabra = nombre_en_el_dominio(fila.get("nombre") or "", o)
            if palabra:
                estado = "AFIRMABLE"
                razon = f"host propio y el dominio contiene '{palabra}'"
            else:
                estado = "SIN_RASTRO_DEL_NOMBRE_EN_EL_DOMINIO"
                razon = ("el nombre no aparece en el dominio; la evidencia de "
                         "nombre leida en la pagina no distingue el sitio propio "
                         "del directorio que lo lista")
        salida.append({
            "canonical_agency_id": fila.get("canonical_agency_id"),
            "nombre": fila.get("nombre"),
            "estado": estado,
            "razon": razon,
            "official_url": o if estado == "AFIRMABLE" else None,
            "origen_descubierto": o or None,
            "url_descubierta": crudo or None,
            "era_ruta_profunda": bool(
                o and urllib.parse.urlparse(crudo).path.strip("/")),
            "entidades_que_reclaman_el_host": reclamos[o] if o else 0,
            "palabra_que_coincide": palabra,
            "estado_del_resolver": fila.get("official_web_status"),
            "identity_score": fila.get("identity_score"),
            "database_writes": 0,
        })
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default="")
    args = ap.parse_args()

    dd = Path(args.data_dir)
    destino = Path(args.salida) if args.salida else dd / "AGENCY_OFFICIAL_WEB.jsonl"

    filas: dict[str, dict[str, Any]] = {}
    for nombre in FUENTES:
        ruta = dd / nombre
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                filas.setdefault(fila.get("canonical_agency_id"), fila)

    resultado = evaluar([f for f in filas.values() if f.get("discovered_domain")])
    with destino.open("w", encoding="utf-8") as archivo:
        for fila in resultado:
            archivo.write(json.dumps(fila, ensure_ascii=False) + "\n")

    conteo = Counter(f["estado"] for f in resultado)
    profundas = sum(1 for f in resultado if f["era_ruta_profunda"])
    compartidos: dict[str, int] = defaultdict(int)
    for f in resultado:
        if f["estado"] == "AMBIGUO_HOST_COMPARTIDO":
            compartidos[f["origen_descubierto"]] += 1

    resumen = {
        "entidades_con_dominio_descubierto": len(resultado),
        "por_estado": dict(conteo),
        "afirmables": conteo.get("AFIRMABLE", 0),
        "rutas_profundas_normalizadas_al_origen": profundas,
        "hosts_compartidos": len(compartidos),
        "peor_host_compartido": max(compartidos.items(),
                                    key=lambda x: x[1], default=(None, 0)),
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (dd / "AGENCY_OFFICIAL_WEB_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

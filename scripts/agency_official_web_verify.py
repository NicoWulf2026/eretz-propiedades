#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Abrir las webs que la compuerta declaro afirmables y exigir que sean de aca.

El apellido en el dominio es necesario y no alcanza. `Sandoval propiedades`
-una inmobiliaria argentina- recibio `sandovalinmobiliaria.com`, que existe, es
inmobiliaria y dice Sandoval en toda la pagina: es la agencia Sandoval de
IBIZA. Un apellido comun produce una homonima real en otro pais, y ninguna
regla sobre la cadena de la URL puede verlo. Hay que abrir la pagina.

Que cuenta como evidencia de pais, y por que tan poco:

  a favor    el dominio es `.ar`, la pagina nombra Argentina, o publica un
             telefono +54
  en contra  el dominio vive bajo el ccTLD de otro pais, o la pagina nombra
             otro pais sin ningun indicio de los de arriba

**Un nombre de lugar no es evidencia de pais.** La primera version de este
script uso el catalogo GeoRef para buscar localidades argentinas en el texto, y
dejo pasar justamente a la Sandoval de Ibiza: su pagina dice "esquina", que es
una palabra corriente en cualquier aviso inmobiliario y ademas una localidad de
Corrientes. Es el mismo error que la geografia canonica ya habia resuelto -el
nombre solo nunca alcanza- reintroducido en version debil. Y no se arregla
subiendo el listado a provincias: Cordoba, La Rioja y Santa Fe son tambien
provincias espanolas.

Sin evidencia a favor no se afirma. Que no hayamos podido demostrar que el
sitio es argentino no prueba que no lo sea, asi que esas entidades quedan
`SIN_EVIDENCIA_DE_PAIS` y no `RECHAZADA`: son dos cosas distintas y mezclarlas
convierte una duda en un veredicto. Por la misma razon, una pagina que no
entrega texto -renderizada por JavaScript- queda `PAGINA_SIN_TEXTO` y no
rechazada: no leerla no es leerla y encontrar otra cosa.

Reanudable: cada entidad terminada se escribe y no se repite.
No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from pathlib import Path
from typing import Any

# ccTLD de paises donde una inmobiliaria argentina no publica su sitio oficial.
# `.com`, `.net` y demas genericos no dicen nada y no entran aca.
TLD_EXTRANJEROS = {
    "es": "Espana", "uy": "Uruguay", "cl": "Chile", "br": "Brasil",
    "mx": "Mexico", "pe": "Peru", "py": "Paraguay", "bo": "Bolivia",
    "co": "Colombia", "ec": "Ecuador", "ve": "Venezuela", "us": "Estados Unidos",
    "pt": "Portugal", "it": "Italia", "fr": "Francia", "de": "Alemania",
    "uk": "Reino Unido", "au": "Australia", "ca": "Canada",
}

# Nombres de pais y de ciudades que solo existen afuera. No se listan lugares
# que Argentina comparte con otros paises: ahi el nombre no decide nada.
OTROS_PAISES = ("espana", "ibiza", "montevideo", "punta del este", "asuncion",
                "santiago de chile", "sao paulo", "miami")

RE_TAG = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.S | re.I)
RE_TITULO = re.compile(r"<title[^>]*>(.{1,300}?)</title>", re.S | re.I)
RE_TEL_AR = re.compile(r"\+\s?54[\s\-.)(]?\d")

# Debajo de esto la pagina no entrego contenido: es un cascaron que se arma en
# el navegador, no una pagina que diga que no.
TEXTO_MINIMO = 120

TIEMPO_LIMITE = 25


def sin_acentos(texto: str) -> str:
    tabla = str.maketrans("\u00e1\u00e9\u00ed\u00f3\u00fa\u00fc\u00f1"
                          "\u00c1\u00c9\u00cd\u00d3\u00da\u00dc\u00d1",
                          "aeiouunAEIOUUN")
    return (texto or "").translate(tabla)


def solo_alfanumerico(texto: str) -> str:
    """`RE/MAX` y `remax` son el mismo nombre.

    Buscar el nombre tal cual dejaba afuera a `Remax Cuore`, cuyo sitio escribe
    la marca con barra. Es el mismo error de alfabetos distintos que ya
    aparecio entre la senal de fuente y su extraccion.
    """
    return re.sub(r"[^a-z0-9]+", "", sin_acentos(texto).lower())


def texto_visible(html: str) -> str:
    t = RE_TAG.sub(" ", html or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t)).strip()


def bajar(url: str) -> str:
    pedido = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)"})
    with urllib.request.urlopen(pedido, timeout=TIEMPO_LIMITE) as respuesta:
        return respuesta.read(400_000).decode("utf-8", "replace")


def evidencia_de_argentina(texto: str, host: str) -> list[str]:
    razones = []
    if host.endswith(".ar"):
        razones.append("dominio .ar")
    plano = sin_acentos(texto).lower()
    if "argentina" in plano:
        razones.append("nombra Argentina")
    if RE_TEL_AR.search(texto):
        razones.append("telefono +54")
    return razones


def evidencia_de_otro_pais(texto: str) -> list[str]:
    plano = sin_acentos(texto).lower()
    return [p for p in OTROS_PAISES if p in plano]


def evaluar(fila: dict[str, Any]) -> dict[str, Any]:
    url = fila["official_url"]
    inicio = time.time()
    host = urllib.parse.urlparse(url).netloc.lower()
    tld = host.rsplit(".", 1)[-1]
    if tld in TLD_EXTRANJEROS:
        return dict(fila, verificacion="RECHAZADA_TLD_EXTRANJERO",
                    verificacion_razon=(f"el dominio vive bajo .{tld} "
                                        f"({TLD_EXTRANJEROS[tld]})"),
                    official_url=None, segundos=0.0)
    try:
        html = bajar(url)
    except Exception as error:  # noqa: BLE001 - cualquier fallo es "no se pudo leer"
        return dict(fila, verificacion="NO_RESPONDE",
                    verificacion_razon=f"{type(error).__name__}: {error}",
                    official_url=None, segundos=round(time.time() - inicio, 2))

    encontrado = RE_TITULO.search(html)
    titulo = re.sub(r"\s+", " ", unescape(encontrado.group(1))).strip() \
        if encontrado else ""
    texto = texto_visible(html)
    favor = evidencia_de_argentina(texto, host)
    contra = evidencia_de_otro_pais(texto)
    palabra = solo_alfanumerico(fila.get("palabra_que_coincide") or "")
    nombre_presente = bool(palabra) and palabra in solo_alfanumerico(
        f"{titulo} {texto}")

    if len(texto) < TEXTO_MINIMO and not nombre_presente:
        estado, razon = ("PAGINA_SIN_TEXTO",
                         f"la pagina entrego {len(texto)} caracteres de texto; "
                         f"se arma en el navegador y no se puede leer asi")
    elif not nombre_presente:
        estado, razon = ("RECHAZADA_SIN_EL_NOMBRE",
                         "el sitio entrega texto y no nombra a la inmobiliaria")
    elif favor:
        estado, razon = "VERIFICADA_ARGENTINA", "; ".join(favor)
    elif contra:
        estado, razon = ("RECHAZADA_OTRO_PAIS",
                         f"nombra {contra[0]} y ningun indicio argentino")
    else:
        estado, razon = ("SIN_EVIDENCIA_DE_PAIS",
                         "no se pudo demostrar que el sitio sea argentino")

    return dict(fila, verificacion=estado, verificacion_razon=razon,
                titulo=titulo[:160], caracteres_de_texto=len(texto),
                official_url=url if estado == "VERIFICADA_ARGENTINA" else None,
                segundos=round(time.time() - inicio, 2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--concurrencia", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    dd = Path(args.data_dir)
    entrada = dd / "AGENCY_OFFICIAL_WEB.jsonl"
    salida = dd / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"

    filas = [json.loads(l)
             for l in entrada.read_text(encoding="utf-8").splitlines() if l.strip()]
    afirmables = [f for f in filas if f.get("estado") == "AFIRMABLE"]
    hechas = set()
    if salida.exists():
        hechas = {json.loads(l)["canonical_agency_id"]
                  for l in salida.read_text(encoding="utf-8").splitlines()
                  if l.strip()}
    pendientes = [f for f in afirmables if f["canonical_agency_id"] not in hechas]
    if args.limite:
        pendientes = pendientes[:args.limite]

    print(f"  afirmables: {len(afirmables)} | ya verificadas: {len(hechas)} "
          f"| a verificar ahora: {len(pendientes)}", flush=True)
    if not pendientes:
        return 0

    cerrojo = threading.Lock()
    archivo = salida.open("a", encoding="utf-8")
    conteo: Counter = Counter()

    def trabajar(fila: dict[str, Any]) -> None:
        resultado = evaluar(fila)
        with cerrojo:
            archivo.write(json.dumps(resultado, ensure_ascii=False) + "\n")
            archivo.flush()
            conteo[resultado["verificacion"]] += 1
            hechas_ahora = sum(conteo.values())
            if hechas_ahora % 50 == 0:
                print(f"    {hechas_ahora}/{len(pendientes)} {dict(conteo)}",
                      flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrencia) as pool:
        list(pool.map(trabajar, pendientes))
    archivo.close()

    todas = [json.loads(l)
             for l in salida.read_text(encoding="utf-8").splitlines() if l.strip()]
    final = Counter(f["verificacion"] for f in todas)
    resumen = {"verificadas": len(todas), "por_estado": dict(final),
               "afirmables_finales": final.get("VERIFICADA_ARGENTINA", 0),
               "database_writes": 0, "artefacto": salida.name}
    (dd / "AGENCY_OFFICIAL_WEB_VERIFIED_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

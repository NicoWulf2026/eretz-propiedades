#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Por donde se enumera este WordPress? Pregunta en cascada, no adivina.

No escribe nada y no toca el conector. Es la herramienta de diagnostico para la
familia de WordPress sin plugin inmobiliario, la que cierra
`VARIANTE_NO_SOPORTADA` con 0 enumeradas.

La leccion que la hizo necesaria: no hay UNA regla. Las seis agencias que
comparten el sintoma publican por cuatro vias distintas, y buscar la regla unica
lleva a la conclusion equivocada de que hay que abrir cada ficha. Lo que
funciona es preguntarle al sitio cual contesta:

    1 TIPO PROPIO      un post type que no es ruido de WordPress y trae filas.
                       `cintia fonzo` las publica como PRODUCTOS de WooCommerce,
                       en /producto/av-marcelo-t-de-alvear-4630-ciudadela.
    2 TAXONOMIA        el sitemap declara `tipo-de-propiedad` o `locacion`.
                       Un blog no las tiene: es lo que separa a `pozzobon`
                       -80 fichas- de `csgestion`, cuyas 105 entradas son
                       articulos.
    3 MARCADOR         el slug lleva un marcador reconocible sin abrir nada,
                       como el `-ficha-edp2409` de `estela d onofrio`.
    4 ENTRADAS         las entradas comunes son las fichas, como en `cordoba`.
                       Va ULTIMO a proposito: es cierto ahi y falso en
                       csgestion, con la misma plataforma y el mismo sintoma.

Uso:
    python scripts/sondeo_wordpress.py https://pozzobon.com.ar
    python scripts/sondeo_wordpress.py --familia
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Encoding": "gzip"}

# Tipos que trae cualquier WordPress y nunca son inventario. `product` NO esta
# en esta lista, y esa ausencia es deliberada: suponer que un tipo llamado
# producto no puede ser una ficha escondio 76 propiedades de `cintia fonzo`
# durante una pasada entera.
RUIDO_TIPOS = {
    "post", "page", "attachment", "nav_menu_item", "wp_block", "wp_template",
    "wp_template_part", "wp_global_styles", "wp_navigation", "wp_font_family",
    "wp_font_face", "elementor_library", "spectra-popup", "rm_content_editor",
    "e-landing-page", "e-floating-buttons", "elementor_snippet",
    "wpcf7_contact_form", "custom_css", "customize_changeset", "oembed_cache",
    "user_request", "acf-field", "acf-field-group",
}
RUIDO_TAXONOMIAS = {"post", "page", "users", "category", "post_tag",
                    "nav_menu", "wp_pattern_category"}
INMOBILIARIA = re.compile(
    r"tipo[-_]?de[-_]?propiedad|operacion|locacion|barrio|zona|ambientes|"
    r"inmueble|propiedad|venta|alquiler", re.I)
MARCADORES = ("-ficha-", "/ficha", "-prop-", "/propiedad")


def traer(url: str, timeout: float = 25) -> str:
    r = urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                               timeout=timeout)
    crudo = r.read()
    if r.headers.get("Content-Encoding") == "gzip":
        crudo = gzip.decompress(crudo)
    return crudo.decode("utf-8", "replace")


def tipo_propio(base: str) -> tuple[str, int, list[str]] | None:
    """Un post type que no sea ruido y que traiga filas."""
    try:
        tipos = json.loads(traer(base + "/wp-json/wp/v2/types"))
    except Exception:
        return None
    for nombre, datos in tipos.items():
        if nombre in RUIDO_TIPOS:
            continue
        ruta = (datos or {}).get("rest_base") or nombre
        try:
            filas = traer(f"{base}/wp-json/wp/v2/{ruta}"
                          f"?per_page=100&_fields=id,slug,link")
            filas = json.loads(filas)
        except Exception:
            continue
        if isinstance(filas, list) and filas:
            enlaces = [(f.get("link") or "").replace(base, "") for f in filas[:3]]
            return nombre, len(filas), enlaces
    return None


def sitemaps(base: str) -> list[str]:
    for sm in ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml"):
        try:
            return re.findall(r"<loc>([^<]+)</loc>", traer(base + sm))
        except Exception:
            continue
    return []


def taxonomia_inmobiliaria(locs: list[str]) -> list[str]:
    hallada = set()
    for loc in locs:
        m = re.search(r"sitemap-taxonomies-([a-z0-9\-_]+?)-\d", loc)
        if m and m.group(1) not in RUIDO_TAXONOMIAS:
            if INMOBILIARIA.search(m.group(1)):
                hallada.add(m.group(1))
    return sorted(hallada)


LISTADOS = ("/propiedades/", "/propiedades", "/inmuebles/", "/ventas/", "/")


def marcador_en_slugs(base: str, locs: list[str]) -> tuple[str, int] | None:
    """Marcador en la ruta, mirando sitemap y, si no hay, el listado.

    `estela d onofrio` no publica sitemap ni abre el REST, pero sus fichas
    llevan '-ficha-' adentro y cuelgan de /propiedades/, que es una pagina que
    el conector pide igual. Si el paso dependiera del sitemap, la unica agencia
    para la que el marcador existe seria justamente la que se escapa.
    """
    urls = [u for u in locs if not u.endswith(".xml")]
    for sub in locs:
        if sub.endswith(".xml") and "taxonom" not in sub and "users" not in sub:
            try:
                urls += re.findall(r"<loc>([^<]+)</loc>", traer(sub))
            except Exception:
                pass
    if not urls:
        for ruta in LISTADOS:
            try:
                html = traer(base + ruta)
            except Exception:
                continue
            urls += re.findall(r'href="([^"]+)"', html)
            if urls:
                break
    for marca in MARCADORES:
        n = sum(1 for u in urls if marca in u)
        if n >= 3:
            return marca, n
    return None


def sondear(base: str) -> dict:
    base = base.rstrip("/")
    fuera: dict = {"web": base, "via": None, "detalle": None}

    hallazgo = tipo_propio(base)
    if hallazgo:
        nombre, n, enlaces = hallazgo
        fuera.update(via="TIPO_PROPIO",
                     detalle=f"{nombre}: {n} filas, p.ej. {enlaces[0][:60]}")
        return fuera

    locs = sitemaps(base)
    taxos = taxonomia_inmobiliaria(locs)
    if taxos:
        fuera.update(via="TAXONOMIA", detalle=", ".join(taxos))
        return fuera

    marca = marcador_en_slugs(base, locs)
    if marca:
        fuera.update(via="MARCADOR", detalle=f"'{marca[0]}' en {marca[1]} urls")
        return fuera

    try:
        entradas = json.loads(traer(
            base + "/wp-json/wp/v2/posts?per_page=100&_fields=id,slug"))
        if isinstance(entradas, list) and entradas:
            fuera.update(via="ENTRADAS",
                         detalle=f"{len(entradas)} entradas comunes; "
                                 f"VERIFICAR que no sean un blog")
            return fuera
    except Exception:
        pass

    fuera.update(via=None, detalle="ninguna via declarada: hay que mirar la ficha")
    return fuera


FAMILIA = {
    "attaguile": "https://attaguile.com",
    "castineira salguero": "https://csgestion.com.ar",
    "cintia fonzo": "https://cintiafonzo.com",
    "cordoba propiedades": "https://cordobapropiedades.com.ar",
    "cristina pozzobon": "https://pozzobon.com.ar",
    "estela d onofrio": "https://donofrioprop.com.ar",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("web", nargs="?")
    ap.add_argument("--familia", action="store_true",
                    help="sondear las 6 con el sintoma conocido")
    args = ap.parse_args()

    objetivos = FAMILIA if args.familia else ({args.web: args.web} if args.web
                                              else {})
    if not objetivos:
        ap.error("pasa una web o --familia")

    print(f"{'agencia':22} {'via':12} detalle")
    for nombre, web in objetivos.items():
        r = sondear(web)
        print(f"{nombre[:20]:22} {str(r['via'] or '-'):12} {r['detalle']}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

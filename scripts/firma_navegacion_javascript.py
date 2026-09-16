#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Por qué 39 agencias cierran SIN_INVENTARIO. §12, §37, §38.

Sólo lectura. No escribe en la base, no toca el padrón, no decide nada:
observa y anota. `database_writes: 0`.

El origen es un incidente concreto. El 2026-09-16 la cola paró en
`david rodriguez propiedades` diciendo que el sitio publicaba catálogo y no lo
habíamos podido enumerar. Era cierto, y la causa no era el sitio: su home no
tiene **un solo** enlace propio de navegación —sus 13 `href` son css, ico y
png—, porque toda la navegación es ``javascript:goToPropiedades()``, y esa
función hace ``window.location.href = "propiedades.php"`` adentro de un script.
El descubridor cosecha ``href=``, encuentra cero rutas candidatas y cierra
SIN_INVENTARIO. El inventario estaba a un POST de distancia.

La pregunta que este script contesta no es "¿cómo arreglo esa agencia?" sino
la del §38: **¿cuántas agencias comparten la firma?** Investigar la misma
causa 35 veces es exactamente lo que el §102 pide dejar de hacer.

Cinco firmas, y son distintas entre sí porque el arreglo de cada una es
distinto:

  NAVEGACION_SOLO_JAVASCRIPT   la ruta del catálogo existe y está escrita en
                               un `location.href` en vez de en un `href`;
  CATALOGO_POR_POST            el listado se pide por POST/AJAX a un `.php`;
  CONTENEDOR_VACIO_JS          hay rutas, pero el listado es un nodo vacío que
                               rellena JavaScript sin endpoint declarado;
  API_DE_TERCEROS              el navegador consume una API externa (Tokko);
  SIN_RASTRO_DE_CATALOGO       no se ve catálogo por ningún lado.

Las tres primeras se recuperan por HTTP plano. Sólo la cuarta y la quinta
justifican navegador o un cierre terminal, y esa diferencia es la que hoy no
estamos haciendo: las 39 caen todas en el mismo cajón.

Uso:
    python scripts/firma_navegacion_javascript.py
    python scripts/firma_navegacion_javascript.py --tope 5 --pausa 2
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
SALIDA = CERT / "ERETZ_FIRMA_NAVEGACION_JS.jsonl"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

# Un `href` que apunta a una hoja de estilo no es navegación. Sin este filtro
# `davidrodriguezprop.com` parecería tener 13 rutas propias y ninguna lo es.
ASSET = re.compile(r"\.(?:css|js|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|eot|pdf|mp4)"
                   r"(?:\?|$)", re.I)

# El corazón del asunto: una ruta de navegación escrita donde el descubridor
# no mira. Las tres formas que aparecen en la práctica.
RE_LOCATION = re.compile(
    r"""(?:window\.)?location(?:\.href)?\s*=\s*["']([^"']{2,120})["']"""
    r"""|location\.assign\(\s*["']([^"']{2,120})["']\s*\)"""
    r"""|location\.replace\(\s*["']([^"']{2,120})["']\s*\)""")

# El listado pedido por POST. `$.ajax({type:"POST", url:"x.php"})` y
# `$(sel).load("x.php", {...})` son las dos que se vieron.
RE_AJAX_URL = re.compile(r"""url\s*:\s*["']([^"']+\.(?:php|aspx|json|asp))["']""", re.I)
RE_LOAD = re.compile(r"""\.load\(\s*["']([^"']+\.(?:php|aspx|html?))["']""", re.I)
RE_POST = re.compile(r"""type\s*:\s*["']POST["']|\$\.post\s*\(""", re.I)

# Un contenedor de resultados que llega vacío: el caso `etcheverry`.
RE_CONTENEDOR = re.compile(
    r"""<(ul|div|section|tbody)[^>]*(?:id|class)="[^"]*"""
    r"""(?:propiedades|resultados|listado|properties|results|listings)"""
    r"""[^"]*"[^>]*>\s*</\1>""", re.I)

TERCEROS = (("TOKKO", ("tokkobroker", "tokko-api", "tokko-config")),
            ("WASI", ("wasi.co", "wasiapp")),
            ("XINTEL", ("xintel.com", "xintelapi")),
            ("MAPAPROP", ("mapaprop.com",)),
            ("KITEPROP", ("kiteprop",)))

# Rutas que, si aparecen en un `location.href`, son catálogo y no "contacto".
RE_RUTA_CATALOGO = re.compile(
    r"(?i)(propiedad|propiedades|inmueble|inmuebles|buscar|busqueda|listado|"
    r"catalogo|emprendimiento|venta|alquiler|resultados|search|listing)")


def bajar(url: str, limite: int = 900_000) -> tuple[int, str, str]:
    peticion = urllib.request.Request(url, headers=UA)
    respuesta = urllib.request.urlopen(peticion, timeout=25)
    crudo = respuesta.read(limite)
    if respuesta.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return respuesta.status, respuesta.url, crudo.decode("utf-8", "replace")


def rutas_en_href(html: str, base: str) -> list[str]:
    """Lo que el descubridor de hoy ve: navegación propia declarada en `href`."""
    host = urlparse(base).netloc.lower()
    vistas = []
    for crudo in re.findall(r'href="([^"]+)"', html):
        if crudo.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absoluta = urljoin(base, crudo)
        if urlparse(absoluta).netloc.lower() != host:
            continue
        if ASSET.search(absoluta):
            continue
        vistas.append(absoluta)
    return sorted(set(vistas))


def rutas_en_javascript(html: str, base: str) -> list[str]:
    """Lo que el descubridor NO ve: navegación escrita en `location.href`."""
    host = urlparse(base).netloc.lower()
    vistas = []
    for grupos in RE_LOCATION.findall(html):
        destino = next((g for g in grupos if g), "")
        if not destino or destino.startswith(("#", "http://", "https://", "//")):
            # Un destino absoluto puede ser legítimo, pero sólo cuenta si es
            # del mismo host: si no, es navegación hacia afuera.
            if not destino.startswith(("http://", "https://")):
                continue
            if urlparse(destino).netloc.lower() != host:
                continue
        absoluta = urljoin(base, destino)
        if urlparse(absoluta).netloc.lower() != host or ASSET.search(absoluta):
            continue
        vistas.append(absoluta)
    return sorted(set(vistas))


def endpoints_post(html: str) -> list[str]:
    return sorted(set(RE_AJAX_URL.findall(html)) | set(RE_LOAD.findall(html)))


def tercero(html: str) -> str | None:
    bajo = html.lower()
    for nombre, marcas in TERCEROS:
        if any(m in bajo for m in marcas):
            return nombre
    return None


def clasificar(url: str) -> dict:
    """Baja el sitio una sola vez y decide. La red y la decisión van aparte.

    Separarlas no es prolijidad: es lo que permite que el test se ejecute
    contra el marcado real sin salir a internet, y que cuando falle señale la
    regla equivocada y no un timeout.
    """
    try:
        http, final, html = bajar(url)
    except Exception as e:
        return {"firma": "NO_RESPONDE",
                "porque": f"{type(e).__name__} {getattr(e, 'code', '')}".strip()}
    return clasificar_html(html, final, http)


def clasificar_html(html: str, final: str, http: int = 200) -> dict:
    """Una sola mirada al marcado, y de ahí salen todas las señales.

    La primera pregunta no es técnica sino de identidad, y va antes que todo
    lo demás por un error concreto: la primera corrida dio 7 recuperables y
    **tres eran perfiles de `buscainmueble.com`**. Su catálogo también vive en
    un `location.href` —apunta al `/List` del portal—, así que la regla lo
    marcaba como inventario recuperable. Recuperable para el portal: esas
    fichas son de cualquiera menos de la agencia. Sin este corte la medición
    habría prometido inventario ajeno.
    """
    if len(html) < 500:
        return {"firma": "SIN_CONTENIDO", "http": http,
                "porque": f"HTTP {http} con {len(html)} bytes"}
    if v2.es_portal_url(final):
        return {"firma": "FUENTE_ES_PORTAL_AJENO", "http": http,
                "url_final": final, "bytes": len(html),
                "porque": f"la fuente registrada es un perfil dentro de "
                          f"{urlparse(final).netloc}: lo que se enumere ahi no "
                          f"es su inventario. Se corrige en el source registry, "
                          f"no en el conector"}

    por_href = rutas_en_href(html, final)
    por_js = rutas_en_javascript(html, final)
    solo_en_js = [r for r in por_js if r not in por_href]
    catalogo_en_js = [r for r in solo_en_js if RE_RUTA_CATALOGO.search(r)]
    post = endpoints_post(html)
    hay_post = bool(post) and bool(RE_POST.search(html))
    contenedor = bool(RE_CONTENEDOR.search(html))
    api = tercero(html)

    comun = {"http": http, "url_final": final, "bytes": len(html),
             "rutas_por_href": len(por_href), "rutas_por_javascript": len(por_js),
             "rutas_solo_en_javascript": solo_en_js[:12],
             "endpoints_post": post[:8], "usa_post": hay_post,
             "contenedor_vacio": contenedor, "api_de_terceros": api}

    # El orden importa: se nombra la firma por lo que HAY QUE ARREGLAR, y la
    # navegación invisible se arregla antes que la forma de pedir el listado.
    if catalogo_en_js and not por_href:
        return {**comun, "firma": "NAVEGACION_SOLO_JAVASCRIPT",
                "porque": f"cero rutas propias en href y {len(catalogo_en_js)} "
                          f"ruta(s) de catalogo escritas en location.href: "
                          f"{catalogo_en_js[:3]}"}
    if catalogo_en_js:
        return {**comun, "firma": "NAVEGACION_SOLO_JAVASCRIPT",
                "porque": f"{len(por_href)} rutas en href pero el catalogo "
                          f"aparece solo en location.href: {catalogo_en_js[:3]}"}
    if hay_post:
        return {**comun, "firma": "CATALOGO_POR_POST",
                "porque": f"el listado se pide por POST a {post[:3]}"}
    if api:
        return {**comun, "firma": "API_DE_TERCEROS",
                "porque": f"el navegador consume la API de {api}"}
    if contenedor:
        return {**comun, "firma": "CONTENEDOR_VACIO_JS",
                "porque": "el listado es un nodo vacio que rellena JavaScript "
                          "y no hay endpoint declarado en el marcado"}
    return {**comun, "firma": "SIN_RASTRO_DE_CATALOGO",
            "porque": f"{len(por_href)} rutas en href, sin POST, sin api "
                      f"conocida y sin contenedor de resultados"}


def agencias_objetivo() -> list[dict]:
    """Las que cierran sin inventario y siguen abiertas.

    `BLOCKED_EXTERNAL` queda afuera a propósito: esas ya tienen desenlace, y
    volver a mirarlas no cambia ninguna decisión.
    """
    ultimo: dict[str, dict] = {}
    for linea in RESULTADOS.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila
    return [f for f in ultimo.values()
            if f.get("publication_mechanism") == "SIN_INVENTARIO"
            and f.get("status") == "NEEDS_FIX"
            and (f.get("official_url") or "").startswith("http")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=1.5,
                    help="segundos entre hosts; el limite por host de la cola")
    ap.add_argument("--tope", type=int, default=100)
    args = ap.parse_args()

    objetivo = agencias_objetivo()
    print(f"agencias SIN_INVENTARIO todavia abiertas: {len(objetivo)}\n")

    filas = []
    for fila in objetivo[:args.tope]:
        nombre = fila.get("agency_name") or fila["canonical_agency_id"]
        url = fila["official_url"]
        senal = clasificar(url)
        filas.append({"agency_id": fila["canonical_agency_id"],
                      "agency_name": nombre, "official_url": url,
                      "platform": fila.get("platform"),
                      "connector_strategy": fila.get("connector_strategy"),
                      **senal})
        marca = "**" if senal["firma"] in RECUPERABLES else "  "
        print(f"{marca} {nombre[:30]:32} {senal['firma']:26} "
              f"{senal['porque'][:60]}")
        time.sleep(args.pausa)

    SALIDA.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")

    print(f"\n{'=' * 78}")
    cuenta = Counter(f["firma"] for f in filas)
    for firma, n in cuenta.most_common():
        marca = "**" if firma in RECUPERABLES else "  "
        print(f"{marca} {firma:30} {n}")
    recuperables = sum(n for f, n in cuenta.items() if f in RECUPERABLES)
    print(f"\n  recuperables por HTTP plano, sin navegador: {recuperables} "
          f"de {len(filas)}")
    print("\n  Esto no arregla nada: nombra la causa y la mide. El arreglo es")
    print("  DATA PLANE -cambia huellas- y va a la ventana semantica.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


RECUPERABLES = {"NAVEGACION_SOLO_JAVASCRIPT", "CATALOGO_POR_POST"}


if __name__ == "__main__":
    raise SystemExit(main())

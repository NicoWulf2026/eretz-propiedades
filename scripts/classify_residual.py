#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clasificar lo que quedo sin cubrir, por MECANISMO de publicacion.

`RESIDUAL_UNCOVERED.jsonl` dice cuantas agencias faltan y con que etiqueta
tecnologica quedaron, pero esa etiqueta no sirve para decidir: 728 dicen
UNKNOWN, y "UNKNOWN" no es un mecanismo. Laravel tampoco: es el framework de
abajo, y ya se comprobo que 36 sitios Laravel no eran Wasi.

La pregunta util es como publica cada sitio su inventario, porque de eso
depende si un connector existente ya lo cubre:

  PLATAFORMA_CONOCIDA   tiene marcadores de una plataforma que ya sabemos leer
  SITEMAP_CON_FICHAS    el sitemap enumera fichas: el connector generico sirve
  LISTADO_SERVIDO       el HTML servido trae enlaces a fichas
  JSON_EMBEBIDO         estado serializado con propiedades
  RENDERIZA_EN_CLIENTE  hay que ejecutar JavaScript
  SIN_INVENTARIO        responde pero no publica propiedades
  INACCESIBLE           no respondio

Agrupar por mecanismo es lo que dice si faltan cuatro connectors o cuarenta.

Baja la home y, a lo sumo, el sitemap y una pagina de listado. No descarga
fichas. Solo lee.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (Bloqueado, Descargador, ErrorPermanente,  # noqa: E402
                             ErrorTransitorio, LimitadorDeRitmo)
from connectors.generico import RE_FICHA, RE_FICHA_RAIZ  # noqa: E402
from scripts.wasi_fingerprint import fingerprint as fp_wasi  # noqa: E402

VERSION = "residual_classifier_v2"

# Ninguna inmobiliaria del padron declara mas que esto. El maximo real
# observado por fuente es del orden de las centenas (Tokko ~690, Wasi 303).
TOPE_INVENTARIO = 20_000

# Plataformas para las que YA existe connector, o que agrupan muchas fuentes.
PLATAFORMAS = {
    "TOKKO": (r"tokkobroker|static\.tokkobroker\.com", "tokko"),
    "WORDPRESS": (r"wp-content|wp-json|wp-includes", "wordpress"),
    "INMOCLICK": (r"inmoclick\.(ai|com)", "generico"),
    "INMOUP": (r"inmoup\.com\.ar", None),
    "MEDIACORE": (r"mediacore|medialabs", None),
    "INMOVAR": (r"/templates/inmovar", None),
    "SIVAL": (r"sival\.com\.ar|sivalweb", None),
    "EASYBROKER": (r"easybroker\.com", None),
    "REDINMOBILIARIA": (r"redinmobiliaria\.com", None),
}

CLIENTE = re.compile(r"__NEXT_DATA__|/_next/|__NUXT__|/_nuxt/|data-reactroot|"
                     r"ng-version=|wixstatic", re.I)
JSON_EMBEBIDO = re.compile(r"application/ld\+json|window\.__INITIAL_STATE__|"
                           r"__NEXT_DATA__", re.I)

# Que la etiqueta este no significa que adentro haya inventario. Casi todo sitio
# moderno trae un bloque application/ld+json con el marcado de la organizacion
# -RealEstateAgent, WebSite, LocalBusiness- y ninguna propiedad. Clasificar eso
# como JSON_EMBEBIDO promete un mecanismo que no existe: la fuente se manda a
# una corrida que no puede encontrar nada, y de paso figura como recuperable.
#
# Estos son los tipos que SI describen un inmueble publicado.
TIPOS_DE_FICHA = ("realestatelisting", "singlefamilyresidence", "apartment",
                  "house", "residence", "accommodation", "offer", "product",
                  "place")

# Tipos que describen a la inmobiliaria o al sitio, no a lo que publica.
TIPOS_DE_LA_CASA = ("realestateagent", "localbusiness", "organization",
                    "website", "webpage", "breadcrumblist", "searchaction",
                    "person", "logo", "imageobject")


# Lo que hay pegado a un numero para que ese numero NO sea un inventario.
ANTES_NO_ES_INVENTARIO = re.compile(
    r"(\+\s*$|\d\s*$|[(]\s*$|"
    r"(?:tel|telefono|cel|celular|whatsapp|wsp|movil|fax|cuit|cuil|"
    r"matricula|mat\.|cmcpsi|cucicba)\W{0,12}$)", re.I)


def _inventario_declarado(texto: str):
    """Cuantas propiedades dice publicar, cuando de verdad lo dice.

    El numero sirve para priorizar, asi que uno inventado es peor que ninguno.
    Dos formas de equivocarse que aparecieron en fuentes reales:

      "+54 9 294 469 7556"        -> 7.556 propiedades
      "+500 Propiedades gestionadas" -> 500, pero es una frase de marketing,
                                        no un contador de listado

    El primero es un telefono partido; el segundo, un "mas de 500" que no dice
    cuantas hay publicadas hoy. Los dos se reconocen por lo que tienen delante:
    un signo mas, otro digito, o una palabra de contacto.
    """
    for m in re.finditer(r"(\d[\d.]*)\s*(?:Resultados|propiedades|inmuebles)",
                         texto or "", re.I):
        if ANTES_NO_ES_INVENTARIO.search((texto or "")[max(0, m.start() - 40):m.start()]):
            continue
        crudo = m.group(1).replace(".", "")
        if not crudo.isdigit():
            continue
        n = int(crudo)
        if n and n <= TOPE_INVENTARIO:
            return n
    return None


def _json_con_fichas(html: str) -> bool:
    """Si el JSON embebido describe inmuebles, no a la inmobiliaria."""
    encontrados = 0
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>",
                         html or "", re.S | re.I):
        try:
            obj = json.loads(m.group(1).strip())
        except Exception:
            continue
        pila = [obj]
        while pila:
            x = pila.pop()
            if isinstance(x, list):
                pila.extend(x)
            elif isinstance(x, dict):
                t = x.get("@type")
                for t in (t if isinstance(t, list) else [t]):
                    if isinstance(t, str) and t.lower() in TIPOS_DE_FICHA:
                        encontrados += 1
                pila.extend(v for v in x.values()
                            if isinstance(v, (list, dict)))
    # Uno solo puede ser la ficha destacada de la portada; dos o mas ya es un
    # listado.
    return encontrados >= 2

RUTAS = ("/propiedades", "/inmuebles", "/venta", "/propiedades-en-venta",
         "/emprendimientos", "/buscar")


def _bajar(d: Descargador, url: str) -> str | None:
    try:
        return d.bajar(url)
    except (Bloqueado, ErrorPermanente, ErrorTransitorio):
        return None


def _fichas(html: str, base: str) -> set[str]:
    out = set()
    for h in re.findall(r'href="([^"]{4,200})"', html):
        u = urllib.parse.urljoin(base, h)
        if urllib.parse.urlparse(u).netloc != urllib.parse.urlparse(base).netloc:
            continue
        if RE_FICHA.search(u) or RE_FICHA_RAIZ.search(urllib.parse.urlparse(u).path):
            out.add(u)
    return out


def analizar(f: dict, lim: LimitadorDeRitmo) -> dict:
    url = f.get("domain") or ""
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme or 'https'}://{p.netloc}"
    d = Descargador(lim, limite_bytes=900_000)
    out = {
        "canonical_agency_id": f.get("canonical_agency_id"),
        "eretz_id": f.get("eretz_id"), "agency_name": f.get("agency_name"),
        "domain": url, "host": f.get("host"), "province": f.get("province"),
        "plataforma_previa": f.get("platform"),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "classifier_version": VERSION,
    }

    html = _bajar(d, base) or _bajar(d, url)
    if html is None:
        return {**out, "mecanismo": "INACCESIBLE", "connector": None,
                "motivo": "no respondio; no se puede afirmar nada del sitio"}
    out["bytes_home"] = len(html)

    # 1. Plataforma conocida.
    plataforma = conector = None
    for nombre, (patron, con) in PLATAFORMAS.items():
        if re.search(patron, html, re.I):
            plataforma, conector = nombre, con
            break
    if plataforma is None and fp_wasi(html, base)["es_wasi"]:
        plataforma, conector = "WASI", "wasi"
    out["plataforma_detectada"] = plataforma

    # 2. Sitemap con fichas: la enumeracion mas barata.
    sm = _bajar(d, base + "/sitemap.xml") or ""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sm) if "<loc>" in sm else []
    fichas_sm = {u for u in locs
                 if RE_FICHA.search(u)
                 or RE_FICHA_RAIZ.search(urllib.parse.urlparse(u).path)}
    out["sitemap_locs"] = len(locs)
    out["sitemap_fichas"] = len(fichas_sm)
    out["sitemap_es_indice"] = "<sitemapindex" in sm

    # 3. Fichas en el HTML servido, en la home o en un listado enlazado.
    fichas = _fichas(html, base)
    ruta = next((r for r in RUTAS if f'href="{r}"' in html), None)
    if not fichas and ruta:
        listado = _bajar(d, base + ruta)
        if listado:
            fichas = _fichas(listado, base)
            out["ruta_listado"] = ruta
    out["fichas_html"] = len(fichas)

    out["json_embebido"] = bool(JSON_EMBEBIDO.search(html)) and _json_con_fichas(html)
    out["json_solo_de_la_casa"] = (bool(JSON_EMBEBIDO.search(html))
                                   and not out["json_embebido"])
    out["renderiza_cliente"] = bool(CLIENTE.search(html))
    texto = re.sub(r"<[^>]+>", " ", html)
    # El numero declarado sirve para PRIORIZAR, asi que un valor absurdo es
    # peor que ninguno. Sin tope entraban telefonos y precios pegados a la
    # palabra: "54 11 6953 7580" daba 541.169.537.580 propiedades, y catorce
    # fuentes sumaban mas inventario que todo el pais.
    out["declared_inventory"] = _inventario_declarado(texto)

    # --- mecanismo, de mas barato a mas caro -------------------------------
    # `connector_candidato` y `official_url` se emiten con esos nombres a
    # proposito: es el formato que `run_rollout.py --censo` ya sabe consumir,
    # asi que este artefacto se puede lanzar sin traducirlo a mano.
    if plataforma and conector:
        out["mecanismo"], out["connector"] = "PLATAFORMA_CONOCIDA", conector
    elif plataforma:
        out["mecanismo"], out["connector"] = "PLATAFORMA_SIN_CONNECTOR", None
    elif fichas_sm:
        out["mecanismo"], out["connector"] = "SITEMAP_CON_FICHAS", "generico"
    elif fichas:
        out["mecanismo"], out["connector"] = "LISTADO_SERVIDO", "generico"
    elif out["json_embebido"] and not out["renderiza_cliente"]:
        out["mecanismo"], out["connector"] = "JSON_EMBEBIDO", "generico"
    elif out["renderiza_cliente"]:
        out["mecanismo"], out["connector"] = "RENDERIZA_EN_CLIENTE", None
    else:
        out["mecanismo"], out["connector"] = "SIN_INVENTARIO", None
        out["motivo"] = ("responde pero no se le vio ninguna ficha: puede ser "
                         "institucional, estar vacio o publicar de una forma "
                         "que este sondeo no reconoce")
    # --- detectar la plataforma NO es encontrar el inventario ---------------
    # Ya paso dos veces. Con WordPress: 57 fuentes se dieron por recuperables
    # por tener marcadores del CMS y las 57 devolvieron cero. Con Tokko: 81
    # fuentes tienen marcadores de Tokko y son TOKKO_FRONTEND_PROPIO, que su
    # connector no sabe leer -y el generico tampoco-.
    #
    # Asi que solo se propone connector cuando hay fichas A LA VISTA. Lo demas
    # queda anotado con su plataforma, pero sin prometer nada.
    hay_fichas = bool(out.get("sitemap_fichas") or out.get("fichas_html"))
    out["status"] = ("CON_EVIDENCIA_DE_INVENTARIO" if hay_fichas and out["connector"]
                     else "PLATAFORMA_SIN_EVIDENCIA" if out["connector"]
                     else "SIN_CONECTOR")
    if not hay_fichas:
        out["connector"] = None
    out["connector_candidato"] = out["connector"]
    out["official_url"] = url or base
    out["clasificacion_nueva"] = out["mecanismo"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada",
                    default=r"D:\INMO CAPITAL\RESIDUAL_UNCOVERED.jsonl")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\RESIDUAL_CLASSIFIED.jsonl")
    ap.add_argument("--plataforma", nargs="*", default=[],
                    help="acota a estas etiquetas previas; vacio = todas")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--concurrencia", type=int, default=2)
    ap.add_argument("--intervalo", type=float, default=1.5)
    a = ap.parse_args()

    filas = [json.loads(l) for l in Path(a.entrada).open(encoding="utf-8") if l.strip()]
    if a.plataforma:
        quiere = {x.upper() for x in a.plataforma}
        filas = [f for f in filas if (f.get("platform") or "").upper() in quiere]
    if a.limite:
        filas = filas[:a.limite]

    print("### CLASIFICACION DEL RESIDUAL ###")
    print(f"  fuentes: {len(filas)}\n", flush=True)
    if not filas:
        return 0

    lim = LimitadorDeRitmo(a.intervalo)
    res = []
    # Escritura incremental: una excepcion al final no puede llevarse lo hecho.
    with Path(a.salida).open("w", encoding="utf-8") as fh:
        for i in range(0, len(filas), 10):
            with ThreadPoolExecutor(max_workers=a.concurrencia) as ex:
                for r in ex.map(lambda f: analizar(f, lim), filas[i:i + 10]):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    res.append(r)
            fh.flush()
            print(f"    {min(i + 10, len(filas))}/{len(filas)}", flush=True)

    print("\n  MECANISMO DE PUBLICACION")
    for k, v in Counter(r["mecanismo"] for r in res).most_common():
        con = {r.get("connector") for r in res if r["mecanismo"] == k} - {None}
        decl = sum(r.get("declared_inventory") or 0 for r in res
                   if r["mecanismo"] == k)
        print(f"    {k:26} {v:5}  connector: {', '.join(sorted(con)) or '-':10} "
              f"inventario declarado {decl:7,}")

    cubribles = [r for r in res if r.get("connector")]
    print(f"\n  RECUPERABLES CON UN CONNECTOR QUE YA EXISTE: {len(cubribles)}/{len(res)}")
    for k, v in Counter(r["connector"] for r in cubribles).most_common():
        print(f"    {k:14} {v:5}")

    print("\n  plataformas encontradas entre las que decian UNKNOWN:")
    porplat = Counter(r.get("plataforma_detectada") for r in res
                      if r.get("plataforma_detectada"))
    for k, v in porplat.most_common(12):
        print(f"    {k:20} {v:5}")

    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Puente LOCAL -> CLOUD: captura una pagina o respuesta publica y la reduce a fixture versionable.

CLOUD no tiene salida a las webs de agencias (politica de red de su entorno). LOCAL
baja la evidencia con esto, la commitea en `tests/fixtures/cloud_bridge/` y CLOUD
desarrolla y testea sin volver a la web.

Descarga con el `Descargador` del proyecto: respeta robots.txt (P11), UA
identificado, ritmo y backoff; un 403/429 NO se evade (la captura falla y se dice).
Tambien reduce un HTML ya cacheado en LOCAL (`--desde-archivo`), sin pedir nada.

Reduccion (lo que queda es la estructura, no el sitio):
- fuera: <style>, <noscript>, <iframe>, <link> de estilos/precarga, comentarios,
  atributos `on*`/`style`/`srcset`, y el contenido de <svg> (queda la etiqueta
  con su clase: un icono `fa-map-marker` es evidencia);
- <script>: fuera, SALVO JSON-LD (`--con-json-ld`) y los ids pedidos
  (`--script-id wix-warmup-data`), que son donde viven los datos;
- emails y telefonos se reemplazan por marcadores; `mailto:`/`tel:`/`wa.me` tambien;
- `--selector-texto` recorta al elemento que contiene ese texto, dos niveles hacia
  arriba, con sus hermanos inmediatos que no sean header/footer/nav: el contexto DOM justo.
Modo `--json`: la respuesta es JSON; toda lista se recorta a `--max-items`.

Cada fixture lleva un `.meta.json` al lado: url, fecha, sha256 del original, bytes
antes/despues, que se conservo y una nota. Nunca guarda cookies ni encabezados.

    python scripts/cloud_bridge/capturar_fixture.py URL --salida tests/fixtures/cloud_bridge/martelliti/ficha_1.html \\
        --selector-texto "Laprida 1835" --nota "linea junto al icono de mapa"
    python scripts/cloud_bridge/capturar_fixture.py --desde-archivo cache.html --url-original URL --salida ...
    python scripts/cloud_bridge/capturar_fixture.py URL_API --json --max-items 3 --salida .../paladino/listado.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from bs4 import BeautifulSoup, Comment  # noqa: E402

RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Telefonos en el texto visible: una secuencia de digitos, espacios, parentesis,
# guiones o «+» con 8 a 13 digitos («(0223) 155-123456», «+54 9 223 555-1234»,
# «2235551234»). Un precio no: lo precede una moneda y se deja.
RE_CANDIDATO_TEL = re.compile(r"(?<![\w$/.])[+(]?\d[\d\s().-]{6,}\d(?![\w/])")
RE_MONEDA_ANTES = re.compile(r"(?:\$|USD|U\$S|US\$|ARS|€)\s*$", re.I)


def _tapar_telefonos(texto: str) -> str:
    def cambiar(m: re.Match) -> str:
        digitos = sum(c.isdigit() for c in m.group(0))
        if not 8 <= digitos <= 13 or RE_MONEDA_ANTES.search(texto[max(0, m.start() - 6):m.start()]):
            return m.group(0)
        return "[TELEFONO]"
    return RE_CANDIDATO_TEL.sub(cambiar, texto)
# En datos (JSON, scripts conservados) un numero largo suele ser un id o un
# timestamp, no un telefono: ahi solo se tapa lo que TIENE forma de telefono
# (con +, parentesis o separadores).
RE_TELEFONO_CON_FORMA = re.compile(
    r"(?:\+54[\s-]?(?:9[\s-]?)?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{4}"
    r"|\(0?\d{2,4}\)[\s-]?(?:15[\s-]?)?\d{3,4}[\s-]?\d{4}"
    r"|\b0?\d{2,4}[\s-](?:15[\s-]?)?\d{3,4}[\s-]\d{4}\b)")
SECCIONES_DEL_SITIO = ("header", "footer", "nav")
ATRIBUTOS_FUERA = ("style", "srcset", "sizes", "nonce", "integrity")


def redactar(texto: str, *, datos: bool = False) -> str:
    texto = RE_EMAIL.sub("[EMAIL]", texto)
    if datos:
        return RE_TELEFONO_CON_FORMA.sub("[TELEFONO]", texto)
    return _tapar_telefonos(texto)


def _redactar_href(valor: str) -> str:
    v = valor.strip().lower()
    if v.startswith("mailto:"):
        return "mailto:[EMAIL]"
    if v.startswith("tel:"):
        return "tel:[TELEFONO]"
    if "wa.me/" in v or "api.whatsapp.com" in v:
        return "https://wa.me/[TELEFONO]"
    return redactar(valor)


def reducir_html(html: str, *, scripts_ids: tuple[str, ...] = (), con_json_ld: bool = False,
                 selector_texto: str | None = None) -> tuple[str, dict[str, Any]]:
    """El HTML reducido y lo que se conservo (para el .meta.json)."""
    sopa = BeautifulSoup(html, "html.parser")
    conservados: list[str] = []
    for comentario in sopa.find_all(string=lambda s: isinstance(s, Comment)):
        comentario.extract()
    for nodo in sopa.find_all(["style", "noscript", "iframe"]):
        nodo.decompose()
    for link in sopa.find_all("link"):
        # html.parser anida los <link> que no se cierran: al borrar el de afuera
        # los de adentro quedan sin atributos (`martelliti`, Pixel Inmobiliario).
        if link.decomposed:
            continue
        if set(link.get("rel") or []) & {"stylesheet", "preload", "prefetch", "preconnect",
                                          "dns-prefetch", "modulepreload", "icon"}:
            link.decompose()
    for script in sopa.find_all("script"):
        if script.decomposed:
            continue
        tipo = (script.get("type") or "").lower()
        if script.get("id") in scripts_ids or (con_json_ld and tipo == "application/ld+json"):
            conservados.append(script.get("id") or tipo)
            continue
        script.decompose()
    for svg in sopa.find_all("svg"):
        svg.clear()
    for tag in sopa.find_all(True):
        for attr in list(tag.attrs):
            if attr.startswith("on") or attr in ATRIBUTOS_FUERA:
                del tag.attrs[attr]
            elif attr in ("href", "content", "value", "title", "alt", "aria-label") or attr.startswith("data-"):
                valor = tag.attrs[attr]
                if isinstance(valor, str):
                    tag.attrs[attr] = _redactar_href(valor) if attr == "href" else redactar(valor)
    for texto in sopa.find_all(string=True):
        es_dato = texto.parent is not None and texto.parent.name == "script"
        nuevo = redactar(str(texto), datos=es_dato)
        if nuevo != texto:
            texto.replace_with(nuevo)
    recorte = None
    if selector_texto:
        encontrado = sopa.find(string=lambda s: s is not None and selector_texto in s)
        if encontrado is None:
            raise ValueError(f"el texto {selector_texto!r} no esta en la pagina")
        recorte = _contexto(encontrado)
    salida = recorte if recorte is not None else str(sopa)
    salida = re.sub(r"\n\s*\n+", "\n", salida)
    return salida, {"scripts_conservados": conservados, "selector_texto": selector_texto}


def _contexto(texto) -> str:
    """El elemento que contiene el texto, subiendo 3 niveles, con sus hermanos inmediatos."""
    nodo = texto.parent
    for _ in range(2):
        if nodo.parent is not None and nodo.parent.name not in ("body", "html", "main", "[document]"):
            nodo = nodo.parent
    partes = []
    # El encabezado y el pie son del SITIO, no de la ficha: no son contexto.
    anterior, siguiente = nodo.find_previous_sibling(), nodo.find_next_sibling()
    if anterior is not None and anterior.name not in SECCIONES_DEL_SITIO:
        partes.append(str(anterior))
    partes.append(str(nodo))
    if siguiente is not None and siguiente.name not in SECCIONES_DEL_SITIO:
        partes.append(str(siguiente))
    ruta = []
    padre = nodo.parent
    while padre is not None and padre.name not in (None, "[document]"):
        clases = ".".join(padre.get("class") or [])
        ruta.append(padre.name + (f"#{padre.get('id')}" if padre.get("id") else "") + (f".{clases}" if clases else ""))
        padre = padre.parent
    camino = " > ".join(reversed(ruta))
    return f"<!-- contexto DOM: {camino} -->\n" + "\n".join(partes)


def reducir_json(datos: Any, max_items: int) -> Any:
    if isinstance(datos, list):
        return [reducir_json(x, max_items) for x in datos[:max_items]]
    if isinstance(datos, dict):
        return {k: reducir_json(v, max_items) for k, v in datos.items()}
    if isinstance(datos, str):
        return redactar(datos, datos=True)
    return datos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="url publica a bajar (respeta robots.txt)")
    ap.add_argument("--desde-archivo", type=Path, help="reducir un HTML/JSON ya cacheado en LOCAL")
    ap.add_argument("--url-original", help="con --desde-archivo: de donde salio")
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--script-id", action="append", default=[], help="conservar <script id=...>")
    ap.add_argument("--con-json-ld", action="store_true")
    ap.add_argument("--selector-texto", help="recortar al contexto DOM de este texto")
    ap.add_argument("--json", action="store_true", help="la respuesta es JSON")
    ap.add_argument("--max-items", type=int, default=3)
    ap.add_argument("--max-bytes", type=int, default=6_000_000,
                    help="tope de descarga (solo para capturar evidencia, no para certificar)")
    ap.add_argument("--nota", default="")
    args = ap.parse_args()
    if bool(args.url) == bool(args.desde_archivo):
        ap.error("una url o --desde-archivo, no las dos")

    if args.desde_archivo:
        crudo = args.desde_archivo.read_text(encoding="utf-8", errors="replace")
        origen, robots = args.url_original, "NO_APLICA (cache local)"
    else:
        from connectors.base import Descargador, RobotsBloqueado
        descargador = Descargador(limite_bytes=args.max_bytes)
        try:
            crudo = descargador.bajar(args.url)
        except RobotsBloqueado:
            print("ROBOTS_BLOCKED: robots.txt no permite esta url; no se captura.")
            return 2
        origen, robots = args.url, "PERMITIDO"

    if args.json:
        reducido = json.dumps(reducir_json(json.loads(crudo), args.max_items), ensure_ascii=False, indent=1)
        detalle: dict[str, Any] = {"max_items": args.max_items}
    else:
        reducido, detalle = reducir_html(crudo, scripts_ids=tuple(args.script_id),
                                         con_json_ld=args.con_json_ld,
                                         selector_texto=args.selector_texto)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(reducido, encoding="utf-8")
    meta = {
        "url": origen, "robots": robots,
        "capturado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256_original": hashlib.sha256(crudo.encode("utf-8")).hexdigest(),
        "bytes_original": len(crudo.encode("utf-8")),
        "bytes_fixture": len(reducido.encode("utf-8")),
        "modo": "json" if args.json else "html", **detalle,
        "redaccion": "emails y telefonos reemplazados por [EMAIL]/[TELEFONO]",
        "nota": args.nota,
        "herramienta": "scripts/cloud_bridge/capturar_fixture.py",
    }
    args.salida.with_name(args.salida.name + ".meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{args.salida}: {meta['bytes_original']} -> {meta['bytes_fixture']} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

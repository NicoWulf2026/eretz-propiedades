#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las agencias que enumeran cero, ¿publican fichas que no sabemos leer?

Solo lectura sobre la web. No escribe en produccion, no cambia extractores, no
cambia huellas. `database_writes: 0`. Propone, no aplica.

Por que existe
--------------
Tenemos 39 agencias que cierran sin inventario y la respuesta habitual fue
mirarlas de a una. Pero la pregunta que decide si hay un arreglo COMPARTIDO no
es "por que falla esta" sino "que forma tienen los enlaces que no reconocemos".

El disparador concreto: `fios consultoria` publica sus fichas como

    /propiedad-9871962-venta-casa-1-dormitorio-con-parque--pileta-en-funes

y ningun patron nuestro la ve. `RE_FICHA` exige que la palabra abra un SEGMENTO
-`/propiedad/algo`- y aca va pegada al id con un guion. `RE_FICHA_RAIZ` exige
que el id vaya PRIMERO -`/8471-venta-casa`- y aca va segundo.

Es la cuarta vez que este proyecto tropieza con la misma suposicion:

    bottai    inmueble_6067                        sin barra
    fios      propiedades                          relativo
    yacopino  busqueda-de-propiedades-en-venta     palabra precedida de guion
    fios      /propiedad-9871962-venta-casa-...    palabra pegada al id

Tres veces se arreglo en `fuente_es_una_ficha.py`, que es una herramienta de
registro de fuentes. La cuarta esta en el conector, que es donde cuesta caro.

Que hace
--------
Para cada agencia que enumera cero, baja su fuente registrada -una sola
pagina-, junta los enlaces del mismo host y los agrupa por FORMA, diciendo de
cada forma si alguno de nuestros patrones la reconoce. El resultado es una
tabla de formas con su frecuencia y sus agencias, que es lo que hace falta para
decidir si un patron nuevo recupera una agencia o cuarenta.

No propone patrones: propone EVIDENCIA. Un patron escrito desde una sola
agencia es como llegamos a tener cuatro reglas que se pisan.

Uso:
    python scripts/que_forma_tienen_sus_fichas.py
    python scripts/que_forma_tienen_sus_fichas.py --limite 20
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_FORMAS_DE_FICHA.json"

AGENTE = {"User-Agent": "Mozilla/5.0 (ERETZ diagnostico, solo lectura)"}

# Palabras que, en una ruta, dicen que eso es una propiedad y no una nota.
PALABRAS = (r"propiedad(?:es)?|inmueble[s]?|emprendimiento[s]?|ficha[s]?|"
            r"propert(?:y|ies)|listing[s]?|aviso[s]?|anuncio[s]?")
# Tipos de inmueble: si el slug los nombra, es casi seguro una ficha.
TIPOS = (r"casa|departamento|depto|terreno|lote|ph|local|oficina|galpon|"
         r"campo|cochera|quinta|duplex|chalet|piso|fondo|hotel")


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


def sin_inventario() -> list[tuple[str, str]]:
    """Agencias `NEEDS_FIX` con cero enumeradas y una fuente que resolver."""
    ultimo: dict[str, dict[str, Any]] = {}
    for fila in _jsonl(CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"):
        clave = fila.get("canonical_agency_id")
        if clave:
            ultimo[clave] = fila
    from scripts.agency_certifier import load_catalog, resolve_identity
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    salida = []
    for clave, resultado in sorted(ultimo.items()):
        if resultado.get("status") != "NEEDS_FIX":
            continue
        if (resultado.get("enumeration_audit") or {}).get("enumerated"):
            continue
        registro = catalogo.get(clave)
        if not registro:
            continue
        url = (resolve_identity(registro, clave) or {}).get("official_url")
        if url:
            salida.append((clave, url))
    return salida


def bajar(url: str, limite: int = 400_000) -> tuple[int, str, str]:
    peticion = urllib.request.Request(url, headers=AGENTE)
    with urllib.request.urlopen(peticion, timeout=25) as respuesta:
        crudo = respuesta.read(limite)
        return respuesta.status, respuesta.geturl(), crudo.decode("utf-8",
                                                                  "replace")


def forma_de(ruta: str) -> str:
    """La ruta con sus partes variables reemplazadas por marcadores.

    `/propiedad-9871962-venta-casa-en-funes` -> `/<palabra>-<id>-<slug>`
    Agrupar por forma es lo que convierte cuarenta urls en una decision.
    """
    if not ruta or ruta == "/":
        return "/"
    partes = []
    for segmento in ruta.strip("/").split("/"):
        if not segmento:
            continue
        s = segmento
        if re.fullmatch(r"\d{2,}", s):
            partes.append("<id>")
            continue
        m = re.fullmatch(rf"({PALABRAS})[-_](\d{{2,}})[-_](.+)", s, re.I)
        if m:
            partes.append("<palabra>-<id>-<slug>")
            continue
        m = re.fullmatch(rf"(\d{{2,}})[-_](.+)", s)
        if m:
            partes.append("<id>-<slug>")
            continue
        m = re.fullmatch(rf"({PALABRAS})[-_](.+)", s, re.I)
        if m:
            partes.append("<palabra>-<slug>")
            continue
        if re.fullmatch(rf"({PALABRAS})", s, re.I):
            partes.append("<palabra>")
            continue
        if re.search(rf"\b({TIPOS})\b", s, re.I) and s.count("-") >= 2:
            partes.append("<slug-con-tipo>")
            continue
        if s.count("-") >= 2:
            partes.append("<slug>")
            continue
        if "." in s:
            partes.append("<archivo>")
            continue
        partes.append("<palabra-suelta>")
    return "/" + "/".join(partes)


def parece_ficha(ruta: str) -> bool:
    """Heuristica de DIAGNOSTICO, deliberadamente distinta a la del conector.

    No se reutiliza `_es_ficha_url` a proposito: la pregunta es justamente
    **que se le escapa**, y medir con la misma regla que se quiere evaluar no
    contesta nada.

    Pide dos cosas juntas: un identificador numerico largo y una palabra que
    diga de que se trata. Las dos juntas son mucho mas dificiles de cumplir por
    accidente que cualquiera de las dos sola -una categoria como
    `/Terreno-en-venta` tiene la palabra y no el id; un `/2024/09` tiene el
    numero y no la palabra-.
    """
    if not re.search(r"\d{3,}", ruta):
        return False
    return bool(re.search(rf"({PALABRAS}|{TIPOS})", ruta, re.I))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--intervalo", type=float, default=1.0)
    args = ap.parse_args()

    from connectors.generico import GenericoConnector

    objetivo = sin_inventario()
    if args.limite:
        objetivo = objetivo[:args.limite]
    print(f"agencias NEEDS_FIX con cero enumeradas y fuente resoluble: "
          f"{len(objetivo)}\n")

    por_forma: dict[str, dict[str, Any]] = collections.defaultdict(
        lambda: {"n": 0, "agencias": set(), "ejemplo": "", "reconocida": None})
    fallaron: list[tuple[str, str]] = []
    revisadas = 0

    for clave, url in objetivo:
        try:
            estado, final, html = bajar(url)
        except Exception as error:  # noqa: BLE001 - un sitio caido no corta
            fallaron.append((clave, f"{type(error).__name__}"))
            continue
        revisadas += 1
        host = urllib.parse.urlparse(final).netloc.lower().replace("www.", "")
        vistas = set()
        for m in re.finditer(r'href="([^"]{2,400})"', html, re.I):
            absoluta = urllib.parse.urljoin(final, m.group(1))
            partes = urllib.parse.urlparse(absoluta)
            if partes.netloc.lower().replace("www.", "") != host:
                continue
            ruta = partes.path
            if not parece_ficha(ruta) or ruta in vistas:
                continue
            vistas.add(ruta)
            f = forma_de(ruta)
            registro = por_forma[f]
            registro["n"] += 1
            registro["agencias"].add(clave)
            if not registro["ejemplo"]:
                registro["ejemplo"] = absoluta
            if registro["reconocida"] is None:
                registro["reconocida"] = GenericoConnector._es_ficha_url(
                    absoluta)
        time.sleep(args.intervalo)

    print(f"revisadas: {revisadas}   no respondieron: {len(fallaron)}\n")
    print(f"  {'FORMA':30} {'N':>5} {'AGENC':>6} {'¿LA VEMOS?':>11}  EJEMPLO")
    print(f"  {'-' * 30} {'-' * 5} {'-' * 6} {'-' * 11}  {'-' * 40}")
    orden = sorted(por_forma.items(),
                   key=lambda kv: (-len(kv[1]["agencias"]), -kv[1]["n"]))
    perdidas = 0
    for forma, datos in orden[:28]:
        ve = "si" if datos["reconocida"] else "NO"
        if not datos["reconocida"]:
            perdidas += len(datos["agencias"])
        print(f"  {forma[:30]:30} {datos['n']:>5} "
              f"{len(datos['agencias']):>6} {ve:>11}  "
              f"{datos['ejemplo'][:44]}")

    print(f"\n  formas distintas: {len(por_forma)}")
    print(f"  agencias con al menos una forma que NO reconocemos: {perdidas}")
    if fallaron:
        print(f"\n  no respondieron ({len(fallaron)}): "
              + ", ".join(f"{c.split(':')[-1][:20]}[{e}]"
                          for c, e in fallaron[:8]))

    SALIDA.write_text(json.dumps({
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "revisadas": revisadas,
        "no_respondieron": [{"agencia": c, "error": e} for c, e in fallaron],
        "formas": [{"forma": f, "enlaces": d["n"],
                    "agencias": sorted(d["agencias"]),
                    "ejemplo": d["ejemplo"], "reconocida": d["reconocida"]}
                   for f, d in orden],
        "database_writes": 0}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

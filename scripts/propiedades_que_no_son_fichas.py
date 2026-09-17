#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`historia.php` no es una propiedad. §1, §22, §35.

Sólo lectura sobre el artefacto local. `database_writes: 0`. No cambia la
enumeración —eso es data plane— : mide cuánto de lo que llamamos "propiedad" no
tiene forma de ficha.

El caso que lo motiva
---------------------
La cola paró en `gama inmobiliaria` diciendo que la extracción de `ciudad`
había fallado en 48 de 49. El triage lo llamó
`extraccion_transversal_de_atributos`, que es el síntoma en el nivel
equivocado: el §35 pone identidad **antes** que extracción de campos.

La web registrada es
`365litoralargentino.com/santa_fe/rosario/gama-inmobiliaria_e.html`: el perfil
de la inmobiliaria dentro de un directorio turístico regional. Y las 49
"propiedades" enumeradas son las páginas del directorio:

    informacion_general.php   historia.php        ubicacion.php
    como_llegar.php           galerias.html       alojamiento.php

Se comprobó una: `historia.php` se titula *"Historia - Rosario - Santa Fe"* y
habla de la historia de la ciudad. `ciudad` no falla por un defecto del
extractor: falla porque **no hay ficha que leer**.

Por qué mirar la forma y no el host
-----------------------------------
La reacción natural es agregar `365litoralargentino.com` a la lista de portales
conocidos. Se midió y rinde poco: ese host lo usa **una sola** agencia, y
barriendo todos los hosts compartidos por dos o más agencias que
`es_portal_url()` no reconoce aparecen sólo dos más, con tres de cuatro ya
cerradas `BLOCKED_EXTERNAL` por otra vía.

Lo que sí generaliza no depende del host: **una url institucional no es una
ficha**, la sirva quien la sirva. Un catálogo puede tener su `contacto.html`
sin que eso sea un problema; lo que delata a `gama` es que *casi todo* lo
enumerado es institucional.

Qué NO hace
-----------
No marca una agencia por tener una o dos urls institucionales entre cien: eso
es ruido normal de un menú. Marca cuando la proporción es tal que lo enumerado
deja de parecer un catálogo.

Uso:
    python scripts/propiedades_que_no_son_fichas.py
    python scripts/propiedades_que_no_son_fichas.py --detalle gama
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
PROPIEDADES = CERT / "ERETZ_PROPIEDADES_CERTIFICADAS.jsonl"
SALIDA = CERT / "ERETZ_ENUMERADO_QUE_NO_ES_FICHA.json"

# Páginas institucionales, de contacto o editoriales.
#
# Se comparan contra el SEGMENTO FINAL COMPLETO de la ruta, no como subcadena.
# La primera versión usaba `(?:^|[/_-])palabra(?:[._/-]|$)` y marcaba
# `casa-cerca-del-museo-de-historia-local` como institucional, porque
# `-historia-` está ahí adentro. Es exactamente el defecto de límite de palabra
# que este proyecto ya tiene abierto en otro lado —el `monoambiente` del menú—
# y no había razón para reintroducirlo acá.
#
# `historia.php` es una página; `casa-cerca-del-museo-de-historia` es una
# ficha, y lo que las distingue no es que contengan la palabra sino que una
# **es** la palabra.
#
# El vocabulario se eligió por PRECISIÓN: cada término nombra una página que
# ninguna inmobiliaria publica como propiedad. Se evitan a propósito "venta",
# "alquiler" y "casas", que son rutas de catálogo legítimas.
INSTITUCIONAL = frozenset("""
historia nosotros quienes-somos quienessomos institucional
informacion-general informaciongeneral empresa la-empresa
contacto contactenos contactanos contactos
ubicacion como-llegar comollegar mapa
galeria galerias fotos videos
servicios tasaciones administracion
faq preguntas-frecuentes ayuda
blog novedades noticias prensa articulos notas
terminos privacidad legales politica-de-privacidad
alojamiento gastronomia turismo eventos agenda clima
login ingresar registro registrarse
sitemap buscador busqueda resultados
sucursales equipo staff agentes
vender vende-con-nosotros tasacion index home inicio
""".split())

# Extensiones que hay que sacar antes de comparar: `historia.php` y
# `historia.html` son la misma página.
RE_EXTENSION = re.compile(r"\.(?:php|html?|aspx?|jsp)$", re.I)

# Debajo de esto no se opina: una agencia con 4 urls no da para medir
# proporciones.
MINIMO_PARA_OPINAR = 8
# Proporción a partir de la cual lo enumerado deja de parecer un catálogo.
UMBRAL_SOSPECHA = 0.30


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


def es_institucional(url: str) -> bool:
    """¿El último segmento de la ruta **es** una página institucional?

    Se mira sólo la RUTA: una inmobiliaria podría llamarse `historia.com.ar` y
    mirar el host marcaría todas sus fichas.
    """
    try:
        ruta = urlparse(url).path
    except ValueError:
        return False
    segmento = ruta.rstrip("/").rsplit("/", 1)[-1] if ruta else ""
    if not segmento:
        return False
    segmento = RE_EXTENSION.sub("", segmento).lower().replace("_", "-")
    return segmento in INSTITUCIONAL


def medir() -> list[dict[str, Any]]:
    por_agencia: dict[str, list[str]] = defaultdict(list)
    for fila in _jsonl(PROPIEDADES):
        agencia, url = fila.get("agency_id"), fila.get("source_url")
        if agencia and url:
            por_agencia[agencia].append(url)

    filas = []
    for agencia, urls in por_agencia.items():
        if len(urls) < MINIMO_PARA_OPINAR:
            continue
        institucionales = [u for u in urls if es_institucional(u)]
        if not institucionales:
            continue
        proporcion = len(institucionales) / len(urls)
        filas.append({
            "canonical_agency_id": agencia,
            "enumeradas": len(urls),
            "institucionales": len(institucionales),
            "proporcion": round(proporcion, 3),
            "sospechosa": proporcion >= UMBRAL_SOSPECHA,
            "ejemplos": institucionales[:6],
        })
    filas.sort(key=lambda f: f["proporcion"], reverse=True)
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detalle", help="ver las urls de una agencia")
    args = ap.parse_args()

    filas = medir()

    if args.detalle:
        elegida = next((f for f in filas
                        if args.detalle.lower() in f["canonical_agency_id"].lower()),
                       None)
        if not elegida:
            print(f"sin urls institucionales para {args.detalle!r}")
            return 1
        print(f"{elegida['canonical_agency_id']}")
        print(f"  {elegida['institucionales']} de {elegida['enumeradas']} "
              f"enumeradas no tienen forma de ficha\n")
        for u in elegida["ejemplos"]:
            print(f"   {u[:104]}")
        print("\ndatabase_writes: 0")
        return 0

    sospechosas = [f for f in filas if f["sospechosa"]]
    reporte = {
        "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agencias_con_alguna_url_institucional": len(filas),
        "agencias_sospechosas": len(sospechosas),
        "umbral": UMBRAL_SOSPECHA,
        "criterio": ("se mira la RUTA de lo enumerado, no el host. Una o dos "
                     "urls institucionales entre cien son el menu; que sean un "
                     "tercio significa que lo enumerado no es un catalogo"),
        "agencias": filas,
        "database_writes": 0,
    }
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    print(f"agencias con alguna url institucional enumerada: {len(filas)}")
    print(f"  de esas, sospechosas (>= {UMBRAL_SOSPECHA:.0%}): "
          f"{len(sospechosas)}\n")
    if filas:
        print(f"  {'AGENCIA':36} {'INST':>5} {'ENUM':>6} {'%':>6}")
        print(f"  {'-' * 36} {'-' * 5} {'-' * 6} {'-' * 6}")
        for f in filas[:15]:
            marca = "**" if f["sospechosa"] else "  "
            print(f"{marca}{f['canonical_agency_id'].split(':')[-1][:36]:36} "
                  f"{f['institucionales']:5} {f['enumeradas']:6} "
                  f"{f['proporcion']:6.0%}")
    print(f"\n  Una o dos urls institucionales son el menu del sitio y no")
    print(f"  prueban nada. Lo que delata a una fuente es que lo enumerado sea")
    print(f"  institucional en su mayoria: ahi no estamos leyendo un catalogo.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

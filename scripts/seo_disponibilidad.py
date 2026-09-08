#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que datos hay para armar URLs canonicas, y cuales NO se pueden inventar.

El frontend necesita una URL estable y legible por propiedad. Armarla es facil;
armarla sin mentir, no: la tentacion es `/venta/casa/rosario/<slug>`, y sobre
las 58.427 solo el 16,5 % tiene localidad demostrada. Poner la ciudad en la URL
de las otras cinco sextas partes seria publicar geografia inventada en el lugar
mas dificil de corregir, porque una URL indexada sobrevive al dato que la
origino.

Lo que este script responde, con numeros:

  cuantas propiedades pueden tener un slug estable y unico
  cuantas colisionan, y por que
  que se puede poner en la URL sin afirmar nada falso
  cuantas pueden llevar datos estructurados completos
  cuantas deberian ir `noindex` y por que

**El slug no lleva geografia salvo que este demostrada.** Un slug con
`area_busqueda` de nivel PROVINCIA diria "rosario" para una propiedad que solo
se sabe que esta en Santa Fe.

**La identidad va al final y siempre.** Dos propiedades distintas pueden tener
el mismo titulo -pasa: dos unidades del mismo edificio- y sin el id la URL de
una pisaria a la otra.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

SEO_VERSION = "seo_disponibilidad_v1"

# Cuanto del titulo entra en el slug. Medido contra las colisiones reales:
#
#    60 caracteres -> 42 % de las propiedades comparten su parte legible
#    80            -> 28 %
#   100            -> 25 %
#   200            -> 25 %
#
# A partir de cien no baja mas: ese 25 % son titulos GENUINAMENTE iguales -dos
# unidades del mismo edificio con el mismo titulo formulario- y ningun largo lo
# arregla. Se elige 80: recupera catorce puntos sobre 60 y no paga los veinte
# caracteres extra que solo compran tres.
LARGO_DEL_SLUG = 80

# Lo que hace falta para que los datos estructurados de una propiedad sean
# utiles: sin precio ni tipo, el buscador no puede mostrarla como propiedad.
CAMPOS_ESTRUCTURADOS = ("titulo", "precio", "moneda", "tipo_propiedad",
                        "operacion")


def _plegar(texto: str) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFD", texto or "")
                  if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sin.lower()).strip("-")


def slug_de(fila: dict[str, Any], geo: dict[str, Any] | None) -> str | None:
    """La parte legible de la URL, sin afirmar nada que no se pueda demostrar.

    Devuelve None cuando no hay ni titulo: sin texto no hay slug legible, y
    una URL que es solo un hash no es peor que una que miente, pero conviene
    saber cuantas son.
    """
    partes: list[str] = []
    if fila.get("operacion"):
        partes.append(_plegar(str(fila["operacion"])))
    if fila.get("tipo_propiedad"):
        partes.append(_plegar(str(fila["tipo_propiedad"])))
    # La geografia entra SOLO con localidad demostrada. El area de busqueda de
    # nivel provincia diria "santa-fe" y quien la lea entendera una ciudad.
    localidad = (geo or {}).get("localidad_canonica")
    if localidad:
        partes.append(_plegar(str(localidad)))
    titulo = _plegar(str(fila.get("titulo") or ""))
    if titulo:
        partes.append(titulo)
    if not partes:
        return None
    return "-".join(p for p in partes if p)[:LARGO_DEL_SLUG].strip("-") or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--cobertura",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_API_CONTRACT")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    geo_por_hash: dict[str, dict[str, Any]] = {}
    ruta = Path(args.cobertura)
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                geo_por_hash[fila["hash_dedup"]] = fila

    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)
    slugs: Counter = Counter()
    sin_slug = 0
    con_geo_en_la_url = 0
    estructurados = 0
    faltantes: Counter = Counter()
    noindex: Counter = Counter()
    total = 0

    for crudo, hash_dedup in conexion.execute(
            "select row_json, hash_dedup from rows where status = 'CANDIDATE'"):
        fila = json.loads(crudo)
        geo = geo_por_hash.get(hash_dedup)
        total += 1

        slug = slug_de(fila, geo)
        if slug is None:
            sin_slug += 1
        else:
            slugs[slug] += 1
        if (geo or {}).get("localidad_canonica"):
            con_geo_en_la_url += 1

        faltan = [c for c in CAMPOS_ESTRUCTURADOS
                  if fila.get(c) in (None, "", 0)]
        if faltan:
            for c in faltan:
                faltantes[c] += 1
        else:
            estructurados += 1

        # Que NO deberia indexarse, y por que. Una pagina sin nada que mostrar
        # compite contra las propias paginas buenas del sitio.
        if not (fila.get("titulo") or fila.get("descripcion")):
            noindex["sin titulo ni descripcion"] += 1
        elif not fila.get("imagenes"):
            noindex["sin ninguna foto"] += 1

    colisiones = {s: n for s, n in slugs.items() if n > 1}
    resumen = {
        "seo_version": SEO_VERSION,
        "propiedades": total,
        "con_slug_legible": total - sin_slug,
        "sin_slug_legible": sin_slug,
        "slugs_distintos": len(slugs),
        "slugs_que_colisionan": len(colisiones),
        "propiedades_en_colision": sum(colisiones.values()),
        # El id va al final SIEMPRE, asi que la colision no rompe la URL: mide
        # cuantas veces el texto legible no alcanza para distinguir.
        "la_url_final_lleva_el_id": True,
        "con_localidad_en_la_url": con_geo_en_la_url,
        "con_localidad_en_la_url_pct": round(100 * con_geo_en_la_url / total, 1),
        "con_datos_estructurados_completos": estructurados,
        "campos_que_faltan_para_estructurados": dict(faltantes.most_common()),
        "recomendadas_noindex": dict(noindex.most_common()),
        "database_writes": 0,
    }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "ERETZ_SEO_DISPONIBILIDAD.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

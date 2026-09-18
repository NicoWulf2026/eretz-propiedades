#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sacar de los artefactos ya extraidos las imagenes que son de la PAGINA.

El chinche del mapa, el icono del telefono, el boton de Pinterest y el banner de
"Agenda un cafe" salen en todas las fichas de un sitio. Medido sobre los
artefactos finales:

  wordpress   91.519 referencias  (15,7%)
  generico    28.724             ( 5,4%)
  wasi           974             ( 1,4%)
  tokko              0           ( 0,0%)  su connector ya verifica el id
  century21          0           ( 0,0%)

El connector ya trae el filtro, pero aplicarlo requeriria volver a bajar 140.000
fichas. No hace falta: la senal es estructural y sale de los propios artefactos,
que ya tienen todas las propiedades de cada inmobiliaria.

No se pisa el original. Se escribe una copia limpia y un informe con cada url
descartada y en cuantas propiedades aparecia, para que la decision se pueda
auditar despues.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import HUELLA_VERSION, PropiedadNormalizada  # noqa: E402
from scripts.run_rollout import (FRACCION_COMPARTIDA,  # noqa: E402
                                 MINIMO_PARA_JUZGAR)
from connectors.wordpress import _sin_variantes_de_tamano  # noqa: E402
from scripts.image_quality import is_known_page_asset  # noqa: E402

import dataclasses  # noqa: E402

CAMPOS = {f.name for f in dataclasses.fields(PropiedadNormalizada)}


def leer(ruta: Path):
    with ruta.open(encoding="utf-8") as fh:
        for number, linea in enumerate(fh, 1):
            linea = linea.strip()
            if linea:
                try:
                    row = json.loads(linea)
                except ValueError:
                    raise ValueError(f'invalid JSON at row {number}') from None
                if not isinstance(row, dict):
                    raise ValueError(f'invalid property object at row {number}')
                yield row


def compartidas_por_agencia(ruta: Path) -> dict[str, set[str]]:
    """Que urls aparecen en la mitad o mas del catalogo de cada inmobiliaria."""
    veces: dict[str, Counter] = defaultdict(Counter)
    cuantas: Counter = Counter()
    for p in leer(ruta):
        cid = p.get("canonical_agency_id")
        cuantas[cid] += 1
        veces[cid].update(set(p.get("imagenes") or []))
    salida = {}
    for cid, c in veces.items():
        n = cuantas[cid]
        if n < MINIMO_PARA_JUZGAR:
            continue
        tope = max(MINIMO_PARA_JUZGAR // 2, n * FRACCION_COMPARTIDA)
        malas = {u for u, v in c.items() if v >= tope and is_known_page_asset(u)}
        if malas:
            salida[cid] = malas
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--salida", default="",
                    help="por defecto, el mismo nombre con .limpio.jsonl")
    ap.add_argument("--informe", default="",
                    help="por defecto, el mismo nombre con .imagenes_descartadas.jsonl")
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo mide; no escribe la copia limpia")
    ap.add_argument("--colapsar-variantes", action="store_true",
                    help="junta las variantes de tamano de WordPress "
                         "(-120x72, -768x1024) en una sola foto")
    a = ap.parse_args()

    ent = Path(a.entrada)
    sal = Path(a.salida) if a.salida else ent.with_suffix(".limpio.jsonl")
    inf = Path(a.informe) if a.informe else ent.with_suffix(".imagenes_descartadas.jsonl")
    if a.aplicar:
        if len({p.resolve() for p in (ent, sal, inf)}) != 3:
            ap.error('input, output and report must be distinct; the original is immutable')
        if sal.exists() or inf.exists():
            ap.error('output/report already exists; choose new artifact paths')

    print("### IMAGENES DE LA PAGINA ###")
    print(f"  artefacto: {ent}", flush=True)
    if not ent.exists():
        print("  !! no existe")
        return 2

    compartidas = compartidas_por_agencia(ent)
    print(f"  inmobiliarias con imagenes de pagina: {len(compartidas):,}")

    total = quitadas = filas = sin_fotos_antes = sin_fotos_despues = 0
    variantes = 0
    detalle: Counter = Counter()
    escritas = []
    for p in leer(ent):
        filas += 1
        imgs = p.get("imagenes") or []
        total += len(imgs)
        if not imgs:
            sin_fotos_antes += 1
        malas = compartidas.get(p.get("canonical_agency_id")) or set()
        if malas:
            nuevas = [u for u in imgs if u not in malas]
            for u in imgs:
                if u in malas:
                    detalle[u] += 1
            quitadas += len(imgs) - len(nuevas)
            p["imagenes"] = nuevas
        if a.colapsar_variantes:
            imgs2 = p.get("imagenes") or []
            juntas = _sin_variantes_de_tamano(imgs2)
            variantes += len(imgs2) - len(juntas)
            p["imagenes"] = juntas
        if not p.get("imagenes"):
            sin_fotos_despues += 1
        if a.aplicar:
            # La huella se RECALCULA con la version vigente: guardar la vieja
            # dejaria el artefacto diciendo una cosa y el contenido otra.
            try:
                p["fingerprint"] = PropiedadNormalizada(
                    **{k: v for k, v in p.items() if k in CAMPOS}).fingerprint
                p["fingerprint_version"] = HUELLA_VERSION
            except TypeError:
                raise ValueError(f'cannot recompute fingerprint at row {filas}') from None
            escritas.append(p)

    print(f"  propiedades:                 {filas:,}")
    print(f"  referencias de imagen:       {total:,}")
    print(f"  descartadas:                 {quitadas:,}  ({quitadas/max(total,1)*100:.1f}%)")
    print(f"  urls distintas descartadas:  {len(detalle):,}")
    if a.colapsar_variantes:
        print(f"  variantes de tamano juntadas: {variantes:,}")
    print(f"  propiedades sin fotos antes: {sin_fotos_antes:,}")
    print(f"  propiedades sin fotos despues: {sin_fotos_despues:,}")
    if detalle:
        print("\n  las mas repetidas:")
        for u, v in detalle.most_common(6):
            print(f"    {v:6,}  {u[:96]}")

    if not a.aplicar:
        print("\n  (solo medicion) usar --aplicar para escribir la copia limpia")
        return 0

    with sal.open("x", encoding="utf-8") as fh:
        for p in escritas:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with inf.open("x", encoding="utf-8") as fh:
        for u, v in detalle.most_common():
            fh.write(json.dumps({"url": u, "propiedades": v,
                                 "motivo": "asset de pagina identificado y repetido "
                                           "en el catalogo de su inmobiliaria",
                                 "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                ensure_ascii=False) + "\n")
    print(f"\n  copia limpia -> {sal.name}")
    print(f"  informe      -> {inf.name}")
    print("  El original no se toca.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

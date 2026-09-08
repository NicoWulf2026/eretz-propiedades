#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Imagenes que no son de ninguna propiedad, detectadas por cruzar agencias.

El filtro que ya existe mira la contaminacion DENTRO de una inmobiliaria: una
imagen que aparece en la mitad o mas de su catalogo no es de ninguna propiedad.
Eso deja pasar todo lo que viene del proveedor del sitio y no de la
inmobiliaria: el boton de compartir en Pinterest esta en 1.169 fichas de TRECE
agencias distintas, y en ninguna llega a la mitad de su catalogo.

La regla que las ve: **una foto de una propiedad no puede estar en el catalogo
de dos inmobiliarias distintas**.

Con una excepcion que no es teorica: la misma propiedad publicada por dos
inmobiliarias -117 grupos medidos- comparte sus fotos legitimamente. Lo que las
separa es cuantas fichas toca en cada agencia:

  boton de Pinterest    13 agencias, 1.169 fichas -> se repite adentro de cada
                        catalogo: no es de ninguna propiedad
  foto compartida       3 agencias, 3 fichas -> una por agencia: es la misma
                        propiedad publicada tres veces

De ahi el criterio: contamina si esta en dos o mas agencias Y aparece en mas
fichas que agencias, o sea si se repite adentro de al menos un catalogo.

**No se descarta la propiedad por quedarse sin fotos.** Una ficha sin imagenes
se muestra igual; lo que no se puede es mostrarle a alguien el logo de la
inmobiliaria como si fuera la casa.

**Es un diagnostico, no un paso del pipeline.** Se midio contra el filtro
intra-agencia que ya aplica la snapshot -una imagen en cinco o mas fichas de la
misma inmobiliaria no es de ninguna propiedad- y su aporte marginal son 48
referencias en 47 fichas: el umbral existente ya atrapa a las diez. Cablearlo
seria un artefacto mas que regenerar y un modo de falla mas, a cambio de nada.

Queda como herramienta para VALIDAR ese umbral: si algun dia se discute si
cinco es el numero, esta es la medicion que lo responde desde el otro lado.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)
from scripts.property_freshest import (CAMPOS_FUSIONABLES,  # noqa: E402
                                       fusionar, mas_frescas)

CONTAMINACION_VERSION = "image_contamination_v1"

# Cuantas fotos de una ficha se miran. Mas alla de cuarenta, una galeria larga
# no cambia el diagnostico y si multiplica el trabajo.
TOPE_POR_FICHA = 40


def contaminantes(uso: dict[str, tuple[set[str], int]]) -> dict[str, dict[str, Any]]:
    """Las urls que no pueden ser de ninguna propiedad, con su evidencia."""
    fuera: dict[str, dict[str, Any]] = {}
    for url, (agencias, fichas) in uso.items():
        if len(agencias) < 2:
            continue
        if fichas <= len(agencias):
            # Una por agencia: es la misma propiedad publicada varias veces.
            continue
        fuera[url] = {"agencias": len(agencias), "fichas": fichas,
                      "motivo": "aparece en varias inmobiliarias y se repite "
                                "adentro de al menos un catalogo"}
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--paquetes",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903")
    args = ap.parse_args()
    exigir_base_vigente(args.db)

    frescas = mas_frescas(Path(args.paquetes))
    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                               uri=True)
    agencias_por_url: dict[str, set[str]] = defaultdict(set)
    fichas_por_url: Counter = Counter()
    fichas = 0

    for crudo, agencia, hash_dedup in conexion.execute(
            "select row_json, canonical_id, hash_dedup from rows "
            "where status = 'CANDIDATE'"):
        fila = fusionar(json.loads(crudo), frescas.get(hash_dedup),
                        CAMPOS_FUSIONABLES)
        fichas += 1
        for url in (fila.get("imagenes") or [])[:TOPE_POR_FICHA]:
            agencias_por_url[url].add(agencia)
            fichas_por_url[url] += 1

    uso = {u: (a, fichas_por_url[u]) for u, a in agencias_por_url.items()}
    sucias = contaminantes(uso)

    destino = Path(args.salida) / "IMAGE_CONTAMINATION.jsonl"
    with destino.open("w", encoding="utf-8") as archivo:
        for url, dato in sorted(sucias.items(), key=lambda x: -x[1]["fichas"]):
            archivo.write(json.dumps(
                dict(dato, url=url, version=CONTAMINACION_VERSION),
                ensure_ascii=False) + "\n")

    compartidas_legitimas = sum(
        1 for u, (a, n) in uso.items() if len(a) >= 2 and n <= len(a))
    resumen = {
        "contaminacion_version": CONTAMINACION_VERSION,
        "fichas_revisadas": fichas,
        "urls_distintas": len(uso),
        "urls_contaminantes": len(sucias),
        "fichas_afectadas": sum(d["fichas"] for d in sucias.values()),
        "compartidas_entre_agencias_pero_legitimas": compartidas_legitimas,
        "peores": [dict(d, url=u) for u, d in
                   sorted(sucias.items(), key=lambda x: -x[1]["fichas"])[:8]],
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "IMAGE_CONTAMINATION_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

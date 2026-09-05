#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que distingue a los miembros de un grupo duplicado, campo por campo.

`property_duplicate_groups` agrupa y no elige ganador, y esta bien: cual se
muestra define quien se lleva el clic. Pero la decision de producto quedaba
planteada sobre 514 grupos indistinguibles entre si, y no todos son el mismo
problema.

La pregunta que la vuelve decidible: **dentro de un grupo, los miembros se
diferencian en algo ademas del id de la URL?**

  no se diferencian en nada    la misma publicacion cargada dos veces. Mostrar
                               las dos es mostrarle a una persona la misma
                               propiedad repetida
  distinta direccion o          pueden ser dos unidades distintas del mismo
  distinta superficie total     edificio, que es exactamente el caso que el
                               documento pedia no romper
  misma direccion, distinto     alguien actualizo una y no la otra. Sin
  precio                        resolver, el portal muestra dos precios para
                               lo mismo
  misma direccion, distinta     la misma propiedad con datos contradictorios:
  cuenta de ambientes o banos   no son dos unidades, es un dato mal cargado o
                               mal leido

**La comparacion normaliza antes de decidir.** `Tissera Esquina Los Cedros` y
`Tissera esquina Los Cedros` son la misma direccion, y compararlas crudas
mandaba el grupo a "pueden ser dos unidades" cuando lo unico que cambiaba era
una mayuscula y un bano. Es el mismo error de alfabetos distintos que ya
aparecio entre la senal de fuente y su extraccion.

Esto NO elige ganador ni borra nada: cuenta y da ejemplos para que la decision
se tome sobre evidencia. `ganadores_elegidos: 0`, `database_writes: 0`.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.preingestion_manifest import base_canonica  # noqa: E402

EVIDENCIA_VERSION = "property_duplicate_evidence_v1"

# Lo que una persona ve de una propiedad. El id interno y la URL quedan fuera a
# proposito: son justamente lo que sabemos que difiere.
VISIBLES = ("titulo", "descripcion", "precio", "moneda", "operacion",
            "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
            "ambientes", "dormitorios", "banos", "superficie_total",
            "superficie_cubierta", "latitud", "longitud")

# Lo unico que distingue de verdad dos unidades del mismo edificio: donde
# esta y cuanto mide. Que difiera la cuenta de banos NO alcanza: dos fichas
# con la misma direccion, el mismo precio y la misma superficie cubierta que
# discrepan en un bano son una propiedad mal cargada, no dos propiedades.
DISTINGUEN_UNIDAD = ("direccion", "superficie_total", "superficie_cubierta")

# Cuentas que la fuente puede contradecirse a si misma sin que cambie el
# inmueble.
CUENTAS = ("ambientes", "dormitorios", "banos")

TEXTO = ("titulo", "descripcion", "direccion", "barrio", "ciudad", "provincia")


def normalizado(campo: str, valor: Any) -> Any:
    """Mayusculas, acentos y espacios no hacen distinta a una direccion."""
    if campo in TEXTO and isinstance(valor, str):
        sin = valor.translate(str.maketrans(
            "áéíóúüñ"
            "ÁÉÍÓÚÜÑ",
            "aeiouunAEIOUUN"))
        return re.sub(r"[^a-z0-9]+", " ", sin.lower()).strip()
    return valor


def _cuantas_imagenes(fila: dict[str, Any]) -> int:
    imagenes = fila.get("imagenes")
    return len(imagenes) if isinstance(imagenes, list) else 0


def campos_que_difieren(filas: list[dict[str, Any]]) -> list[str]:
    """Que campos visibles NO son iguales en todos los miembros."""
    distintos = []
    for campo in VISIBLES:
        valores = {json.dumps(normalizado(campo, f.get(campo)),
                              sort_keys=True, default=str)
                   for f in filas}
        if len(valores) > 1:
            distintos.append(campo)
    return distintos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--grupos",
                    default=str(base_canonica().parent
                                / "PROPERTY_DUPLICATE_GROUPS.jsonl"))
    ap.add_argument("--salida", default=str(base_canonica().parent))
    args = ap.parse_args()

    grupos = [json.loads(l) for l in
              Path(args.grupos).read_text(encoding="utf-8").splitlines() if l.strip()]

    conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro", uri=True)
    por_hash: dict[str, dict[str, Any]] = {}
    necesarios = {m["hash_dedup"] for g in grupos for m in g["miembros"]}
    for crudo, hash_dedup in conexion.execute(
            "select row_json, hash_dedup from rows where status = 'CANDIDATE'"):
        if hash_dedup in necesarios:
            por_hash[hash_dedup] = json.loads(crudo)

    destino = Path(args.salida) / "PROPERTY_DUPLICATE_EVIDENCE.jsonl"
    campos = Counter()
    clases: Counter = Counter()
    por_alcance: Counter = Counter()
    sin_fila = 0

    with destino.open("w", encoding="utf-8") as archivo:
        for grupo in grupos:
            filas = [por_hash[m["hash_dedup"]] for m in grupo["miembros"]
                     if m["hash_dedup"] in por_hash]
            if len(filas) < 2:
                # Sin las filas completas no se puede afirmar nada del grupo.
                sin_fila += 1
                continue
            difieren = campos_que_difieren(filas)
            for campo in difieren:
                campos[campo] += 1

            if not difieren:
                clase = "IDENTICOS_EN_TODO_LO_VISIBLE"
            elif any(c in DISTINGUEN_UNIDAD for c in difieren):
                clase = "PUEDEN_SER_UNIDADES_DISTINTAS"
            elif "precio" in difieren or "moneda" in difieren:
                clase = "MISMO_INMUEBLE_PRECIO_DISTINTO"
            elif any(c in CUENTAS for c in difieren):
                clase = "MISMO_INMUEBLE_DATOS_INCONSISTENTES"
            else:
                clase = "SOLO_TEXTO_O_UBICACION_IMPRECISA"
            clases[clase] += 1
            por_alcance[(grupo["alcance"], clase)] += 1

            archivo.write(json.dumps({
                "grupo_id": grupo["grupo_id"],
                "alcance": grupo["alcance"],
                "evidencia_version": EVIDENCIA_VERSION,
                "clase": clase,
                "campos_que_difieren": difieren,
                "miembros": len(filas),
                "imagenes_por_miembro": [_cuantas_imagenes(f) for f in filas],
                "urls": [f.get("source_url") for f in filas],
                "ganador_elegido": None,
                "database_writes": 0,
            }, ensure_ascii=False) + "\n")

    resumen = {
        "evidencia_version": EVIDENCIA_VERSION,
        "grupos_analizados": sum(clases.values()),
        "grupos_sin_filas_completas": sin_fila,
        "por_clase": dict(clases.most_common()),
        "por_alcance_y_clase": {f"{a}|{c}": n
                                for (a, c), n in por_alcance.most_common()},
        "campos_que_difieren": dict(campos.most_common()),
        "ganadores_elegidos": 0,
        "database_writes": 0,
        "artefacto": destino.name,
    }
    (Path(args.salida) / "PROPERTY_DUPLICATE_EVIDENCE_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

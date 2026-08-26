#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aplicar las guardas de coherencia a lo ya extraido, sin volver a bajar nada.

Las guardas viven en el connector y corrigen lo que se extrae de ahora en mas.
Pero 29.780 propiedades ya extraidas siguen teniendo los mismos defectos, y
volver a recorrer 1.400 sitios para arreglar un campo seria absurdo: los
defectos son de lectura, no de la fuente, y se pueden corregir sobre el
artefacto.

  - mas dormitorios que ambientes -> ninguno de los dos es confiable
  - superficie cubierta mayor que la total -> lo mismo
  - dormitorios en un terreno -> vinieron de otra ficha de la pagina
  - precio sin moneda -> no es un precio; el numero se guarda aparte

Escribe al lado, con sufijo `.coherente.jsonl`. No pisa el original.

IMPORTANTE: si se va a correr otra vez sobre esa fuente, hay que reconstruir el
baseline desde el archivo corregido -rebuild_checkpoint_baseline.py-. Si no, la
corrida siguiente compara contra huellas calculadas sobre los valores viejos y
reporta MODIFICADA por una correccion nuestra.

Solo lee y escribe artefactos.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.coherencia import revisar  # noqa: E402


def corregir(p: dict) -> tuple[dict, list[str]]:
    motivos = revisar(p)
    if p.get("precio") is not None and not p.get("moneda"):
        extra = p.get("extra") or {}
        extra["precio_sin_moneda"] = p["precio"]
        p["extra"], p["precio"] = extra, None
        motivos.append("precio_sin_moneda")
    return p, motivos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entradas", nargs="+", required=True)
    ap.add_argument("--sufijo", default=".coherente.jsonl")
    a = ap.parse_args()

    print("### GUARDAS DE COHERENCIA SOBRE LO YA EXTRAIDO ###")
    total_g = Counter()
    for ruta in a.entradas:
        origen = Path(ruta)
        if not origen.exists():
            print(f"  {origen} no existe")
            continue
        filas, motivos = [], Counter()
        for l in origen.open(encoding="utf-8"):
            l = l.strip()
            if not l:
                continue
            p, ms = corregir(json.loads(l))
            filas.append(p)
            for m in ms:
                motivos[m] += 1
                total_g[m] += 1

        destino = origen.with_name(origen.name.replace(".jsonl", "") + a.sufijo)
        destino.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                                   for f in filas), encoding="utf-8")
        tocadas = sum(motivos.values())
        print(f"\n  {origen.parent.name}/{origen.name}  ({len(filas):,} propiedades)")
        for k, v in motivos.most_common():
            print(f"      {k:34} {v:6,}")
        if not tocadas:
            print("      nada que corregir")
        print(f"      -> {destino.name}")

    print("\n  TOTAL")
    for k, v in total_g.most_common():
        print(f"    {k:36} {v:7,}")
    print("\n  el original no se toca. Antes de la proxima corrida sobre estas")
    print("  fuentes hay que reconstruir el baseline desde el archivo corregido,")
    print("  o la corrida siguiente va a leer nuestra correccion como un cambio")
    print("  de la inmobiliaria.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

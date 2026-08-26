#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que pasaria si la regla de bajas estuviera activa. No desactiva nada.

Una propiedad que hoy no aparece NO es una baja. Puede ser un timeout, un
listado paginado a la mitad, un sitio que cambio de plantilla o un aviso que
paso a otra pagina. Por eso la ingesta corre en modo observacion: anota
`POTENTIAL_INACTIVE` y sigue.

Antes de encender la regla hay que poder responder dos cosas con numeros:

  cuantas propiedades desactivaria hoy, y de que fuentes
  cuantas de esas volvieron a aparecer despues de "desaparecer"

La segunda es la que importa. Una regla que da de baja algo que reaparece a la
corrida siguiente es una regla que borra inventario vivo, y eso en un
agregador se ve enseguida: la inmobiliaria llama para preguntar por que no
esta su propiedad.

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.mission_report import corridas_de  # noqa: E402

# La regla propuesta: tres corridas seguidas sin verla. Ninguna cuenta si la
# fuente no respondio o si la enumeracion quedo incompleta -eso ya lo decide el
# runner, que no emite ausencias cuando no puede confiar en lo que vio-.
AUSENCIAS_PARA_BAJA = 3

# Las ausencias de las primeras corridas se anotaron con la clave vieja del
# checkpoint -el id del listado, "7797368"- y no con el hash. Mezclarlas con
# las nuevas no da error: da un resultado sin sentido, porque ninguna clave
# vieja coincide nunca con una propiedad actual y todas parecen desaparecidas
# para siempre. Se reconocen por la forma y se informan aparte.
RE_HASH = re.compile(r"^[0-9a-f]{32}$")


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--rollouts", nargs="*", default=[
        "TOKKO_ROLLOUT_FULL", "WP_ROLLOUT_FULL", "WASI_ROLLOUT_FULL",
        "C21_CANARY", "FORMAS_ROLLOUT"])
    ap.add_argument("--umbral", type=int, default=AUSENCIAS_PARA_BAJA)
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\DELETION_DRY_RUN.jsonl")
    a = ap.parse_args()

    print("### REGLA DE BAJAS: SIMULACION ###")
    print(f"  umbral: {a.umbral} corridas seguidas sin ver la propiedad\n")

    candidatas, resucitadas, observadas = [], [], []
    formato_viejo: Counter = Counter()
    for nombre in a.rollouts:
        base = Path(a.raiz) / nombre
        corridas = corridas_de(base, "absences_")
        if not corridas:
            continue

        # Que vio cada corrida, para saber si una ausente volvio a aparecer.
        vistas_por_corrida: dict[str, set] = {}
        for c in corridas_de(base, "properties_"):
            props = base / f"properties_run{c}.jsonl"
            vistas_por_corrida[c] = {p.get("hash_dedup") for p in leer(props)}

        ausencias: dict[str, list[str]] = defaultdict(list)
        detalle: dict[str, dict] = {}
        for c in corridas:
            for x in leer(base / f"absences_run{c}.jsonl"):
                clave = str(x.get("hash_dedup") or "")
                if not RE_HASH.match(clave):
                    formato_viejo[f"{nombre} run{c}"] += 1
                    continue
                ausencias[clave].append(c)
                detalle[clave] = x

        for h, cs in ausencias.items():
            # Reaparecio: estuvo ausente en una corrida y presente en otra
            # POSTERIOR. Es la prueba de que la ausencia no era una baja.
            # Comparadas como numeros. Con strings, la corrida 10 seria
            # "anterior" a la 3 y una reaparicion tardia pasaria inadvertida.
            ultima_ausencia = max(int(c) for c in cs)
            volvio = [c for c in vistas_por_corrida
                      if int(c) > ultima_ausencia and h in vistas_por_corrida[c]]
            fila = {"hash_dedup": h, "rollout": nombre,
                    "canonical_agency_id": detalle[h].get("canonical_agency_id"),
                    "source_listing_id": detalle[h].get("source_listing_id"),
                    "corridas_ausente": cs,
                    "ausencias_consecutivas": max(
                        detalle[h].get("ausencias_consecutivas") or 0, len(cs)),
                    "reaparecio_en": volvio}
            observadas.append(fila)
            if volvio:
                resucitadas.append(fila)
            elif fila["ausencias_consecutivas"] >= a.umbral:
                candidatas.append(fila)

    salida = Path(a.salida)
    salida.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in candidatas + resucitadas), encoding="utf-8")

    print(f"  ausencias comparables:     {len(observadas):,}")
    print(f"  se desactivarian hoy:      {len(candidatas):,}")
    print(f"  volvieron a aparecer:      {len(resucitadas):,}"
          f"   <- la regla las habria borrado vivas" if resucitadas else
          f"  volvieron a aparecer:      0")
    # Sobre TODAS las ausencias validas, no solo las que llegaron al umbral:
    # la pregunta es si la racha mas larga se acerca siquiera a la regla.
    maxima = max([f["ausencias_consecutivas"] for f in observadas] + [0])
    print(f"  ausencia consecutiva mas larga:  {maxima}")
    if maxima < a.umbral:
        print("  la regla no tuvo ocasion de dispararse todavia: ninguna "
              f"propiedad estuvo ausente {a.umbral} corridas seguidas.")

    if candidatas:
        print("\n  por fuente (las diez con mas):")
        for k, v in Counter(f["canonical_agency_id"] for f in candidatas).most_common(10):
            print(f"    {str(k)[:44]:46} {v:5}")
    if formato_viejo:
        print("\n  ausencias con la clave vieja del checkpoint, no comparables:")
        for k, v in formato_viejo.most_common():
            print(f"    {k:34} {v:7,}")
        print("    (se anotaron con el id del listado; ninguna puede "
              "cruzarse con una propiedad de hoy)")

    print("\n  nada se desactiva: esto es una simulacion sobre los artefactos.")
    print(f"  artefacto -> {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

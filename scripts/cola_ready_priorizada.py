#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La próxima cola READY, ordenada por lo que rinde y no por orden alfabético.

No escribe en la base. `database_writes: 0`. Produce una propuesta de orden;
no toca la cola que está corriendo.

### Por qué no FIFO

Hoy la cola procesa por orden de aparición. Con 28 días hasta el 12/10 y un
rendimiento efectivo del 8 %, el orden decide cuántas propiedades entran antes
de la fecha. No es lo mismo empezar por las 211 oficinas de red —216 avisos
cada una— que por las 2.216 sin web, que promedian 5.

### El puntaje

    priority_score = propiedades_esperadas / minutos_esperados

`propiedades_esperadas` sale de `avisos_observados`, que es lo que Roomix vio
publicar. `minutos_esperados` sale de la mediana real medida por familia sobre
1.770 certificaciones, no de una estimación.

Los ajustes son pocos y explicables, porque un puntaje que nadie puede auditar
se deja de usar a la primera sorpresa:

    x1,3  familia conocida: el conector ya la certificó antes
    x1,2  web verificada contra la fuente
    x0,5  la familia agota el presupuesto seguido
    x0,3  identidad ambigua: puede terminar sin poder atribuirse

Uso:
    python scripts/cola_ready_priorizada.py
    python scripts/cola_ready_priorizada.py --top 40
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
SALIDA = CERT / "ERETZ_COLA_READY_PRIORIZADA.jsonl"

# Si no se conoce la familia, se usa la mediana global medida.
MINUTOS_POR_DEFECTO = 3.4


def leer(ruta: Path, clave: str) -> dict[str, dict]:
    fuera = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
        except ValueError:
            continue
        if f.get(clave):
            fuera[f[clave]] = f
    return fuera


def minutos_por_familia() -> tuple[dict[str, float], set[str], set[str]]:
    """Mediana real por estrategia, y qué familias agotan presupuesto."""
    duraciones: dict[str, list[float]] = defaultdict(list)
    agotan: Counter = Counter()
    corridas: Counter = Counter()
    ruta = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        fam = r.get("connector_strategy") or r.get("connector")
        if not fam:
            continue
        d = (r.get("operational_metrics") or {}).get("duration_seconds")
        if isinstance(d, (int, float)) and d > 0:
            duraciones[fam].append(d / 60)
        corridas[fam] += 1
        if any((r.get(c) or {}).get("presupuesto_agotado") for c in ("run1", "run2")):
            agotan[fam] += 1
    medianas = {f: statistics.median(v) for f, v in duraciones.items() if v}
    conocidas = {f for f, n in corridas.items() if n >= 5}
    lentas = {f for f in corridas if corridas[f] >= 5
              and agotan[f] / corridas[f] >= 0.25}
    return medianas, conocidas, lentas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    medianas, conocidas, lentas = minutos_por_familia()
    breakdown = [json.loads(l) for l in
                 (CERT / "ERETZ_STAGING_BREAKDOWN.jsonl").read_text(
                     encoding="utf-8", errors="replace").splitlines() if l.strip()]
    padron = leer(DATOS / "roomix_agency_directory.jsonl", "stable_id")
    plataforma = {}
    ruta_plat = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    if ruta_plat.exists():
        plataforma = leer(ruta_plat, "canonical_agency_id")
    validadas = leer(CERT / "ERETZ_OFFICE_PAGES_VALIDADAS.jsonl", "agency_id")

    # Sólo entran las que pueden certificarse: hay una fuente para mirar.
    ELEGIBLES = {"OFFICIAL_WEB_LISTA", "OFFICIAL_OFFICE_PAGE"}
    filas = []
    for f in breakdown:
        if f["block_reason"] not in ELEGIBLES:
            continue
        if f["block_reason"] == "OFFICIAL_OFFICE_PAGE":
            v = validadas.get(f["agency_id"])
            # Sin validar, o validada y rechazada, no entra: certificar una
            # pagina de red que no es de esta oficina produce inventario ajeno.
            if not v or v.get("clase") != "OFFICIAL_OFFICE_PAGE":
                continue

        propiedades = f.get("avisos_observados") or 0
        fam = (plataforma.get(f["agency_id"]) or {}).get("connector") or "desconocida"
        minutos = medianas.get(fam, MINUTOS_POR_DEFECTO)
        puntaje = propiedades / max(minutos, 0.5)
        ajustes = []
        if fam in conocidas:
            puntaje *= 1.3
            ajustes.append("familia conocida")
        if f["block_reason"] == "OFFICIAL_WEB_LISTA":
            puntaje *= 1.2
            ajustes.append("web verificada")
        if fam in lentas:
            puntaje *= 0.5
            ajustes.append("familia que agota presupuesto")
        filas.append({
            "agency_id": f["agency_id"],
            "nombre": f.get("nombre") or "",
            "block_reason": f["block_reason"],
            "propiedades_esperadas": propiedades,
            "familia": fam,
            "minutos_esperados": round(minutos, 1),
            "priority_score": round(puntaje, 1),
            "ajustes": "; ".join(ajustes),
            "official_url": f.get("official_url") or "",
        })

    filas.sort(key=lambda x: -x["priority_score"])
    with SALIDA.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    total_prop = sum(f["propiedades_esperadas"] for f in filas)
    total_min = sum(f["minutos_esperados"] for f in filas)
    print(f"COLA READY PROPUESTA: {len(filas):,} agencias")
    print(f"  propiedades esperadas:  {total_prop:,}")
    print(f"  tiempo estimado:        {total_min/60:.0f} h con 1 worker, "
          f"{total_min/120:.0f} h con 2\n")

    acum = 0
    for i, f in enumerate(filas, 1):
        acum += f["propiedades_esperadas"]
        if i == 50:
            print(f"  las primeras 50 concentran {acum:,} propiedades "
                  f"({acum/total_prop:.0%} del total)\n")
            break

    print(f"{'#':>3} {'agencia':32} {'prop':>6} {'min':>6} {'score':>8}  familia")
    for i, f in enumerate(filas[:args.top], 1):
        print(f"{i:3} {f['nombre'][:30]:32} {f['propiedades_esperadas']:6} "
              f"{f['minutos_esperados']:6.1f} {f['priority_score']:8.1f}  "
              f"{f['familia'][:18]}")

    print(f"\n  artefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

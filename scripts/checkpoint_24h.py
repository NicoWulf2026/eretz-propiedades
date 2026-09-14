#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La línea de base de hoy, para poder medir el progreso de mañana.

No escribe en la base. `database_writes: 0`.

El §14 pide un checkpoint de 24 h sobre **trabajo nuevo**, no sobre corridas
ejecutadas. La diferencia no es formal: en las últimas 24 h se ejecutaron 348
certificaciones y sólo 18 fueron agencias nuevas. Medir "corridas por día"
habría dado un número veinte veces mejor que la realidad.

Por eso la base se guarda con los contadores que importan, y la comparación de
mañana los resta. Sin base guardada hoy, mañana no hay contra qué comparar y el
checkpoint se convierte en otra estimación.

Uso:
    python scripts/checkpoint_24h.py --guardar     # fija la base
    python scripts/checkpoint_24h.py               # compara contra la base
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
BASE = CERT / "ERETZ_CHECKPOINT_BASE.json"

DEADLINE = date(2026, 10, 12)
UNIVERSO = 6597
# Terminal de inventario. Identity terminal se mide aparte.
INVENTARIO_TERMINAL = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
                       "NO_INVENTORY_CONFIRMED", "BLOCKED_EXTERNAL"}
IDENTIDAD_TERMINAL = INVENTARIO_TERMINAL | {"IDENTITY_PENDING"}


def epoch(t: str) -> float | None:
    try:
        return datetime.strptime((t or "")[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
    except ValueError:
        return None


def foto() -> dict:
    """El estado actual, con los contadores que el §14 pide."""
    ultimo: dict[str, dict] = {}
    primera: dict[str, float] = {}
    corridas = 0
    for linea in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        a = r.get("canonical_agency_id")
        if not a:
            continue
        corridas += 1
        ultimo[a] = r
        t = epoch(r.get("checked_at") or "")
        if t and a not in primera:
            primera[a] = t

    estados = Counter(r.get("status") for r in ultimo.values())
    propiedades = sum((r.get("enumeration_audit") or {}).get("enumerated") or 0
                      for r in ultimo.values()
                      if r.get("status") in INVENTARIO_TERMINAL)
    diferidas = 0
    ruta_dif = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
    if ruta_dif.exists():
        diferidas = sum(1 for l in ruta_dif.read_text(
            encoding="utf-8", errors="replace").splitlines() if l.strip())

    return {
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "epoch": time.time(),
        "agencias_con_resultado": len(ultimo),
        "total_certification_runs": corridas,
        "identity_done": sum(n for e, n in estados.items()
                             if e in IDENTIDAD_TERMINAL),
        "inventory_done": sum(n for e, n in estados.items()
                              if e in INVENTARIO_TERMINAL),
        "propiedades_certificadas": propiedades,
        "diferidas": diferidas,
        "por_estado": dict(estados),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--guardar", action="store_true")
    args = ap.parse_args()

    ahora = foto()

    if args.guardar:
        BASE.write_text(json.dumps(ahora, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        print("BASE DEL CHECKPOINT GUARDADA\n")
        for k in ("agencias_con_resultado", "total_certification_runs",
                  "identity_done", "inventory_done", "propiedades_certificadas",
                  "diferidas"):
            print(f"   {k:28} {ahora[k]:>8,}")
        print(f"\n   {BASE}")
        print("\n   en 24 h: python scripts/checkpoint_24h.py")
        print("database_writes: 0")
        return 0

    if not BASE.exists():
        print("no hay base guardada. Primero:")
        print("   python scripts/checkpoint_24h.py --guardar")
        return 1

    base = json.loads(BASE.read_text(encoding="utf-8"))
    horas = (ahora["epoch"] - base["epoch"]) / 3600
    if horas < 0.05:
        print("la base se guardo recien: no hay nada que comparar todavia")
        return 0

    def delta(k: str) -> int:
        return ahora[k] - base[k]

    corridas = delta("total_certification_runs")
    nuevas = delta("agencias_con_resultado")
    recert = corridas - nuevas

    print(f"CHECKPOINT — {horas:.1f} h desde la base ({base['cuando']})\n")
    print(f"   NEW_AGENCIES_PROCESSED       {nuevas:8,}")
    print(f"   RECERTIFICATIONS             {recert:8,}")
    if corridas:
        print(f"   NEW_WORK_RATIO               {nuevas/corridas:8.1%}")
    print(f"   NEW_IDENTITY_DONE            {delta('identity_done'):8,}")
    print(f"   NEW_INVENTORY_DONE           {delta('inventory_done'):8,}")
    print(f"   PROPERTIES_NEWLY_CERTIFIED   {delta('propiedades_certificadas'):8,}")
    print(f"   DEFERRED_ADDED               {delta('diferidas'):8,}")

    por_dia = delta("inventory_done") / max(horas / 24, 0.01)
    ident_dia = delta("identity_done") / max(horas / 24, 0.01)
    dias = (DEADLINE - date.today()).days
    faltan = UNIVERSO - ahora["inventory_done"]
    print(f"\n   NEW_AGENCY_TERMINAL/dia      {por_dia:8.0f}")
    print(f"   NEW_IDENTITY_DONE/dia        {ident_dia:8.0f}")
    print(f"   REQUIRED_RATE_TO_OCT12       {faltan/max(dias,1):8.0f}")

    # Las dos fechas del §24, que no son la misma.
    if ident_dia > 0:
        falta_id = UNIVERSO - ahora["identity_done"]
        print(f"\n   IDENTITY_COMPLETION_DATE     "
              f"{date.fromordinal(date.today().toordinal() + int(falta_id/ident_dia))}")
    else:
        print("\n   IDENTITY_COMPLETION_DATE     sin avance en la ventana")
    if por_dia > 0:
        print(f"   FULL_AGENCY_TERMINAL_DATE    "
              f"{date.fromordinal(date.today().toordinal() + int(faltan/por_dia))}")
    else:
        print("   FULL_AGENCY_TERMINAL_DATE    sin avance en la ventana")

    objetivo = faltan / max(dias, 1)
    estado = ("GREEN" if por_dia >= 200 else "YELLOW" if por_dia >= 130
              else "RED")
    print(f"\n   STATUS: {estado}   (minimo tolerable 130, objetivo 150-180)")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

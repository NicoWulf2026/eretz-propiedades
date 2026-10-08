#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Fecha de finalizacion de la mision, MEDIDA: cuantas agencias faltan y a que ritmo se estan cerrando.

Pedido del usuario (08-10): una vez por dia, la fecha de finalizacion. No se inventa: sale del registro
unificado (`registro_unificado.py`) y del ledger de certificacion.

- Abordada = la agencia tiene un cierre demostrado: CERTIFICADA, SIN_INVENTARIO_CONFIRMADO o BLOCKED_EXTERNAL
  con evidencia. Todo lo demas (sin web, web sin verificar, lista, NEEDS_FIX, conflictiva, MAIN sin datos)
  esta pendiente.
- Ritmo = agencias que tuvieron su PRIMER cierre en cada uno de los ultimos 7 dias (promedio).
- Proyeccion = hoy + pendientes / ritmo. Se informa junto a la fecha objetivo del plan (30-11) y al ritmo que
  haria falta para llegar a esa fecha.
- Cada corrida agrega una linea a `ERETZ_REGISTRO/AVANCE_DIARIO.jsonl` para ver la tendencia.

    python scripts/fecha_de_finalizacion.py
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from scripts.ledger_de_certificacion import leer_ledger  # noqa: E402
from scripts.registro_unificado import construir  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402

OBJETIVO = dt.date(2026, 11, 30)
ABORDADAS = ("CERTIFICADA", "SIN_INVENTARIO_CONFIRMADO", "BLOCKED_EXTERNAL")
TERMINALES_LEDGER = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "NO_INVENTORY_CONFIRMED",
                     "BLOCKED_EXTERNAL")


def ritmo(hoy: dt.date, dias: int = 7) -> tuple[float, dict[str, int]]:
    filas, _ = leer_ledger(dato("ERETZ_AGENCY_CERTIFICATION_20260827", "AGENCY_CERTIFICATION_RESULTS.jsonl"),
                           estricto=False)
    primero: dict[str, str] = {}
    for f in sorted(filas, key=lambda f: str(f.get("checked_at"))):
        if f.get("status") in TERMINALES_LEDGER:
            primero.setdefault(f.get("canonical_agency_id"), str(f.get("checked_at"))[:10])
    por_dia = collections.Counter(primero.values())
    ventana = {(hoy - dt.timedelta(days=i)).isoformat(): por_dia.get((hoy - dt.timedelta(days=i)).isoformat(), 0)
               for i in range(1, dias + 1)}
    return sum(ventana.values()) / dias, ventana


def calcular(hoy: dt.date | None = None) -> dict:
    hoy = hoy or dt.date.today()
    filas, resumen = construir()
    por_estado = collections.Counter(f["estado"] for f in filas)
    abordadas = sum(por_estado[e] for e in ABORDADAS)
    pendientes = len(filas) - abordadas
    por_dia, ventana = ritmo(hoy)
    proyectada = (hoy + dt.timedelta(days=round(pendientes / por_dia))) if por_dia > 0 else None
    dias_al_objetivo = max(1, (OBJETIVO - hoy).days)
    return {
        "fecha": hoy.isoformat(), "entidades": len(filas), "abordadas": abordadas, "pendientes": pendientes,
        "por_estado": dict(por_estado.most_common()),
        "ritmo_medido_por_dia": round(por_dia, 1), "ventana": ventana,
        "fecha_proyectada_al_ritmo_actual": proyectada.isoformat() if proyectada else None,
        "fecha_objetivo": OBJETIVO.isoformat(),
        "ritmo_necesario_para_el_objetivo": round(pendientes / dias_al_objetivo, 1),
        "invariante_ninguna_olvidada": resumen["invariante_ninguna_olvidada"]["ok"],
        "nota": ("5.369 de MAIN no tienen datos locales y una parte son la misma agencia que una canonica sin "
                 "fusionar: el universo real es menor que el contado hasta leer inmobiliarias_main."),
    }


def main() -> int:
    salida = calcular()
    ruta = dato("ERETZ_REGISTRO", "AVANCE_DIARIO.jsonl")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(salida, ensure_ascii=False) + "\n")
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

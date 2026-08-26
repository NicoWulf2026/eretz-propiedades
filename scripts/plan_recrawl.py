#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cada cuanto volver a leer cada fuente, decidido por lo que cada fuente hace.

Volver a recorrerlas todas todos los dias es tirar la mayor parte del trabajo:
entre la corrida 2 y la 3 de Tokko, 91.503 de 91.659 propiedades -el 99,83%-
estaban exactamente iguales. Casi todo el gasto se fue en confirmar que nada
habia cambiado.

Pero bajar la frecuencia parejo tampoco sirve: una inmobiliaria que publica
todas las semanas y otra que no toca su web desde hace un ano no son el mismo
problema. Asi que la cadencia sale de la evidencia de cada fuente:

  cuantas propiedades cambiaron  ->  cada cuanto vale la pena volver

Este script NO corre nada. Escribe el plan y quien lo ejecute decide. Un
planificador que ademas dispara es un planificador que no se puede leer antes
de que actue.

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# Los limites existen para que ninguna heuristica se vaya de rango. Un dia es lo
# mas seguido que tiene sentido volver a una web de inmobiliaria; dos semanas es
# lo mas espaciado antes de que "no cambio nunca" empiece a significar "dejamos
# de mirar".
MINIMO_DIAS = 1
MAXIMO_DIAS = 14

# Una fuente que no respondio no se castiga con menos frecuencia: al contrario,
# hay que volver pronto para saber si fue un problema pasajero.
ESTADOS_SANOS = {"OK", "ENUMERACION_INCOMPLETA"}

# Pero hay dos maneras distintas de fallar, y confundirlas hace que el plan
# gaste su presupuesto en el lugar equivocado:
#
#   PASAJERO   la fuente estaba caida, bloqueada o lenta. Volver manana puede
#              resolverlo solo.
#   ESTRUCTURAL  no supimos leerla. Volver manana da exactamente el mismo
#              resultado 365 veces al ano: lo que falta es codigo, no otra
#              lectura. 334 fuentes estaban pidiendo lectura diaria por esto.
PASAJEROS = {"BLOQUEADA", "ERROR_DISCOVERY", "EXCEPCION", "ERROR_TRANSITORIO"}
ESTRUCTURALES = {"VARIANTE_NO_SOPORTADA", "SIN_INVENTARIO", "NO_SOPORTADA"}


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def corridas_de(directorio: Path) -> list[Path]:
    """Los inventarios de ese rollout, de la corrida mas vieja a la mas nueva."""
    def clave(p: Path) -> tuple:
        n = p.stem.replace("source_inventory_run", "")
        return (0, int(n)) if n.isdigit() else (1, 0)
    return sorted(directorio.glob("source_inventory_run*.jsonl"), key=clave)


def tasa_de_cambio(filas: list[dict]) -> tuple[float, int, int]:
    """Que proporcion del inventario de esa fuente cambio en su ultima corrida.

    Se mira la ultima corrida que la vio, no el promedio historico: una
    inmobiliaria que estuvo quieta seis meses y publico veinte propiedades esta
    semana necesita que volvamos pronto, y el promedio lo escondería.
    """
    ultima = filas[-1]
    cambios = ultima.get("cambios") or {}
    movidas = sum(v for k, v in cambios.items() if k in ("NUEVA", "MODIFICADA"))
    total = sum(cambios.values()) or ultima.get("detalles_obtenidos") or 0
    ausentes = ultima.get("ausentes") or 0
    return ((movidas + ausentes) / total if total else 0.0), movidas + ausentes, total


def cadencia(tasa: float, estado: str, corridas: int) -> tuple[int, str]:
    """Dias hasta la proxima lectura, y por que."""
    if estado in ESTRUCTURALES:
        return MAXIMO_DIAS, (f"{estado}: no la supimos leer. Volver manana da el "
                             f"mismo resultado; lo que falta es un connector")
    if estado not in ESTADOS_SANOS:
        motivo = ("puede haber sido pasajero" if estado in PASAJEROS
                  else "estado desconocido")
        return MINIMO_DIAS, f"la ultima corrida termino en {estado}: {motivo}"
    if corridas < 2:
        return 3, "una sola corrida: todavia no hay con que comparar"
    if tasa >= 0.10:
        return MINIMO_DIAS, f"{tasa*100:.0f}% del inventario se movio"
    if tasa >= 0.02:
        return 3, f"{tasa*100:.1f}% del inventario se movio"
    if tasa > 0:
        return 7, f"{tasa*100:.2f}% del inventario se movio"
    return MAXIMO_DIAS, "no cambio nada en la ultima corrida"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--rollouts", nargs="*", default=[
        "TOKKO_ROLLOUT_FULL", "WP_ROLLOUT_FULL", "WASI_ROLLOUT_FULL",
        "C21_CANARY", "RESCATE2_generico", "RESCATE2_tokko",
        "RESCATE2_wordpress", "RESCATE3_shapes", "FORMAS_ROLLOUT",
        "RESIDUAL_ROLLOUT"])
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\RECRAWL_PLAN.jsonl")
    a = ap.parse_args()

    hoy = datetime.now()
    plan: dict[str, dict] = {}
    for nombre in a.rollouts:
        d = Path(a.raiz) / nombre
        rutas = corridas_de(d)
        if not rutas:
            continue
        por_fuente: dict[str, list[dict]] = {}
        for ruta in rutas:
            for r in leer(ruta):
                por_fuente.setdefault(r["canonical_agency_id"], []).append(r)

        for cid, filas in por_fuente.items():
            tasa, movidas, total = tasa_de_cambio(filas)
            estado = filas[-1].get("estado") or "UNKNOWN"
            dias, motivo = cadencia(tasa, estado, len(filas))
            visto = filas[-1].get("checked_at") or ""
            fila = {
                "canonical_agency_id": cid,
                "agency_name": filas[-1].get("agency_name"),
                "rollout": nombre,
                "connector": filas[-1].get("connector"),
                "ultima_lectura": visto,
                "corridas": len(filas),
                "propiedades": total,
                "se_movieron": movidas,
                "tasa_de_cambio": round(tasa, 4),
                "estado": estado,
                "cada_dias": dias,
                "motivo": motivo,
                "proxima": (hoy + timedelta(days=dias)).strftime("%Y-%m-%d"),
            }
            # Si una fuente aparece en dos rollouts, manda la que la vio mas
            # seguido: la cadencia protege contra quedarse corto, no largo.
            previo = plan.get(cid)
            if not previo or dias < previo["cada_dias"]:
                plan[cid] = fila

    salida = Path(a.salida)
    salida.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in sorted(plan.values(),
                                              key=lambda x: (x["cada_dias"],
                                                             x["canonical_agency_id"]))),
                      encoding="utf-8")

    print("### PLAN DE RELECTURA ###")
    print(f"  fuentes con historial: {len(plan):,}\n")
    c = Counter(f["cada_dias"] for f in plan.values())
    porc = sum(f["propiedades"] for f in plan.values())
    for dias in sorted(c):
        fuentes = [f for f in plan.values() if f["cada_dias"] == dias]
        props = sum(f["propiedades"] for f in fuentes)
        print(f"  cada {dias:2} dias  {len(fuentes):5} fuentes  {props:7,} propiedades"
              f"  ({props/porc*100 if porc else 0:5.1f}%)")

    # Lo que se ahorra: hoy se recorre todo cada vez.
    diario = sum(f["propiedades"] for f in plan.values())
    por_dia = sum(f["propiedades"] / f["cada_dias"] for f in plan.values())
    print(f"\n  recorrer todo cada dia:   {diario:8,.0f} fichas/dia")
    print(f"  con este plan:            {por_dia:8,.0f} fichas/dia"
          f"   ({(1 - por_dia / diario) * 100:.0f}% menos)" if diario else "")
    print(f"\n  la cadencia va de {MINIMO_DIAS} a {MAXIMO_DIAS} dias; "
          f"lo que no respondio vuelve al minimo")
    print(f"  generado {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(f"\n  artefacto -> {salida}")
    print("  este plan no corre nada: dice a quien volver y cuando")
    return 0


if __name__ == "__main__":
    sys.exit(main())

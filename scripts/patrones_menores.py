#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los defectos chicos que se repiten. Solo lee.

Un defecto de una ficha no detiene la cola, y esta bien. Pero cuatro agencias
distintas perdiendo el mismo campo por el mismo motivo no son cuatro
accidentes: son un patron, y el patron no puede desaparecer solo porque cada
pieza sea chica.

Esto agrupa los defectos que el triage dejo pasar por magnitud y cuenta cuantas
veces aparecio cada firma. No decide nada ni cambia el triage: pone el numero
donde se pueda ver, que es lo que faltaba.

La escala de atencion que propone, y que es una sugerencia y no una regla:

    1 vez     anotado y nada mas
    2 veces   mirar si comparten plataforma
    3 o mas   candidato firme para la ventana semantica
    6 o mas   probablemente valga mas que varios de los diferidos grandes
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

COLA = (r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
        r"\AGENCY_DEFECT_QUEUE.jsonl")
RESULTADOS = (r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
              r"\AGENCY_CERTIFICATION_RESULTS.jsonl")

COMPONENTE_MENOR = "extraccion_de_baja_magnitud"


def _ultimos(ruta: Path, clave: str = "canonical_agency_id") -> dict[str, dict]:
    fuera: dict[str, dict] = {}
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


def campos_fallidos(resultado: dict[str, Any]) -> dict[str, dict]:
    cobertura = resultado.get("field_coverage") or {}
    return {k: v for k, v in cobertura.items()
            if isinstance(v, dict) and v.get("state") == "EXTRACTION_FAILED"}


def plataforma(resultado: dict[str, Any]) -> str:
    """Con que familia se sirve el sitio, para ver si la firma es de ahi."""
    url = str(resultado.get("official_url") or "")
    for marca, nombre in (("kitepropcrm", "kiteprop"), ("/site/properties",
                                                        "kiteprop"),
                          ("tuinmobiliaria", "tuinmobiliaria")):
        if marca in url:
            return nombre
    return str(resultado.get("platform") or resultado.get("connector") or "?")


def agrupar(resultados: dict[str, dict]) -> dict[tuple[str, str], list[dict]]:
    """Agrupa por (campo, plataforma) los defectos chicos."""
    fuera: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for clave, resultado in resultados.items():
        for campo, dato in campos_fallidos(resultado).items():
            n = int(dato.get("extraction_failed") or 0)
            p = int(dato.get("source_provided") or 0)
            fuera[(campo, plataforma(resultado))].append(
                {"agencia": clave, "fallas": n, "provistos": p,
                 "pct": (n / p) if p else None})
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", default=RESULTADOS)
    ap.add_argument("--minimo", type=int, default=2,
                    help="cuantas repeticiones para mostrar la firma")
    args = ap.parse_args()

    resultados = _ultimos(Path(args.resultados))
    grupos = agrupar(resultados)
    repetidos = {k: v for k, v in grupos.items() if len(v) >= args.minimo}

    print(f"agencias con resultado: {len(resultados)}")
    print(f"firmas de campo distintas: {len(grupos)}")
    print(f"firmas repetidas {args.minimo}+ veces: {len(repetidos)}\n")

    for (campo, plat), casos in sorted(repetidos.items(),
                                       key=lambda x: -len(x[1])):
        total_fallas = sum(c["fallas"] for c in casos)
        total_prov = sum(c["provistos"] for c in casos)
        escala = ("candidato firme para la ventana" if len(casos) >= 3
                  else "mirar si comparten plataforma")
        print(f"{campo} / {plat}: {len(casos)} agencias, "
              f"{total_fallas} fichas de {total_prov}  -> {escala}")
        for c in sorted(casos, key=lambda x: -x["fallas"])[:6]:
            pct = f"{100*c['pct']:.1f} %" if c["pct"] is not None else "  -  "
            print(f"     {c['agencia'].split(':')[-1][:38]:40} "
                  f"{c['fallas']:4} de {c['provistos']:5}  {pct}")
        print()

    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

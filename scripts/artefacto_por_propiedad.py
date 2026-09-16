#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Qué sabemos de cada propiedad, fila por fila. §39, §40, §41.

No escribe en la base. `database_writes: 0`. **No toca el runtime**: lee los
paquetes que la certificación ya dejó en disco y produce un artefacto aparte.
No importa un solo módulo semántico, así que no puede cambiar una huella.

Por qué hace falta. Hoy la certificación resume por agencia: "precio falla en
1.206 de 1.213". Eso alcanza para decidir qué arreglar, pero no para dos cosas
que vienen después:

  - la Regression Gate V2 (§42), que tiene que comparar LEGACY contra FRESH
    contra PRODUCCIÓN **campo por campo y fila por fila**, no cobertura contra
    cobertura;
  - explicar de dónde salió cada valor que se publicaría (§41). Sin eso, un
    NULL en producción no se distingue de un NULL que la fuente nunca trajo.

El modelo de estado de campo (§40) es el corazón: un valor vacío no es una
sola cosa. Son cinco cosas distintas y cada una pide una decisión distinta:

    PROVIDED_EXTRACTED   la fuente lo trae y lo leímos
    PROVIDED_REJECTED    la fuente lo trae, lo leímos y una validación lo tiró
    EXTRACTION_FAILED    la fuente lo trae y NO lo leímos          <- defecto
    NOT_PROVIDED         la fuente no lo trae                       <- no es defecto
    NOT_ATTEMPTED        no se llegó a intentar

Confundir `EXTRACTION_FAILED` con `NOT_PROVIDED` fue exactamente el error que
infló el ranking en 1.133 fichas.

Uso:
    python scripts/artefacto_por_propiedad.py
    python scripts/artefacto_por_propiedad.py --agencia blanco
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_PROPIEDADES_CERTIFICADAS.jsonl"
RESUMEN = CERT / "ERETZ_PROPIEDADES_CERTIFICADAS_SUMMARY.json"

PROVIDED_EXTRACTED = "PROVIDED_EXTRACTED"
PROVIDED_REJECTED = "PROVIDED_REJECTED"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
NOT_PROVIDED = "NOT_PROVIDED"
NOT_ATTEMPTED = "NOT_ATTEMPTED"

CAMPOS = ("titulo", "descripcion", "precio", "moneda", "operacion",
          "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
          "ambientes", "dormitorios", "banos", "superficie_total",
          "superficie_cubierta", "latitud", "longitud")


def estado_del_campo(valor, campo: str, cobertura: dict,
                     url: str, fallidas: set[str]) -> str:
    """El estado de UN campo en UNA propiedad.

    `field_coverage` es por agencia, así que dice cuántas fallaron pero no
    cuáles. Lo único que identifica a una ficha concreta son los
    `failure_examples`, y por eso `EXTRACTION_FAILED` sólo se afirma cuando la
    url está ahí. Para el resto se usa el estado declarado de la agencia, que
    es una aproximación —y se dice que lo es— en vez de inventar precisión.
    """
    d = cobertura.get(campo) or {}
    if valor not in (None, "", [], {}):
        return PROVIDED_EXTRACTED
    if url in fallidas:
        return EXTRACTION_FAILED
    estado = d.get("state")
    if estado == "SOURCE_NOT_PROVIDED":
        return NOT_PROVIDED
    if estado == "REJECTED_BY_VALIDATION":
        return PROVIDED_REJECTED
    if estado == "EXTRACTION_FAILED":
        # La agencia tiene fallas en este campo pero ESTA ficha no figura entre
        # los ejemplos. No se puede afirmar cuál de las dos cosas es.
        return NOT_ATTEMPTED
    if not estado:
        return NOT_ATTEMPTED
    return NOT_PROVIDED


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agencia")
    args = ap.parse_args()

    ult = {}
    for l in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r

    filas = 0
    por_estado: Counter = Counter()
    por_campo: dict[str, Counter] = {c: Counter() for c in CAMPOS}
    agencias = 0
    sin_paquete = 0

    with SALIDA.open("w", encoding="utf-8") as fh:
        for d in sorted((CERT / "agencies").iterdir()):
            cert = d / "certification.json"
            props = d / "properties_run1.jsonl"
            if not cert.exists():
                continue
            try:
                j = json.loads(cert.read_text(encoding="utf-8"))
            except ValueError:
                continue
            a = j.get("canonical_agency_id") or ""
            if args.agencia and args.agencia not in a:
                continue
            if not props.exists():
                sin_paquete += 1
                continue
            r = ult.get(a) or {}
            cobertura = r.get("field_coverage") or {}
            # Las urls que el certificador nombro como fallidas, por campo.
            fallidas: dict[str, set[str]] = {
                c: set((cobertura.get(c) or {}).get("failure_examples") or [])
                for c in CAMPOS}
            agencias += 1

            for linea in props.read_text(encoding="utf-8",
                                         errors="replace").splitlines():
                if not linea.strip():
                    continue
                try:
                    p = json.loads(linea)
                except ValueError:
                    continue
                url = p.get("source_url") or ""
                campos = {}
                for c in CAMPOS:
                    e = estado_del_campo(p.get(c), c, cobertura, url,
                                         fallidas.get(c, set()))
                    campos[c] = {"valor": p.get(c), "estado": e,
                                 "origen": "FRESH_CERTIFICATION"
                                           if e == PROVIDED_EXTRACTED else None}
                    por_estado[e] += 1
                    por_campo[c][e] += 1
                fh.write(json.dumps({
                    "run_id": r.get("checked_at"),
                    "agency_id": a,
                    "source_url": url,
                    "source_listing_id": p.get("source_listing_id"),
                    "connector": r.get("connector"),
                    "strategy": r.get("connector_strategy"),
                    "strategy_fingerprint": r.get("strategy_fingerprint"),
                    "agency_status": r.get("status"),
                    "campos": campos,
                    "imagenes": len(p.get("imagenes") or []),
                    "fingerprint": p.get("fingerprint"),
                    "scraped_at": p.get("scraped_at"),
                }, ensure_ascii=False) + "\n")
                filas += 1

    total = sum(por_estado.values())
    resumen = {
        "propiedades": filas, "agencias": agencias,
        "agencias_sin_paquete": sin_paquete,
        "campos_por_propiedad": len(CAMPOS),
        "por_estado": dict(por_estado),
    }
    RESUMEN.write_text(json.dumps(resumen, ensure_ascii=False, indent=1),
                       encoding="utf-8")

    print(f"propiedades con artefacto: {filas:,}")
    print(f"agencias con paquete:      {agencias}")
    print(f"agencias SIN paquete:      {sin_paquete}   "
          f"(certificadas antes de que se guardaran, o sin propiedades)\n")
    print(f"{'estado del campo':22} {'n':>9}  {'%':>6}")
    for k, n in por_estado.most_common():
        print(f"{k:22} {n:9,}  {n/max(total,1):6.1%}")

    print(f"\n{'campo':20} {'extraido':>9} {'rechazado':>10} "
          f"{'fallo':>8} {'no provisto':>12}")
    for c in CAMPOS:
        p = por_campo[c]
        print(f"{c:20} {p[PROVIDED_EXTRACTED]:9,} {p[PROVIDED_REJECTED]:10,} "
              f"{p[EXTRACTION_FAILED]:8,} {p[NOT_PROVIDED]:12,}")

    print(f"\nartefacto: {SALIDA}")
    print("\n  LIMITE CONOCIDO: `field_coverage` es por AGENCIA, asi que dice")
    print("  cuantas fichas fallaron pero no cuales. `EXTRACTION_FAILED` solo")
    print("  se afirma cuando la url figura en `failure_examples`; el resto")
    print("  queda NOT_ATTEMPTED en vez de inventar precision que no hay.")
    print("  Para cerrar ese hueco hace falta que la certificacion anote el")
    print("  estado por ficha, y eso toca codigo semantico: va a la ventana.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

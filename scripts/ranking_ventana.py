#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dos rankings separados: lo que falta y lo que está incompleto.

No escribe nada. `database_writes: 0`.

El §8 pide no mezclarlos, y la razón se ve en un ejemplo del propio proyecto:

    extraccion_transversal_de_atributos   15 agencias, 1.708 propiedades
    variante_no_soportada                 20 agencias,    54 propiedades

Por volumen de propiedades afectadas gana la primera por treinta veces. Pero
las 1.708 **ya están en ERETZ** y les falta un campo secundario, mientras que
detrás de las 54 hay **479 propiedades que no tenemos** —y sólo `bottai` aporta
333—.

Arreglar lo segundo trae propiedades nuevas al catálogo. Arreglar lo primero
mejora fichas que ya están. Los dos valen, pero no compiten por el mismo lugar.

    INVENTORY_RISK_SCORE   propiedades que existen y NO tenemos
    FIELD_QUALITY_SCORE    propiedades que tenemos con un campo faltante

Uso:
    python scripts/ranking_ventana.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

# Firmas que significan "faltan propiedades enteras".
DE_INVENTARIO = {
    "catalogo_declarado_mayor_que_el_enumerado",
    "posible_perdida_de_inventario",
    "perdida_sistematica_de_inventario",
    "inventario_inestable_entre_corridas",
    "variante_no_soportada",
    "enumeracion_compartida",
}
# Firmas que significan "la propiedad esta, le falta un campo".
DE_CAMPO = {
    "extraccion_transversal_de_atributos",
    "imagenes_compartidas",
    "extraccion_de_baja_magnitud",
}
# Riesgo de COMPLETE falso: que el defecto pase desapercibido y se publique.
RIESGO_FALSO_COMPLETE = {
    "catalogo_declarado_mayor_que_el_enumerado": 3,
    "inventario_inestable_entre_corridas": 3,
    "perdida_sistematica_de_inventario": 2,
    "posible_perdida_de_inventario": 2,
    "variante_no_soportada": 1,   # cierra NEEDS_FIX: no se publica sin verse
    "enumeracion_compartida": 2,
}
# Peso del campo para el producto: sin estos, la ficha no se puede filtrar.
PESO_DE_CAMPO = {
    "precio": 3, "moneda": 3, "operacion": 3, "tipo_propiedad": 3,
    "ciudad": 3, "provincia": 3, "ambientes": 2, "dormitorios": 2,
    "banos": 2, "superficie_total": 2, "superficie_cubierta": 1,
    "barrio": 2, "latitud": 1, "longitud": 1, "direccion": 1,
    "titulo": 2, "descripcion": 1, "imagenes": 2,
}


def cargar() -> tuple[list[dict], dict[str, dict]]:
    dif = [json.loads(l) for l in
           (CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl").read_text(
               encoding="utf-8", errors="replace").splitlines() if l.strip()]
    ult: dict[str, dict] = {}
    for linea in (CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("canonical_agency_id"):
            ult[r["canonical_agency_id"]] = r
    return dif, ult


def main() -> int:
    dif, ult = cargar()

    inv: dict[str, dict] = defaultdict(
        lambda: {"agencias": set(), "recuperables": 0, "riesgo": 0})
    campos: dict[str, dict] = defaultdict(
        lambda: {"agencias": set(), "afectadas": 0, "peso": 0})

    for f in dif:
        firma = f.get("componente") or "(sin firma)"
        agencia = f["canonical_agency_id"]
        r = ult.get(agencia) or {}
        enumeradas = (r.get("enumeration_audit") or {}).get("enumerated") or 0

        if firma in DE_INVENTARIO:
            # Lo recuperable es lo que existe y no tenemos. Si la diferida lo
            # midio contra la fuente, se usa ese numero; si no, se usa 0 y se
            # dice, en vez de inventar una estimacion.
            real = f.get("inventario_real") or 0
            visto = f.get("inventario_que_vemos")
            visto = enumeradas if visto is None else visto
            inv[firma]["agencias"].add(agencia)
            inv[firma]["recuperables"] += max(0, real - visto)
            inv[firma]["riesgo"] = max(inv[firma]["riesgo"],
                                       RIESGO_FALSO_COMPLETE.get(firma, 1))
        elif firma in DE_CAMPO:
            campos[firma]["agencias"].add(agencia)
            campos[firma]["afectadas"] += enumeradas
            cob = r.get("field_coverage") or {}
            peor = 0
            for campo, d in cob.items():
                if (d or {}).get("extraction_failed"):
                    peor = max(peor, PESO_DE_CAMPO.get(campo, 1))
            campos[firma]["peso"] = max(campos[firma]["peso"], peor)

    print("=" * 66)
    print("P0/P1 — INVENTORY_RISK: propiedades que existen y NO tenemos")
    print("=" * 66)
    print(f"{'firma':42} {'agen':>5} {'recup':>7} {'riesgo':>7} {'score':>9}")
    filas = []
    for firma, d in inv.items():
        n = len(d["agencias"])
        score = d["recuperables"] * d["riesgo"] + n * d["riesgo"]
        filas.append((score, firma, n, d["recuperables"], d["riesgo"]))
    for score, firma, n, rec, riesgo in sorted(filas, reverse=True):
        print(f"{firma[:40]:42} {n:5} {rec:7,} {riesgo:7} {score:9,}")
    total_rec = sum(d["recuperables"] for d in inv.values())
    print(f"\n  propiedades recuperables medidas: {total_rec:,}")
    print("  (solo las que una diferida midio contra la fuente; el resto no se")
    print("   estima, se deja en cero y se dice)")

    print("\n" + "=" * 66)
    print("P2 — FIELD_QUALITY: propiedades que tenemos, con un campo faltante")
    print("=" * 66)
    print(f"{'firma':42} {'agen':>5} {'afect':>7} {'peso':>6} {'score':>9}")
    filas2 = []
    for firma, d in campos.items():
        n = len(d["agencias"])
        score = d["afectadas"] * d["peso"]
        filas2.append((score, firma, n, d["afectadas"], d["peso"]))
    for score, firma, n, af, peso in sorted(filas2, reverse=True):
        print(f"{firma[:40]:42} {n:5} {af:7,} {peso:6} {score:9,}")

    print("\n" + "=" * 66)
    print("LECTURA")
    print("=" * 66)
    print("  Los dos rankings no compiten: el primero trae propiedades NUEVAS")
    print("  al catalogo, el segundo mejora fichas que ya estan. El §7 pide")
    print("  resolver inventario primero, y el orden de arriba es ese.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

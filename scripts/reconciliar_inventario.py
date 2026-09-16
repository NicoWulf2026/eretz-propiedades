#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""De dónde sale cada propiedad faltante, una por una. §1 y §2.

No escribe en la base. `database_writes: 0`.

El total de `INVENTORY_RECOVERY` se venía usando como cifra maestra sin poder
abrirlo. Esto lo abre: cada fila es una agencia, con lo que enumeramos, lo que
la diferida midió contra la fuente, la diferencia, la evidencia que la sostiene
y cuánta confianza merece.

`SUM(MISSING)` de esta tabla tiene que dar exactamente el total del ranking. Si
no da, el que está mal es el ranking.

La confianza NO se infiere del tamaño del número. Sale de qué tan verificable
es la evidencia escrita en la diferida:

    ALTA    la diferida trae `inventario_real` y dice contra qué se midió
    MEDIA   trae el número pero la evidencia no dice cómo se obtuvo
    BAJA    el número sale de `declared_total` de la propia fuente, que ya
            demostró equivocarse -`civile` declaraba 3.250 y era la altura de
            una calle, "Aizpurua 3250"-

Uso:
    python scripts/reconciliar_inventario.py
    python scripts/reconciliar_inventario.py --firma variante_no_soportada
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

DE_INVENTARIO = {
    "variante_no_soportada",
    "inventario_inestable_entre_corridas",
    "posible_perdida_de_inventario",
    "perdida_sistematica_de_inventario",
    "catalogo_declarado_mayor_que_el_enumerado",
    "enumeracion_compartida",
}


def cargar():
    dif = []
    for l in (CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if l.strip():
            try:
                dif.append(json.loads(l))
            except ValueError:
                continue
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
    return dif, ult


def confianza(f: dict, r: dict) -> tuple[str, str]:
    """Cuánto vale el `EXPECTED_REAL` de esta fila, y por qué."""
    if not f.get("inventario_real"):
        return "N/A", "la diferida no midio un total, asi que no aporta faltantes"
    diag = (f.get("diagnostico") or "").lower()
    # Que la diferida diga contra QUE se midio es lo que separa ALTA de MEDIA.
    mide_contra_fuente = any(p in diag for p in (
        "verificado", "se descargo", "descargada", "contado", "se conto",
        "la fuente publica", "en el sitio", "el sitio publica"))
    solo_declarado = "declared_total" in diag or "declara" in diag
    ea = r.get("enumeration_audit") or {}
    if solo_declarado and not mide_contra_fuente:
        return "BAJA", ("el total sale de lo que declara la propia fuente, que "
                        "ya se equivoco antes")
    if mide_contra_fuente:
        return "ALTA", "la diferida dice contra que se midio"
    if ea.get("declared_total"):
        return "MEDIA", ("hay numero pero la evidencia no dice como se "
                         "obtuvo; coincide con declared_total")
    return "MEDIA", "hay numero pero la evidencia no dice como se obtuvo"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--firma")
    ap.add_argument("--detalle", action="store_true")
    args = ap.parse_args()

    dif, ult = cargar()
    filas = []
    for f in dif:
        firma = f.get("componente") or "(sin firma)"
        if firma not in DE_INVENTARIO:
            continue
        if args.firma and firma != args.firma:
            continue
        agencia = f["canonical_agency_id"]
        r = ult.get(agencia) or {}
        ea = r.get("enumeration_audit") or {}
        enumeradas = ea.get("enumerated") or 0
        real = f.get("inventario_real") or 0
        visto = f.get("inventario_que_vemos")
        visto = enumeradas if visto is None else visto
        faltan = max(0, real - visto)
        conf, porque = confianza(f, r)
        filas.append({
            "SIGNATURE": firma,
            "AGENCY": agencia,
            "ENUMERATED": enumeradas,
            "VISTO_SEGUN_LA_DIFERIDA": visto,
            "EXPECTED_REAL": real,
            "MISSING": faltan,
            "EVIDENCE": (f.get("diagnostico") or "")[:150],
            "CONFIDENCE": conf,
            "POR_QUE_ESA_CONFIANZA": porque,
            "STATUS_ACTUAL": r.get("status"),
            "ESTRATEGIA": r.get("connector_strategy"),
        })

    print(f"{'firma':38} {'agencia':26} {'enum':>6} {'esper':>6} {'falta':>6} conf")
    for x in sorted(filas, key=lambda x: (-x["MISSING"], x["SIGNATURE"])):
        print(f"{x['SIGNATURE'][:36]:38} {x['AGENCY'].split(':')[-1][:24]:26} "
              f"{x['ENUMERATED']:6} {x['EXPECTED_REAL']:6} {x['MISSING']:6} "
              f"{x['CONFIDENCE']}")

    print("\n" + "=" * 70)
    print("POR FIRMA")
    print("=" * 70)
    por = defaultdict(lambda: {"n": 0, "falta": 0, "conf": Counter()})
    for x in filas:
        p = por[x["SIGNATURE"]]
        p["n"] += 1
        p["falta"] += x["MISSING"]
        p["conf"][x["CONFIDENCE"]] += 1
    total = 0
    for firma, p in sorted(por.items(), key=lambda kv: -kv[1]["falta"]):
        total += p["falta"]
        print(f"{firma[:44]:46} {p['n']:3} agencias {p['falta']:6,} faltantes  "
              f"{dict(p['conf'])}")
    print(f"\n{'SUM(MISSING)':46} {'':14} {total:6,}")

    print("\nla misma suma, por confianza:")
    porc = Counter()
    for x in filas:
        porc[x["CONFIDENCE"]] += x["MISSING"]
    for c in ("ALTA", "MEDIA", "BAJA", "N/A"):
        if porc.get(c) is not None:
            print(f"   {c:6} {porc.get(c, 0):6,}")
    print("\n   Sumar ALTA + MEDIA + BAJA en un solo numero y llamarlo")
    print("   'propiedades recuperables' es lo que hay que dejar de hacer: una")
    print("   cifra BAJA sale del total que declara la propia fuente, y eso ya")
    print("   se equivoco antes.")

    salida = CERT / "ERETZ_INVENTARIO_RECONCILIADO.jsonl"
    salida.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n"
                              for x in filas), encoding="utf-8")
    print(f"\nartefacto: {salida}")
    if args.detalle:
        print("\nEVIDENCIA, fila por fila:")
        for x in sorted(filas, key=lambda x: -x["MISSING"]):
            if x["MISSING"]:
                print(f"\n   {x['AGENCY'].split(':')[-1]}  ({x['MISSING']} faltantes, "
                      f"{x['CONFIDENCE']})")
                print(f"      {x['EVIDENCE']}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Buscar web sólo donde buscar sirve, y medir lo que cuesta.

Sin `BRAVE_SEARCH_API_KEY` no gasta nada y no falla: informa
`WAITING_USER_ACTION_BRAVE_KEY` y sale. Las entidades quedan en
`SEARCH_API_PENDING`, que es un estado operativo — nunca `NOT_FOUND`, que
sería afirmar algo sobre la inmobiliaria en vez de sobre nuestras herramientas.

### Por qué el canario es la población entera

El §31 pide una muestra representativa antes del lote completo. Acá no hace
falta: **la población es de 112**. Medido el 2026-09-14 sobre las 6.597 del
universo, las que una búsqueda nueva destraba hoy son exactamente las que
cumplen las tres cosas a la vez:

    tienen FK de `main` resuelta      -> certificarlas es posible
    les falta la web                  -> es lo único que las frena
    no tienen candidatas sin verificar -> no hay nada gratis que cobrar primero

Las otras 3.845 sin web no las destraba Brave: 3.625 están esperando la
promoción de staging a main, y para 108 ya hay candidatas pagas esperando que
alguien las abra, que sale gratis y va primero.

Buscar para las 3.625 antes de la promoción sería pagar por un dato que no se
puede usar todavía.

Uso:
    python scripts/canario_brave.py --dry-run     # no gasta, muestra el plan
    python scripts/canario_brave.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import search_provider as sp  # noqa: E402

CERT_DIR = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
UNIVERSO = CERT_DIR / "ERETZ_UNIVERSO.jsonl"
SALIDA = DATOS / "BRAVE_CANARIO.jsonl"
CACHE = DATOS / "search_cache.jsonl"

# Lo que Brave cobra por mil consultas en el plan Base, para el reporte de
# costo del §32. Si cambia, cambia acá y no en cinco lugares.
USD_POR_MIL = 5.0
# Techo por agencia. El §14 lo pide explicito: sin techo, una sola inmobiliaria
# dificil se come el presupuesto de cien faciles.
CONSULTAS_MAXIMAS = 3


def objetivo() -> list[dict]:
    """Las que una busqueda nueva destraba HOY."""
    if not UNIVERSO.exists():
        raise SystemExit("falta ERETZ_UNIVERSO.jsonl: corre universo_tabla.py")
    verificadas = set()
    ruta = DATOS / "AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            if linea.strip():
                try:
                    verificadas.add(json.loads(linea)["canonical_agency_id"])
                except (ValueError, KeyError):
                    pass
    fuera = []
    for linea in UNIVERSO.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("blocker") != "FALTA_WEB":
            continue
        # Si ya tiene candidatas esperando verificacion, esa via es gratis y va
        # primero: no se paga una consulta por algo que ya se pago.
        if fila["agency_id"] in verificadas:
            continue
        fuera.append(fila)
    return fuera


def consultas_de(fila: dict) -> list[str]:
    """Escalonadas, de la mas distintiva a la mas generica. Se corta apenas hay
    candidata fuerte, asi que la tercera casi nunca se gasta."""
    nombre = (fila.get("nombre") or "").strip()
    ciudad = (fila.get("ciudad") or "").strip()
    provincia = (fila.get("provincia") or "").strip()
    fuera = []
    if nombre and ciudad:
        fuera.append(f'"{nombre}" "{ciudad}" inmobiliaria')
    if nombre and provincia and provincia != ciudad:
        fuera.append(f'"{nombre}" "{provincia}" inmobiliaria')
    if nombre:
        fuera.append(f'"{nombre}" inmobiliaria argentina')
    return fuera[:CONSULTAS_MAXIMAS]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    agencias = objetivo()
    if args.limite:
        agencias = agencias[:args.limite]

    buscador = sp.ConCache(sp.Brave(), CACHE)
    hay_key = buscador.disponible()

    print("### CANARIO BRAVE ###")
    print(f"  agencias objetivo:       {len(agencias):,}")
    print(f"  consultas maximas c/u:   {CONSULTAS_MAXIMAS}")
    print(f"  techo de consultas:      {len(agencias) * CONSULTAS_MAXIMAS:,}")
    print(f"  costo techo estimado:    "
          f"USD {len(agencias) * CONSULTAS_MAXIMAS / 1000 * USD_POR_MIL:.2f}")
    print(f"  API key:                 "
          f"{'presente' if hay_key else 'AUSENTE'}")

    if not hay_key:
        print("\nWAITING_USER_ACTION_BRAVE_KEY")
        print("  1. brave.com/search/api")
        print("  2. plan Free (2.000/mes) alcanza para este canario")
        print(f"  3. variable: {sp.Brave.ENV}")
        print("  4. test: python -c \"import sys;sys.path.insert(0,'scripts');"
              "import search_provider as sp;print(sp.Brave().disponible())\"")
        print("  5. despues: python scripts/canario_brave.py")
        print("\n  las agencias quedan en SEARCH_API_PENDING, no en NOT_FOUND")
        print("database_writes: 0")
        return 0

    if args.dry_run:
        print("\nplan (dry-run, no se gasta nada):")
        for fila in agencias[:10]:
            print(f"   {fila['nombre'][:34]:36} {consultas_de(fila)[:1]}")
        print(f"\n   ... y {max(0, len(agencias) - 10)} mas")
        print("database_writes: 0")
        return 0

    gastadas = 0
    estados: Counter = Counter()
    empezo = time.time()
    with SALIDA.open("a", encoding="utf-8") as fh:
        for i, fila in enumerate(agencias, 1):
            candidatas, usadas = [], 0
            for consulta in consultas_de(fila):
                try:
                    resultados = buscador.buscar(consulta)
                except sp.ConsultaInvalida:
                    continue
                except sp.ProveedorAgotado:
                    print("  proveedor agotado: se corta el lote")
                    fila = None
                    break
                usadas += 1
                gastadas += 1
                candidatas.extend(resultados)
                # Corte temprano: con una candidata que no sea portal alcanza
                # para pasar a verificacion, y la segunda consulta ya no aporta.
                if any(r.url for r in resultados):
                    break
            if fila is None:
                break
            estados["con candidata" if candidatas else "sin resultado"] += 1
            fh.write(json.dumps({
                "canonical_agency_id": fila["agency_id"],
                "nombre": fila["nombre"],
                "consultas_usadas": usadas,
                "candidatas": [{"url": r.url, "titulo": r.titulo,
                                "rank": r.rank, "provider": r.provider}
                               for r in candidatas[:6]],
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 20 == 0:
                print(f"  {i}/{len(agencias)}  consultas {gastadas}", flush=True)

    con = estados["con candidata"]
    print("\nREPORTE DE COSTO")
    print(f"   agencias procesadas:      {sum(estados.values()):,}")
    print(f"   consultas gastadas:       {gastadas:,}")
    print(f"   con candidata:            {con:,}")
    print(f"   sin resultado:            {estados['sin resultado']:,}")
    if con:
        print(f"   consultas / con candidata: {gastadas / con:.2f}")
        print(f"   USD / con candidata:       "
              f"{gastadas / con / 1000 * USD_POR_MIL:.4f}")
    print(f"   costo total:              "
          f"USD {gastadas / 1000 * USD_POR_MIL:.2f}")
    print(f"   duracion:                 {(time.time() - empezo) / 60:.1f} min")
    print(f"\n   artefacto: {SALIDA}")
    print("   OJO: una candidata NO es una web oficial. El paso siguiente es")
    print("   verificar_candidatas_web.py, que abre la pagina y decide.")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

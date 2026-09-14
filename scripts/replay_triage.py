#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Corre la politica de triage sobre el historial real. No escribe nada.

Un umbral elegido a ojo es una opinion. Este script lo convierte en una
medicion: toma los resultados de certificacion ya guardados, los vuelve a
clasificar con la politica que tenga el codigo hoy, y muestra cuales paran,
cuales no, y con que magnitud.

Con `--comparar` corre ademas la politica SIN la regla de baja magnitud
-desactivandola por variable de entorno- y muestra el diff: que paradas se
evitarian y cuales se conservarian.

Lo que hay que mirar no es cuantas paradas se ahorran. Es si alguna de las que
se ahorran era una que habia que hacer.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.defect_triage import STOP, clasificar  # noqa: E402

RESULTADOS = (r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
              r"\AGENCY_CERTIFICATION_RESULTS.jsonl")

# Las que el mandato exige que sigan parando, pase lo que pase.
DEBEN_PARAR = {
    "roomix:blanco propiedades": "99,7 % de los precios perdidos",
    "roomix:carames bienes raices lanus este": "estrategia distinta por corrida",
    "roomix:diego malizia estudio inmobiliario": "paginacion que se declara completa",
    # `baron inmobiliaria` estuvo aca por "192 propiedades invisibles" y se
    # retira el 2026-09-14: su resultado guardado ya no tiene ese defecto.
    # Hoy enumera 182, declara 182, independent_gap 0 y las dos corridas
    # ven el mismo conjunto. El control vigilaba un fixture que cambio.
    #
    # La garantia no se pierde, se muda: vive en
    # test_un_catalogo_corto_para_aunque_no_falle_ningun_campo, donde el
    # fixture es sintetico y no puede envejecer.
    "roomix:civile propiedades": "colapso aparente de inventario",
    "roomix:carlos castano propiedades": "enumeracion contaminada / sitio en obra",
}
# Las que el mandato quiere dejar de parar por magnitud minima.
DEBERIAN_SEGUIR = {
    "roomix:conti propiedades": "1 de 275",
    "roomix:civeira bienes raices": "1 de 163",
    "roomix:cocucci inmobiliaria": "1 de 153",
    "roomix:christian arce propiedades": "1 de 77 en ambientes",
}


def ultimos(ruta: Path) -> dict[str, dict]:
    fuera: dict[str, dict] = {}
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
        except ValueError:
            continue
        if f.get("canonical_agency_id"):
            fuera[f["canonical_agency_id"]] = f
    return fuera


def magnitud(resultado: dict) -> tuple[int, int, float]:
    """(fichas fallidas, fichas que la fuente provee, peor porcentaje)."""
    cobertura = resultado.get("field_coverage") or {}
    peor = 0.0
    fallas = provistos = 0
    for dato in cobertura.values():
        if not isinstance(dato, dict) or not dato.get("extraction_failed"):
            continue
        n = int(dato["extraction_failed"])
        p = int(dato.get("source_provided") or 0)
        fallas += n
        provistos += p
        if p:
            peor = max(peor, n / p)
    return fallas, provistos, peor


def clasificar_con(resultado: dict, baja_magnitud: bool) -> dict:
    anterior = os.environ.get("ERETZ_TRIAGE_SIN_BAJA_MAGNITUD")
    if baja_magnitud:
        os.environ.pop("ERETZ_TRIAGE_SIN_BAJA_MAGNITUD", None)
    else:
        os.environ["ERETZ_TRIAGE_SIN_BAJA_MAGNITUD"] = "1"
    try:
        return clasificar(resultado)
    finally:
        os.environ.pop("ERETZ_TRIAGE_SIN_BAJA_MAGNITUD", None)
        if anterior is not None:
            os.environ["ERETZ_TRIAGE_SIN_BAJA_MAGNITUD"] = anterior


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", default=RESULTADOS)
    ap.add_argument("--comparar", action="store_true",
                    help="corre las dos politicas y muestra el diff")
    args = ap.parse_args()

    datos = ultimos(Path(args.resultados))
    print(f"agencias con resultado: {len(datos)}")

    nueva: dict[str, dict] = {}
    vieja: dict[str, dict] = {}
    for clave, resultado in datos.items():
        nueva[clave] = clasificar_con(resultado, True)
        if args.comparar:
            vieja[clave] = clasificar_con(resultado, False)

    c_nueva = Counter(v["decision"] for v in nueva.values())
    print(f"\npolitica ACTUAL del codigo: {dict(c_nueva)}")
    if args.comparar:
        c_vieja = Counter(v["decision"] for v in vieja.values())
        print(f"politica SIN baja magnitud: {dict(c_vieja)}")

        evitadas = [k for k in datos
                    if vieja[k]["decision"] == STOP
                    and nueva[k]["decision"] != STOP]
        nuevas = [k for k in datos
                  if vieja[k]["decision"] != STOP
                  and nueva[k]["decision"] == STOP]
        print(f"\nparadas EVITADAS: {len(evitadas)}")
        for k in sorted(evitadas):
            f, p, pct = magnitud(datos[k])
            print(f"   {k[:44]:46} {f:4} de {p:5} ({100*pct:5.1f} %) "
                  f"-> {nueva[k]['componente_sospechoso'][:30]}")
        if nuevas:
            print(f"\nparadas NUEVAS (no deberia haber): {len(nuevas)}")
            for k in sorted(nuevas):
                print(f"   {k}")

    print("\n--- control: las que DEBEN seguir parando ---")
    fallos = 0
    for clave, por_que in sorted(DEBEN_PARAR.items()):
        if clave not in nueva:
            print(f"   [sin datos] {clave[:44]}")
            continue
        d = nueva[clave]["decision"]
        ok = d == STOP
        fallos += 0 if ok else 1
        print(f"   [{'OK ' if ok else 'FALLA'}] {clave[:42]:44} {d:9} "
              f"({por_que})")

    print("\n--- las que el mandato quiere dejar pasar ---")
    for clave, por_que in sorted(DEBERIAN_SEGUIR.items()):
        if clave not in nueva:
            print(f"   [sin datos] {clave[:44]}")
            continue
        d = nueva[clave]["decision"]
        f, p, pct = magnitud(datos[clave])
        marca = "pasa " if d != STOP else "PARA "
        print(f"   [{marca}] {clave[:42]:44} {d:9} "
              f"{f} de {p} ({100*pct:.1f} %)  ({por_que})")

    print(f"\n{'VEREDICTO: ningun STOP critico se perdio' if not fallos else f'VEREDICTO: {fallos} STOP critico(s) PERDIDO(S)'}")
    print("database_writes: 0")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Reconstruir el checkpoint de un rollout desde sus propiedades ya extraidas.

Por que hace falta
------------------
La corrida 2 de Tokko arranco 08-23 04:01 y el fix del formato de checkpoint
entro 08-23 07:44. Corrio sin el. Su checkpoint quedo mezclado: las claves de
la corrida 1 son `source_listing_id` numerico y las de la corrida 2 son
`hash_dedup` hexadecimal, y ninguna fuente tiene el campo `esquema`. Comparar
un hash contra un id numerico no coincide nunca, asi que la corrida informo
91.715 NUEVA y 91.367 ausentes sin que hubiera pasado ninguna de las dos cosas.

Que NO se hace
--------------
No se traducen las claves viejas. Un `source_listing_id` no permite recuperar
la url, y sin url no hay hash: cualquier conversion seria una adivinanza que
despues nadie podria auditar.

Que si se hace
--------------
El baseline se construye desde `properties_run<N>.jsonl`, que es la salida de
la propia corrida y ya trae `hash_dedup` y `fingerprint` calculados con el
esquema de identidad vigente. No hay aproximacion: son exactamente los valores
que el checkpoint deberia tener.

Antes de escribir nada se verifica una muestra recalculando el hash desde
`inmobiliaria_id` + `source_url` con la MISMA funcion del pipeline. Si un solo
caso no coincide, no se escribe.

Dry run por defecto. El checkpoint anterior se conserva.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import random
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import (ESQUEMA_CHECKPOINT, HUELLA_VERSION,  # noqa: E402
                             REUSA_PIPELINE, PropiedadNormalizada,
                             calcular_hash_dedup)

# Campos que la propiedad normalizada tiene como tales. El artefacto trae
# ademas hash_dedup, fingerprint, problemas y las marcas de la corrida.
CAMPOS = {f.name for f in dataclasses.fields(PropiedadNormalizada)}


def fingerprint_actual(p: dict) -> str | None:
    """Recalcula la huella con el codigo de HOY, no la que quedo guardada.

    Hace falta cuando la definicion de huella cambia: si se copiara la vieja,
    la corrida siguiente marcaria MODIFICADA todo el inventario por un cambio
    de formula, no por un cambio real.
    """
    try:
        return PropiedadNormalizada(
            **{k: v for k, v in p.items() if k in CAMPOS}).fingerprint
    except TypeError:
        return None

RE_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def formato_clave(k: str) -> str:
    if RE_HEX32.match(k):
        return "hash_dedup"
    if k.isdigit():
        return "source_listing_id"
    return "otro"


def auditar(ruta: Path) -> dict:
    """Que hay hoy en el checkpoint, sin tocarlo."""
    if not ruta.exists():
        return {"existe": False}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    fuentes = datos.get("fuentes") or {}
    esquemas, lineas, claves = Counter(), Counter(), Counter()
    mixtas = 0
    for est in fuentes.values():
        esquemas[est.get("esquema")] += 1
        lineas[est.get("linea_base")] += 1
        formatos = {formato_clave(k) for k in (est.get("vistos") or {})}
        for f in formatos:
            claves[f] += 1
        if len(formatos) > 1:
            mixtas += 1
    return {
        "existe": True, "fuentes": len(fuentes),
        "esquema": dict(esquemas), "linea_base": dict(lineas),
        "formatos_de_clave": dict(claves),
        "fuentes_con_claves_mezcladas": mixtas,
        "vistos_totales": sum(len(e.get("vistos") or {}) for e in fuentes.values()),
    }


def leer_propiedades(ruta: Path):
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def verificar_identidad(muestra: list[dict]) -> tuple[bool, list[dict]]:
    """El hash guardado tiene que salir de recalcularlo con el codigo de hoy."""
    fallos = []
    for p in muestra:
        esperado = calcular_hash_dedup(p.get("inmobiliaria_id"), p.get("source_url"))
        if esperado != p.get("hash_dedup"):
            fallos.append({"source_url": p.get("source_url"),
                           "guardado": p.get("hash_dedup"), "recalculado": esperado})
    return not fallos, fallos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollout", required=True,
                    help="carpeta del rollout, ej. 'D:/INMO CAPITAL/TOKKO_ROLLOUT_FULL'")
    ap.add_argument("--corrida", default="2",
                    help="de que properties_run<N>.jsonl se toma el baseline")
    ap.add_argument("--muestra", type=int, default=500)
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo audita e informa; no escribe el checkpoint")
    a = ap.parse_args()

    base = Path(a.rollout)
    ckpt = base / "checkpoint.json"
    props = base / f"properties_run{a.corrida}.jsonl"
    # Si las guardas de coherencia corrigieron algo, el baseline tiene que
    # salir del archivo corregido. Desde el original, la corrida siguiente lee
    # nuestra propia correccion como un cambio que hizo la inmobiliaria: una
    # superficie que arreglamos nosotros vuelve como MODIFICADA y contamina la
    # medicion de idempotencia, que es exactamente lo que se estaba midiendo.
    corregido = props.with_name(props.name.replace(".jsonl", ".coherente.jsonl"))
    if corregido.exists():
        props = corregido

    print("### RECONSTRUCCION DEL BASELINE ###")
    print(f"  rollout:  {base}")
    print(f"  origen:   {props.name}")
    print(f"  identidad reusada del pipeline: {REUSA_PIPELINE}\n", flush=True)
    if not REUSA_PIPELINE:
        print("  !! El pipeline no esta montado: el hash se calcularia con la copia")
        print("     de respaldo y podria no coincidir. No se sigue.")
        return 2
    if not props.exists():
        print(f"  !! no existe {props}")
        return 2

    # --- 1. auditar lo que hay -------------------------------------------
    antes = auditar(ckpt)
    print("  CHECKPOINT ACTUAL")
    for k, v in antes.items():
        print(f"    {k:32} {v}")
    if antes.get("existe") and antes.get("fuentes_con_claves_mezcladas"):
        print(f"\n    DIAGNOSTICO: {antes['fuentes_con_claves_mezcladas']} fuentes "
              f"mezclan claves de dos formatos.")
        print("    La corrida vieja escribio source_listing_id y la nueva "
              "hash_dedup;")
        print("    comparar una contra otra no coincide nunca, asi que todo "
              "figura NUEVA")
        print("    y todo el inventario anterior figura ausente.")

    # --- 2. construir el baseline desde las propiedades -------------------
    vistos: dict[str, dict[str, str]] = defaultdict(dict)
    ids: dict[str, dict[str, str]] = defaultdict(dict)
    total, sin_datos = 0, 0
    reservorio: list[dict] = []
    for p in leer_propiedades(props):
        cid, h = p.get("canonical_agency_id"), p.get("hash_dedup")
        # La huella se RECALCULA. Copiar la guardada ataria el baseline a una
        # definicion vieja, y la corrida siguiente veria MODIFICADA todo el
        # inventario por un cambio de formula y no por un cambio real.
        fp = fingerprint_actual(p)
        if not (cid and h and fp):
            sin_datos += 1
            continue
        total += 1
        vistos[cid][h] = fp
        ids[cid][h] = p.get("source_listing_id")
        # Muestreo por reservorio: el archivo pesa cientos de MB y no entra en
        # memoria, pero la muestra tiene que ser de todo el archivo y no de las
        # primeras filas -que son siempre las mismas agencias-.
        if len(reservorio) < a.muestra:
            reservorio.append(p)
        else:
            j = random.randrange(total)
            if j < a.muestra:
                reservorio[j] = p

    print(f"\n  BASELINE PROPUESTO")
    print(f"    propiedades leidas:        {total:,}")
    print(f"    filas sin identidad:       {sin_datos:,}")
    print(f"    fuentes:                   {len(vistos):,}")
    print(f"    hashes unicos por fuente:  {sum(len(v) for v in vistos.values()):,}")

    # --- 3. verificar la identidad antes de escribir ----------------------
    ok, fallos = verificar_identidad(reservorio)
    recalculadas = sum(1 for p in reservorio
                       if fingerprint_actual(p) != p.get("fingerprint"))
    print(f"\n  VERIFICACION DE IDENTIDAD (muestra de {len(reservorio)})")
    print(f"    hash recalculado == hash guardado: {'si' if ok else 'NO'}")
    print(f"    huellas con valor distinto:        {recalculadas}/{len(reservorio)} "
          f"(cambio de formula, no de contenido)")
    if not ok:
        print(f"    {len(fallos)} discrepancias; se muestran 3:")
        for f in fallos[:3]:
            print(f"      {f['source_url'][:70]}")
            print(f"        guardado    {f['guardado']}")
            print(f"        recalculado {f['recalculado']}")
        print("\n  NO se escribe nada: el baseline no seria comparable.")
        return 1

    if not a.aplicar:
        print("\n  (dry run) usar --aplicar para escribir el checkpoint")
        return 0

    # --- 4. escribir, conservando el anterior -----------------------------
    if ckpt.exists():
        respaldo = ckpt.with_name(
            f"checkpoint.previo-{time.strftime('%Y%m%d-%H%M%S')}.json")
        shutil.copy2(ckpt, respaldo)
        print(f"\n  checkpoint anterior conservado en {respaldo.name}")

    datos = {"fuentes": {}}
    for cid, v in vistos.items():
        datos["fuentes"][cid] = {
            "vistos": v,
            "ids": ids[cid],
            "ausencias": {},
            "corridas": 1,
            "ultima_pagina": 0,
            "completa": False,
            "esquema": ESQUEMA_CHECKPOINT,
            # Las huellas se recalcularon recien con la formula vigente, asi
            # que el baseline queda sellado con SU version: si manana cambia la
            # formula, la corrida lo informa en vez de fingir una ola de
            # cambios comerciales.
            "huella_version": HUELLA_VERSION,
            # Deliberadamente SIN linea_base: este baseline si es comparable, y
            # marcarlo obligaria a gastar una corrida entera en volver a
            # establecerlo.
            "origen_baseline": f"{props.name} verificado por recalculo de hash",
        }
    tmp = ckpt.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(ckpt)

    despues = auditar(ckpt)
    print("\n  CHECKPOINT NUEVO")
    for k, v in despues.items():
        print(f"    {k:32} {v}")
    print("\n  La proxima corrida sobre estas fuentes deberia dar SIN_CAMBIOS "
          "dominante.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

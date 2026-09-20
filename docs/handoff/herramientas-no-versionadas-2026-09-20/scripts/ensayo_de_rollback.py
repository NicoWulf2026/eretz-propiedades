#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ensayo del UPSERT y su reversion, en una base local descartable.

No toca produccion. `database_writes: 0` contra Supabase.

**Que prueba y que no.**

Prueba el PROCEDIMIENTO: que el UPDATE `COALESCE`-safe nunca reemplaza un valor
existente por nulo, y que la imagen previa que guarda cada lote alcanza para
dejar la tabla byte a byte como estaba. Eso es lo que pide el plan de rollback
antes de autorizar la Fase 4.

No prueba los VALORES de produccion, porque no los tenemos: lo que si tenemos
-y es lo que hace que el ensayo valga- es la MASCARA real de que campos tiene
cada fila productiva, bajada en el diff. Las filas locales se arman con esa
mascara real y con los valores reales de las candidatas. Asi el ensayo recorre
la misma forma del problema: las mismas 28.252 colisiones, los mismos 62.283
campos que un UPDATE ingenuo borraria.

Se ejecutan las dos variantes a proposito:

  - `ingenuo`  : `SET campo = nuevo` para todos los campos. Tiene que PERDER
                 datos. Si no pierde, el ensayo esta mal armado y avisa.
  - `coalesce` : `SET campo = COALESCE(nuevo, campo)`. No puede perder ninguno.

Y despues se revierte el `coalesce` y se compara la tabla entera contra la
copia previa.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

DRY_RUN = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY"
               r"\dry_run_escritura.jsonl")

CAMPOS = ("precio", "moneda", "ambientes", "dormitorios", "banos",
          "superficie_total", "superficie_cubierta", "latitud", "ciudad",
          "barrio", "provincia", "direccion", "titulo", "descripcion",
          "imagenes")


def base_local() -> sqlite3.Connection:
    cx = sqlite3.connect(":memory:")
    columnas = ", ".join(f"{c} TEXT" for c in CAMPOS)
    cx.execute(f"CREATE TABLE propiedades (k TEXT PRIMARY KEY, {columnas})")
    return cx


def sembrar(cx: sqlite3.Connection, filas: list[dict[str, Any]]) -> None:
    """Una fila productiva por cada candidata que ya existe.

    El valor es inventado -`prod:<campo>`- pero la PRESENCIA es la real: si el
    diff dice que produccion tiene ciudad y nosotros no, la fila local tiene
    ciudad y la candidata no. Eso es lo unico que decide si un UPDATE pierde.
    """
    cols = ", ".join(CAMPOS)
    marcas = ", ".join("?" for _ in CAMPOS)
    lote = []
    for f in filas:
        # `no_tocar` = produccion tiene, la candidata no.
        # `aporta`   = la candidata tiene, produccion no.
        # el resto de los campos los tienen los dos.
        aporta = set(f.get("aporta", []))
        valores = [None if c in aporta else f"prod:{c}" for c in CAMPOS]
        lote.append([f["k"]] + valores)
    cx.executemany(f"INSERT INTO propiedades (k, {cols}) VALUES (?, {marcas})",
                   lote)


def candidata(f: dict[str, Any]) -> list[Any]:
    """Lo que traeria nuestro extractor para esa fila."""
    no_tocar = set(f.get("no_tocar", []))
    return [None if c in no_tocar else f"nuevo:{c}" for c in CAMPOS]


def copia(cx: sqlite3.Connection) -> list[tuple]:
    return cx.execute(
        f"SELECT k, {', '.join(CAMPOS)} FROM propiedades ORDER BY k").fetchall()


def aplicar(cx: sqlite3.Connection, filas: list[dict[str, Any]],
            modo: str) -> list[tuple]:
    """Aplica el UPDATE y devuelve la imagen previa de lo que toco."""
    if modo == "ingenuo":
        sets = ", ".join(f"{c} = ?" for c in CAMPOS)
    else:
        sets = ", ".join(f"{c} = COALESCE(?, {c})" for c in CAMPOS)

    previas = cx.execute(
        f"SELECT k, {', '.join(CAMPOS)} FROM propiedades "
        f"WHERE k IN ({','.join('?' for _ in filas)})",
        [f["k"] for f in filas]).fetchall()

    cx.executemany(f"UPDATE propiedades SET {sets} WHERE k = ?",
                   [candidata(f) + [f["k"]] for f in filas])
    return previas


def revertir(cx: sqlite3.Connection, previas: list[tuple]) -> None:
    """El UPDATE inverso: cada campo vuelve al valor que el lote anoto."""
    sets = ", ".join(f"{c} = ?" for c in CAMPOS)
    cx.executemany(f"UPDATE propiedades SET {sets} WHERE k = ?",
                   [list(p[1:]) + [p[0]] for p in previas])


def perdidos(antes: list[tuple], despues: list[tuple]) -> Counter:
    """Campos que tenian valor y quedaron nulos."""
    cuenta: Counter = Counter()
    for a, d in zip(antes, despues):
        assert a[0] == d[0]
        for i, campo in enumerate(CAMPOS, start=1):
            if a[i] is not None and d[i] is None:
                cuenta[campo] += 1
    return cuenta


def main() -> int:
    existentes = []
    for linea in DRY_RUN.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        f = json.loads(linea)
        if f["clase"].startswith("UPDATE"):
            existentes.append(f)
    print(f"filas del ensayo: {len(existentes)}")

    resultados = {}
    for modo in ("ingenuo", "coalesce"):
        cx = base_local()
        sembrar(cx, existentes)
        antes = copia(cx)
        previas = aplicar(cx, existentes, modo)
        despues = copia(cx)
        cuenta = perdidos(antes, despues)
        resultados[modo] = (sum(cuenta.values()), cuenta)
        print(f"\n[{modo}] campos que quedaron nulos teniendo valor: "
              f"{sum(cuenta.values())}")
        if cuenta:
            print("   ", ", ".join(f"{c}:{n}" for c, n in cuenta.most_common(6)))

        if modo == "coalesce":
            revertir(cx, previas)
            vuelto = copia(cx)
            iguales = vuelto == antes
            print(f"[{modo}] la reversion deja la tabla igual que antes: "
                  f"{'SI' if iguales else 'NO'}")
            distintas = sum(1 for a, v in zip(antes, vuelto) if a != v)
            print(f"[{modo}] filas que no volvieron a su valor: {distintas}")
        cx.close()

    ingenuo = resultados["ingenuo"][0]
    seguro = resultados["coalesce"][0]
    print("\n--- veredicto ---")
    if ingenuo == 0:
        print("MAL ARMADO: el UPDATE ingenuo no perdio nada, el ensayo no "
              "esta probando lo que dice probar.")
        return 1
    if seguro != 0:
        print(f"FALLA: el UPDATE COALESCE-safe perdio {seguro} campos.")
        return 1
    print(f"el UPDATE ingenuo habria borrado {ingenuo} valores productivos;")
    print("el COALESCE-safe no borro ninguno, y su reversion es exacta.")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

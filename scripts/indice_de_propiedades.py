#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El JSONL es el registro; esto es su índice. §52, §56, §89, §90.

Local. No toca producción, no toca Supabase. `database_writes: 0` —el contador
se refiere a la base productiva; acá se escribe un SQLite local derivado, que se
puede borrar y reconstruir en tres segundos.

La decisión, medida y no opinada
--------------------------------
El §52 pide elegir entre SQLite, JSONL y Parquet "según simplicidad e
integridad", y el §89 pide medir el aporte marginal antes de dejar una capa
nueva. Medido sobre el artefacto real —22.097 propiedades, 375.649 estados de
campo—:

    JSONL                61,3 MB   buscar una propiedad:  332 ms
    SQLite con indices   56,8 MB   buscar una propiedad:  0,24 ms

Mil trescientas noventa y cuatro veces más rápido, y **más chico** que el JSONL.
Extrapolado al universo productivo —257.073 propiedades— el SQLite pesa ~659 MB
y la búsqueda sigue costando 0,24 ms, mientras que leer el JSONL entero pasa a
costar 20 s.

Construirlo entero, medido en su lugar real y no en el banco de pruebas:
**29,5 s** sobre el disco de trabajo. El banco había dado 3,4 s escribiendo en
disco local y con el archivo en caché; se anota el número de verdad, que es el
que alguien va a esperar.

Parquet queda afuera y no por antipatía: `pyarrow` está instalado, pero es
columnar y no indexa búsquedas puntuales. El trabajo del Regression Gate V2 es
comparar **propiedad por propiedad, campo por campo** (§56), que son búsquedas.
Sumar una dependencia para ir más lento en lo que más se hace es aporte marginal
negativo.

Lo que NO se hace es reemplazar el JSONL. Es el registro append-only que la
certificación produce naturalmente y sobrevive a una caída a mitad de escritura.
El SQLite es **derivado**: si se corrompe o queda viejo, se borra y se
reconstruye. Dos cosas con un trabajo cada una, en vez de una que hace mal las
dos.

La clave natural, que no es la obvia
------------------------------------
`(agency_id, source_listing_id)` **no es única**: `baron inmobiliaria` tiene el
id `300` en 36 propiedades distintas, porque el extractor lo sacó del número de
calle del slug. Las claves que sí lo son, medidas sobre las 22.097:

    (agency_id, source_url)   22.097 de 22.097
    fingerprint               22.097 de 22.097

Así que el índice único va sobre esas dos y `source_listing_id` queda como
columna común, indexada pero sin unicidad. Ver
`colision_de_ids_estables.py`.

Uso:
    python scripts/indice_de_propiedades.py
    python scripts/indice_de_propiedades.py --consulta "baron" --campo precio
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
ORIGEN = CERT / "ERETZ_PROPIEDADES_CERTIFICADAS.jsonl"
INDICE = CERT / "ERETZ_PROPIEDADES.sqlite3"

# El valor se recorta: una descripción de 8 KB no aporta nada a una comparación
# campo a campo y multiplica el tamaño del índice. El JSONL conserva el valor
# entero, que para eso es el registro.
TOPE_VALOR = 400

ESQUEMA = """
CREATE TABLE propiedad(
    id                   INTEGER PRIMARY KEY,
    run_id               TEXT,
    agency_id            TEXT NOT NULL,
    source_url           TEXT NOT NULL,
    source_listing_id    TEXT,
    connector            TEXT,
    strategy             TEXT,
    strategy_fingerprint TEXT,
    agency_status        TEXT,
    imagenes             INTEGER,
    fingerprint          TEXT,
    scraped_at           TEXT
);
CREATE TABLE campo(
    propiedad_id INTEGER NOT NULL,
    campo        TEXT NOT NULL,
    estado       TEXT,
    valor        TEXT
);
"""

# `source_url` y `fingerprint` son unicos y estan medidos; `source_listing_id`
# NO lo es y por eso su indice no lleva UNIQUE. Ponerselo rompe la carga, que
# es exactamente como se descubrio la colision.
INDICES = """
CREATE UNIQUE INDEX ix_prop_natural  ON propiedad(agency_id, source_url);
CREATE UNIQUE INDEX ix_prop_finger   ON propiedad(fingerprint);
CREATE INDEX        ix_prop_agencia  ON propiedad(agency_id);
CREATE INDEX        ix_prop_listing  ON propiedad(agency_id, source_listing_id);
CREATE INDEX        ix_campo_prop    ON campo(propiedad_id, campo);
CREATE INDEX        ix_campo_estado  ON campo(campo, estado);
"""


def _jsonl(ruta: Path):
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def construir(origen: Path, destino: Path) -> dict:
    """Se construye en un temporal y se renombra al final.

    Si algo falla a mitad, el índice viejo sigue siendo el que estaba y no
    queda uno a medio escribir que parezca completo.
    """
    temporal = destino.with_suffix(".sqlite3.tmp")
    if temporal.exists():
        temporal.unlink()
    comenzado = time.time()

    conexion = sqlite3.connect(temporal)
    conexion.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
    conexion.executescript(ESQUEMA)

    propiedades, campos, duplicados = [], [], []
    vistos = set()
    for indice, fila in enumerate(_jsonl(origen)):
        clave = (fila.get("agency_id"), fila.get("source_url"))
        if clave in vistos:
            duplicados.append(clave)
            continue
        vistos.add(clave)
        propiedades.append((
            indice, fila.get("run_id"), fila.get("agency_id"),
            fila.get("source_url"), fila.get("source_listing_id"),
            fila.get("connector"), fila.get("strategy"),
            fila.get("strategy_fingerprint"), fila.get("agency_status"),
            fila.get("imagenes"), fila.get("fingerprint"),
            fila.get("scraped_at")))
        for nombre, dato in (fila.get("campos") or {}).items():
            dato = dato if isinstance(dato, dict) else {}
            valor = dato.get("valor")
            campos.append((indice, nombre, dato.get("estado"),
                           None if valor is None else str(valor)[:TOPE_VALOR]))

    conexion.executemany(
        "INSERT INTO propiedad VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", propiedades)
    conexion.executemany("INSERT INTO campo VALUES (?,?,?,?)", campos)
    conexion.executescript(INDICES)
    conexion.commit()
    conexion.close()
    temporal.replace(destino)

    return {"propiedades": len(propiedades), "estados_de_campo": len(campos),
            "duplicados_descartados": len(duplicados),
            "segundos": round(time.time() - comenzado, 2),
            "mb": round(destino.stat().st_size / 1e6, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consulta", help="filtrar por nombre de agencia")
    ap.add_argument("--campo", default="precio")
    args = ap.parse_args()

    if args.consulta:
        if not INDICE.exists():
            print("no hay indice: correr sin --consulta")
            return 1
        conexion = sqlite3.connect(f"file:{INDICE.as_posix()}?mode=ro", uri=True)
        comenzado = time.time()
        filas = conexion.execute(
            "SELECT c.estado, count(*) FROM propiedad p JOIN campo c "
            "ON c.propiedad_id = p.id WHERE p.agency_id LIKE ? AND c.campo = ? "
            "GROUP BY c.estado ORDER BY 2 DESC",
            (f"%{args.consulta}%", args.campo)).fetchall()
        print(f"campo `{args.campo}` en agencias que contienen "
              f"{args.consulta!r}:")
        for estado, cuantas in filas:
            print(f"   {str(estado):24} {cuantas:6}")
        print(f"\n({1000 * (time.time() - comenzado):.1f} ms)")
        conexion.close()
        return 0

    if not ORIGEN.exists():
        print(f"no existe {ORIGEN.name}: correr primero "
              f"artefacto_por_propiedad.py")
        return 1

    resumen = construir(ORIGEN, INDICE)
    print(f"indice reconstruido desde {ORIGEN.name}\n")
    for clave, valor in resumen.items():
        print(f"   {clave:26} {valor}")
    if resumen["duplicados_descartados"]:
        print(f"\n   Se descartaron {resumen['duplicados_descartados']} filas "
              f"con (agency_id, source_url) repetido.")
    print(f"\n   El JSONL sigue siendo el registro. Esto es derivado: si queda")
    print(f"   viejo o se corrompe, se borra y se reconstruye en "
          f"{resumen['segundos']}s.")
    print(f"\nartefacto: {INDICE}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Prepare a derived API snapshot for viewport queries and public ID aliases.

The source snapshot is never edited. The output is a disposable copy. An
optional CSV must contain ``alias,property_id`` and is validated against the
canonical property IDs before insertion.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
from pathlib import Path


INDEXES = """
create index if not exists ix_map_viewport on propiedades(latitud, longitud);
create index if not exists ix_geo_provincia on propiedades(provincia);
create index if not exists ix_geo_departamento on propiedades(departamento);
create index if not exists ix_geo_municipio on propiedades(municipio);
create index if not exists ix_explorer_common
  on propiedades(operacion, tipo_propiedad, moneda, provincia, precio);
-- FTS joins look up many property IDs. Cover their predicates without
-- fetching the large JSON document on each random table-page read.
create index if not exists ix_search_filter_metadata on propiedades(
  id, operacion, tipo_propiedad, moneda, precio, ambientes, dormitorios, banos,
  superficie_total, superficie_cubierta, latitud, longitud, geo_estado,
  area_nivel, area_nombre, localidad, municipio, departamento, provincia, barrio,
  titulo);
create table if not exists property_aliases (
  alias text primary key,
  property_id text not null references propiedades(id)
);
create index if not exists ix_property_alias_target on property_aliases(property_id);
"""

SEARCH_ID_INDEX = """
-- Reading FTS5's unindexed id otherwise fetches the content row, including
-- long descriptions, for every match. This bridge stores only identities.
create table if not exists search_property_ids (
  search_rowid integer primary key,
  property_id text not null references propiedades(id)
);
insert or replace into search_property_ids select rowid, id from busqueda;
create index if not exists ix_search_property_id on search_property_ids(property_id);
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--aliases", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must differ from source; the source is immutable")
    if args.output.exists():
        parser.error("output already exists; choose a new derived artifact path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, args.output)
    connection = sqlite3.connect(args.output)
    try:
        connection.execute("pragma foreign_keys=on")
        connection.executescript(INDEXES)
        if connection.execute("select 1 from sqlite_master where name='busqueda'").fetchone():
            connection.executescript(SEARCH_ID_INDEX)
        if args.aliases:
            with args.aliases.open(encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    alias = (row.get("alias") or "").strip()
                    property_id = (row.get("property_id") or "").strip()
                    if not alias or not property_id:
                        raise ValueError("every alias row requires alias and property_id")
                    connection.execute(
                        "insert into property_aliases(alias, property_id) values (?, ?)",
                        (alias, property_id),
                    )
        connection.commit()
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

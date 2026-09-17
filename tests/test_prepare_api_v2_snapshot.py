from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_prepare_snapshot_preserves_source_and_loads_verified_aliases(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    output = tmp_path / "output.sqlite3"
    aliases = tmp_path / "aliases.csv"
    connection = sqlite3.connect(source)
    connection.execute(
        "create table propiedades (id text primary key, latitud real, longitud real, "
        "provincia text, departamento text, municipio text, operacion text, "
        "tipo_propiedad text, moneda text, precio real, titulo text, localidad text, "
        "ambientes integer, dormitorios integer, banos integer, superficie_total real, "
        "superficie_cubierta real, geo_estado text, area_nivel text, area_id text, "
        "area_nombre text, barrio text)"
    )
    connection.execute("insert into propiedades(id) values ('canonical-1')")
    connection.execute('create virtual table busqueda using fts5(id unindexed, titulo)')
    connection.execute("insert into busqueda values ('canonical-1', 'Casa')")
    connection.commit()
    connection.close()
    with aliases.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["alias", "property_id"])
        writer.writeheader()
        writer.writerow({"alias": "123", "property_id": "canonical-1"})

    subprocess.run(
        [
            sys.executable,
            "scripts/prepare_api_v2_snapshot.py",
            str(source),
            str(output),
            "--aliases",
            str(aliases),
        ],
        check=True,
    )

    original = sqlite3.connect(source)
    assert (
        original.execute(
            "select count(*) from sqlite_master where name='property_aliases'"
        ).fetchone()[0]
        == 0
    )
    original.close()
    prepared = sqlite3.connect(output)
    assert prepared.execute('select property_id from search_property_ids').fetchall() == [('canonical-1',)]
    assert prepared.execute("select alias, property_id from property_aliases").fetchall() == [
        ("123", "canonical-1")
    ]
    prepared.close()
    result = subprocess.run([sys.executable, 'scripts/prepare_api_v2_snapshot.py',
                             str(source), str(output)], capture_output=True)
    assert result.returncode != 0
    assert b'output already exists' in result.stderr

import argparse
import io
import json
import sys
from pathlib import Path

from scripts import reconcile_supabase_inventory as reconciliation


def property_record(index: int, agency: int = 10) -> dict:
    url = f"https://example.com/property/{index}"
    return {
        "canonical_agency_id": f"agency-{agency}",
        "source_listing_id": str(index),
        "source_url": url,
        "connector": "test",
        "titulo": f"Propiedad {index}",
        "descripcion": "Descripción verificable",
        "precio": 100000 + index,
        "moneda": "USD",
        "operacion": "venta",
        "tipo_propiedad": "departamento",
        "direccion": "Calle 123",
        "barrio": "Centro",
        "ciudad": "Córdoba",
        "provincia": "Córdoba",
        "latitud": -31.4,
        "longitud": -64.2,
        "dormitorios": 2,
        "banos": 1,
        "ambientes": 3,
        "superficie_total": 80,
        "superficie_cubierta": 70,
        "imagenes": ["https://img/1.jpg", "https://img/2.jpg"],
        "inmobiliaria_id": agency,
        "hash_dedup": reconciliation.calcular_hash_dedup(agency, url),
        "fingerprint": f"fingerprint-{index}",
    }


def snapshot_row(record: dict, row_id: int, fingerprint: str | None = None, agency: int | None = None) -> dict:
    values = reconciliation.digests(record)
    return {
        "row_id": row_id,
        "inmobiliaria_id": record["inmobiliaria_id"] if agency is None else agency,
        "hash_dedup": record["hash_dedup"],
        "source_url": record["source_url"],
        "url_normalizada": reconciliation.normalizar_url(record["source_url"]),
        "source_listing_id": record["source_listing_id"],
        "fingerprint": fingerprint,
        **{f"d_{field}": values[field] for field in reconciliation.DIGEST_FIELDS},
    }


def test_reconciliation_is_exhaustive_and_mutually_exclusive(tmp_path: Path, monkeypatch):
    records = [property_record(index) for index in range(1, 6)]
    source = tmp_path / "write.jsonl"
    source.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")
    output = tmp_path / "output"

    assert reconciliation.prepare(argparse.Namespace(write_set=str(source), output_dir=str(output))) == 0
    database = output / "SUPABASE_RECONCILIATION.sqlite3"

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps([{"id": 10}]) + "\n"))
    reconciliation.ingest_agencies(argparse.Namespace(database=str(database)))

    changed = dict(records[1])
    changed["precio"] = 999999
    rows = [
        snapshot_row(records[0], 1, records[0]["fingerprint"]),
        snapshot_row(changed, 2, "previous-fingerprint"),
        snapshot_row(records[3], 3, None, agency=99),
    ]
    payload = json.dumps({"relation": "internal_scraping.propiedades_raw", "rows": rows}) + "\n" + json.dumps({"_end": True}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    reconciliation.ingest_snapshot(argparse.Namespace(database=str(database)))

    reconciliation.reconcile(argparse.Namespace(database=str(database)))
    connection = reconciliation._connect(database)
    actual = dict(connection.execute("select classification,count(*) from results group by classification"))
    assert actual == {
        "DUPLICATE_OR_CONFLICT": 1,
        "EXISTS_CHANGED": 1,
        "EXISTS_UNCHANGED": 1,
        "TRULY_NEW": 2,
    }
    assert connection.execute("select count(*) from results").fetchone()[0] == len(records)


def test_validation_rejects_synthetic_or_mismatched_identity():
    record = property_record(1)
    record["inmobiliaria_id"] = -1
    assert "inmobiliaria_id_invalido" in reconciliation._validation_reasons(record)
    assert "hash_no_corresponde_agencia_url" in reconciliation._validation_reasons(record)


def test_snapshot_sql_is_select_only():
    sql = reconciliation.snapshot_sql("public", after=100, limit=50).lower()
    assert sql.lstrip().startswith("select")
    assert "from public.propiedades" in sql
    assert "where id > 100" in sql
    assert not any(keyword in sql for keyword in ("insert into", "update ", "delete ", "alter ", "drop "))


def test_targeted_snapshot_sql_is_select_only_and_escapes_keys():
    sql = reconciliation.targeted_snapshot_sql("raw", [{
        "hash_dedup": "abc",
        "url_normalizada": "https://example.com/o'hare",
        "inmobiliaria_id": 10,
        "source_listing_id": "external-1",
    }]).lower()
    assert sql.lstrip().startswith("with keys as")
    assert "candidate_ids" in sql
    assert "o''hare" in sql
    assert "from internal_scraping.propiedades_raw" in sql
    assert not any(keyword in sql for keyword in ("insert into", "update ", "delete ", "alter ", "drop "))


def test_resolution_releases_only_declared_owner(tmp_path: Path, monkeypatch):
    owner = property_record(1, agency=20)
    losing = dict(owner)
    losing["inmobiliaria_id"] = 10
    losing["source_url"] = owner["source_url"].replace("https://", "https://www.")
    losing["hash_dedup"] = reconciliation.calcular_hash_dedup(10, losing["source_url"])
    source = tmp_path / "write.jsonl"
    source.write_text(
        json.dumps(owner, ensure_ascii=False) + "\n" + json.dumps(losing, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"

    assert reconciliation.prepare(argparse.Namespace(write_set=str(source), output_dir=str(output))) == 2
    database = output / "SUPABASE_RECONCILIATION.sqlite3"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps([{"id": 10}, {"id": 20}]) + "\n"))
    reconciliation.ingest_agencies(argparse.Namespace(database=str(database)))
    resolution = tmp_path / "resolution.jsonl"
    resolution.write_text(json.dumps({
        "url_normalizada": reconciliation.normalizar_url(owner["source_url"]),
        "owner_agency_id": 20,
        "category": "CLEAR_OWNER",
        "evidence": ["dominio oficial y titularidad verificada"],
    }) + "\n", encoding="utf-8")
    reconciliation.ingest_resolutions(argparse.Namespace(database=str(database), file=str(resolution)))

    reconciliation.reconcile(argparse.Namespace(database=str(database)))
    connection = reconciliation._connect(database)
    actual = list(connection.execute("select i.inmobiliaria_id,r.classification from inputs i join results r using(seq) order by i.inmobiliaria_id"))
    assert actual == [(10, "DUPLICATE_OR_CONFLICT"), (20, "TRULY_NEW")]


def test_field_difference_overrides_equal_fingerprint(tmp_path: Path, monkeypatch):
    record = property_record(1)
    source = tmp_path / "write.jsonl"
    source.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    output = tmp_path / "output"
    assert reconciliation.prepare(argparse.Namespace(write_set=str(source), output_dir=str(output))) == 0
    database = output / "SUPABASE_RECONCILIATION.sqlite3"
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps([{"id": 10}]) + "\n" + json.dumps({"_end": True}) + "\n"))
    reconciliation.ingest_agencies(argparse.Namespace(database=str(database)))
    changed = dict(record)
    changed["precio"] = record["precio"] + 1
    payload = json.dumps({
        "relation": "internal_scraping.propiedades_raw",
        "rows": [snapshot_row(changed, 1, record["fingerprint"])],
    }) + "\n" + json.dumps({"_end": True}) + "\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    reconciliation.ingest_snapshot(argparse.Namespace(database=str(database)))
    reconciliation.reconcile(argparse.Namespace(database=str(database)))
    connection = reconciliation._connect(database)
    classification, changed_fields = connection.execute(
        "select classification,changed_fields from results").fetchone()
    assert classification == "EXISTS_CHANGED"
    assert "precio" in json.loads(changed_fields)

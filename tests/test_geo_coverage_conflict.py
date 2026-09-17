import json
import sqlite3
from types import SimpleNamespace

from scripts import geo_coverage_audit as audit


def test_conflicting_province_is_not_counted_as_demonstrated(tmp_path, monkeypatch):
    db = tmp_path / 'inventory.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('create table rows(row_json text, connector text, hash_dedup text, status text)')
        conn.execute('insert into rows values(?,?,?,?)',
                     (json.dumps(dict(provincia='CABA', latitud=-34, longitud=-58)),
                      'generico', 'h', 'CANDIDATE'))
    cache = tmp_path / 'geometry.jsonl'
    cache.write_text(json.dumps(dict(clave='-34.0,-58.0', provincia='Buenos Aires',
                                    municipio='La Plata')) + '\n', encoding='utf-8')
    monkeypatch.setattr(audit, 'exigir_base_vigente', lambda db: None)
    monkeypatch.setattr(audit, 'geografia', lambda: SimpleNamespace(entidades=[]))
    monkeypatch.setattr('sys.argv', ['audit', '--db', str(db), '--salida', str(tmp_path),
                                  '--cache-geometrica', str(cache)])
    assert audit.main() == 0
    row = json.loads((tmp_path / 'GEO_COVERAGE_AUDIT.jsonl').read_text(encoding='utf-8'))
    summary = json.loads((tmp_path / 'GEO_COVERAGE_AUDIT_SUMMARY.json').read_text(encoding='utf-8'))
    assert row['estado_geografico'] == 'GEO_CONFLICT'
    assert row['provincia_canonica'] is None
    assert row['area_busqueda']['nivel'] == 'SIN_AREA'
    assert row['fuente']['provincia'] == 'CABA'
    assert summary['demostrable_por_dimension'].get('provincia', 0) == 0
    assert summary['area_busqueda_total'] == 0

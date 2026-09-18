"""No missing reference or mismatched checksum can yield a safe replacement."""
import hashlib
import json
import sys

import pytest

from scripts import geo_snapshot, geo_snapshot_diff
from scripts.geo_reference import verified_rows


def reference(directory, rows=None, *, legacy=False):
    directory.mkdir()
    rows = [{'id': '01', 'nombre': 'Entidad fixture'}] if rows is None else rows
    raw = json.dumps(rows, ensure_ascii=False, indent=1).encode('utf-8')
    manifest = {'recursos': {'municipios': {'archivo': 'municipios.json',
        'total_declarado': len(rows), 'filas_traidas': len(rows), 'completo': True,
        'sha256': hashlib.sha256(raw).hexdigest()}}}
    if legacy:
        raw = raw.replace(b'\n', b'\r\n')
    else:
        manifest.update(schema_version=2, sha256_scope='file_bytes_utf8_lf')
    (directory / 'municipios.json').write_bytes(raw)
    (directory / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


@pytest.mark.parametrize('legacy', [True, False])
def test_demonstrated_hash_formats_are_verified_explicitly(tmp_path, legacy):
    reference(tmp_path / 'reference', legacy=legacy)
    assert verified_rows(tmp_path / 'reference', 'municipios')[0]['id'] == '01'


def test_missing_both_references_cannot_be_a_safe_zero_diff(tmp_path):
    with pytest.raises(FileNotFoundError):
        geo_snapshot_diff.indexar(tmp_path / 'missing', 'municipios')


@pytest.mark.parametrize('change', [
    {'total_declarado': 2}, {'total_declarado': True}, {'filas_traidas': 2},
    {'completo': False}, {'completo': 1}, {'sha256': '0' * 64},
    {'sha256': True}, {'archivo': '../other.json'},
])
def test_false_manifest_evidence_does_not_verify_reference(tmp_path, change):
    folder = tmp_path / 'reference'
    manifest = reference(folder)
    manifest['recursos']['municipios'].update(change)
    (folder / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError):
        verified_rows(folder, 'municipios')


@pytest.mark.parametrize('change', [{'sha256_scope': 'unknown'}, {'schema_version': 999},
                                     {'schema_version': 2.0}])
def test_unknown_hash_scope_or_version_cannot_guess_success(tmp_path, change):
    folder = tmp_path / 'reference'
    manifest = reference(folder)
    manifest.update(change)
    (folder / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError, match='Unknown'):
        verified_rows(folder, 'municipios')


def test_changed_data_is_not_accepted_under_old_checksum(tmp_path):
    folder = tmp_path / 'reference'
    reference(folder)
    (folder / 'municipios.json').write_text('[{"id":"changed"}]', encoding='utf-8')
    with pytest.raises(ValueError, match='hash does not match'):
        verified_rows(folder, 'municipios')


def test_duplicate_ids_do_not_get_collapsed_into_a_smaller_reference(tmp_path):
    folder = tmp_path / 'reference'
    reference(folder, [{'id': '01'}, {'id': '01'}])
    with pytest.raises(ValueError, match='duplicate'):
        verified_rows(folder, 'municipios')


@pytest.mark.parametrize('payload', ['[]', 'null', '{not JSON'])
def test_corrupt_manifest_is_explicit_error(tmp_path, payload):
    folder = tmp_path / 'reference'
    reference(folder)
    (folder / 'MANIFEST.json').write_text(payload, encoding='utf-8')
    with pytest.raises(ValueError):
        verified_rows(folder, 'municipios')


def test_new_writer_checksum_is_of_physical_utf8_lf_bytes(tmp_path, monkeypatch):
    target = tmp_path / 'new'
    monkeypatch.setattr(geo_snapshot, 'RECURSOS', ('municipios',))
    monkeypatch.setattr(geo_snapshot, 'traer', lambda _resource: ([{'id': '01'}], 1, 'volcado'))
    monkeypatch.setattr(geo_snapshot.time, 'sleep', lambda _seconds: None)
    monkeypatch.setattr(sys, 'argv', ['geo_snapshot', '--destino', str(target)])
    assert geo_snapshot.main() == 0
    raw = (target / 'municipios.json').read_bytes()
    manifest = json.loads((target / 'MANIFEST.json').read_text(encoding='utf-8'))
    assert b'\r\n' not in raw
    assert manifest['recursos']['municipios']['sha256'] == hashlib.sha256(raw).hexdigest()
    assert verified_rows(target, 'municipios') == [{'id': '01'}]


def test_successful_diff_is_diagnostic_not_replacement_authorization(tmp_path, monkeypatch, capsys):
    old, new = tmp_path / 'old', tmp_path / 'new'
    reference(old)
    reference(new)
    report = tmp_path / 'report.json'
    monkeypatch.setattr(geo_snapshot_diff, 'RECURSOS', ('municipios',))
    monkeypatch.setattr(sys, 'argv', ['geo_diff', str(old), str(new), '--salida', str(report)])
    assert geo_snapshot_diff.main() == 0
    assert json.loads(report.read_text(encoding='utf-8'))['replacement_authorized'] is False
    assert 'no autoriza' in capsys.readouterr().out

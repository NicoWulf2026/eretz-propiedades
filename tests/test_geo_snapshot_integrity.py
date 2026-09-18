"""Offline controls: an incomplete reference cannot overwrite a valid snapshot."""
import json
import sys
import urllib.error

import pytest

from scripts import geo_snapshot as snapshot


def page(ids=('01',), total=1, start=0):
    return {'municipios': [{'id': value, 'nombre': 'Entidad fixture'} for value in ids],
            'total': total, 'cantidad': len(ids), 'inicio': start}


def fallback(monkeypatch, pages):
    responses = iter(pages)
    def download(url):
        if url.startswith(snapshot.VOLCADO):
            raise urllib.error.HTTPError(url, 404, 'not available', None, None)
        return next(responses)
    monkeypatch.setattr(snapshot, 'bajar', download)
    monkeypatch.setattr(snapshot.time, 'sleep', lambda _seconds: None)


def test_complete_dump_returns_requested_resource_not_first_arbitrary_list(monkeypatch):
    payload = {'unrelated': [], **page()}
    monkeypatch.setattr(snapshot, 'bajar', lambda _url: payload)
    rows, total, source = snapshot.traer('municipios')
    assert rows == payload['municipios'] and total == 1 and source == 'volcado'


@pytest.mark.parametrize('payload', [
    [], {}, {'unrelated': [], 'total': 1}, page(total=True), page(total=0),
    page(total='1'), page(total=100_001), page(ids=('01', '01'), total=2),
    page(ids=(True,)), page(ids=('',)),
    {**page(), 'cantidad': 2}, {**page(), 'municipios': [None]},
])
def test_invalid_dump_is_not_accepted_or_silently_replaced_by_fallback(monkeypatch, payload):
    calls = []
    def download(url):
        calls.append(url)
        return payload
    monkeypatch.setattr(snapshot, 'bajar', download)
    with pytest.raises(ValueError):
        snapshot.traer('municipios')
    assert len(calls) == 1


def test_incomplete_dump_fails_closed(monkeypatch):
    monkeypatch.setattr(snapshot, 'bajar', lambda _url: page(total=2))
    with pytest.raises(ValueError, match='dump is incomplete'):
        snapshot.traer('municipios')


def test_short_api_pages_continue_until_exact_total(monkeypatch):
    fallback(monkeypatch, [page(('01',), 2, 0), page(('02',), 2, 1)])
    rows, total, source = snapshot.traer('municipios')
    assert [row['id'] for row in rows] == ['01', '02']
    assert total == 2 and source == 'api'


@pytest.mark.parametrize('pages,reason', [
    ([page(('01',), 2), page((), 2, 1)], 'ended before'),
    ([page(('01',), 2), page(('02',), 3, 1)], 'total changed'),
    ([page(('01',), 2), page(('01',), 2, 1)], 'repeats entities'),
    ([page(('01',), 2), page(('02',), 2, 0)], 'offset does not match'),
    ([page(('01',), 10_001)], 'API window'),
])
def test_incomplete_or_inconsistent_api_never_becomes_complete(monkeypatch, pages, reason):
    fallback(monkeypatch, pages)
    with pytest.raises(ValueError, match=reason):
        snapshot.traer('municipios')


@pytest.mark.parametrize('status', [401, 429, 500])
def test_http_failure_is_not_disguised_as_missing_dump(monkeypatch, status):
    def download(url):
        raise urllib.error.HTTPError(url, status, 'synthetic error', None, None)
    monkeypatch.setattr(snapshot, 'bajar', download)
    with pytest.raises(urllib.error.HTTPError) as error:
        snapshot.traer('municipios')
    assert error.value.code == status


def test_failed_later_download_preserves_existing_reference_and_manifest(tmp_path, monkeypatch):
    target = tmp_path / 'reference'
    target.mkdir()
    (target / 'provincias.json').write_text(json.dumps([{'id': 'old'}]), encoding='utf-8')
    (target / 'MANIFEST.json').write_text('old manifest', encoding='utf-8')
    original = {path.name: path.read_bytes() for path in target.iterdir()}
    def download(resource):
        if resource == 'municipios':
            raise ValueError('incomplete fixture')
        return [{'id': 'new'}], 1, 'volcado'
    monkeypatch.setattr(snapshot, 'traer', download)
    monkeypatch.setattr(sys, 'argv', ['geo_snapshot', '--destino', str(target)])
    with pytest.raises(ValueError, match='incomplete fixture'):
        snapshot.main()
    assert {path.name: path.read_bytes() for path in target.iterdir()} == original


def test_failed_download_does_not_create_new_reference_directory(tmp_path, monkeypatch):
    target = tmp_path / 'not-created'
    def download(_resource):
        raise ValueError('failed fixture')
    monkeypatch.setattr(snapshot, 'traer', download)
    monkeypatch.setattr(sys, 'argv', ['geo_snapshot', '--destino', str(target)])
    with pytest.raises(ValueError):
        snapshot.main()
    assert not target.exists()

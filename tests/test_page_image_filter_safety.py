import json
import sys

import pytest

from scripts import apply_page_image_filter as tool


def test_frequency_alone_never_removes_shared_render(tmp_path):
    path = tmp_path / 'rows.jsonl'
    path.write_text(''.join(json.dumps({'canonical_agency_id': 'one',
                                       'imagenes': ['https://a.test/render.jpg', 'https://a.test/footer.png']})
                            + '\n' for _ in range(12)), encoding='utf-8')
    assert tool.compartidas_por_agencia(path) == {'one': {'https://a.test/footer.png'}}


@pytest.mark.parametrize('target', ['input', 'existing'])
def test_cleanup_cannot_overwrite_input_or_previous_output(monkeypatch, tmp_path, target):
    source = tmp_path / 'source.jsonl'
    output = source if target == 'input' else tmp_path / 'existing.jsonl'
    source.write_text('original', encoding='utf-8')
    output.write_text('original', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['filter', '--entrada', str(source), '--salida', str(output), '--aplicar'])
    with pytest.raises(SystemExit):
        tool.main()
    assert source.read_text() == 'original'
    assert output.read_text() == 'original'


def test_malformed_input_is_not_silently_dropped(tmp_path):
    source = tmp_path / 'source.jsonl'
    source.write_text('{}\nnot-json\n', encoding='utf-8')
    with pytest.raises(ValueError, match='invalid JSON at row 2'):
        list(tool.leer(source))


def test_fingerprint_failure_does_not_create_clean_artifact(monkeypatch, tmp_path):
    source = tmp_path / 'source.jsonl'
    source.write_text(json.dumps({'imagenes': []}), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['filter', '--entrada', str(source), '--aplicar'])
    with pytest.raises(ValueError, match='cannot recompute fingerprint'):
        tool.main()
    assert not source.with_suffix('.limpio.jsonl').exists()
    assert not source.with_suffix('.imagenes_descartadas.jsonl').exists()

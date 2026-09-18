"""Offline controls: imports/dry-run are inert, discovery fetches fail closed."""
import gzip
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

from scripts import search_provider as sp


@pytest.mark.parametrize('name', ['canario_brave_50', 'canario_brave_50_v2', 'brave_250'])
def test_import_does_not_load_environment(monkeypatch, name):
    import dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **k: pytest.fail('implicit env load'))
    original = Path.read_text

    def guarded(path, *args, **kwargs):
        if path.name.startswith('.env'):
            pytest.fail('secret file read during import')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', guarded)
    importlib.reload(importlib.import_module(f'scripts.{name}'))


def test_environment_loader_only_targets_own_worktree(monkeypatch):
    import dotenv
    monkeypatch.delenv('PYTHON_DOTENV_DISABLED', raising=False)
    calls = []
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda path, **kw: calls.append((path, kw)))
    sp.cargar_env_local()
    root = Path(sp.__file__).resolve().parents[1]
    assert calls == [(root / '.env.local', {'override': False}),
                     (root / '.env', {'override': False})]


def test_environment_loader_can_be_disabled_without_io(monkeypatch):
    import dotenv
    monkeypatch.setenv('PYTHON_DOTENV_DISABLED', '1')
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **kw: pytest.fail('env read'))
    sp.cargar_env_local()


def test_dry_run_needs_no_key_or_environment(monkeypatch):
    from scripts import canario_brave_50 as canary
    monkeypatch.setattr(sys, 'argv', ['canary', '--dry-run'])
    monkeypatch.setattr(canary, 'pendientes_de_web', lambda: [])
    monkeypatch.setattr(canary.sp, 'cargar_env_local', lambda: pytest.fail('env read'))
    monkeypatch.setattr(canary.sp, 'Brave', lambda: pytest.fail('provider started'))
    assert canary.main() == 0


class Response(io.BytesIO):
    url = 'https://agency.test/own'
    status = 200

    def __init__(self, data, encoding=''):
        super().__init__(data)
        self.headers = {'Content-Encoding': encoding}

    def geturl(self):
        return self.url


@pytest.mark.parametrize('name', ['canario_brave_50', 'canario_brave_50_v2', 'run_web_discovery'])
@pytest.mark.parametrize('body,encoding', [(b'x' * 400_001, ''),
                                          (gzip.compress(b'x' * 500_000), 'gzip')],
                         ids=['oversized', 'gzip-expansion'])
def test_oversized_or_expanding_response_is_not_verified(monkeypatch, name, body, encoding):
    module = importlib.import_module(f'scripts.{name}')
    monkeypatch.setattr(module, 'secure_urlopen', lambda *a, **kw: Response(body, encoding))
    assert module.bajar('https://agency.test/own').http is None


@pytest.mark.parametrize('name', ['canario_brave_50', 'canario_brave_50_v2', 'run_web_discovery'])
def test_local_destination_is_rejected_before_connection(monkeypatch, name):
    import urllib.request
    module = importlib.import_module(f'scripts.{name}')
    monkeypatch.setattr(urllib.request, 'build_opener', lambda *a: pytest.fail('connection attempted'))
    assert module.bajar('http://127.0.0.1/private').http is None


@pytest.mark.parametrize('name', ['canario_brave_50', 'canario_brave_50_v2', 'run_web_discovery'])
def test_valid_bounded_response_keeps_final_url(monkeypatch, name):
    module = importlib.import_module(f'scripts.{name}')
    monkeypatch.setattr(module, 'secure_urlopen',
                        lambda *a, **kw: Response(b'<title>Agency</title><p>catalog</p>'))
    candidate = module.bajar('https://agency.test')
    assert candidate.http == 200
    assert candidate.url == Response.url
    assert candidate.titulo == 'Agency'


@pytest.mark.parametrize('name', ['canario_brave_50', 'canario_brave_50_v2'])
def test_provider_failure_is_partial_not_success(monkeypatch, tmp_path, capsys, name):
    module = importlib.import_module(f'scripts.{name}')
    row = {'stable_id': 'one', 'nombre_original': 'Agency', 'avisos_observados': 1}
    monkeypatch.setattr(sys, 'argv', ['canary'])
    monkeypatch.setattr(module.sp, 'cargar_env_local', lambda: None)
    monkeypatch.setattr(module.sp.Brave, 'disponible', lambda self: True)
    monkeypatch.setattr(module, 'SALIDA', tmp_path / 'result.jsonl')
    if name.endswith('_v2'):
        prior = tmp_path / 'prior.jsonl'
        prior.write_text(json.dumps({'agency_id': 'one', 'source_class': 'REVIEW_REQUIRED'}))
        monkeypatch.setattr(module, 'V1', prior)
        monkeypatch.setattr(module, 'padron_por_id', lambda: {'one': row})
    else:
        monkeypatch.setattr(module, 'pendientes_de_web', lambda: [row])
        monkeypatch.setattr(module, 'seleccionar', lambda rows: rows)

    def failed(*args):
        raise RuntimeError('provider unavailable')

    monkeypatch.setattr(module, 'resolver', failed)
    assert module.main() == 2
    assert 'RUN_STATUS                   PARTIAL' in capsys.readouterr().out


def test_larger_discovery_batch_does_not_report_unprocessed_as_resolved(monkeypatch, tmp_path, capsys):
    from scripts import brave_250 as batch
    monkeypatch.setattr(batch.sp, 'cargar_env_local', lambda: None)
    monkeypatch.setattr(batch.sp.Brave, 'disponible', lambda self: True)
    monkeypatch.setattr(batch.canario, 'padron_por_id', lambda: {})
    monkeypatch.setattr(batch, 'SALIDA', tmp_path / 'result.jsonl')
    assert batch.correr([{'agency_id': 'absent'}], 0) == 2
    output = capsys.readouterr().out
    assert 'PROCESADAS         0' in output
    assert 'RESUELTAS' not in output

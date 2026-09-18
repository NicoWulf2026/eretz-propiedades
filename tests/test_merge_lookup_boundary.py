import sys
from unittest.mock import Mock

import pytest

from scraper.clients import SupabaseClient


def client_with_rows(rows):
    session = Mock()
    session.get.return_value.status_code = 200
    session.get.return_value.json.return_value = rows
    return SupabaseClient(session, 'https://database.test', 'test-only-placeholder')


def test_package_method_does_not_import_top_level_models(monkeypatch):
    monkeypatch.setitem(sys.modules, 'models', None)
    client = client_with_rows([])
    assert client._fetch_merge_candidates([]) == []
    client.session.get.assert_not_called()


@pytest.mark.parametrize('rows', [[None], [{'id': 1}, {}], {'items': []}, [{'id': 1}] * 1000])
def test_malformed_or_truncated_identity_lookup_cannot_become_an_insert(rows):
    client = client_with_rows(rows)
    with pytest.raises(RuntimeError):
        client.batch_save_safe_merge([{'url': 'https://agency.test/p/1', 'inmobiliaria_id': 10}],
                                    source_id=10, run_id='test-run')
    client.session.post.assert_not_called()


def test_identity_lookup_error_does_not_echo_response_or_exception():
    client = client_with_rows([])
    client.session.get.side_effect = RuntimeError('do-not-echo-request-secret')
    with pytest.raises(RuntimeError) as error:
        client._fetch_merge_candidates([{'url': 'https://agency.test/p/1'}])
    assert 'do-not-echo' not in str(error.value)
    client.session.get.side_effect = None
    client.session.get.return_value.status_code = 500
    client.session.get.return_value.text = 'do-not-echo-response-secret'
    with pytest.raises(RuntimeError) as error:
        client._fetch_merge_candidates([{'url': 'https://agency.test/p/1'}])
    assert 'do-not-echo' not in str(error.value)


def test_rpc_boolean_is_not_a_valid_audit_count():
    client = client_with_rows([])
    client.session.post.return_value.status_code = 200
    client.session.post.return_value.json.return_value = True
    with pytest.raises(RuntimeError, match='invalid payload'):
        client._call_merge_rpc('record_property_merge_audit', {})

"""Exercise the still-consumed publisher with denied network and mocked REST."""
from unittest.mock import Mock
from functools import lru_cache

import pytest

from scripts.replay_unification_sample import ROOT


@lru_cache(maxsize=1)
def _publisher_code():
    # Compile once; execute into a fresh namespace per test. Parsing the large
    # historical module repeatedly cost ~45s in the eight-test focused block.
    import ast
    from scripts.replay_unification_sample import NoEnvironment
    tree = ast.parse((ROOT / 'scraper/scraper_propiedades.py').read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if isinstance(node, (
        ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))]
    return compile(ast.fix_missing_locations(NoEnvironment().visit(tree)), 'current-publication', 'exec')


@pytest.fixture
def publisher(monkeypatch):
    import types
    from scripts.replay_unification_sample import deny_network
    monkeypatch.setattr('requests.sessions.Session.request', deny_network)
    monkeypatch.setattr('urllib.request.urlopen', deny_network)
    monkeypatch.setattr('socket.create_connection', deny_network)
    module = types.ModuleType('publication_test')
    exec(_publisher_code(), module.__dict__)
    db = object.__new__(module.SupabasePropiedades)
    db.session = Mock()
    db._headers = db._headers_minimal = {}
    db.last_save_protection_stats = {}
    db._sanitize_property_payload = lambda p: dict(p)
    db._get_property_columns = lambda: {'id','hash_dedup','url','url_normalizada','inmobiliaria_id'}
    db._normalize_payload_batch_keys = lambda rows, columns: rows
    db._load_existing_property_by_url_normalizada = lambda *args: None
    db.expected_failure = module.SavePropertiesError
    return db


@pytest.mark.parametrize('operation', [None, 'desconocida', 'proyecto', 'venta', 'consultar'])
def test_actual_rest_sanitizer_obeys_public_operation_enum(publisher, operation):
    from scraper.models import operation_for_storage
    publisher._get_property_columns = lambda: {'titulo', 'operacion'}
    # The fixture's method is a mock for unrelated identity tests. Bind the
    # actual class implementation here without importing the .env bootstrap.
    result = type(publisher)._sanitize_property_payload(
        publisher, {'titulo': 'Casa real', 'operacion': operation})
    assert result['titulo'] == 'Casa real'
    assert result['operacion'] == operation_for_storage(operation)


def prop(**changes):
    row = dict(inmobiliaria_id=7, hash_dedup='fixture', url='https://official.test/propiedad/123',
               url_normalizada='official.test/propiedad/123', id_externo='123')
    row.update(changes)
    return row


def response(rows, content_range='0-0/1', status=200):
    return Mock(status_code=status, headers={'Content-Range': content_range},
                json=Mock(return_value=rows), text='NEVER_LOG_THIS_BODY')


@pytest.mark.parametrize('bad_response', [
    response([], '*/0', 500), response({'error': 'not a list'}),
    response([None]), response([prop(id=True)]), response([prop(id=1, inmobiliaria_id=8)]),
    response([prop(id=1)], '0-0/*'), response([prop(id=1)], '0-2/3'),
    response([], '*/1'), response([prop(id=1)], ''),
])
def test_identity_failure_never_becomes_a_new_property_write(publisher, bad_response, caplog):
    publisher.session.get.return_value = bad_response
    with pytest.raises(publisher.expected_failure, match='identity_lookup') as error:
        publisher.save_propiedades([prop()])
    assert publisher.last_save_result['failed'] == 1
    assert 'NEVER_LOG_THIS_BODY' not in str(error.value) + caplog.text
    publisher.session.post.assert_not_called()
    publisher.session.patch.assert_not_called()


def test_network_exception_details_never_leak_or_permit_write(publisher, caplog):
    publisher.session.get.side_effect = RuntimeError('SECRET_EXCEPTION_DETAILS')
    with pytest.raises(publisher.expected_failure, match='identity_lookup_failed_RuntimeError') as error:
        publisher.save_propiedades([prop()])
    assert 'SECRET_EXCEPTION_DETAILS' not in str(error.value) + caplog.text
    publisher.session.post.assert_not_called()
    publisher.session.patch.assert_not_called()


@pytest.mark.parametrize('agency', [None, 0, -1, True, 'not-an-id', '²'])
def test_invalid_agency_cannot_skip_identity_lookup_and_insert(publisher, agency):
    with pytest.raises(publisher.expected_failure, match='identity_lookup_invalid_agency'):
        publisher.save_propiedades([prop(inmobiliaria_id=agency)])
    publisher.session.get.assert_not_called()
    publisher.session.post.assert_not_called()
    publisher.session.patch.assert_not_called()


def test_exact_empty_inventory_is_a_valid_identity_lookup(publisher):
    publisher.session.get.return_value = response([], '*/0')
    assert publisher.get_existing_properties_for_dedup([prop()])['by_hash'] == {}


def test_server_short_page_does_not_truncate_identity_inventory(publisher):
    publisher.session.get.side_effect = [response([prop(id=1)], '0-0/2', 206),
        response([prop(id=2, hash_dedup='second', url='https://official.test/p/2',
                       url_normalizada='official.test/p/2')], '1-1/2')]
    result = publisher.get_existing_properties_for_dedup([prop()])
    assert set(result['by_hash']) == {'fixture', 'second'}
    assert [call.kwargs['params']['offset'] for call in publisher.session.get.call_args_list] == [0, 1]
    assert all(call.kwargs['headers']['Prefer'] == 'count=exact'
               for call in publisher.session.get.call_args_list)


@pytest.mark.parametrize('second', [response([prop(id=2)], '1-1/3'),
                                    response([prop(id=1)], '1-1/2')])
def test_changed_inventory_or_repeated_page_is_not_complete(publisher, second):
    publisher.session.get.side_effect = [response([prop(id=1)], '0-0/2', 206), second]
    with pytest.raises(publisher.expected_failure, match='identity_lookup'):
        publisher.save_propiedades([prop()])
    publisher.session.post.assert_not_called()
    publisher.session.patch.assert_not_called()


def test_unresolved_unique_collision_never_counts_as_successful_publication(publisher):
    publisher.get_existing_properties_for_dedup = lambda rows: {'by_hash': {}}
    publisher.session.post.return_value = Mock(status_code=409,
        text='idx_propiedades_unique_inmobiliaria_url_normalizada url_normalizada')
    with pytest.raises(publisher.expected_failure, match='save_failed'):
        publisher.save_propiedades([prop()])
    assert publisher.last_save_result['failed'] == 1
    assert publisher.last_save_result['unchanged'] == 0
    publisher.session.patch.assert_not_called()


@pytest.mark.parametrize('other', [prop(id=2), prop(id=1, inmobiliaria_id=8)])
def test_conflicting_identifiers_never_select_first_row_or_write(publisher, other):
    key = (7, 'official.test/propiedad/123')
    publisher.get_existing_properties_for_dedup = lambda rows: {
        'by_hash': {'fixture': other}, 'by_url_all': {key: [prop(id=1)]}}
    with pytest.raises(publisher.expected_failure, match='ambiguous_identity'):
        publisher.save_propiedades([prop()])
    assert publisher.last_save_result['failed'] == 1
    publisher.session.post.assert_not_called()
    publisher.session.patch.assert_not_called()

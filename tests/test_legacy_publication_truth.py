"""Exercise the still-consumed publisher with denied network and mocked REST."""
from unittest.mock import Mock

import pytest

from scripts.replay_unification_sample import ROOT


@pytest.fixture
def publisher(monkeypatch):
    # AST import avoids legacy bootstrap/.env while testing actual current code.
    import ast
    import types
    from scripts.replay_unification_sample import NoEnvironment, deny_network
    monkeypatch.setattr('requests.sessions.Session.request', deny_network)
    monkeypatch.setattr('urllib.request.urlopen', deny_network)
    monkeypatch.setattr('socket.create_connection', deny_network)
    tree = ast.parse((ROOT / 'scraper/scraper_propiedades.py').read_text(encoding='utf-8'))
    tree.body = [node for node in tree.body if isinstance(node, (
        ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign))]
    module = types.ModuleType('publication_test')
    exec(compile(ast.fix_missing_locations(NoEnvironment().visit(tree)), 'current-publication', 'exec'), module.__dict__)
    db = object.__new__(module.SupabasePropiedades)
    db.session = Mock()
    db._headers = db._headers_minimal = {}
    db._sanitize_property_payload = lambda p: dict(p)
    db._get_property_columns = lambda: {'id','hash_dedup','url','url_normalizada','inmobiliaria_id'}
    db._normalize_payload_batch_keys = lambda rows, columns: rows
    db._load_existing_property_by_url_normalizada = lambda *args: None
    db.expected_failure = module.SavePropertiesError
    return db


def prop(**changes):
    row = dict(inmobiliaria_id=7, hash_dedup='fixture', url='https://official.test/propiedad/123',
               url_normalizada='official.test/propiedad/123', id_externo='123')
    row.update(changes)
    return row


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

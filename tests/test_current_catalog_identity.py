from copy import deepcopy

import pytest

from scripts import run_agency_certification_queue as queue
from scripts.agency_fingerprints import FINGERPRINT_SCHEMA_VERSION, strategy_fingerprint


def record():
    return {'resolution': {'resolution_status': 'RESOLVED', 'eretz_id': 7},
            'live': {'validation_status': 'VALIDATED'},
            'source': {'official_url': 'https://official.example.test'},
            'platform': {'web_kind': 'OFFICIAL_WEB'}, 'directory': {}}


def previous(status):
    result = {'canonical_agency_id': 'fixture:agency', 'status': status,
              'certifier_version': queue.CERTIFIER_VERSION}
    if status not in {'IDENTITY_PENDING', 'BLOCKED_EXTERNAL'}:
        result.update(eretz_id=7, connector='generico', connector_version='recorded-code',
                      connector_strategy='generic/html_catalog',
                      fingerprint_schema_version=FINGERPRINT_SCHEMA_VERSION,
                      strategy_fingerprint=strategy_fingerprint('generico', 'generic/html_catalog'),
                      official_url='https://official.example.test')
    return result


@pytest.mark.parametrize('status', ['IDENTITY_PENDING', 'BLOCKED_EXTERNAL'])
def test_newly_ready_identity_reopens_old_identity_only_closure(status):
    assert not queue.is_current_catalog_result(previous(status), record(), 'fixture:agency')


def test_still_pending_identity_does_not_trigger_mass_recertification():
    data = record()
    data['resolution']['resolution_status'] = 'PENDING'
    assert queue.is_current_catalog_result(previous('IDENTITY_PENDING'), data, 'fixture:agency')


def test_still_forbidden_portal_identity_remains_blocked_without_network():
    data = record()
    data['source']['official_url'] = 'https://www.zonaprop.com.ar/inmobiliarias/7'
    data['platform']['web_kind'] = 'EXTERNAL_PORTAL_PROFILE'
    old = previous('BLOCKED_EXTERNAL')
    old['official_url'] = data['source']['official_url']
    assert queue.is_current_catalog_result(old, data, 'fixture:agency')


@pytest.mark.parametrize('change', ['resolution', 'live', 'source', 'portal'])
def test_old_parser_success_requires_current_executable_identity(change):
    data = record()
    if change == 'resolution':
        data['resolution']['resolution_status'] = 'PENDING'
    elif change == 'live':
        data['live']['validation_status'] = 'UNVALIDATED'
    elif change == 'source':
        data['source'].pop('official_url')
    else:
        data['source']['official_url'] = 'https://www.argenprop.com/perfil/7'
    assert not queue.is_current_catalog_result(previous('CERTIFIED_COMPLETE'), data, 'fixture:agency')


def test_current_official_identity_and_code_preserve_current_success():
    data, old = record(), previous('CERTIFIED_COMPLETE')
    before = deepcopy((data, old))
    assert queue.is_current_catalog_result(old, data, 'fixture:agency')
    assert (data, old) == before


@pytest.mark.parametrize('identity', [None, [], {}, {'official_url': 'https://official.example.test'}])
def test_missing_classification_cannot_reuse_success(monkeypatch, identity):
    monkeypatch.setattr(queue, 'resolve_identity', lambda *_: identity)
    assert not queue.is_current_catalog_result(previous('CERTIFIED_COMPLETE'), record(), 'fixture:agency')


def test_identity_exception_is_not_converted_to_no_op_source_guard(monkeypatch):
    def broken(*_):
        raise ValueError('invalid catalog')
    monkeypatch.setattr(queue, 'resolve_identity', broken)
    assert not queue.is_current_catalog_result(previous('CERTIFIED_COMPLETE'), record(), 'fixture:agency')


def test_different_canonical_agency_cannot_borrow_closure():
    assert not queue.is_current_catalog_result(previous('CERTIFIED_COMPLETE'), record(), 'fixture:other')


@pytest.mark.parametrize('url', [None, '', {}, True])
def test_parser_closure_without_observed_source_cannot_borrow_current_url(url):
    old = previous('CERTIFIED_COMPLETE')
    old['official_url'] = url
    assert not queue.is_current_catalog_result(old, record(), 'fixture:agency')


@pytest.mark.parametrize('identifier', [None, 0, True, '7', 8])
def test_parser_closure_cannot_borrow_changed_or_unproven_agency_fk(identifier):
    old = previous('CERTIFIED_COMPLETE')
    old['eretz_id'] = identifier
    assert not queue.is_current_catalog_result(old, record(), 'fixture:agency')


def test_validated_agency_fk_change_invalidates_unchanged_source_and_code():
    data = record()
    data['resolution']['eretz_id'] = 8
    assert not queue.is_current_catalog_result(previous('CERTIFIED_COMPLETE'), data, 'fixture:agency')

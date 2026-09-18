"""Determinism is not permission to stamp a historical run with today's code."""
import copy

import pytest

from scripts.agency_fingerprints import (
    FINGERPRINT_SCHEMA_VERSION, current_code_evidence, strategy_fingerprint,
)
from scripts.backfill_strategy_fingerprints import migrate_result, safe_to_backfill
from scripts.run_agency_certification_queue import is_current_result


def evidence(connector='generico'):
    strategy = 'generic/html_catalog' if connector == 'generico' else connector
    return {'canonical_agency_id': 'fixture:agency', 'status': 'CERTIFIED_COMPLETE',
            'connector': connector, 'connector_strategy': strategy,
            'strategy_fingerprint': strategy_fingerprint(connector, strategy),
            'fingerprint_schema_version': FINGERPRINT_SCHEMA_VERSION,
            'comparison': {'idempotent': True},
            'run1': {'detalles_fallidos': 0}, 'run2': {'detalles_fallidos': 0}}


@pytest.mark.parametrize('connector', ['generico', 'tokko', 'wasi', 'wordpress', 'century21'])
def test_current_registered_code_evidence_does_not_trigger_unnecessary_recertification(connector):
    result = evidence(connector)
    assert current_code_evidence(result)
    assert is_current_result(result, {})


@pytest.mark.parametrize('change', [
    {'fingerprint_schema_version': None}, {'fingerprint_schema_version': 4},
    {'fingerprint_schema_version': True}, {'fingerprint_schema_version': 5.0},
    {'strategy_fingerprint': 'stale'}, {'strategy_fingerprint': None},
    {'fingerprint_backfilled_from_terminal_evidence': True},
    {'fingerprint_backfilled_from_terminal_evidence': 'true'},
    {'connector': []}, {'connector': '../../private'},
    {'connector_strategy': []}, {'connector_strategy': 'generic/unknown'},
    {'publication_mechanism': 'MAPAPROP_HTML'},
])
def test_unproven_or_retroactively_stamped_run_cannot_become_current(change):
    result = {**evidence(), **change}
    original = copy.deepcopy(result)
    assert not current_code_evidence(result)
    assert not safe_to_backfill(result)
    assert not is_current_result(result, {})
    with pytest.raises(ValueError, match='requires recertification'):
        migrate_result(result)
    assert result == original


def test_refresh_keeps_fingerprint_schema_time_status_and_payload_unchanged():
    result = {**evidence(), 'checked_at': '2026-09-18T10:00:00', 'extra': {'test': 'unchanged'}}
    original = copy.deepcopy(result)
    refreshed = migrate_result(result)
    for key, value in original.items():
        assert refreshed[key] == value
    assert result == original
    assert 'fingerprint_backfilled_from_terminal_evidence' not in refreshed
    assert refreshed['operational_metrics_refreshed_without_recertification'] is True


def test_historical_whole_connector_hash_is_not_positive_strategy_evidence():
    result = evidence()
    result.pop('strategy_fingerprint')
    result.pop('fingerprint_schema_version')
    result['connector_version'] = 'historical-code'
    assert not is_current_result(result, {})
    assert not safe_to_backfill(result)


@pytest.mark.parametrize('value', [None, True, [], '0'])
def test_unknown_failure_count_is_not_zero_failures(value):
    result = evidence()
    result['run2']['detalles_fallidos'] = value
    assert not safe_to_backfill(result)


def test_unknown_defect_evidence_does_not_get_success_amnesty():
    from scripts.agency_rollout_preflight import huella_vigente
    assert huella_vigente({'status': 'NEEDS_FIX', 'connector': 'generico'}, {})
    assert huella_vigente({**evidence(), 'status': 'NEEDS_FIX', 'fingerprint_schema_version': 4}, {})

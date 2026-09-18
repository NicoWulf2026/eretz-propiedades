import pytest

from scripts.property_write_canary import Fallo, resolved_main_ids


def resolution(**values):
    return {'canonical_agency_id': 'agency:a', 'resolution_status': 'RESOLVED',
            'eretz_id': 42, 'agency_name': 'Agencia Real', **values}


def test_resolved_main_identity_is_corroborated_not_rematched():
    assert resolved_main_ids([resolution()], [(42, 'AGENCIA REAL')]) == {'agency:a': 42}


def test_staging_and_ambiguous_records_do_not_become_public_fks():
    assert resolved_main_ids([resolution(resolution_status='NOT_FOUND_IN_ERETZ'),
                              resolution(resolution_status='AMBIGUOUS')], [(42, 'Agencia Real')]) == {}


@pytest.mark.parametrize('main', [[], [(42, 'Otra Agencia')], [(99, 'Agencia Real')]])
def test_stale_or_wrong_main_identity_is_refused(main):
    with pytest.raises(Fallo):
        resolved_main_ids([resolution()], main)


@pytest.mark.parametrize('ident', [True, '42', -42, 0, None])
def test_malformed_or_non_main_manifest_ids_are_refused(ident):
    with pytest.raises(Fallo):
        resolved_main_ids([resolution(eretz_id=ident)], [(42, 'Agencia Real')])


def test_two_canonical_agencies_cannot_silently_share_a_main_id():
    with pytest.raises(Fallo):
        resolved_main_ids([resolution(), resolution(canonical_agency_id='agency:b')], [(42, 'Agencia Real')])


def test_duplicate_canonical_records_have_no_last_winner():
    with pytest.raises(Fallo):
        resolved_main_ids([resolution(), resolution(eretz_id=43)], [(42, 'Agencia Real'), (43, 'Agencia Real')])

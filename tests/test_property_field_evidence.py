import pytest

from scripts.artefacto_por_propiedad import NOT_ATTEMPTED, NOT_PROVIDED, estado_del_campo


@pytest.mark.parametrize('state', ['SOURCE_UNKNOWN', 'EXTRACTED', 'unrecognized-state'])
def test_agency_level_presence_does_not_prove_missing_field_absence_on_a_row(state):
    assert estado_del_campo(None, 'provincia', {'provincia': {'state': state}},
                           'https://agency.test/p/1', set()) == NOT_ATTEMPTED


def test_explicit_declared_absence_keeps_its_distinct_state():
    assert estado_del_campo(None, 'provincia', {'provincia': {'state': 'SOURCE_NOT_PROVIDED'}},
                           'https://agency.test/p/1', set()) == NOT_PROVIDED


@pytest.mark.parametrize('value', [True, False])
def test_boolean_never_counts_as_an_extracted_numeric_field(value):
    assert estado_del_campo(value, 'dormitorios', {'dormitorios': {'state': 'EXTRACTED'}},
                           'https://agency.test/p/1', set()) == NOT_ATTEMPTED

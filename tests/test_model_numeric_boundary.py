import pytest

from scraper.models import Propiedad, _safe_int


@pytest.mark.parametrize('value', [True, False, 2.5, '2.5', float('nan'), float('inf'), 2147483648])
def test_room_count_boundary_never_truncates_or_converts_boolean(value):
    assert _safe_int(value) is None


@pytest.mark.parametrize('value,expected', [(None, None), (0, 0), (90.75, 90.75), ('90.75', 90.75)])
def test_surface_boundary_preserves_fraction_and_null_zero(value, expected):
    prop = Propiedad(url='https://agency.test/p/1', titulo='Casa', metros=value)
    assert prop.to_payload()['superficie_total'] == expected


def test_fractional_surface_keeps_the_existing_storage_range_guard():
    prop = Propiedad(url='https://agency.test/p/1', titulo='Casa', metros=3413024001)
    assert prop.to_payload()['superficie_total'] is None


@pytest.mark.parametrize('operation', [None, '', 'desconocida', 'proyecto', 'unknown'])
def test_unknown_operation_keeps_property_and_domain_evidence(operation):
    prop = Propiedad(url='https://agency.test/p/1', titulo='Casa', operacion=operation)
    assert prop.to_payload()['operacion'] is None
    assert prop.operacion == operation


@pytest.mark.parametrize('operation', [
    'venta', 'alquiler', 'alquiler_temporario', 'consultar', 'venta_y_alquiler',
])
def test_known_operation_is_preserved_in_public_storage(operation):
    prop = Propiedad(url='https://agency.test/p/1', titulo='Casa', operacion=operation)
    assert prop.to_payload()['operacion'] == operation

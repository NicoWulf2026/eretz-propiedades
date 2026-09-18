import pytest

from scraper.models import Propiedad, _safe_int


@pytest.mark.parametrize('value', [True, False, 2.5, '2.5', float('nan'), float('inf'), 2147483648])
def test_room_count_boundary_never_truncates_or_converts_boolean(value):
    assert _safe_int(value) is None


@pytest.mark.parametrize('value,expected', [(None, None), (0, 0), (90.75, 90.75), ('90.75', 90.75)])
def test_surface_boundary_preserves_fraction_and_null_zero(value, expected):
    prop = Propiedad(url='https://agency.test/p/1', titulo='Casa', metros=value)
    assert prop.to_payload()['superficie_total'] == expected

import pytest

from scripts.property_contract import estado_de_campo, alcances, EXTRACTED


def property_row(**changes):
    return dict(source_url='https://agency.test/p/1', hash_dedup='identity',
                canonical_agency_id='audit:agency', titulo='Casa', **changes)


@pytest.mark.parametrize('field', ['precio', 'dormitorios', 'banos', 'ambientes',
                                 'superficie_total', 'superficie_cubierta'])
def test_accepted_zero_is_extracted_not_missing(field):
    assert estado_de_campo(property_row(**{field: 0}), field) == EXTRACTED
    assert estado_de_campo(property_row(**{field: None}), field) != EXTRACTED


def test_explicit_zero_price_with_currency_keeps_price_scope():
    assert 'FILTRO_PRECIO' in alcances(property_row(precio=0, moneda='ARS'))[0]
    assert 'FILTRO_PRECIO' not in alcances(property_row(precio=0, moneda=None))[0]


@pytest.mark.parametrize('lat,lon', [(None, None), (0, 0), (float('nan'), -58),
                                  (-34, float('inf')), (40, -58), (True, -58)])
def test_invalid_coordinates_never_grant_map_scope(lat, lon):
    scopes, _ = alcances(property_row(latitud=lat, longitud=lon))
    assert 'MAPA' not in scopes
    assert {'LISTADO', 'FICHA'} <= scopes


def test_real_coordinates_grant_map_scope():
    assert 'MAPA' in alcances(property_row(latitud=-34.6, longitud=-58.4))[0]

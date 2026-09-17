import pytest

from scraper.models import Propiedad
from scraper.safe_merge import prepare_insert_payload


def test_verified_property_does_not_require_price_location_images_or_coordinates():
    prop = Propiedad(url='https://official.test/propiedad/123', titulo='Casa con patio')
    assert prop.is_valid()
    doc = prepare_insert_payload(prop.to_payload())
    assert doc['precio'] is None
    assert doc['direccion'] is None
    assert doc['barrio'] is None
    assert doc['operacion'] == 'desconocida'
    assert doc['latitud'] is doc['longitud'] is None


@pytest.mark.parametrize('url', ['httpwhatever', 'https://', 'https://user:pass@official.test/p/1', '/p/1'])
def test_missing_fields_do_not_relax_url_identity_validation(url):
    assert not Propiedad(url=url, titulo='Casa con patio').is_valid()


@pytest.mark.parametrize('operation,expected', [(None, 'desconocida'), ('UNKNOWN', 'desconocida'),
                                              ('consultar', 'consultar'), ('venta', 'venta')])
def test_unknown_operation_is_not_source_explicit_consultation(operation, expected):
    assert prepare_insert_payload(dict(operacion=operation))['operacion'] == expected


def test_accepted_zero_price_survives_insert_sanitization():
    assert prepare_insert_payload(dict(precio=0, moneda='ARS'))['precio'] == 0
    assert prepare_insert_payload(dict(precio=-1))['precio'] is None
    assert prepare_insert_payload(dict(precio=True))['precio'] is None

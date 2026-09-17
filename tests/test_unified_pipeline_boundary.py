"""Exercise actual raw -> staging and write guards, never a live database."""
from unittest.mock import Mock

import pytest

from scripts import validate_raw_properties as validation
from scripts.ingest_to_pipeline import a_fila_raw, rechazos
from scripts.write_eligibility import motivo_rechazo


def raw(**changes):
    row = dict(id=1, inmobiliaria_id=7, hash_dedup='real-hash',
               titulo='Casa con patio en venta', descripcion='Detalle publicado ' * 150,
               url='https://official.test/propiedad/123', precio=None, moneda=None,
               tipo_propiedad='casa', operacion=None, imagenes=[], datos_extra={})
    row.update(changes)
    return row


@pytest.mark.parametrize('query', ['id=123&id=123', 'id=123&code=456', 'id=123&id=', 'id=123%2F456'])
def test_ambiguous_query_identity_cannot_reach_the_writer(query):
    assert motivo_rechazo({'source_url': f'https://official.test/ficha?{query}',
                           'source_listing_id': '123'}) == 'query_string'


@pytest.fixture(autouse=True)
def no_database(monkeypatch):
    monkeypatch.setattr(validation, 'staging_duplicate_exists', lambda cur, identity: False)


@pytest.mark.parametrize('price', [None, 0, -1, float('nan'), 'bad-price'])
def test_real_property_survives_optional_price_absence_zero_or_invalidity(price):
    stage, issues, duplicate = validation.build_validation(Mock(), raw(precio=price))
    assert stage is not None and not duplicate
    assert stage['precio'] == (0 if price == 0 else None)
    assert stage['operacion'] == 'desconocida'
    assert len(stage['descripcion']) > 1000
    assert stage['imagenes'] == []
    assert stage['latitud'] is stage['longitud'] is None


def test_currency_unknown_does_not_erase_property_or_invent_currency():
    stage, issues, _ = validation.build_validation(Mock(), raw(precio=100000, moneda='???'))
    assert stage['precio'] == 100000 and stage['moneda'] is None
    assert any(i['issue_type'] == 'invalid_currency' for i in issues)


def test_invalid_currency_is_withheld_even_when_price_is_missing():
    stage, issues, _ = validation.build_validation(Mock(), raw(moneda='???'))
    assert stage['precio'] is stage['moneda'] is None
    assert any(i['issue_type'] == 'invalid_currency' for i in issues)


def test_geo_conflict_is_not_reintroduced_by_the_legacy_staging_adapter():
    row = raw(ciudad='Rosario', provincia='Santa Fe', latitud=-34.6, longitud=-58.4,
              datos_extra={'geo': {'estado_geografico': 'GEO_CONFLICT'}})
    stage, issues, _ = validation.build_validation(Mock(), row)
    assert stage is not None
    assert stage['ciudad'] is stage['provincia'] is stage['latitud'] is stage['longitud'] is None
    assert stage['geocoding_status'] == 'skipped'
    assert any(i['issue_type'] == 'geo_conflict' for i in issues)


def test_raw_adapter_keeps_zero_and_unknown_operation_without_dropping_the_property():
    property = dict(hash_dedup='real-hash', inmobiliaria_id=7,
                    source_url='https://official.test/ficha?id=123', precio=0)
    assert rechazos(property) == []
    assert a_fila_raw(property)['operacion'] == 'desconocida'
    assert a_fila_raw(property)['precio'] == 0


def test_known_legacy_query_identity_survives_write_guard_but_search_does_not():
    assert motivo_rechazo(dict(source_url='https://official.test/ficha?id=123',
                               source_listing_id='123')) is None
    assert motivo_rechazo(dict(source_url='https://official.test/ficha?id=123',
                               source_listing_id='different')) == 'query_string'
    assert motivo_rechazo(dict(source_url='https://official.test/buscar-propiedades?sort=newest',
                               source_listing_id='123')) == 'query_string'


@pytest.mark.parametrize('host', ['zonaprop.com.ar', 'argenprop.com', 'facebook.com'])
def test_inventory_from_forbidden_or_nonofficial_sources_is_never_write_eligible(host):
    assert motivo_rechazo(dict(source_url=f'https://{host}/propiedad/123',
                               source_listing_id='123')) == 'fuente_no_oficial'

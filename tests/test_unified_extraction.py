"""Replays use production normalize(), not copied code that tests itself."""
from pathlib import Path

import pytest

from connectors.base import Fuente
from connectors.generico import GenericoConnector, ETIQUETAS_DE_CONTEO, _texto


FIXTURES = Path(__file__).parent / 'fixtures'


def normalize(html):
    cached = type('Cached', (), {'bajar': lambda self, url: html})()
    return GenericoConnector(cached).normalize(
        {'source_listing_id': '618', 'source_url': 'https://ejemplo.test/propiedades/618'},
        Fuente('audit:agency', 'Ejemplo', 'https://ejemplo.test'),
    )


@pytest.mark.parametrize('rooms,bedrooms,bathrooms', [(5, 3, 1), (4, 3, 1), (3, 2, 2)])
def test_real_th_td_family_does_not_shift_neighbors(rooms, bedrooms, bathrooms):
    # Structural pattern observed on Bottega /site/properties/527501 on 2026-09-17.
    html = f'''<html><title>Casa en alquiler</title><main><h1>Casa</h1>
    <p>Descripcion: Amplia casa con 3 dormitorios y patio, zona residencial.</p>
    <table><tr><th>Ambientes</th><td>{rooms}</td></tr>
    <tr><th>Dormitorios</th><td>{bedrooms}</td></tr>
    <tr><th>Baños</th><td>{bathrooms}</td></tr></table>
    {' espacio ' * 45}</main></html>'''
    prop = normalize(html)
    assert prop is not None
    assert (prop.ambientes, prop.dormitorios, prop.banos) == (rooms, bedrooms, bathrooms)


def test_unknown_th_value_cannot_borrow_number_from_neighbor():
    html = '<table><tr><th>Dormitorios</th><td>3</td></tr><tr><th>Ambientes</th><td>X</td></tr></table>'
    assert GenericoConnector._cuenta_de_ficha(html, _texto(html), ETIQUETAS_DE_CONTEO['ambientes'], None) is None


def test_jsonld_amount_can_use_matching_visible_currency():
    prop = normalize((FIXTURES / 'jsonld_price_sin_currency.html').read_text(encoding='utf-8'))
    assert prop is not None
    assert (prop.precio, prop.moneda) == (180000, 'USD')


def test_unrelated_visible_amount_cannot_supply_currency():
    html = (FIXTURES / 'jsonld_price_sin_currency.html').read_text(encoding='utf-8')
    html = html.replace('180.000', '999.000')
    prop = normalize(html)
    assert prop is not None
    assert prop.precio is None
    assert prop.extra['precio_sin_moneda'] == 180000


def test_document_title_supplies_missing_editorial_operation():
    prop = normalize((FIXTURES / 'operacion_solo_en_title.html').read_text(encoding='utf-8'))
    assert prop is not None
    assert prop.operacion == 'venta'


def test_document_title_does_not_override_editorial_operation():
    html = (FIXTURES / 'operacion_solo_en_title.html').read_text(encoding='utf-8')
    prop = normalize(html.replace('z/ EL BRETE. EDIF. EJEMPLO.', 'Casa en alquiler'))
    assert prop.operacion == 'alquiler'
def test_agency_jsonld_does_not_supply_property_title_address_or_evidence():
    from connectors.generico import GenericoConnector
    html = '<script type="application/ld+json">{"@type":"RealEstateAgent", "name":"Agencia", "address":{"addressLocality":"Ciudad ajena"}}</script>'
    assert GenericoConnector._de_json_ld(html) == {}


def test_property_jsonld_type_array_is_supported():
    from connectors.generico import GenericoConnector
    html = '<script type="application/ld+json">{"@type":["Thing","https://schema.org/House"],"name":"Casa real"}</script>'
    assert GenericoConnector._de_json_ld(html)['titulo'] == 'Casa real'


def test_verified_catalogue_property_survives_without_photos_or_price():
    from connectors.generico import GenericoConnector
    assert GenericoConnector._confirma_ficha('', 'Casa en venta', None, [],
                                            catalogo_verificado=True)
    assert not GenericoConnector._confirma_ficha('', 'Casa en venta', None, [],
                                                catalogo_verificado=False)
@pytest.mark.parametrize('attribute', [
    "href='/propiedad/casa-en-venta-123'",
    'data-href="/propiedad/casa-en-venta-123"',
    'data-url="/propiedad/casa-en-venta-123"',
    'onclick="window.location.href=\'/propiedad/casa-en-venta-123\'"',
])
def test_historical_detail_link_capabilities_are_used_by_the_canonical_connector(attribute):
    html = '<article class="property-card"><h3>Casa en venta</h3><b>USD 120000</b><a ' + attribute + '>Ver</a></article>'
    assert GenericoConnector._fichas_en(html, 'https://official.test') == [
        'https://official.test/propiedad/casa-en-venta-123']


def test_recovered_routes_cannot_escape_a_white_label_tenant():
    html = '<article class="property-card"><b>Casa en venta USD 100000</b><a href="https://provider.test/propiedad/casa-en-venta-123">Ver</a></article>'
    assert GenericoConnector._fichas_en(html, 'https://agency.provider.test') == []


def test_recovered_legacy_query_requires_detail_confirmation():
    assert GenericoConnector._solo_por_forma('https://official.test/ficha?id=123', None)


@pytest.mark.parametrize('key', ['id', 'idprop', 'id_prop', 'codigo', 'cod', 'code', 'ficha', 'idFicha', 'pid'])
def test_query_detail_identity_does_not_collapse_every_property_into_ficha_php(key):
    assert GenericoConnector._id_de(f'https://official.test/ficha.php?{key}=123') == '123'
    assert GenericoConnector._id_de(f'https://official.test/ficha.php?{key}=456') == '456'


def test_recovered_query_shape_still_needs_proof_with_a_source_pattern():
    import re
    assert GenericoConnector._solo_por_forma('https://official.test/ficha?id=123', re.compile('/propiedad/'))

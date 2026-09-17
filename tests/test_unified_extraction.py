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

from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_DIR = REPO_ROOT / "scraper"
for path in (REPO_ROOT, SCRAPER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from playwright_scraper import (  # noqa: E402
    extract_candidate_detail_urls_from_card,
    extract_candidate_detail_urls_from_document,
    parse_cards,
)


BASE = "https://demo-inmobiliaria.com"


def _card(inner: str):
    html = f"""
    <article class="property-card">
      <h3>Casa en venta en Centro</h3>
      <strong>USD 120.000</strong>
      <span>80 m2 - 3 ambientes</span>
      <img src="/foto.jpg" />
      {inner}
    </article>
    """
    return BeautifulSoup(html, "html.parser").select_one(".property-card")


def _urls(inner: str):
    return extract_candidate_detail_urls_from_card(_card(inner), BASE)


def test_relative_propiedad_url():
    assert _urls('<a href="/propiedad/casa-en-venta-123">Ver</a>') == [
        f"{BASE}/propiedad/casa-en-venta-123"
    ]


def test_relative_propiedades_url():
    assert _urls('<a href="/propiedades/casa-en-venta-123">Ver</a>') == [
        f"{BASE}/propiedades/casa-en-venta-123"
    ]


def test_relative_ad_url():
    assert _urls('<a href="/ad/casa-en-venta-123">Ver</a>') == [
        f"{BASE}/ad/casa-en-venta-123"
    ]


def test_query_param_idprop():
    assert _urls('<a href="/detalle?idprop=123">Ver</a>') == [
        f"{BASE}/detalle?idprop=123"
    ]


def test_query_param_id():
    assert _urls('<a href="/ficha?id=123">Ver</a>') == [
        f"{BASE}/ficha?id=123"
    ]


def test_query_param_codigo():
    assert _urls('<a href="/ver?codigo=ABC">Ver</a>') == [
        f"{BASE}/ver?codigo=ABC"
    ]


def test_query_param_code_legacy_ficha_php():
    assert _urls('<a href="/motor/ficha.php?code=117-4315">Ver</a>') == [
        f"{BASE}/motor/ficha.php?code=117-4315"
    ]


def test_query_param_idficha_legacy_alias():
    assert _urls('<a href="/detalle.php?idFicha=4315">Ver</a>') == [
        f"{BASE}/detalle.php?idFicha=4315"
    ]


def test_query_param_ficha():
    assert _urls('<a href="/detalle?ficha=123">Ver</a>') == [
        f"{BASE}/detalle?ficha=123"
    ]


def test_query_param_pid():
    assert _urls('<a href="/venta/?pid=123&wplview=property_show">Ver</a>') == [
        f"{BASE}/venta/?pid=123&wplview=property_show"
    ]


def test_data_href():
    assert _urls('<div data-href="/propiedad/departamento-en-venta-123">Ver</div>') == [
        f"{BASE}/propiedad/departamento-en-venta-123"
    ]


def test_data_url():
    assert _urls('<div data-url="/inmueble/departamento-en-venta-123">Ver</div>') == [
        f"{BASE}/inmueble/departamento-en-venta-123"
    ]


def test_onclick_url():
    assert _urls('<button onclick="window.location.href=\'/propiedad/casa-en-venta-123\'">Ver</button>') == [
        f"{BASE}/propiedad/casa-en-venta-123"
    ]


def test_reject_home():
    assert _urls('<a href="/">Inicio</a>') == []


def test_reject_contacto():
    assert _urls('<a href="/contacto">Contacto</a>') == []


def test_reject_blog():
    assert _urls('<a href="/blog/casa-en-venta-123">Blog</a>') == []


def test_reject_editorial_market_article():
    assert _urls(
        '<a href="/mercado-inmobiliario/con-mas-de-100-000-propiedades-en-venta/">'
        "Informe de mercado"
        "</a>"
    ) == []


def test_reject_listado_puro():
    assert _urls('<a href="/propiedades/venta">Venta</a>') == []


def test_reject_empty_code_query():
    assert _urls('<a href="/motor/ficha.php?code=">Ver</a>') == []


def test_reject_short_category_route():
    assert _urls('<a href="/inmuebles/cat/">Categoria</a>') == []


def test_reject_wordpress_property_category_route():
    assert _urls('<a href="/property-category/la-falda/">Categoria</a>') == []


def test_reject_operation_category_routes():
    assert _urls('<a href="/properties/operation/forSale">Venta</a>') == []
    assert _urls('<a href="/properties/operation/forRent">Alquiler</a>') == []
    assert _urls('<a href="/properties/operation/forTemporaryRent">Temporario</a>') == []


def test_reject_prohibited_portal():
    assert _urls('<a href="https://www.zonaprop.com.ar/propiedades/casa-123.html">Ver</a>') == []


def test_reject_internal_link_without_card_signals():
    html = '<nav><a href="/propiedad/casa-en-venta-123">Casa</a></nav>'
    node = BeautifulSoup(html, "html.parser").select_one("nav")
    assert extract_candidate_detail_urls_from_card(node, BASE) == []


def _document_urls(inner: str):
    soup = BeautifulSoup(inner, "html.parser")
    return [url for url, _text in extract_candidate_detail_urls_from_document(soup, BASE)]


def test_document_accepts_public_admin_property_path():
    assert _document_urls('<a href="/admin/web/propiedades/123">Ficha</a>') == [
        f"{BASE}/admin/web/propiedades/123"
    ]


def test_document_accepts_ficha_slug_and_inmueble_underscore():
    assert _document_urls(
        '<a href="/casa-en-venta-ficha-ABC123">Casa</a>'
        '<a href="/inmueble_5971">Inmueble</a>'
    ) == [
        f"{BASE}/casa-en-venta-ficha-ABC123",
        f"{BASE}/inmueble_5971",
    ]


def test_document_accepts_product_and_portfolio_property_paths():
    assert _document_urls(
        '<a href="/producto/casa-en-venta-centro">Casa</a>'
        '<a href="/portfolio_page/departamento-en-venta">Depto</a>'
    ) == [
        f"{BASE}/producto/casa-en-venta-centro",
        f"{BASE}/portfolio_page/departamento-en-venta",
    ]


def test_document_accepts_listing_slug_and_short_d_route():
    assert _document_urls(
        '<a href="/es/listing-palermo-casa-123">Casa</a>'
        '<a href="/d/456-casas-en-pilara">Casa</a>'
    ) == [
        f"{BASE}/es/listing-palermo-casa-123",
        f"{BASE}/d/456-casas-en-pilara",
    ]


def test_document_accepts_contextual_venta_slug_but_rejects_plain_navigation():
    html = """
    <nav><a href="/venta/casas">Casas</a></nav>
    <article class="property-card">
      <strong>USD 100000</strong><span>Casa en venta, 3 ambientes</span>
      <a href="/venta/calle-wilde">Ver ficha</a>
    </article>
    """
    assert _document_urls(html) == [f"{BASE}/venta/calle-wilde"]


def test_document_extracts_data_link_and_embedded_script_url():
    html = """
    <article class="property-card" data-link="/propiedad/casa-123">
      Casa en venta USD 100000
    </article>
    <script>window.__STATE__ = {"url":"/producto/departamento-centro"};</script>
    """
    assert _document_urls(html) == [
        f"{BASE}/propiedad/casa-123",
        f"{BASE}/producto/departamento-centro",
    ]


def test_parse_cards_fast_path_deduplicates_detail_links():
    html = """
    <article class="property-card">
      <strong>USD 100000</strong><span>Casa en venta, 3 ambientes</span>
      <a href="/propiedad/casa-123">Casa</a>
      <a href="/propiedad/casa-123">Ver</a>
    </article>
    """
    properties = parse_cards(html, "venta", "fixture", BASE, "Cordoba")
    assert [prop.url for prop in properties] == [f"{BASE}/propiedad/casa-123"]


def test_parse_cards_keeps_numeric_detail_slug_with_safe_title_fallback():
    html = '<a href="/admin/web/propiedades/12"><img src="/casa.jpg" alt="Casa" /></a>'
    properties = parse_cards(html, "venta", "fixture", BASE, "Cordoba")
    assert [prop.url for prop in properties] == [f"{BASE}/admin/web/propiedades/12"]
    assert properties[0].titulo == "Propiedad 12"


def test_parse_cards_rejects_prohibited_absolute_url_in_segment_fallback():
    html = """
    <a href="https://www.argenprop.com/inmobiliarias/acme/inmuebles/venta?anunciante=123">
      Ver propiedades
    </a>
    """
    properties = parse_cards(html, "venta", "fixture", BASE, "Cordoba")
    assert properties == []


def test_parse_cards_accepts_detail_links_after_canonical_domain_redirect():
    html = """
    <article class="property-card">
      <strong>USD 100000</strong><span>Casa en venta, 3 ambientes</span>
      <a href="https://labatepropiedadesmunro.com.ar/ad/casa-en-venta-en-villa-adelina">
        Casa en venta en Villa Adelina
      </a>
    </article>
    """
    old_base = "http://www.labatepropiedades.com.ar"
    final_base = "https://labatepropiedadesmunro.com.ar"

    assert parse_cards(html, "venta", "fixture", old_base, "Cordoba") == []
    properties = parse_cards(html, "venta", "fixture", final_base, "Cordoba")
    assert [prop.url for prop in properties] == [
        "https://labatepropiedadesmunro.com.ar/ad/casa-en-venta-en-villa-adelina"
    ]


def test_document_rejects_institutional_and_prohibited_urls():
    html = """
    <article class="property-card">Casa en venta USD 100000
      <a href="/contacto">Contacto</a>
      <a href="/tasacion/casa-123">Tasacion</a>
      <a href="https://www.zonaprop.com.ar/propiedad/casa-123">Portal</a>
    </article>
    """
    assert _document_urls(html) == []


def test_document_accepts_repeated_operation_slug_without_broad_navigation_match():
    html = """
    <div><a href="/venta/calle-wilde">Ficha A</a></div>
    <div><a href="/venta/calle-wilde">Ficha A duplicada</a></div>
    <nav><a href="/venta/casas">Casas</a><a href="/venta/casas">Casas</a></nav>
    """
    assert _document_urls(html) == [f"{BASE}/venta/calle-wilde"]


def test_document_accepts_repeated_numeric_realestate_slug():
    html = """
    <div><a href="/238-lotes-country-del-norte">Lote</a></div>
    <div><a href="/238-lotes-country-del-norte">Ver lote</a></div>
    """
    assert _document_urls(html) == [f"{BASE}/238-lotes-country-del-norte"]


def test_document_accepts_legacy_fichashtml_detail_page():
    html = '<a href="/fichashtml/florida1y2.html">Casa en venta Florida USD 100000</a>'
    assert _document_urls(html) == [f"{BASE}/fichashtml/florida1y2.html"]

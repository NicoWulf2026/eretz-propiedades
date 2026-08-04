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
    discover_listing_page_urls,
    extract_candidate_detail_urls_from_card,
    extract_candidate_detail_urls_from_document,
    parse_cards,
)


BASE = "https://demo-inmobiliaria.com"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


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


def test_document_accepts_repeated_branded_reference_slug_from_fixture():
    html = (FIXTURES / "next_branded_reference_cards.html").read_text(
        encoding="utf-8"
    )

    assert _document_urls(html) == [f"{BASE}/tringali-1489"]


def test_parse_cards_builds_deterministic_nuxt_click_only_route_from_fixture():
    html = (FIXTURES / "nuxt_click_only_property_card.html").read_text(
        encoding="utf-8"
    )

    properties = parse_cards(html, "venta", "fixture", BASE, "Cordoba")

    assert [prop.url for prop in properties] == [
        f"{BASE}/propiedad/1499-departamento-calle-ledesma-123"
    ]


def test_parse_cards_accepts_relative_ficha_in_location_href_fixture():
    html = (FIXTURES / "onclick_relative_ficha_card.html").read_text(
        encoding="utf-8"
    )

    properties = parse_cards(html, "venta", "fixture", BASE, "Buenos Aires")

    assert [prop.url for prop in properties] == [f"{BASE}/ficha.php?ficha=LOK46"]


def test_listing_discovery_accepts_navigation_and_operation_queries_only():
    html = """
    <nav>
      <a href="/contacto">Contacto</a>
      <a href="/propiedades/casa-123">Detalle</a>
      <a href="/ventas">Ventas</a>
      <a href="/?operacion=Alquiler">Alquileres</a>
    </nav>
    """

    assert discover_listing_page_urls(html, f"{BASE}/propiedades") == [
        f"{BASE}/ventas",
        f"{BASE}/?operacion=Alquiler",
    ]


def test_document_accepts_legacy_fichashtml_detail_page():
    html = '<a href="/fichashtml/florida1y2.html">Casa en venta Florida USD 100000</a>'
    assert _document_urls(html) == [f"{BASE}/fichashtml/florida1y2.html"]


def test_document_accepts_descriptive_slug_inside_strong_property_card():
    html = """
    <article class="property-card">
      <a href="/gral-paz-2326-zona-centro-casa-p-h-en-venta/">Ver</a>
      <div>Casa en venta</div>
      <div>USD 120.000</div>
      <img src="/uploads/casa.jpg">
    </article>
    """

    assert _document_urls(html) == [
        f"{BASE}/gral-paz-2326-zona-centro-casa-p-h-en-venta/"
    ]


def test_document_rejects_descriptive_navigation_slug_without_card_signal():
    html = """
    <nav>
      <a href="/guia-para-comprar-casa-en-venta/">Blog</a>
    </nav>
    """

    assert _document_urls(html) == []


def test_parse_cards_uses_strong_card_text_when_first_detail_anchor_is_an_image():
    html = """
    <article class="property-card">
      <a href="/propiedad?id=7936107"><img src="/uploads/casa.jpg"></a>
      <h2>Casa 6 ambientes con jardin en Florida</h2>
      <div>Venta USD 350.000</div>
      <a href="/propiedad?id=7936107">Mas detalles</a>
    </article>
    """

    properties = parse_cards(
        html,
        "venta",
        "frumento_fixture",
        BASE,
        "Buenos Aires",
    )

    assert len(properties) == 1
    assert properties[0].url == f"{BASE}/propiedad?id=7936107"
    assert "Casa 6 ambientes" in properties[0].titulo


def test_document_duplicate_url_keeps_stronger_context():
    html = """
    <div><a href="/propiedad?id=7936107"><img src="/empty.jpg"></a></div>
    <article class="property-card">
      <h2>Casa 6 ambientes con jardin en Florida</h2>
      <div>Venta USD 350.000</div>
      <a href="/propiedad?id=7936107">Mas detalles</a>
    </article>
    """
    soup = BeautifulSoup(html, "html.parser")

    rows = extract_candidate_detail_urls_from_document(soup, BASE)

    assert rows == [
        (
            f"{BASE}/propiedad?id=7936107",
            "Casa 6 ambientes con jardin en Florida",
        )
    ]


def test_parse_lissa_card_keeps_isolated_card_fields():
    html = """
    <h1>Propiedades</h1>
    <div class="lissa-grid">
      <a href="/propiedades/?id=7806570" class="lissa-card"
         data-tipo="Cochera" data-op="Alquiler">
        <img class="lissa-card-img"
             src="https://static.tokkobroker.com/card-7806570.jpg"
             alt="Cochera en alquiler - tolosa">
        <div class="lissa-card-title">Cochera en alquiler - tolosa</div>
        <div class="lissa-card-addr">4 e 523 y 524</div>
        <div class="lissa-card-spec"><strong>1 Amb.</strong></div>
        <span class="lissa-card-precio">ARS 55.000</span>
      </a>
      <a href="/propiedades/?id=8471096" class="lissa-card"
         data-tipo="Casa" data-op="Venta">
        <img src="https://static.tokkobroker.com/card-8471096.jpg"
             alt="Casa en venta calle 518">
        <div class="lissa-card-title">Casa en venta calle 518</div>
        <span class="lissa-card-precio">ARS 145.000</span>
      </a>
    </div>
    """

    properties = parse_cards(
        html,
        None,
        "lissa_propiedades",
        "https://lissapropiedades.com.ar",
        "La Plata",
    )
    by_url = {prop.url: prop for prop in properties}
    first = by_url["https://lissapropiedades.com.ar/propiedades/?id=7806570"]

    assert len(properties) == 2
    assert first.titulo == "Cochera en alquiler - tolosa"
    assert first.precio == 55000
    assert first.moneda == "ARS"
    assert first.imagenes == ["https://static.tokkobroker.com/card-7806570.jpg"]
    assert "Casa en venta calle 518" not in first.titulo

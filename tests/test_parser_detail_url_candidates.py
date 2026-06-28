from __future__ import annotations

import sys
from pathlib import Path

from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_DIR = REPO_ROOT / "scraper"
for path in (REPO_ROOT, SCRAPER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from playwright_scraper import extract_candidate_detail_urls_from_card  # noqa: E402


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


def test_query_param_ficha():
    assert _urls('<a href="/detalle?ficha=123">Ver</a>') == [
        f"{BASE}/detalle?ficha=123"
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


def test_reject_listado_puro():
    assert _urls('<a href="/propiedades/venta">Venta</a>') == []


def test_reject_prohibited_portal():
    assert _urls('<a href="https://www.zonaprop.com.ar/propiedades/casa-123.html">Ver</a>') == []


def test_reject_internal_link_without_card_signals():
    html = '<nav><a href="/propiedad/casa-en-venta-123">Casa</a></nav>'
    node = BeautifulSoup(html, "html.parser").select_one("nav")
    assert extract_candidate_detail_urls_from_card(node, BASE) == []

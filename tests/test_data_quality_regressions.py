from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_DIR = REPO_ROOT / "scraper"
for path in (REPO_ROOT, SCRAPER_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from extractors import DataCleaner  # noqa: E402
from models import Propiedad  # noqa: E402
from playwright_scraper import parse_cards  # noqa: E402


def test_clean_title_strips_residual_html_and_property_id_markup():
    raw = '<span class="property-id">ID del Inmueble: 2805</span> Casa en venta'

    assert DataCleaner.clean_title(raw) == "Casa en venta"


def test_clean_description_strips_html_before_persisting():
    raw = "<div>Excelente casa familiar con patio, parrilla y cochera.</div>"

    assert DataCleaner.clean_description(raw) == "Excelente casa familiar con patio, parrilla y cochera."


def test_clean_price_rejects_concatenated_outlier_instead_of_persisting_false_value():
    price, currency = DataCleaner.clean_price("USD 100000225000")

    assert price is None
    assert currency == "USD"


def test_propiedad_rejects_generic_fallback_title():
    prop = Propiedad(
        url="https://example.com/propiedad/casa-123",
        titulo="Sin título",
        barrio="Centro",
        tipo_propiedad="casa",
    )

    assert prop.is_valid() is False


def test_parse_cards_uses_url_title_fallback_instead_of_generic_placeholder():
    html = """
    <article class="property-card">
      <strong>USD 100000</strong><span>Casa en venta, 3 ambientes</span>
      <a href="/propiedad/casa-en-venta-centro-123">Ver</a>
    </article>
    """

    properties = parse_cards(html, "venta", "fixture", "https://demo.test", "Cordoba")

    assert len(properties) == 1
    assert properties[0].titulo == "Casa En Venta Centro"
    assert properties[0].is_valid()

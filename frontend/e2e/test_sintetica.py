"""Lo que solo se puede afirmar con la snapshot SINTETICA de QA.

La corre `scripts/qa_navegador_sintetica.py`, que pasa los ids de los casos borde
en ERETZ_E2E_SINTETICA_CASOS. Contra la snapshot servida no hay casos conocidos
y el modulo se saltea.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/")
CASOS = json.loads(os.environ.get("ERETZ_E2E_SINTETICA_CASOS") or "{}")

pytestmark = pytest.mark.skipif(not CASOS, reason="solo con la snapshot sintetica de QA")


@pytest.fixture()
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=True, executable_path=os.environ.get("ERETZ_E2E_CHROMIUM") or None)
        yield instance
        instance.close()


@pytest.fixture()
def page(browser: Browser):
    context = browser.new_context(locale="es-AR", reduced_motion="reduce")
    current = context.new_page()
    current.set_default_timeout(30_000)
    yield current
    context.close()


def test_una_ficha_sin_titulo_muestra_el_titulo_derivado_p9(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/propiedades?q={quote('sin titulo publicado')}", wait_until="domcontentloaded")
    card = page.locator(f'[data-property-id="{CASOS["sin_titulo"]}"]')
    expect(card).to_be_visible(timeout=60_000)
    page.wait_for_load_state("networkidle")
    # La tarjeta muestra tipo y ubicacion; el titulo aparece al ocultarla (y en
    # mapa, favoritos, compartir y el asunto del correo).
    card.get_by_label("Más acciones", exact=True).click()
    card.get_by_text("Ocultar propiedad").click()
    expect(card).to_contain_text("Ocultaste esta propiedad.")
    expect(card).to_contain_text("Casa en venta · Rosario")
    expect(card).not_to_contain_text("Propiedad sin título")

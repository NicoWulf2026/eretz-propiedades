"""Playwright acceptance checks for the private Phase A preview.

The suite never writes to the database and never follows external contact links.
Set ERETZ_E2E_BASE_URL when the local server does not use port 3100.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://localhost:3100").rstrip("/")
AXE_PATH = Path(__file__).parents[1] / "node_modules" / "axe-core" / "axe.min.js"


def app_url(path: str = "/") -> str:
    """Build an application URL without carrying QA access query parameters."""
    return urljoin(f"{BASE_URL}/", path.lstrip("/"))


def activate_interactive_map(page: Page) -> None:
    """Exercise the intentional V2 progressive-map activation contract."""
    activate = page.get_by_role("button", name="Activar ahora")
    if activate.is_visible():
        activate.click()
    expect(page.locator(".leaflet-container")).to_be_visible(timeout=20_000)


@pytest.fixture()
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture()
def page(browser: Browser):
    context = browser.new_context(locale="es-AR", reduced_motion="reduce")
    current = context.new_page()
    current.set_default_timeout(60_000)
    expect.set_options(timeout=60_000)
    yield current
    context.close()


def test_map_first_real_server_flow_and_no_supabase_browser_requests(page: Page) -> None:
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()
    expect(page.locator("[data-property-id]")).to_have_count(24)
    activate_interactive_map(page)
    expect(page.locator(".map-result-indicator")).to_be_visible(timeout=60_000)
    expect(page.locator(".eretz-map-cluster, .eretz-price-marker").first).to_be_visible(timeout=60_000)
    assert not [url for url in requests if "supabase.co" in url or "/rest/v1/" in url]


def test_search_filter_map_area_detail_and_restoration(page: Page) -> None:
    page.goto(BASE_URL, wait_until="domcontentloaded")
    search = page.get_by_role("combobox", name="Buscar por ubicación, dirección, tipo, inmobiliaria, agente o ID")
    search.fill("Palermo")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page).to_have_url(re.compile(r"[?&]q=Palermo(?:&|$)"))
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()

    page.get_by_role("button", name="Filtros", exact=False).click()
    expect(page.get_by_role("dialog", name="Filtros de propiedades")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog", name="Filtros de propiedades")).not_to_be_visible()

    activate_interactive_map(page)
    expect(page.locator(".map-result-indicator")).to_be_visible(timeout=30_000)
    page.locator(".leaflet-control-zoom-in").click()
    area_button = page.get_by_role("button", name="Buscar en esta zona")
    expect(area_button).to_be_visible()
    area_button.click()
    expect(area_button).not_to_be_visible(timeout=30_000)

    first_card = page.locator("[data-property-id] a").first
    expect(first_card).to_be_visible(timeout=60_000)
    first_card.click()
    page.wait_for_url("**/propiedad/**")
    expect(page.get_by_text("Contacto directo")).to_be_visible()
    expect(page.locator("p").filter(has_text=re.compile(r"^ID ERETZ \d+$")).first).to_be_visible()
    page.get_by_role("link", name="Volver a resultados", exact=False).click()
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()
    assert "q=Palermo" in page.url


def test_mobile_map_results_and_missing_property(page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.get_by_role("button", name="Mapa", exact=True)).to_be_visible()
    results_button = page.get_by_role("button", name="Resultados", exact=True)
    results_button.click()
    expect(results_button).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("region", name="Resultados de propiedades")).to_be_visible()
    expect(page.get_by_role("region", name="Explorar en el mapa")).not_to_be_visible()
    expect(page.locator("[data-property-id]").first).to_be_visible(timeout=60_000)
    page.goto(app_url("/propiedad/999999999999"), wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="No encontramos esta propiedad")).to_be_visible()


@pytest.mark.parametrize("width,height", [(390, 844), (1366, 900)])
def test_accessibility_has_no_serious_or_critical_axe_violations(page: Page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.locator(".leaflet-container")).to_be_visible(timeout=20_000)
    page.add_script_tag(path=str(AXE_PATH))
    result = page.evaluate("async () => await axe.run(document, { resultTypes: ['violations'] })")
    severe = [
        violation
        for violation in result["violations"]
        if violation.get("impact") in {"serious", "critical"}
    ]
    assert severe == [], [
        {"id": violation["id"], "impact": violation["impact"], "nodes": len(violation["nodes"])}
        for violation in severe
    ]


@pytest.mark.parametrize("width", [320, 375, 390, 768, 1024, 1366, 1440])
def test_supported_viewports_have_no_horizontal_overflow(page: Page, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()
    dimensions = page.evaluate(
        "() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth })"
    )
    assert dimensions["content"] <= dimensions["viewport"] + 1, dimensions

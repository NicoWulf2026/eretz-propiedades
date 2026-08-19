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
VERCEL_COOKIE_FILE = os.environ.get("ERETZ_E2E_VERCEL_COOKIE_FILE")
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


def load_vercel_qa_cookies() -> list[dict[str, object]]:
    """Load a temporary Netscape cookie jar without exposing its values."""
    if not VERCEL_COOKIE_FILE:
        return []

    cookies: list[dict[str, object]] = []
    for raw_line in Path(VERCEL_COOKIE_FILE).read_text(encoding="utf-8").splitlines():
        line = raw_line.removeprefix("#HttpOnly_")
        if not line or line.startswith("#"):
            continue
        domain, _include_subdomains, path, secure, expires, name, value = line.split("\t", 6)
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure.upper() == "TRUE",
                "httpOnly": raw_line.startswith("#HttpOnly_"),
                "expires": int(expires),
                "sameSite": "Lax",
            }
        )
    return cookies


@pytest.fixture()
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture()
def page(browser: Browser):
    context = browser.new_context(locale="es-AR", reduced_motion="reduce")
    cookies = load_vercel_qa_cookies()
    if cookies:
        context.add_cookies(cookies)
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
    search = page.get_by_role("combobox", name=re.compile(r"Buscá por barrio, ciudad, dirección"))
    search.fill("Palermo")
    page.get_by_role("button", name="Buscar", exact=True).click()
    expect(page).to_have_url(re.compile(r"[?&]q=Palermo(?:&|$)"))
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()

    page.get_by_role("button", name="Más filtros", exact=False).click()
    expect(page.get_by_role("dialog", name="Más filtros de propiedades")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog", name="Más filtros de propiedades")).not_to_be_visible()

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
    expect(page.get_by_role("button", name="Solo mapa", exact=True)).to_be_visible()
    results_button = page.get_by_role("button", name="Solo propiedades", exact=True)
    results_button.click()
    expect(results_button).to_have_attribute("aria-pressed", "true")
    expect(page.get_by_role("region", name="Resultados de propiedades")).to_be_visible()
    expect(page.get_by_role("region", name="Explorar en el mapa")).not_to_be_visible()
    expect(page.locator("[data-property-id]").first).to_be_visible(timeout=60_000)
    page.goto(app_url("/propiedad/999999999999"), wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="No encontramos esta propiedad")).to_be_visible()


def test_three_desktop_views_preserve_filters_url_and_selection(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(app_url("/propiedades?operacion=venta"), wait_until="domcontentloaded")
    expect(page.locator("[data-property-id]")).to_have_count(24)
    buttons = page.get_by_role("group", name="Vista del explorador").get_by_role("button")
    expect(buttons).to_have_count(3)

    first_card = page.locator("[data-property-id]").first
    property_id = first_card.get_attribute("data-property-id")
    first_card.hover()
    expect(first_card).to_have_class(re.compile(r"is-selected"))
    expect(page).to_have_url(re.compile(rf"[?&]seleccion={property_id}(?:&|$)"))

    properties_button = page.get_by_role("button", name="Solo propiedades", exact=True)
    properties_button.click()
    expect(properties_button).to_have_attribute("aria-pressed", "true")
    expect(page).to_have_url(re.compile(r"[?&]modo=results_only(?:&|$)"))
    assert "operacion=venta" in page.url and f"seleccion={property_id}" in page.url
    expect(page.get_by_role("region", name="Resultados de propiedades")).to_be_visible()
    expect(page.get_by_role("region", name="Explorar en el mapa")).not_to_be_visible()

    map_button = page.get_by_role("button", name="Solo mapa", exact=True)
    map_button.click()
    expect(map_button).to_have_attribute("aria-pressed", "true")
    expect(page).to_have_url(re.compile(r"[?&]modo=map_only(?:&|$)"))
    assert "operacion=venta" in page.url and f"seleccion={property_id}" in page.url
    expect(page.get_by_role("region", name="Explorar en el mapa")).to_be_visible()
    expect(page.get_by_role("region", name="Resultados de propiedades")).not_to_be_visible()
    expect(page.locator(".map-view-summary")).to_contain_text("propiedades")

    combined_button = page.get_by_role("button", name="Mapa + propiedades", exact=True)
    combined_button.click()
    expect(combined_button).to_have_attribute("aria-pressed", "true")
    assert "modo=" not in page.url and "operacion=venta" in page.url and f"seleccion={property_id}" in page.url
    expect(page.get_by_role("region", name="Explorar en el mapa")).to_be_visible()
    expect(page.get_by_role("region", name="Resultados de propiedades")).to_be_visible()


@pytest.mark.parametrize("width,height,solo_columns", [(1180, 800, 3), (1366, 768, 4), (1440, 900, 4), (1600, 900, 4)])
def test_desktop_views_density_and_overflow(page: Page, width: int, height: int, solo_columns: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(app_url("/propiedades?tipo=departamento"), wait_until="domcontentloaded")
    expect(page.locator("[data-property-id]")).to_have_count(24)

    combined_columns = page.locator("#property-results").evaluate(
        "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
    )
    assert combined_columns == 2

    page.get_by_role("button", name="Solo propiedades", exact=True).click()
    columns = page.locator("#property-results").evaluate(
        "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
    )
    assert columns == solo_columns

    for label in ("Solo mapa", "Mapa + propiedades"):
        page.get_by_role("button", name=label, exact=True).click()
        dimensions = page.evaluate(
            "() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth })"
        )
        assert dimensions["content"] <= dimensions["viewport"] + 1, {"view": label, **dimensions}


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


def test_filter_panel_keyboard_focus_and_axe(page: Page) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    toggle = page.get_by_role("button", name="Más filtros", exact=False)
    toggle.click()
    panel = page.get_by_role("dialog", name="Más filtros de propiedades")
    expect(panel).to_be_visible()
    expect(page.get_by_role("textbox", name="Provincia")).to_be_focused()
    page.add_script_tag(path=str(AXE_PATH))
    result = page.evaluate("async () => await axe.run(document, { resultTypes: ['violations'] })")
    severe = [v for v in result["violations"] if v.get("impact") in {"serious", "critical"}]
    assert severe == [], [{"id": v["id"], "impact": v["impact"], "nodes": len(v["nodes"])} for v in severe]
    page.keyboard.press("Escape")
    expect(panel).not_to_be_visible()
    expect(toggle).to_be_focused()


@pytest.mark.parametrize("width,height", [(320, 900), (375, 900), (390, 844), (768, 900), (1024, 900), (1180, 800), (1366, 768), (1440, 900), (1600, 900)])
def test_supported_viewports_have_no_horizontal_overflow(page: Page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Encontrá propiedades en el mapa")).to_be_visible()
    dimensions = page.evaluate(
        "() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth })"
    )
    assert dimensions["content"] <= dimensions["viewport"] + 1, dimensions

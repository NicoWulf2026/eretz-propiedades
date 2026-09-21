"""Focused browser acceptance for the API v2 discovery cutover."""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/")


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
    current.set_default_timeout(30_000)
    expect.set_options(timeout=30_000)
    yield current
    context.close()


def open_explorer(page: Page, width: int = 1440) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{BASE_URL}/propiedades", wait_until="domcontentloaded")
    expect(page.locator('input[role="combobox"]')).to_be_visible()
    # The input is server-rendered before its client handlers hydrate.
    page.wait_for_load_state("networkidle")


def query_url(page: Page) -> dict[str, list[str]]:
    return parse_qs(urlparse(page.url).query)


@pytest.mark.parametrize(
    "width,query,expected_name,niveles,ausentes",
    [
        # Cordoba es provincia, municipio Y localidad: los tres niveles
        # existen de verdad y los tres tienen que mostrarse con su nombre.
        (1440, "cór", "Córdoba", ("Municipio", "Provincia", "Localidad"), ()),
        # Rosario NO es una provincia: es municipio y localidad de Santa Fe.
        # Este caso exigia los tres niveles, asi que no podia pasar nunca.
        # Lo comprobado contra el catalogo: `area_nivel = PROVINCIA` no tiene
        # ningun `Rosario`, y esta bien que no lo tenga.
        #
        # Lo que este test protege no es que aparezcan tres niveles, sino que
        # cada nivel que aparece sea real. Por eso ahora tambien se afirma el
        # nivel AUSENTE: si algun dia el autocompletado ofreciera
        # «Provincia Rosario», seria geografia inventada y esto lo muerde.
        (1366, "ros", "Rosario", ("Municipio", "Localidad"), ("Provincia",)),
        (1280, "san", "Sa", ("Municipio", "Provincia", "Localidad"), ()),
    ],
)
def test_accented_api_v2_autocomplete_keeps_real_levels(
    page: Page,
    width: int,
    query: str,
    expected_name: str,
    niveles: tuple[str, ...],
    ausentes: tuple[str, ...],
) -> None:
    console_errors: list[str] = []
    requests: list[str] = []
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("request", lambda request: requests.append(request.url))
    open_explorer(page, width)
    search = page.locator('input[role="combobox"]')
    with page.expect_response(lambda response: "/api/properties/suggestions" in response.url) as response_info:
        search.fill(query)
    assert response_info.value.status == 200
    for nivel in niveles:
        expect(page.get_by_role("option").filter(has_text=nivel).first).to_contain_text(expected_name)
    for nivel in ausentes:
        expect(
            page.get_by_role("option").filter(has_text=nivel).filter(has_text=expected_name)
        ).to_have_count(0)
    assert [url for url in requests if "/api/properties/suggestions" in url]
    assert not [url for url in requests if "supabase.co" in url or "/rest/v1/" in url]
    assert console_errors == []


def test_mouse_keyboard_close_requery_and_typed_url(page: Page) -> None:
    open_explorer(page)
    search = page.locator('input[role="combobox"]')

    search.fill("bue")
    province = page.get_by_role("option").filter(has_text="Provincia").first
    expect(province).to_contain_text("Buenos Aires")
    province.click()
    expect(page.locator('input[name="__suggestion_level"]')).to_have_value("PROVINCIA")

    search.fill("ros")
    expect(page.get_by_role("option").filter(has_text="Localidad").first).to_be_visible()
    search.press("ArrowDown")
    search.press("ArrowDown")
    search.press("Enter")
    expect(page.locator('input[name="__suggestion_level"]')).to_have_value("LOCALIDAD")

    search.fill("cór")
    municipality = page.get_by_role("option").filter(has_text="Municipio").filter(has_text="Córdoba").first
    expect(municipality).to_be_visible()
    search.press("Escape")
    expect(search).to_have_attribute("aria-expanded", "false")
    search.blur()
    search.focus()
    expect(municipality).to_be_visible()
    # Selection is intentionally handled on mousedown so the input cannot blur
    # before the option is chosen. Dispatch that contract directly; a full click
    # can race React replacing the highlighted list item after focus is restored.
    municipality.dispatch_event("mousedown")
    page.get_by_role("button", name="Buscar", exact=True).click()
    page.wait_for_url("**/propiedades?**")
    params = query_url(page)
    assert params["area_nivel"] == ["MUNICIPIO"]
    assert params["area_nombre"] == ["Córdoba"]
    assert params["ubicaciones"] == ["Córdoba"]
    assert "ciudad" not in params


def test_empty_error_and_noncanonical_neighborhood_are_distinct(page: Page) -> None:
    open_explorer(page)
    search = page.locator('input[role="combobox"]')

    search.fill("zzzzzz")
    expect(page.get_by_text("No encontramos sugerencias. Podés buscar igual.")).to_be_visible()

    page.route(
        "**/api/properties/suggestions?q=qa-error-no-cache",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"status":"FAILURE","suggestions":[],"error":{"kind":"NETWORK_ERROR"}}',
        ),
    )
    search.fill("qa-error-no-cache")
    expect(page.get_by_text("No pudimos cargar sugerencias. Podés buscar igual.")).to_be_visible()
    page.unroute("**/api/properties/suggestions?q=qa-error-no-cache")

    search.fill("pal")
    neighborhood = page.get_by_role("option").filter(has_text="Barrio").filter(has_text="Palermo").first
    expect(neighborhood).to_be_visible()
    neighborhood.click()
    expect(page.locator('input[name="__suggestion_canonical"]')).to_have_value("0")
    page.get_by_role("button", name="Buscar", exact=True).click()
    page.wait_for_url("**/propiedades?**")
    params = query_url(page)
    assert params["barrio"] == ["Palermo"]
    assert params["barrio_canonico"] == ["0"]


def test_filter_metadata_enriches_existing_controls_without_changing_values(page: Page) -> None:
    with page.expect_response(lambda response: "/api/properties/filter-metadata" in response.url) as response_info:
        open_explorer(page)
    assert response_info.value.status == 200

    operation = page.locator('select[name="operacion"]')
    expect(operation.locator('option[value="venta"]')).to_have_text("Comprar (42.536)")
    expect(operation.locator('option[value="temporario"]')).to_have_text("Temporario (303)")
    operation.select_option("venta")
    expect(operation).to_have_value("venta")

    page.get_by_role("button", name="Más filtros").click()
    currency = page.locator('select[name="moneda"]')
    expect(currency.locator('option[value="USD"]')).to_have_text("USD (46.361)")
    currency.select_option("USD")
    expect(currency).to_have_value("USD")


def test_filter_metadata_error_keeps_legacy_controls_usable(page: Page) -> None:
    page.route(
        "**/api/properties/filter-metadata",
        lambda route: route.fulfill(
            status=503,
            content_type="application/json",
            body='{"status":"FAILURE","metadata":null,"error":{"kind":"NETWORK_ERROR"}}',
        ),
    )
    open_explorer(page)
    operation = page.locator('select[name="operacion"]')
    expect(operation.locator('option[value="venta"]')).to_have_text("Comprar")
    operation.select_option("venta")
    expect(operation).to_have_value("venta")
    page.get_by_role("button", name="Más filtros").click()
    expect(page.locator(".filter-data-note[role='alert']")).to_contain_text(
        "No pudimos actualizar las cantidades del catálogo"
    )

"""Playwright acceptance checks for the ERETZ calculators.

These routes are fully client-side: no database, no network calls, no secrets.
That makes them the one part of the app that can be exercised end to end without
credentials, so this suite deliberately never touches the catalogue.

Set ERETZ_E2E_BASE_URL when the local server does not use port 3100.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://localhost:3100").rstrip("/")
AXE_PATH = Path(__file__).parents[1] / "node_modules" / "axe-core" / "axe.min.js"

CALCULATORS = [
    "cuota-hipotecaria",
    "capacidad-de-compra",
    "precio-por-m2",
    "gastos-de-operacion",
    "rentabilidad",
]


def app_url(path: str = "/") -> str:
    return urljoin(f"{BASE_URL}/", path.lstrip("/"))


def axe_violations(page: Page) -> list[dict]:
    """Serious and critical violations only; the rest is reported, not enforced."""
    page.add_script_tag(path=str(AXE_PATH))
    result = page.evaluate("async () => await axe.run(document, { resultTypes: ['violations'] })")
    return [v for v in result["violations"] if v["impact"] in {"serious", "critical"}]


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


def test_hub_lists_every_calculator_and_declares_what_is_missing(page: Page) -> None:
    page.goto(app_url("/calculadoras"), wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Calculadoras", exact=True)).to_be_visible()

    for slug in CALCULATORS:
        expect(page.locator(f'a[href="/calculadoras/{slug}"]')).to_be_visible()

    # The absences are published with their reason instead of being omitted.
    expect(page.get_by_role("heading", name="Todavía no están, y por qué")).to_be_visible()
    expect(page.get_by_text("Créditos UVA")).to_be_visible()


@pytest.mark.parametrize("slug", CALCULATORS)
def test_every_calculator_loads_and_makes_no_network_calls(page: Page, slug: str) -> None:
    """The calculators must not reach any backend: the maths is entirely local."""
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    page.goto(app_url(f"/calculadoras/{slug}"), wait_until="networkidle")
    expect(page.locator("h1")).to_be_visible()

    # No API, no Supabase, no third party. Only the app's own assets.
    assert not [
        url
        for url in requests
        if "/api/" in url or "supabase" in url or not url.startswith(BASE_URL)
    ]


def test_mortgage_end_to_end_produces_the_canonical_instalment(page: Page) -> None:
    """USD 100,000 at 6% over 30 years is USD 599.55. A factor-of-100 slip in the
    percentage conversion would show up here and nowhere else in the browser."""
    page.goto(app_url("/calculadoras/cuota-hipotecaria"), wait_until="domcontentloaded")

    page.get_by_label("Monto del préstamo").fill("100000")
    page.get_by_label("Tasa nominal anual").fill("6")
    page.get_by_label("Plazo").select_option("360")

    expect(page.locator(".calc-result-value")).to_have_text("USD 599,55")
    expect(page.get_by_text("Intereses totales")).to_be_visible()
    # The result is never presented as an offer.
    expect(page.get_by_text("No es una oferta", exact=False)).to_be_visible()


def test_no_rate_is_prefilled(page: Page) -> None:
    """A "reasonable" default would carry the authority of a quote while being
    potentially wrong by a lot."""
    page.goto(app_url("/calculadoras/cuota-hipotecaria"), wait_until="domcontentloaded")
    expect(page.get_by_label("Tasa nominal anual")).to_have_value("")
    expect(page.get_by_label("Monto del préstamo")).to_have_value("")
    expect(page.get_by_text("Completá el monto, la tasa y el plazo", exact=False)).to_be_visible()


def test_invalid_input_is_announced_and_marked(page: Page) -> None:
    page.goto(app_url("/calculadoras/cuota-hipotecaria"), wait_until="domcontentloaded")
    rate = page.get_by_label("Tasa nominal anual")
    rate.fill("500")

    alert = page.locator(".calc-error")
    expect(alert).to_be_visible()
    expect(alert).to_contain_text("100 o menos")
    expect(rate).to_have_attribute("aria-invalid", "true")


def test_result_region_is_announced_to_assistive_technology(page: Page) -> None:
    """The result changes without a reload or a submit, so without aria-live a
    screen-reader user would never learn that it updated."""
    page.goto(app_url("/calculadoras/precio-por-m2"), wait_until="domcontentloaded")
    page.get_by_label("Precio").fill("100000")
    page.get_by_label("Superficie").fill("50")

    value = page.locator(".calc-result-value")
    expect(value).to_have_text("USD 2.000")
    expect(value).to_have_attribute("aria-live", "polite")


def test_keyboard_only_navigation_reaches_the_fields(page: Page) -> None:
    page.goto(app_url("/calculadoras/precio-por-m2"), wait_until="domcontentloaded")

    focused_labels: list[str] = []
    for _ in range(14):
        page.keyboard.press("Tab")
        focused_labels.append(
            page.evaluate(
                "() => { const el = document.activeElement;"
                " return el ? (el.getAttribute('aria-label') || el.id || el.tagName) : ''; }"
            )
        )

    # Both inputs are reachable without a mouse.
    reached = page.evaluate(
        "() => Array.from(document.querySelectorAll('.calc-field input, .calc-field select'))"
        ".every(el => el.tabIndex >= 0)"
    )
    assert reached
    assert focused_labels


@pytest.mark.parametrize("slug", CALCULATORS)
def test_calculators_have_no_serious_or_critical_axe_violations(page: Page, slug: str) -> None:
    page.goto(app_url(f"/calculadoras/{slug}"), wait_until="domcontentloaded")
    assert axe_violations(page) == []


def test_hub_has_no_serious_or_critical_axe_violations(page: Page) -> None:
    page.goto(app_url("/calculadoras"), wait_until="domcontentloaded")
    assert axe_violations(page) == []


def test_error_state_has_no_serious_or_critical_axe_violations(page: Page) -> None:
    """An error state is a different rendering and deserves its own check."""
    page.goto(app_url("/calculadoras/rentabilidad"), wait_until="domcontentloaded")
    page.get_by_label("Meses vacíos por año").fill("15")
    expect(page.locator(".calc-error")).to_be_visible()
    assert axe_violations(page) == []


@pytest.mark.parametrize(("width", "height"), [(1280, 800), (1440, 900), (1920, 1080)])
def test_desktop_widths_have_no_horizontal_overflow(page: Page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(app_url("/calculadoras/gastos-de-operacion"), wait_until="domcontentloaded")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0

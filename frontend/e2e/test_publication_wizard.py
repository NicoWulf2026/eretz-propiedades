"""Playwright checks for the internal publication wizard.

The wizard lives behind ERETZ_PUBLICATION_WIZARD_PREVIEW and is never linked
from public navigation. It writes nothing: the draft stays in this browser.

Requires the server to run with the flag on. Skipped otherwise, so the suite
stays green in an environment where the wizard is (correctly) off.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urljoin

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://localhost:3100").rstrip("/")
AXE_PATH = Path(__file__).parents[1] / "node_modules" / "axe-core" / "axe.min.js"
WIZARD_PATH = "/internal/publicar-preview"


def app_url(path: str = "/") -> str:
    return urljoin(f"{BASE_URL}/", path.lstrip("/"))


def axe_violations(page: Page) -> list[dict]:
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


@pytest.fixture()
def wizard(page: Page) -> Page:
    """Open the wizard, or skip if the flag is off in this environment."""
    response = page.goto(app_url(WIZARD_PATH), wait_until="domcontentloaded")
    if response is not None and response.status == 404:
        pytest.skip("wizard flag is off; nothing to exercise")
    expect(page.get_by_role("heading", name="Publicar una propiedad")).to_be_visible()
    return page


def fill_step_one(page: Page) -> None:
    page.get_by_label("Venta", exact=True).check()
    page.get_by_label("Tipo de propiedad").select_option("departamento")
    page.get_by_role("button", name="Continuar", exact=True).click()


def test_wizard_is_not_linked_from_public_navigation(page: Page) -> None:
    """Nothing must lead a visitor here: it cannot keep its promise yet."""
    page.goto(BASE_URL, wait_until="domcontentloaded")
    assert page.locator(f'a[href*="{WIZARD_PATH}"]').count() == 0
    assert page.get_by_role("link", name="Publicar").count() == 0


def test_wizard_route_is_noindex(page: Page) -> None:
    response = page.goto(app_url(WIZARD_PATH), wait_until="domcontentloaded")
    if response is not None and response.status == 404:
        pytest.skip("wizard flag is off")
    robots = page.locator('meta[name="robots"]').first
    content = robots.get_attribute("content") or ""
    assert "noindex" in content and "nofollow" in content


def test_first_step_blocks_until_completed(wizard: Page) -> None:
    wizard.get_by_role("button", name="Continuar", exact=True).click()
    expect(wizard.get_by_role("heading", name="Qué publicás")).to_be_visible()
    expect(wizard.locator(".pub-error").first).to_be_visible()


def test_draft_survives_a_reload_and_offers_to_continue(wizard: Page) -> None:
    """Nobody should lose a form because they refreshed the page."""
    fill_step_one(wizard)
    wizard.get_by_label("Provincia").fill("Santa Fe")
    wizard.get_by_label("Ciudad").fill("Rosario")
    # Wait past the autosave debounce.
    wizard.wait_for_timeout(1200)

    wizard.reload(wait_until="domcontentloaded")
    expect(wizard.get_by_text("Encontramos un borrador en este dispositivo")).to_be_visible()

    wizard.get_by_role("button", name="Continuar el borrador").click()
    wizard.get_by_role("button", name="Continuar", exact=True).click()
    expect(wizard.get_by_label("Ciudad")).to_have_value("Rosario")


def test_discarding_the_draft_really_clears_it(wizard: Page) -> None:
    fill_step_one(wizard)
    wizard.wait_for_timeout(1200)
    wizard.reload(wait_until="domcontentloaded")

    wizard.get_by_role("button", name="Empezar de cero").click()
    expect(wizard.get_by_label("Tipo de propiedad")).to_have_value("")

    wizard.reload(wait_until="domcontentloaded")
    expect(wizard.get_by_text("Encontramos un borrador en este dispositivo")).to_have_count(0)


def test_review_step_never_offers_a_publish_button(wizard: Page) -> None:
    """There is nowhere to save yet: a publish button would accept someone's
    work in order to lose it."""
    fill_step_one(wizard)
    for _ in range(6):
        wizard.get_by_role("button", name="Continuar", exact=True).click()
        wizard.wait_for_timeout(60)

    # Whatever step we ended on, no publish button exists anywhere.
    assert wizard.get_by_role("button", name="Publicar", exact=True).count() == 0


def test_wizard_has_no_serious_or_critical_axe_violations(wizard: Page) -> None:
    assert axe_violations(wizard) == []


def test_error_state_has_no_serious_or_critical_axe_violations(wizard: Page) -> None:
    wizard.get_by_role("button", name="Continuar", exact=True).click()
    expect(wizard.locator(".pub-error").first).to_be_visible()
    assert axe_violations(wizard) == []


def test_later_step_has_no_serious_or_critical_axe_violations(wizard: Page) -> None:
    fill_step_one(wizard)
    expect(wizard.get_by_role("heading", name="Dónde está")).to_be_visible()
    assert axe_violations(wizard) == []


@pytest.mark.parametrize(("width", "height"), [(1280, 800), (1920, 1080)])
def test_desktop_widths_have_no_horizontal_overflow(page: Page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    response = page.goto(app_url(WIZARD_PATH), wait_until="domcontentloaded")
    if response is not None and response.status == 404:
        pytest.skip("wizard flag is off")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0

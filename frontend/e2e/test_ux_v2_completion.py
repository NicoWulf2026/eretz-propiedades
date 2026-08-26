"""Acceptance checks for the UX/UI V2 completion surfaces that do not require data writes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright


BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/")
AXE_PATH = Path(__file__).parents[1] / "node_modules" / "axe-core" / "axe.min.js"


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
    yield current
    context.close()


def test_mi_eretz_is_local_unified_and_keyboard_navigable(page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/mi-eretz", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="Mi ERETZ")).to_be_visible()
    expect(page.get_by_text("Todo está guardado en este dispositivo.")).to_be_visible()
    guardadas = page.get_by_role("tab", name="Guardadas")
    expect(guardadas).to_have_attribute("aria-selected", "true")
    guardadas.press("ArrowRight")
    expect(page.get_by_role("tab", name="Colecciones")).to_have_attribute("aria-selected", "true")
    expect(page).to_have_url(f"{BASE_URL}/mi-eretz?seccion=colecciones")


@pytest.mark.parametrize("path,heading,search_name", [
    ("/inmobiliarias", "Inmobiliarias", "Buscar inmobiliaria por nombre o ubicación"),
    ("/agentes", "Agentes", "Buscar agente por nombre o ubicación"),
])
def test_professional_directories_have_clear_real_search(page: Page, path: str, heading: str, search_name: str) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=heading)).to_be_visible()
    expect(page.get_by_role("searchbox", name=search_name)).to_be_visible()
    dimensions = page.evaluate("() => ({ viewport: document.documentElement.clientWidth, content: document.documentElement.scrollWidth })")
    assert dimensions["content"] <= dimensions["viewport"] + 1


def test_property_specific_not_found_preserves_a_useful_exit(page: Page) -> None:
    page.goto(f"{BASE_URL}/propiedad/999999999999", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name="No encontramos esta propiedad")).to_be_visible()
    expect(page.get_by_role("link", name="Explorar propiedades")).to_be_visible()


@pytest.mark.parametrize("path", ["/mi-eretz", "/inmobiliarias", "/agentes", "/contacto", "/terminos", "/privacidad"])
def test_completion_routes_have_no_serious_or_critical_axe_violations(page: Page, path: str) -> None:
    page.set_viewport_size({"width": 1180, "height": 800})
    page.goto(f"{BASE_URL}{path}", wait_until="domcontentloaded")
    page.add_script_tag(path=str(AXE_PATH))
    result = page.evaluate("async () => await axe.run(document, { resultTypes: ['violations'] })")
    severe = [item for item in result["violations"] if item.get("impact") in {"serious", "critical"}]
    assert severe == [], [{"id": item["id"], "impact": item["impact"], "nodes": len(item["nodes"])} for item in severe]

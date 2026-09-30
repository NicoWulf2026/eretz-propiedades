"""Accesibilidad automatica (axe-core) de las paginas de escritorio.

axe-core ya viene en node_modules por eslint-plugin-jsx-a11y: no suma dependencias.
Falla ante violaciones SERIAS o CRITICAS, y ante la regresion que se corrigio el
30-09: un <main> adentro de otro (SiteShell ya pone el <main> de la pagina).
Mobile esta congelado: solo escritorio.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright

BASE_URL = os.environ.get("ERETZ_E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/")
AXE = Path(__file__).resolve().parents[1] / "node_modules" / "axe-core" / "axe.min.js"
CASOS = json.loads(os.environ.get("ERETZ_E2E_SINTETICA_CASOS") or "{}")
BLOQUEANTES = {"serious", "critical"}
LANDMARKS = {"landmark-no-duplicate-main", "landmark-main-is-top-level", "landmark-one-main"}

pytestmark = pytest.mark.skipif(not AXE.exists(), reason="falta node_modules/axe-core (npm ci)")

PAGINAS = ["/", "/propiedades", "/propiedades?operacion=venta&tipo=casa", "/calculadoras",
           "/terminos", "/propiedad/ffffffffffffffffffffffffffffffff"]
PAGINAS += [f"/propiedad/{CASOS[c]}" for c in ("combinado", "sin_titulo", "sin_coordenadas") if c in CASOS]


@pytest.fixture(scope="module")
def browser() -> Browser:
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=True, executable_path=os.environ.get("ERETZ_E2E_CHROMIUM") or None)
        yield instance
        instance.close()


@pytest.mark.parametrize("ruta", PAGINAS)
def test_sin_violaciones_serias_ni_mains_anidados(browser: Browser, ruta: str) -> None:
    context = browser.new_context(locale="es-AR", viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        page.goto(f"{BASE_URL}{ruta}", wait_until="networkidle", timeout=60_000)
        page.add_script_tag(path=str(AXE))
        violaciones = page.evaluate(
            "async () => (await axe.run(document, {resultTypes: ['violations']})).violations"
            ".map(v => ({id: v.id, impact: v.impact, nodos: v.nodes.slice(0, 3).map(n => n.target.join(' '))}))")
    finally:
        context.close()
    malas = [v for v in violaciones if v["impact"] in BLOQUEANTES or v["id"] in LANDMARKS]
    assert malas == [], json.dumps(malas, ensure_ascii=False, indent=1)

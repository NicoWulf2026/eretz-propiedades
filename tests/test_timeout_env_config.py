"""Tests para timeouts configurables por env en scraper/scraper_propiedades.py.

Verifica que SCRAPER_TIMEOUT_MULTIPLIER:
- sin env -> valores actuales exactos,
- 1.5 -> valores multiplicados,
- invalida / fuera de rango -> fallback seguro a 1.0,
- no imprime secretos.
"""

import importlib
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# Valores base historicos (deben coincidir con multiplier=1.0)
BASE_ITEM = {
    "CONTROL_ITEM_TIMEOUT_SECONDS": 240,
    "SIMPLE_ITEM_TIMEOUT_SECONDS": 90,
    "CUSTOM_OR_SITEMAP_ITEM_TIMEOUT_SECONDS": 240,
    "PLAYWRIGHT_ITEM_TIMEOUT_SECONDS": 300,
}
BASE_STRATEGY = {
    "tokko_api": 45, "tokko_html": 150, "wordpress_html": 35, "network_intercept": 30,
    "static_html": 35, "static_html_detail": 200, "static_html_tokko_detail": 150,
    "wordpress_sitemap_detail": 90, "wordpress_essential_real_estate_detail": 230,
    "wordpress_estatik_detail": 75, "wordpress_realhomes_detail": 230,
    "wordpress_generic_detail": 65, "custom_listing_detail": 75, "json_ld": 20,
    "sitemap": 200, "html_scraper": 45, "playwright_html": 45,
}


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SCRAPER_TIMEOUT_MULTIPLIER", raising=False)
    else:
        monkeypatch.setenv("SCRAPER_TIMEOUT_MULTIPLIER", value)
    import scraper.scraper_propiedades as mod
    return importlib.reload(mod)


# --- Tests de funciones puras ---
def test_scale_timeout_pura():
    from scraper.scraper_propiedades import _scale_timeout
    assert _scale_timeout(240, 1.0) == 240
    assert _scale_timeout(240, 1.5) == 360
    assert _scale_timeout(90, 2.0) == 180
    assert _scale_timeout(1, 0.0) == 1  # minimo 1s


def test_env_float_fallback(monkeypatch):
    from scraper.scraper_propiedades import _env_float
    monkeypatch.delenv("X_T", raising=False)
    assert _env_float("X_T", 1.0, 0.5, 5.0) == 1.0          # sin env
    monkeypatch.setenv("X_T", "abc")
    assert _env_float("X_T", 1.0, 0.5, 5.0) == 1.0          # no numerica
    monkeypatch.setenv("X_T", "99")
    assert _env_float("X_T", 1.0, 0.5, 5.0) == 1.0          # fuera de rango
    monkeypatch.setenv("X_T", "1.5")
    assert _env_float("X_T", 1.0, 0.5, 5.0) == 1.5          # valida


# 1. Sin env -> valores actuales exactos
def test_sin_env_valores_actuales(monkeypatch):
    mod = _reload(monkeypatch, None)
    for name, base in BASE_ITEM.items():
        assert getattr(mod, name) == base, name
    assert mod.STRATEGY_TIMEOUT_SECONDS == BASE_STRATEGY


# 2. Env 1.5 -> multiplicado
def test_env_multiplicado(monkeypatch):
    mod = _reload(monkeypatch, "1.5")
    assert mod.CONTROL_ITEM_TIMEOUT_SECONDS == 360
    assert mod.SIMPLE_ITEM_TIMEOUT_SECONDS == 135
    assert mod.PLAYWRIGHT_ITEM_TIMEOUT_SECONDS == 450
    assert mod.STRATEGY_TIMEOUT_SECONDS["wordpress_html"] == round(35 * 1.5)
    assert mod.STRATEGY_TIMEOUT_SECONDS["static_html_detail"] == 300


# 3. Env invalida -> fallback (identico al actual)
def test_env_invalida_fallback(monkeypatch):
    mod = _reload(monkeypatch, "no-numero")
    assert mod.CONTROL_ITEM_TIMEOUT_SECONDS == 240
    assert mod.STRATEGY_TIMEOUT_SECONDS == BASE_STRATEGY


# 4. Env fuera de rango -> fallback
@pytest.mark.parametrize("bad", ["0", "0.1", "10", "999"])
def test_env_fuera_de_rango_fallback(monkeypatch, bad):
    mod = _reload(monkeypatch, bad)
    assert mod.CONTROL_ITEM_TIMEOUT_SECONDS == 240


# 5. No se imprimen secretos en el warning de env invalida
def test_no_imprime_secretos(monkeypatch, caplog):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-token-123")
    with caplog.at_level(logging.WARNING):
        _reload(monkeypatch, "abc")  # dispara warning de env invalida
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "super-secret-token-123" not in joined
    assert "abc" not in joined  # tampoco el valor crudo del multiplier


def teardown_module(module):
    # Restaurar el modulo a su estado por defecto (sin env)
    import os
    os.environ.pop("SCRAPER_TIMEOUT_MULTIPLIER", None)
    import scraper.scraper_propiedades as mod
    importlib.reload(mod)

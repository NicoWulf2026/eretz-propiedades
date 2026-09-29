"""Fixtures compartidas de la suite."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _robots_permitido_por_defecto(request, monkeypatch):
    """La suite no sale a leer robots.txt (politica P11).

    Los tests que cuentan conexiones o simulan la red verian un pedido extra a
    /robots.txt. Solo los tests de la politica (`test_robots_*`) la ejercitan.
    """
    if "robots" in request.node.nodeid:
        return
    from connectors.base import Descargador
    monkeypatch.setattr(Descargador, "permite_robots", lambda self, url: True)


# ---------------------------------------------------------------------------
# Datos que viven solo en el nodo LOCAL (arquitectura hibrida, 29-09).
#
# El snapshot de GeoRef (`ERETZ_GEO/`) no esta en el repo. Sin el, la geografia
# compartida no normaliza (a proposito: `base.py` no rompe ni inventa), y un test
# que ejercita esa normalizacion falla con un KeyError o un None que no dicen
# por que. Se marcan con `@pytest.mark.georef` y se saltean con el motivo a la
# vista. En el nodo LOCAL, `ERETZ_REQUIRE_LOCAL_DATA=1` convierte la ausencia en
# fallo: ahi faltar el snapshot es un problema, no una condicion esperada.
# ---------------------------------------------------------------------------
import os  # noqa: E402

EXIGIR_DATOS_LOCALES = os.environ.get("ERETZ_REQUIRE_LOCAL_DATA") == "1"


def hay_georef() -> bool:
    from connectors.geografia import DIRECTORIO_POR_DEFECTO
    return all((DIRECTORIO_POR_DEFECTO / f).exists()
               for f in ("provincias.json", "localidades_censales.json"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "georef: necesita el snapshot local de GeoRef (ERETZ_GEO)")


def pytest_collection_modifyitems(config, items):
    if EXIGIR_DATOS_LOCALES or hay_georef():
        return
    salto = pytest.mark.skip(
        reason="falta el snapshot de GeoRef (dato LOCAL); se baja con "
               "scripts/geo_snapshot.py. ERETZ_REQUIRE_LOCAL_DATA=1 lo exige")
    for item in items:
        if "georef" in item.keywords:
            item.add_marker(salto)

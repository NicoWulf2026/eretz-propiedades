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

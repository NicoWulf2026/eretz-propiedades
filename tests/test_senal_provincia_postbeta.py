"""La senal de provincia publicada no se dispara con palabras que no son la provincia.

Prioridad v6 (04-10): `brick` («Ruta Provincial 36»), `bigsur` («leyes
provinciales vigentes» en el aviso legal, 22 de 22 fichas) y `campal`
(«Provincia NET», el servicio del banco) contaban como provincia publicada y
la ficha quedaba como mal extraida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import source_signals  # noqa: E402


def senal(texto: str) -> bool:
    html = f"<html><body><main><h1>Casa</h1><p>{texto}</p></main></body></html>"
    return source_signals(html, "https://ejemplo.com/p/1")["provincia"]


@pytest.mark.parametrize("texto", [
    "A 2 cuadras de la Ruta Provincial 36",
    "En cumplimiento de las leyes provinciales vigentes que regulan el corretaje",
    "Cajero automatico, Provincia NET y servicios de internet",
    "Banco Provincia a dos cuadras",
])
def test_MUERDE_lo_que_no_es_la_provincia_no_cuenta(texto):
    assert senal(texto) is False


@pytest.mark.parametrize("texto", [
    "Provincia: Buenos Aires",
    "Caceres, B1862 Buenos Aires, Provincia De Buenos Aires, Canning",
])
def test_la_provincia_publicada_sigue_contando(texto):
    assert senal(texto) is True

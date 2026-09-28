"""«Otras propiedades <em>parecidas.</em>» (`moyano`) corta la ficha.

Paro de la familia generico del 28-09 18:49 («second run is not idempotent»):
la unica ficha que cambiaba tomaba «1 baño» / «2 baños» de una tarjeta vecina
elegida al azar en cada carga. Radio: 2 de 197, solo la señal de tipo del
auditor (que venia de las tarjetas) en la misma plataforma.
"""
from __future__ import annotations

import pytest

from connectors.generico import cuerpo_principal

FICHA = "<h1>Fondo de comercio</h1><p>Local listo para abrir.</p>"
TARJETA = '<article class="card"><ul class="specs"><li>2 baños</li></ul></article>'


@pytest.mark.parametrize("encabezado", [
    '<h2 class="h2">Otras propiedades <em>parecidas.</em></h2>',
    "<h5>Otras propiedades</h5>",
    "<h3>Otras propiedades similares:</h3>",
    "<h6 class='heading'>Propiedades parecidas</h6>",
])
def test_las_tarjetas_vecinas_quedan_afuera(encabezado) -> None:
    cuerpo = cuerpo_principal(FICHA + encabezado + TARJETA)
    assert "Local listo para abrir" in cuerpo
    assert "baños" not in cuerpo


def test_una_frase_de_la_ficha_no_corta() -> None:
    html = FICHA + "<p>Otras propiedades del complejo también están en venta.</p>" + TARJETA
    assert "baños" in cuerpo_principal(html)

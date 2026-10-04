"""GVAMAX: el rotulo en una fila de la tabla y el valor en la siguiente.

`flavia caceres` y la familia GVAMAX (10 agencias, 571 fichas sin ciudad, 04-10)
publican <tr><td><strong>Localidad</strong></td></tr><tr><td>Malagueno</td></tr>.
"""
from __future__ import annotations

from connectors.generico import GenericoConnector as G

HTML = ("<table><tr><td><strong>Provincia</strong></td></tr><tr><td>Cordoba</td></tr>"
        "<tr><td><strong>Localidad</strong></td></tr><tr><td>Malagueño</td></tr></table>")


def test_MUERDE_el_valor_en_la_fila_siguiente() -> None:
    assert G._par_rotulado(HTML, "localidad|ciudad") == "Malagueño"
    assert G._par_rotulado(HTML, "provincia") == "Cordoba"


def test_el_valor_en_la_misma_fila_sigue_leyendose() -> None:
    assert G._par_rotulado("<tr><td><strong>Localidad</strong></td><td>Rosario</td></tr>",
                           "localidad|ciudad") == "Rosario"

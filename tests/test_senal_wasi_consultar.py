"""«Precio: Consultar» en el bloque estructurado de Wasi no es un precio provisto.

`casamia` y `domus` (25-09 06:23) publican «Precio de alquiler: Consultar» y
montos en la descripcion (por oficina, alquiler anual): la senal de fuente veia
«$» en el texto, contaba el precio como provisto y las dos agencias seguidas
dispararon el corte por lote que detuvo TODA la cola.
"""
from __future__ import annotations

from scripts.agency_certifier import wasi_source_signals

CONSULTAR = ('<div class="blq_precio"><span>Precio de alquiler:</span> Consultar</div>'
             '<script type="application/ld+json">{"description": "Oficinas desde $ 450.000 '
             'mensuales, alquiler anual con ajuste", "address": {}}</script>'
             '<p>Oficinas desde $ 450.000 mensuales.</p>')
CON_PRECIO = ('<div class="blq_precio"><span>Precio de venta:</span> US$110,000 Dólares</div>'
              '<p>Casa en venta US$110,000</p>')


def test_MUERDE_consultar_en_el_bloque_de_precio_no_es_precio_provisto():
    s = wasi_source_signals(CONSULTAR)
    assert s["precio"] is False and s["moneda"] is False


def test_un_precio_publicado_sigue_siendo_provisto():
    s = wasi_source_signals(CON_PRECIO)
    assert s["precio"] is True

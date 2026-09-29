"""Precio simbolico: «US$1», «USD100», una venta por USD 460.

Medido el 28-09 en los paquetes: 13 fichas en USD <= 100 (venta y alquiler,
`benedetti`, `domus`, `baron`, `pozzobon`...), 26 ventas por menos de USD 1.000
(`blanco`: casas «a 460», «a 559») y 1 en ARS 100. Un alquiler en dolares de
unos cientos por mes (`acevedo` 850, `atencio` 500) es real y no se toca.
"""
from __future__ import annotations

import pytest

from connectors.base import PropiedadNormalizada
from connectors.coherencia import revisar


@pytest.mark.parametrize("precio,moneda,operacion", [
    (1.0, "USD", "venta"), (1.0, "USD", "alquiler"), (100.0, "USD", None),
    (460.0, "USD", "venta"), (999.0, "USD", "venta"), (100.0, "ARS", "venta"),
])
def test_un_precio_simbolico_no_se_afirma(precio, moneda, operacion) -> None:
    p = {"precio": precio, "moneda": moneda, "operacion": operacion}
    assert "precio_simbolico" in revisar(p)
    assert p["precio"] is None and p["moneda"] is None


@pytest.mark.parametrize("precio,moneda,operacion", [
    (850.0, "USD", "alquiler"), (200.0, "USD", "alquiler_temporario"),
    (1000.0, "USD", "venta"), (45000.0, "USD", "venta"), (500000.0, "ARS", "alquiler"),
    (50.0, None, "venta"),
])
def test_un_precio_posible_se_conserva(precio, moneda, operacion) -> None:
    p = {"precio": precio, "moneda": moneda, "operacion": operacion}
    assert "precio_simbolico" not in revisar(p)
    assert p["precio"] == precio


def test_la_construccion_de_cualquier_connector_lo_aplica() -> None:
    prop = PropiedadNormalizada(canonical_agency_id="roomix:x", source_listing_id="1",
                                source_url="https://x.test/p/1", connector="tokko",
                                titulo="Casa", operacion="venta", precio=100.0, moneda="USD")
    assert prop.precio is None and prop.moneda is None
    assert prop.operacion == "venta"
    assert "precio_simbolico" in prop.extra["atributos_descartados"]

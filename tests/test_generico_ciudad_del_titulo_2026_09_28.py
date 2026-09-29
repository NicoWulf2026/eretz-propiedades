"""Ultimo recurso: la ubicacion del titulo «… en Venta en Barrio, Ciudad - …».

Medido el 28-09: 930 fichas sin ciudad con esa forma (ballarre 258 con
«… :: Inmobiliaria Ballarre», lazzaro 118, castro y compania 89...). Solo se
toma una ciudad que el catalogo resuelve como localidad. Radio: 2 de 201.
"""
from __future__ import annotations

import pytest

from connectors.geografia import DIRECTORIO_POR_DEFECTO
from connectors.generico import _ubicacion_del_titulo

pytestmark = pytest.mark.skipif(
    not (DIRECTORIO_POR_DEFECTO / "localidades_censales.json").exists(),
    reason="falta el snapshot de GeoRef; se baja con scripts/geo_snapshot.py")


@pytest.mark.parametrize("titulo,esperado", [
    ("Departamento en Venta en Centro, Mar del Plata - U$S 179.000 | Lazzaro Propiedades",
     ("Centro", "Mar del Plata")),
    ("Casa en Venta en San Martin, Miramar :: Inmobiliaria Ballarre", ("San Martin", "Miramar")),
    ("Casa en Venta en Las Malvinas - Las Malvinas, Villa Carlos Paz", ("Las Malvinas", "Villa Carlos Paz")),
    ("Departamento en venta en La Perla, Mar Del Plata", ("La Perla", "Mar Del Plata")),
])
def test_barrio_y_ciudad_que_la_ficha_titula(titulo, esperado) -> None:
    assert _ubicacion_del_titulo(titulo) == esperado


@pytest.mark.parametrize("titulo", [
    "Oficina en Alquiler en Guemes - Guemes 3154, entre San Lorenzo y Avellaneda",
    "Casa en Venta en Tanti - Tanti, Punilla",          # Punilla es un departamento
    "Duplex en venta en Villa Rosa, Pilar - Condominio",  # hay varios Pilar
    "Casa de 4 ambientes en Barrio La Campiña - Pilar",
    "Venta de Propiedades",
])
def test_lo_que_no_es_una_localidad_no_se_toma(titulo) -> None:
    assert _ubicacion_del_titulo(titulo) == (None, None)

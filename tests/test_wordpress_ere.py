# -*- coding: utf-8 -*-
"""El tema Essential Real Estate de WordPress: moneda posfija y rótulos en
elementos.

`ente inmobiliaria` publica «$990,000 / DOLARES» y «<strong>Property
status</strong><span>En Venta</span>». Guardábamos 990.000 pesos —mil veces
menos— y 49 de 50 fichas sin operación.
"""
from __future__ import annotations

import re

from connectors.wordpress import _moneda_con_posfijo, _rotulo_estructural

RE_PRECIO = re.compile(r"(USD|U\$S|US\$|\$|ARS)\s*([\d][\d.,]{2,15})", re.I)


def _moneda(texto: str) -> str | None:
    return _moneda_con_posfijo(RE_PRECIO.search(texto), texto)


def test_MUERDE_la_moneda_escrita_despues_del_numero_gana_sobre_el_signo():
    assert _moneda("CASA BARRIO DALVIAN $990,000 / DOLARES En Venta") == "USD"
    assert _moneda("Precio $ 350.000 - USD") == "USD"
    assert _moneda("Precio $ 350.000 dólares") == "USD"


def test_sin_palabra_detras_el_signo_sigue_siendo_pesos():
    """La convención del pipeline no cambia: «$» solo es ARS."""
    assert _moneda("Alquiler $ 500.000 por mes") == "ARS"
    assert _moneda("USD 120.000") == "USD"


def test_una_palabra_lejos_del_numero_no_cambia_la_moneda():
    """Treinta caracteres, pegada al número: un «dólares» en la descripción
    no convierte un alquiler en pesos."""
    texto = "Alquiler $ 500.000 por mes, expensas incluidas. Se aceptan dólares"
    assert _moneda(texto) == "ARS"


def test_MUERDE_el_rotulo_en_elementos_se_lee():
    ficha = ('<li><strong>Property status</strong> <span class="ere__property-status">'
             '<a href="/property-status/en-venta/" rel="tag">En Venta</a></span></li>'
             '<div><strong class="mr-2">City/Town</strong> <span>'
             '<a href="/property-city/lujan-de-cuyo/">Luján de Cuyo</a></span></div>')
    assert _rotulo_estructural(ficha, r"Property status") == "En Venta"
    assert _rotulo_estructural(ficha, r"City/Town|Localidad|Ciudad") == "Luján de Cuyo"


def test_un_rotulo_que_no_esta_solo_en_su_elemento_no_se_toma():
    ficha = "<p><strong>Ver Property status abajo</strong><span>En Venta</span></p>"
    assert _rotulo_estructural(ficha, r"Property status") is None

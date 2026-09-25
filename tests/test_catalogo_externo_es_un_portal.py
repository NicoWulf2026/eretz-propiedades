"""Delegar el inventario es enlazar a un PORTAL inmobiliario, no a una red social.

El 25-09, 15 de las 22 agencias BLOCKED_EXTERNAL por «official site delegates
inventory to an external property portal» solo enlazaban WhatsApp, Facebook,
Instagram o Google Maps (`attaguile`, `forja`, `castro`, `gentina`…): el
predicado era el de identidad -«no es web oficial»-, que incluye redes y
agregadores. Asi un sitio que no sabiamos leer quedaba como bloqueo externo.
"""
from __future__ import annotations

import pytest

from scripts.agency_certifier import portal_inmobiliario


@pytest.mark.parametrize("url", [
    "https://www.zonaprop.com.ar/inmobiliarias/acuna_123.html",
    "https://www.argenprop.com/inmobiliaria/davo",
    "https://inmuebles.mercadolibre.com.ar/_CustId_123",
    "https://www.buscainmueble.com/inmobiliarias/x",
])
def test_un_portal_inmobiliario_es_catalogo_externo(url):
    assert portal_inmobiliario(url)


@pytest.mark.parametrize("url", [
    "https://wa.me/5491100000000", "https://api.whatsapp.com/send?phone=1",
    "https://www.facebook.com/forjapropiedades", "https://www.instagram.com/gentina",
    "https://maps.app.goo.gl/abc", "https://www.google.com/maps/place/x",
    "https://policies.google.com/privacy", "https://ru.linkedin.com/in/x",
])
def test_MUERDE_una_red_social_no_es_un_catalogo_externo(url):
    assert not portal_inmobiliario(url)

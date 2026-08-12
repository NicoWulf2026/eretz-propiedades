"""Clasificacion de imagenes que no representan la propiedad.

Los casos salen de la auditoria real sobre el inventario: el problema no eran
solo los logos, sino tiles de mapa, Open Graph del home, samples de theme,
GIFs transparentes, "sinfoto", matriculas y avatares. Casi ninguno contenia la
palabra "logo", por eso el detector anterior no los veia.
"""
import pytest

from scraper.scraper_propiedades import (
    IMAGE_CLASS_HIGH,
    IMAGE_CLASS_POSSIBLE,
    IMAGE_CLASS_VALID,
    classify_property_image,
    is_high_confidence_non_property_image,
)

WP = "https://ejemplo.com.ar/wp-content/uploads/2024/07/"


@pytest.mark.parametrize("url,publisher", [
    # Recursos tecnicamente imposibles de ser la foto de un aviso.
    ("http://{s}.tile.osm.org/{z}/{x}/{y}.png", None),
    ("https://maps.gstatic.com/mapfiles/api-3/images/spotlight-poi3.png", None),
    ("https://ssl.gstatic.com/atari/images/impression-header.png", None),
    # Recursos de plantilla / CMS.
    ("https://bh.com.ar/ing_real_estate_web_base/static/src/img/realestate.jpg", None),
    ("https://meta.com.ar/assets/og/og-home.jpg", None),
    ("https://conectiva.com/wp-content/uploads/2025/07/mt-sample-background.jpg", None),
    # Marcadores semanticos explicitos.
    ("http://ortiz.com.ar/contenido/sinfoto.jpg", None),
    (WP + "losandesdefault.jpg", None),
    ("https://x.com/plugins/jw_sigpro/includes/images/transparent.gif", None),
    (WP + "PROPAR-Avatar-210x210-1.jpg", None),
    (WP + "MATRICULA_HECTOR_LEZCANO.png", None),
    # Branding del publicador: nombre + firma de exportacion de logo.
    ("https://rbessa.com.ar/wp-content/uploads/2022/09/BESSA-BLANCA-FONDOTRANSP542-e1663633539937.png",
     "Inmobiliaria Bessa"),
    (WP + "calicio-blanco.png", "Griselda Calicio Inmobiliaria Propiedades"),
    (WP + "logo-header.png", None),
])
def test_high_confidence(url, publisher):
    cls, reasons, conf = classify_property_image(url, publisher)
    assert cls == IMAGE_CLASS_HIGH, (url, reasons)
    assert reasons
    assert conf >= 0.9
    assert is_high_confidence_non_property_image(url, publisher)


@pytest.mark.parametrize("url,publisher,rep", [
    # Repetidas sin ninguna otra senal: la auditoria mostro que pueden ser
    # legitimas (un loteo compartido entre lotes, una fachada entre unidades).
    ("https://aquino.com.ar/wp-content/uploads/2026/03/Loteo-Sumio-25-1024x745.webp",
     "Pablo Aquino Inmobiliaria", 30),
    ("https://garces.com.ar/wp-content/uploads/2026/06/963eff4d-7dea-4939-9943-244af72094e9-600x600.jpg",
     "Garces Negocios", 18),
    (WP + "fachada-edificio.jpg", "Sur Propiedades", 12),
])
def test_possible_not_high(url, publisher, rep):
    cls, reasons, _ = classify_property_image(url, publisher, rep)
    assert cls == IMAGE_CLASS_POSSIBLE, (url, reasons)
    assert not is_high_confidence_non_property_image(url, publisher, rep)


@pytest.mark.parametrize("url,publisher,rep", [
    ("https://rbessa.com.ar/wp-content/uploads/2024/12/frente.jpeg", "Inmobiliaria Bessa", 0),
    (WP + "casa-frente-jardin.jpg", None, 0),
    # "blanca" en medio del nombre no es variante cromatica de logo.
    (WP + "casa-blanca-frente.jpg", "Inmobiliaria Sur", 0),
    # La palabra generica del rubro no debe disparar el match de publicador.
    ("https://sur.com/uploads/depto-inmobiliaria-vista.jpg", "Inmobiliaria Sur", 0),
    # Repeticion baja: no alcanza ni para POSSIBLE.
    (WP + "living-luminoso.jpg", "Sur Propiedades", 3),
])
def test_valid_images(url, publisher, rep):
    cls, reasons, _ = classify_property_image(url, publisher, rep)
    assert cls == IMAGE_CLASS_VALID, (url, reasons)


def test_empty_and_null():
    for value in ("", "   ", None):
        cls, reasons, _ = classify_property_image(value)
        assert cls == IMAGE_CLASS_HIGH
        assert "empty_url" in reasons


def test_repeticion_sola_nunca_es_high():
    """La regla central: repetir no invalida."""
    cls, _, _ = classify_property_image(WP + "patio-con-parrilla.jpg", "Sur Propiedades", 500)
    assert cls == IMAGE_CLASS_POSSIBLE


def test_publisher_desconocido_no_rompe():
    cls, _, _ = classify_property_image(WP + "frente.jpg", None, 0)
    assert cls == IMAGE_CLASS_VALID

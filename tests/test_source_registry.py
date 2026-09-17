# -*- coding: utf-8 -*-
"""Un host compartido no es un portal, y un portal no es una web propia.

Los dos errores tienen el mismo costo y son opuestos:

  - tratar un perfil de portal como web propia hace que scrapeemos inventario
    ajeno. Medido: 4.007 propiedades de terceros enumeradas desde siete
    fuentes, y más de 27 h de cola parada en 48 h;
  - tratar una web propia como portal apaga a una inmobiliaria real. Pasó al
    escribir este clasificador: las cuatro agencias de
    `tuinmobiliaria.com.ar` quedaron marcadas como perfiles de portal, y
    `aimaropropiedades.tuinmobiliaria.com.ar` es el sitio de AIMARO —su título
    dice "AIMARO PROPIEDADES" y no nombra a ninguna otra—.

El §5 lo dice y aún así caí: **HOST COMPARTIDO ≠ PORTAL**. La regla que lo
separa es mirar el host ENTERO, subdominio incluido, y no sólo el dominio
registrable.
"""
import pytest

from scripts.auditar_source_registry import (EXTERNAL_PORTAL_LISTING,
                                             EXTERNAL_PORTAL_PROFILE,
                                             NO_OFFICIAL_WEB,
                                             OFFICIAL_OFFICE_PAGE,
                                             OFFICIAL_WEB, SOCIAL_ONLY,
                                             clasificar, registrable)


def tipo(nombre, url, vecinas=1):
    por_host = {registrable(url.split("//")[-1].split("/")[0]):
                set(range(vecinas))} if url.startswith("http") else {}
    return clasificar("roomix:x", nombre, url, por_host)


# --- lo que NO se puede scrapear ----------------------------------------

@pytest.mark.parametrize('url', ['https://[broken', 'https://agency.test:bad', 'https://user:pass@agency.test'])
def test_invalid_source_url_never_authorizes_inventory(url):
    assert clasificar('agency', 'Agency', url, {})['inventory_allowed'] is False

@pytest.mark.parametrize("nombre,url", [
    ("ALONSO PROPIEDADES",
     "https://www.buscainmueble.com/inmobiliarias/alonso-propiedades"),
    ("Analia Verga Propiedades",
     "https://www.buscainmueble.com/inmobiliarias/analia-verga-propiedades"),
    ("Calderon Inmobiliaria",
     "https://www.buscainmueble.com/inmobiliarias/calderon-inmobiliaria/inmuebles/alquiler"),
    ("Benjamín Ferreyra Brokers Inmobiliarios",
     "https://proppies.app/inmobiliarias/benjamin-ferreyra-brokers-inmobiliarios-337"),
    ("Emir Elhelou Estudio Inmobiliario",
     "https://www.agroads.com.ar/e/emir-elhelou-estudio-inmobiliario"),
])
def test_los_perfiles_de_portal_no_son_web_propia(nombre, url):
    """Los cinco que pararon la cola. Ninguna lista de hosts los conocía: se
    reconocen por la RUTA, que es una sección de terceros."""
    r = tipo(nombre, url)
    assert r["source_type"] == EXTERNAL_PORTAL_PROFILE
    assert r["inventory_allowed"] is False


def test_una_ficha_suelta_es_todavia_peor_que_un_perfil():
    """`danisa robledo` declaraba como web LA URL DE UNA PROPIEDAD."""
    r = tipo("Danisa Robledo Servicios Inmobiliarios",
             "https://www.mercado-unico.com/propiedades/69019270b5bada00113d470b")
    assert r["source_type"] == EXTERNAL_PORTAL_LISTING
    assert r["inventory_allowed"] is False


def test_una_red_social_no_es_una_web():
    r = tipo("Alguna Propiedades", "https://www.facebook.com/algunaprop")
    assert r["source_type"] == SOCIAL_ONLY
    assert r["inventory_allowed"] is False


# --- lo que SÍ es propio, y el clasificador no puede apagar -------------

def test_un_subdominio_white_label_ES_su_sitio():
    """El error que cometí. `tuinmobiliaria.com.ar` es un proveedor, no un
    marketplace: cada agencia tiene su subdominio con su nombre y su sitio.

    Comparando sólo el dominio registrable, las cuatro agencias del proveedor
    quedaban marcadas como perfiles de portal y se apagaban solas.
    """
    r = tipo("AIMARO PROPIEDADES",
             "https://www.aimaropropiedades.tuinmobiliaria.com.ar/", vecinas=4)
    assert r["source_type"] == OFFICIAL_WEB
    assert r["inventory_allowed"] is True


def test_un_dominio_propio_es_web_propia():
    r = tipo("Brunetti Propiedades", "https://www.brunettipropiedades.com/")
    assert r["source_type"] == OFFICIAL_WEB
    assert r["inventory_allowed"] is True


def test_la_oficina_de_una_red_no_es_un_portal_ajeno():
    """El §5 en su forma más directa: `century21.com.ar/oficina/x` comparte
    host con decenas de agencias y NO es un marketplace. Es su casa dentro de
    su franquicia, y merece una clase propia."""
    r = tipo("Century 21 Alguna", "https://century21.com.ar/agencias/alguna",
             vecinas=40)
    assert r["source_type"] == OFFICIAL_OFFICE_PAGE
    assert r["inventory_allowed"] is False


def test_sin_url_declarada_no_hay_fuente():
    r = tipo("Alguna Propiedades", "")
    assert r["source_type"] == NO_OFFICIAL_WEB
    assert r["inventory_allowed"] is False


def test_port_number_cannot_hide_a_social_or_portal_host():
    assert tipo('Alguna', 'https://facebook.com:443/algunaprop')['source_type'] == SOCIAL_ONLY
    assert tipo('Alguna', 'https://zonaprop.com.ar:443/')['inventory_allowed'] is False


def test_unknown_attribution_is_review_not_inventory_permission():
    assert tipo('Agency', 'https://unrelated.test/')['inventory_allowed'] is False
    assert tipo('Agency', 'https://user:password@agency.test/')['inventory_allowed'] is False


# --- la evidencia, que es lo que hace auditable la decisión -------------

def test_cada_clasificacion_explica_por_que():
    """El §4 prohíbe frases narrativas como INPUT de decisiones, pero exige
    evidencia como SALIDA: sin ella nadie puede discutir una clasificación."""
    for nombre, url in (
            ("ALONSO PROPIEDADES",
             "https://www.buscainmueble.com/inmobiliarias/alonso-propiedades"),
            ("Brunetti Propiedades", "https://www.brunettipropiedades.com/")):
        r = tipo(nombre, url)
        assert r["evidence"] and len(r["evidence"]) > 20
        assert r["confidence"] in ("ALTA", "MEDIA", "BAJA")


def test_el_host_compartido_manda_a_revisar_y_no_condena():
    """Cuatro agencias en un host desconocido, sin ruta de perfil ni nombre en
    el dominio: no alcanza para condenar. Va a revisión."""
    r = tipo("Alguna Propiedades", "https://plataformax.com.ar/sitio/alguna",
             vecinas=6)
    assert r["source_type"] == "IDENTITY_REVIEW"
    assert r["confidence"] == "BAJA"
    assert "NO prueba" in r["evidence"]

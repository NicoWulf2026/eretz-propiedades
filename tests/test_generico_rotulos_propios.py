# -*- coding: utf-8 -*-
"""Lo que la ficha rotula como suyo gana sobre lo que el sitio repite en todas.

Tres casos reales del 2026-09-24:
- `abinmobiliaria.com.ar`: el meta description es el eslogan de la agencia y
  la ficha tiene debajo su «Descripcion de la Propiedad»;
- `cortespropiedades.com.ar`: el h1 es «Cortes Propiedades | Departamento…» y
  la descripcion esta bajo «Descripcion ampliada», dentro de un textarea;
- `baroninmobiliaria.com.ar`: los conteos solo estan en `additionalProperty`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors import base as B  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

RELLENO = "<p>" + "Contacto, horarios y redes de la inmobiliaria. " * 12 + "</p>"
URL = "https://alfa.test/propiedad/123"


class Falso(B.Descargador):
    def __init__(self, html: str):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.html = html

    def bajar(self, url: str) -> str:
        return self.html


def _normalizar(html: str, nombre: str = "Alfa Propiedades"):
    c = GenericoConnector(descargador=Falso(html))
    f = B.Fuente(canonical_agency_id="roomix:alfa propiedades", agency_name=nombre,
                 official_url="https://alfa.test/", inmobiliaria_id=1)
    return c.normalize({"source_url": URL, "source_listing_id": "123"}, f)


def _pagina(cabeza: str = "", cuerpo: str = "") -> str:
    return (f"<html><head>{cabeza}</head><body><main>{cuerpo}"
            f"<p>Precio USD 100.000</p>{RELLENO}</main></body></html>")


ESLOGAN = ('<meta name="description" content="Alfa Propiedades es una inmobiliaria '
           'de la ciudad de Rafaela. Administra y alquila todo tipo de inmuebles.">')
PROPIA = "Se alquila departamento en planta alta con balcon al frente y cocina comedor."


# ---------------------------------------------------------------- descripcion

def test_MUERDE_el_rotulo_de_la_ficha_gana_sobre_el_eslogan_del_meta():
    p = _normalizar(_pagina(ESLOGAN, "<h1>Depto en alquiler</h1>"
                            f"<h3>Descripción de la Propiedad</h3><p>{PROPIA}</p>"))
    assert p.descripcion == PROPIA


def test_sin_rotulo_el_meta_sigue_siendo_la_descripcion():
    p = _normalizar(_pagina(ESLOGAN, "<h1>Depto en alquiler</h1>"))
    assert p.descripcion.startswith("Alfa Propiedades es una inmobiliaria")


def test_si_el_rotulo_es_solo_el_comienzo_del_meta_gana_el_meta():
    meta = ('<meta name="description" content="VENTA - Casa de 4 dormitorios - Roldan. '
            'Propiedad desarrollada en dos plantas con pileta y quincho.">')
    p = _normalizar(_pagina(meta, "<h1>Casa</h1><h3>Descripción</h3>"
                            "<p>VENTA - Casa de 4 dormitorios - Roldan.</p>"))
    assert p.descripcion.endswith("pileta y quincho.")


def test_el_json_ld_sigue_ganando_sobre_rotulo_y_meta():
    ld = ('<script type="application/ld+json">{"@context":"https://schema.org",'
          '"@type":"Product","name":"Casa en venta","description":"Texto del JSON-LD '
          f'con la descripcion publicada.","url":"{URL}"}}</script>')
    p = _normalizar(_pagina(ESLOGAN + ld, f"<h3>Descripción</h3><p>{PROPIA}</p>"))
    assert p.descripcion == "Texto del JSON-LD con la descripcion publicada."


def test_descripcion_ampliada_dentro_de_un_textarea():
    cuerpo = ('<h1>Depto</h1><div class="information-box"><h3>Descripción ampliada </h3>'
              '<div class="box-content"><textarea disabled="disabled">'
              f'{PROPIA}</textarea></div></div><h3>Ubicación</h3>')
    p = _normalizar(_pagina(ESLOGAN, cuerpo))
    assert p.descripcion == PROPIA


def test_MUERDE_un_script_partido_por_la_ventana_no_entra_como_descripcion():
    # `cbdestino.com.ar`: el texto sigue al rotulo sin bloque propio y, mas
    # abajo, un <script> que empieza adentro de la ventana de 6.000 caracteres
    # y cierra afuera. Cortado, perdia su cierre y el codigo pasaba como texto.
    script = "<script>" + "$('#contact_email').attr('placeholder', 'x'); " * 200 + "</script>"
    cuerpo = (f"<h1>Depto</h1><h3>Descripción</h3>{PROPIA} "
              + "Detalles de la ficha. " * 20 + script + "<h3>Contacto</h3>")
    p = _normalizar(_pagina(ESLOGAN, cuerpo))
    assert p.descripcion.startswith(PROPIA)
    assert "contact_email" not in p.descripcion


# --------------------------------------------------------------------- titulo

def test_MUERDE_el_nombre_de_la_agencia_delante_del_titulo_no_tira_el_titulo():
    h1 = ('<h1>\n                        <span>\n                            '
          '<span id="LEmpresa">Alfa Propiedades</span>\n                            |\n'
          '                            <span id="LTitulo">Departamento 1 dormitorio en '
          'villa sarita </span></span>\n                    </h1>')
    p = _normalizar(_pagina("<title>Alfa Propiedades</title>", h1))
    assert p.titulo == "Departamento 1 dormitorio en villa sarita"


def test_un_candidato_limpio_gana_sobre_el_resto_de_otro():
    cabeza = ('<meta property="og:title" content="Alfa Propiedades | Inicio del sitio">'
              "<title>Alfa Propiedades</title>")
    p = _normalizar(_pagina(cabeza, "<h1>Casa con pileta en Centro</h1>"))
    assert p.titulo == "Casa con pileta en Centro"


def test_un_resto_corto_no_se_toma_como_titulo():
    p = _normalizar(_pagina("<title>Alfa Propiedades | Home</title>", ""))
    assert p.titulo == "Alfa Propiedades | Home"


# --------------------------------------------------------- additionalProperty

def _ld(**nodo):
    base = {"@context": "https://schema.org", "@type": "Product",
            "name": "Casa en venta", "url": URL}
    base.update(nodo)
    return ('<script type="application/ld+json">' + json.dumps(base, ensure_ascii=False)
            + "</script>")


def _par(nombre, valor):
    return {"@type": "PropertyValue", "name": nombre, "value": valor}


def test_MUERDE_los_conteos_de_additional_property_se_leen():
    datos = GenericoConnector._de_json_ld(_ld(additionalProperty=[
        _par("Tipo", "Casa"), _par("Ambientes", "4"), _par("Dormitorios", "3"),
        _par("Baños", "2")]), URL)
    assert (datos["ambientes"], datos["dorm"], datos["banos"]) == (4, 3, 2)


def test_additional_property_exige_el_nombre_exacto_y_un_entero_razonable():
    datos = GenericoConnector._de_json_ld(_ld(additionalProperty=[
        _par("Baños en suite", "1"), _par("Ambientes de servicio", "2"),
        _par("Dormitorios", "3.5"), _par("Ambientes", "140")]), URL)
    assert "banos" not in datos and "ambientes" not in datos and "dorm" not in datos


def test_el_conteo_tipado_de_schema_org_gana_sobre_additional_property():
    datos = GenericoConnector._de_json_ld(_ld(
        numberOfRooms=5, additionalProperty=[_par("Ambientes", "4")]), URL)
    assert datos["ambientes"] == 5


def test_los_conteos_llegan_a_la_ficha_normalizada():
    p = _normalizar(_pagina(_ld(additionalProperty=[
        _par("Ambientes", "4"), _par("Dormitorios", "3")],
        offers={"@type": "Offer", "price": 118000, "priceCurrency": "USD"}),
        "<h1>Casa en venta</h1>"))
    assert (p.ambientes, p.dormitorios) == (4, 3)

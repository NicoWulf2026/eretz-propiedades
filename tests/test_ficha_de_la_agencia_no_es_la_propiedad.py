# -*- coding: utf-8 -*-
"""La dirección de la inmobiliaria no es la dirección de la propiedad.

`arturo pereyra bienes inmuebles` paró la cola con radio FAMILIA: la señal dice
que la fuente publica `ciudad` en **36 de 36** fichas y el extractor no sacó
ninguna. Cobertura 0.

Bajada una ficha, la única `addressLocality` de la página está acá:

    {"@type": "RealEstateAgent",
     "name": "Arturo Pereyra Bienes Inmuebles",
     "address": {"streetAddress": "Sarmiento 1726",
                 "addressLocality": "Rosario",
                 "addressRegion": "Santa Fe"}}

Es la oficina de la inmobiliaria. La propiedad no publica su ciudad en ningún
lado.

**El extractor tiene razón en no tomarla**: usar la ciudad de la oficina como
ciudad de cada propiedad pondría las 36 en Rosario estén donde estén, que es
inventar geografía. La que está mal es la señal, que ve `addressLocality` en
el HTML y concluye que la ficha provee ciudad.

Es la misma forma que dos casos ya conocidos de este proyecto: el patrón de
`ambientes` encontrando «ambiente 1» dentro de **Mono**ambiente en el menú de
filtros, y `inmobiliariacip` publicando `data-lat=""` vacío en 49 fichas. En
los tres, la señal se conformó con que la palabra apareciera.

Medido: **4 agencias y 838 propiedades** tienen `ciudad` con la señal
disparando en el 100 % y la extracción fallando en el 100 %. Confirmado el
mismo nodo `RealEstateAgent` en `arturo pereyra` y en `bottega`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.agency_certifier import (sin_ficha_de_la_agencia,  # noqa: E402
                                      source_signals)

TARJETA_DE_AGENCIA = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"RealEstateAgent","name":"Arturo Pereyra Bienes Inmuebles",
  "address":{"@type":"PostalAddress","streetAddress":"Sarmiento 1726",
             "addressLocality":"Rosario","addressRegion":"Santa Fe"}},
 {"@type":"WebSite","name":"Arturo Pereyra Bienes Inmuebles"}]}
</script>
"""

FICHA_CON_CIUDAD_PROPIA = """
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Casa en Funes",
 "address":{"@type":"PostalAddress","addressLocality":"Funes",
            "addressRegion":"Santa Fe"}}
</script>
"""


def pagina(*bloques: str) -> str:
    return ("<html><head><title>Casa</title></head><body>"
            + "".join(bloques) + "<p>Una casa linda</p></body></html>")


def test_MUERDE_la_tarjeta_de_la_agencia_no_prueba_que_la_ficha_tenga_ciudad():
    """El caso `arturo pereyra`, exacto.

    Sin esto son 4 agencias y 838 propiedades reportando un campo que la
    fuente no publica, y cada una con derecho a parar las dos colas con radio
    FAMILIA.
    """
    assert source_signals(pagina(TARJETA_DE_AGENCIA))["ciudad"] is False


def test_una_ciudad_de_la_PROPIEDAD_si_cuenta():
    """La otra mitad, y la que impide que esto apague la señal.

    Si el arreglo silenciara toda `addressLocality`, las fuentes que sí
    publican la ciudad de la propiedad quedarían como si no la publicaran, y
    perderíamos la señal que detecta extracciones fallidas de verdad.
    """
    assert source_signals(pagina(FICHA_CON_CIUDAD_PROPIA))["ciudad"] is True


def test_MUERDE_con_las_dos_gana_la_de_la_propiedad():
    """Muchas fichas traen las dos cosas: la tarjeta y su propio schema.

    Quitar el bloque entero por contener una tarjeta perdería la ciudad real.
    Sólo se quitan los bloques donde TODO es institucional.
    """
    html = pagina(TARJETA_DE_AGENCIA, FICHA_CON_CIUDAD_PROPIA)
    assert source_signals(html)["ciudad"] is True


def test_un_bloque_mixto_no_se_descarta():
    """Un solo `@graph` con la agencia y la propiedad adentro."""
    mixto = """
    <script type="application/ld+json">
    {"@graph":[{"@type":"RealEstateAgent","name":"X",
                "address":{"addressLocality":"Rosario"}},
               {"@type":"Product","name":"Casa",
                "address":{"addressLocality":"Funes"}}]}
    </script>
    """
    assert source_signals(pagina(mixto))["ciudad"] is True


def test_la_ciudad_en_el_html_visible_sigue_contando():
    """No se toca nada fuera de los bloques JSON-LD institucionales."""
    html = pagina('<span class="ciudad">Funes</span>')
    assert source_signals(html)["ciudad"] is True


def test_sin_json_ld_no_cambia_nada():
    antes = pagina('<p>una casa</p>')
    assert sin_ficha_de_la_agencia(antes) == antes


def test_un_json_ld_ilegible_no_se_borra():
    """Si no se puede parsear, no se puede afirmar que sea institucional.

    Borrarlo por las dudas sería silenciar evidencia que no se entendió.
    """
    roto = '<script type="application/ld+json">{no es json</script>'
    assert "no es json" in sin_ficha_de_la_agencia(pagina(roto))

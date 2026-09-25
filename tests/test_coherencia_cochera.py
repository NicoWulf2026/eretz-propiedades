"""Una cochera no tiene dormitorios ni varios ambientes; el titulo dice que sobra.

157 de las 594 cocheras de los paquetes del 25-09 (26 %) traian dormitorios o
2+ ambientes. Dos clases, que el titulo separa:
- el titulo dice cochera y no describe una vivienda -> sobran los conteos
  (`farina` «Newbery 9192 – Cochera» con 1 dormitorio de la meta de Houzez);
- el titulo describe una vivienda o no nombra tipo -> sobra el tipo
  (`berrueta` «3 AMBIENTES AL FRENTE», tipo tomado de un tooltip).
El tipo que falta nunca se inventa.
"""
from __future__ import annotations

from connectors.base import PropiedadNormalizada
from connectors.coherencia import revisar


def test_MUERDE_cochera_explicita_con_dormitorios_pierde_los_conteos():
    p = {"tipo_propiedad": "cochera", "dormitorios": 1, "titulo": "Newbery 9192 – Cochera"}
    fuera = revisar(p)
    assert p["tipo_propiedad"] == "cochera" and p["dormitorios"] is None
    assert "dormitorios_en_una_cochera" in fuera


def test_MUERDE_titulo_de_vivienda_con_tipo_cochera_pierde_el_tipo():
    p = {"tipo_propiedad": "cochera", "dormitorios": 2, "ambientes": 3,
         "titulo": "3 AMBIENTES AL FRENTE - OPORTUNIDAD"}
    fuera = revisar(p)
    assert p["tipo_propiedad"] is None and (p["dormitorios"], p["ambientes"]) == (2, 3)
    assert "tipo_propiedad_cochera_con_dormitorios" in fuera


def test_sin_titulo_no_se_decide():
    p = {"tipo_propiedad": "cochera", "dormitorios": 2}
    revisar(p)
    assert (p["tipo_propiedad"], p["dormitorios"]) == ("cochera", 2)


def test_una_cochera_con_un_ambiente_es_normal():
    p = {"tipo_propiedad": "cochera", "ambientes": 1, "titulo": "Cochera en venta"}
    assert revisar(p) == [] and p["ambientes"] == 1


def test_la_construccion_de_la_propiedad_aplica_la_regla_con_el_titulo():
    p = PropiedadNormalizada(canonical_agency_id="roomix:farina", source_listing_id="1",
                             source_url="https://f.test/p/1", connector="wordpress",
                             titulo="ALVEAR Y MENDOZA – Cochera", tipo_propiedad="cochera",
                             dormitorios=1)
    assert p.dormitorios is None and p.tipo_propiedad == "cochera"


def test_un_numero_en_letras_tambien_describe_una_vivienda():
    """`adriana nuti`: «HAEDO - TRES AMBIENTE CON COCHERA»."""
    p = {"tipo_propiedad": "cochera", "ambientes": 3, "dormitorios": 2,
         "titulo": "HAEDO - TRES AMBIENTE CON COCHERA- ACEPTA MENOR"}
    revisar(p)
    assert p["tipo_propiedad"] is None and (p["ambientes"], p["dormitorios"]) == (3, 2)

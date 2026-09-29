"""Lote compartido preparado el 29-09: aglomerados de GeoRef y descartes sin senal."""
from __future__ import annotations

import pytest

from connectors.geografia import geografia
from scripts.agency_certifier import descartes_sin_senal


@pytest.fixture(scope="module")
def geo():
    try:
        return geografia()
    except (OSError, ValueError):
        pytest.skip("sin catalogo GeoRef local")


def test_la_parte_de_un_aglomerado_resuelve_en_su_provincia(geo):
    r = geo.resolver_localidad("Necochea", provincia="Buenos Aires")
    assert r.entidad is not None and "Quequ" in r.entidad.official_name


def test_en_otra_provincia_no_resuelve_ni_contradice(geo):
    r = geo.resolver_localidad("Necochea", provincia="Santa Fe")
    assert r.entidad is None
    assert "contradice" not in r.motivo


def test_un_nombre_que_ya_es_localidad_no_se_vuelve_alias(geo):
    assert "bella vista" not in geo.alias_de_aglomerado


def _run(**campos):
    return dict({"descartadas_por_forma": 1, "descartes_con_senal": 0,
                 "detalles_obtenidos": 315, "enumeradas": 316}, **campos)


def test_un_descarte_sin_senal_en_un_catalogo_leido_no_es_un_fallo():
    assert descartes_sin_senal(_run()) == 1


@pytest.mark.parametrize("campos", [
    {"descartes_con_senal": 1},                       # traia precio o schema
    {"detalles_obtenidos": 0},                        # se descarto todo
    {"descartadas_por_forma": 34, "enumeradas": 101},  # una porcion grande
])
def test_lo_sospechoso_sigue_contando(campos):
    assert descartes_sin_senal(_run(**campos)) == 0


# --- o feely (familia wordpress detenida el 29-09) --------------------------

def test_una_casilla_del_buscador_no_es_un_dato_de_la_ficha():
    from connectors.generico import sin_filtros_catalogo
    html = ('<div>Tipo de operacion<label class="control control--checkbox">'
            '<input name="status[]" type="checkbox" value="alquiler">Alquiler'
            '<span class="control__indicator"></span></label></div><li>Casa en Victoria</li>')
    limpio = sin_filtros_catalogo(html)
    assert "Alquiler" not in limpio and "Casa en Victoria" in limpio


def test_la_operacion_de_las_unidades_no_es_la_del_emprendimiento():
    from scripts.agency_certifier import source_signals
    pagina = ('<html><head><title>Fideicomiso Alameda</title></head><body>'
              '<h1>Fideicomiso Alameda</h1><p>Departamentos de 1 dormitorio.</p>'
              '<div class="property-sub-listings-wrap" id="property-sub-listings-wrap">'
              '<h2>Unidades disponibles</h2><span>Venta</span><span>USD 80.600</span>'
              '</div></body></html>')
    assert source_signals(pagina, "https://ofeely.com.ar/emprendimiento/fideicomiso-alameda/")[
        "operacion"] is False


def test_una_provincia_leida_que_no_es_provincia_es_validacion():
    from scripts.agency_certifier import field_audit
    url = "https://ofeely.com.ar/property/casa-en-victoria-con-jardin/"
    fila = {"source_url": url, "connector": "generico", "provincia": None,
            "extra": {"provincia_declarada_sin_resolver": "Argentina"}}
    r = field_audit([fila], {url: {"source_signals": {"provincia": True}}})["provincia"]
    assert (r["extraction_failed"], r["validation_rejected"]) == (0, 1)

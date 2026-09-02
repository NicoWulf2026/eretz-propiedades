"""Regresiones de la geografia canonica, con casos reales del universo ERETZ.

Los casos no salen de un manual: son cadenas que aparecen en las propiedades ya
extraidas, y varios de ellos rompieron la primera version de este modulo.
"""
from __future__ import annotations

import pytest

from connectors.geografia import (AMBIGUA, CONTRADICHA, DIRECTORIO_POR_DEFECTO,
                                  EXACTA, NO_ENCONTRADA, POR_ALIAS,
                                  POR_CONTEXTO, Geografia, normalizar)

pytestmark = pytest.mark.skipif(
    not (DIRECTORIO_POR_DEFECTO / "localidades_censales.json").exists(),
    reason="falta el snapshot de GeoRef; se baja con scripts/geo_snapshot.py")


@pytest.fixture(scope="module")
def geo() -> Geografia:
    return Geografia()


def test_un_barrio_no_se_convierte_en_ciudad(geo) -> None:
    """El caso que motivo todo esto.

    Una ficha de Tokko publica `Ubicacion: Alberdi`, que es un barrio de la
    ciudad de Cordoba. GeoRef no cataloga barrios: no hay ninguna localidad
    llamada Alberdi. El unico `Alberdi` exacto del pais es un Paraje en Chaco, y
    tomarlo pondria la propiedad a mil kilometros de donde esta.
    """
    resultado = geo.resolver_localidad("Alberdi")
    assert resultado.certeza == NO_ENCONTRADA
    assert resultado.entidad is None


def test_otros_barrios_reales_del_universo_tampoco_resuelven(geo) -> None:
    """Palermo, Caballito y Villa Crespo aparecen como `ciudad` en cientos de
    avisos. Son barrios porteños, y afirmarlos como ciudad seria inventar una
    localidad que no existe."""
    for barrio in ("Palermo", "Caballito", "Villa Crespo", "Centro",
                   "Nordelta"):
        assert not geo.resolver_localidad(barrio).resuelta, barrio


def test_una_localidad_repetida_no_se_resuelve_sin_contexto(geo) -> None:
    """`San Pedro` son trece localidades censales distintas. El nombre solo
    nunca alcanza."""
    resultado = geo.resolver_localidad("San Pedro")
    assert resultado.certeza == AMBIGUA
    assert resultado.candidatas > 1


def test_la_provincia_desambigua_a_las_homonimas(geo) -> None:
    for provincia in ("Buenos Aires", "Jujuy", "Misiones"):
        resultado = geo.resolver_localidad("San Pedro", provincia=provincia)
        assert resultado.certeza == POR_CONTEXTO, provincia
        assert resultado.entidad.provincia == provincia


def test_un_campo_provincia_que_no_es_una_provincia_no_contradice(geo) -> None:
    """Regresion real: 1.498 avisos de La Plata traen `provincia = "GBA Sur"`,
    una zona comercial, y otros traen `/api/v1/state/149/`, una ruta de API sin
    normalizar. Tratar eso como contradiccion descartaba la unica candidata
    correcta y dejaba sin ciudad a una ciudad que el catalogo tiene."""
    for ruido in ("GBA Sur", "G.B.A. Sur", "/api/v1/state/149/", "Zona Norte"):
        resultado = geo.resolver_localidad("La Plata", provincia=ruido)
        assert resultado.resuelta, ruido
        assert resultado.entidad.official_name == "La Plata"


def test_los_acentos_y_las_mayusculas_no_cambian_la_resolucion(geo) -> None:
    esperada = geo.resolver_localidad("Córdoba", provincia="Córdoba").entidad
    for forma in ("CORDOBA", "cordoba", "Cordoba", "  Córdoba  "):
        otra = geo.resolver_localidad(forma, provincia="Cordoba").entidad
        assert otra is not None and otra.official_id == esperada.official_id


def test_la_capital_se_deduce_del_catalogo_y_no_de_una_tabla(geo) -> None:
    """"Cordoba Capital" es la forma comercial de la ciudad de Cordoba. Se
    resuelve por la localidad homonima de su provincia, o por el departamento
    capital donde el nombre no coincide -Tucuman-, sin escribir a mano ninguna
    correspondencia."""
    for texto, esperado in (("Cordoba Capital", "Córdoba"),
                            ("Santa Fe Capital", "Santa Fe"),
                            ("Mendoza Capital", "Mendoza"),
                            ("Tucuman Capital", "San Miguel de Tucumán")):
        resultado = geo.resolver_localidad(texto)
        assert resultado.certeza == POR_ALIAS, texto
        assert resultado.entidad.official_name == esperado, texto


def test_caba_resuelve_a_la_provincia_y_no_a_una_comuna(geo) -> None:
    """CABA no tiene localidad censal propia: esta partida en quince comunas.
    Nadie publica "CABA - Comuna 4" como ciudad de un aviso, y elegir una
    inventaria una precision que la fuente nunca dio."""
    for forma in ("CABA", "Capital Federal", "Ciudad Autonoma de Buenos Aires"):
        resultado = geo.resolver_localidad(forma)
        assert resultado.certeza == POR_ALIAS, forma
        assert resultado.entidad.official_name == (
            "Ciudad Autónoma de Buenos Aires")
        assert "Comuna" not in resultado.entidad.official_name


def test_una_coordenada_coherente_no_estorba(geo) -> None:
    resultado = geo.resolver_localidad("Rosario", lat=-32.95, lon=-60.66)
    assert resultado.certeza == EXACTA
    assert resultado.entidad.official_name == "Rosario"


def test_una_coordenada_contradictoria_impide_afirmar_la_ciudad(geo) -> None:
    """Regresion real de argentinasothebysrealty.com: publica
    `ciudad = Ciudad Autonoma de Buenos Aires` en avisos cuyas coordenadas caen
    a 3,7 km de Lago Moreno, Rio Negro. El campo tiene la oficina de la
    inmobiliaria, no la propiedad.

    Son 1.422 propiedades que quedaban afirmadas como porteñas estando en
    Bariloche. Ante dos evidencias que se contradicen no se elige una.
    """
    resultado = geo.resolver_localidad(
        "Ciudad Autonoma de Buenos Aires", lat=-41.10, lon=-71.48)
    assert resultado.certeza == CONTRADICHA
    assert resultado.entidad is None


def test_una_coordenada_fuera_de_argentina_se_ignora(geo) -> None:
    """Una coordenada invertida o de otro pais no puede desmentir a la fuente:
    no es evidencia de nada."""
    resultado = geo.resolver_localidad("Rosario", lat=40.4, lon=-3.7)
    assert resultado.resuelta
    assert resultado.entidad.official_name == "Rosario"


def test_sin_informacion_no_se_inventa_nada(geo) -> None:
    for vacio in (None, "", "   ", 0):
        resultado = geo.resolver_localidad(vacio)
        assert not resultado.resuelta
        assert resultado.provenance == "UNKNOWN"


def test_una_ciudad_inexistente_no_resuelve(geo) -> None:
    assert not geo.resolver_localidad("Ciudad Que No Existe 123").resuelta


def test_toda_resolucion_dice_de_donde_salio(geo) -> None:
    """Una resolucion sin procedencia no se puede auditar despues."""
    for texto, contexto in (("Rosario", {}), ("Alberdi", {}),
                            ("San Pedro", {}), ("CABA", {})):
        salida = geo.resolver_localidad(texto, **contexto).a_dict()
        assert salida["match"] and salida["provenance"] and salida["reason"]


def test_la_normalizacion_es_estable(geo) -> None:
    assert normalizar("Córdoba") == normalizar("CORDOBA") == "cordoba"
    assert normalizar("Gral. San Martín") == "gral san martin"
    assert normalizar(None) == ""

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


@pytest.mark.parametrize('city,province', [('CABA', 'Santa Fe'),
                                         ('Cordoba Capital', 'Buenos Aires'),
                                         ('Capital Federal', 'Buenos Aires')])
def test_alias_does_not_bypass_conflicting_province(city, province, geo):
    result = geo.resolver_localidad(city, provincia=province)
    assert result.entidad is None
    assert result.certeza == CONTRADICHA


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


# --------------------------------------------------------- integracion comun
def _propiedad(**campos):
    from connectors.base import PropiedadNormalizada

    base = {"canonical_agency_id": "roomix:x", "source_listing_id": "1",
            "source_url": "https://x.test/p/1", "connector": "generico"}
    return PropiedadNormalizada(**{**base, **campos})


def _resolver(prop):
    from connectors.base import Connector

    Connector._resolver_geografia(prop)
    return prop


def test_el_pipeline_normaliza_la_ciudad_publicada() -> None:
    prop = _resolver(_propiedad(ciudad="Capital Federal"))
    assert prop.ciudad == "Ciudad Autónoma de Buenos Aires"
    assert prop.extra["ciudad_match"] == POR_ALIAS
    assert prop.extra["ciudad_publicada"] == "Capital Federal"
    assert prop.extra["localidad_id"]


def test_un_barrio_sale_de_ciudad_y_va_a_barrio() -> None:
    """No se tira el dato: se guarda donde vale. Barrio y localidad son
    dimensiones distintas, y `ciudad` no puede quedar con algo que no es una
    localidad real."""
    prop = _resolver(_propiedad(ciudad="Palermo"))
    assert prop.ciudad is None
    assert prop.barrio == "Palermo"


def test_no_se_pisa_un_barrio_que_la_fuente_ya_publico() -> None:
    prop = _resolver(_propiedad(ciudad="Palermo", barrio="Palermo Chico"))
    assert prop.ciudad is None
    assert prop.barrio == "Palermo Chico"


def test_la_ciudad_de_la_oficina_no_sobrevive_a_la_coordenada() -> None:
    """Regresion de Sotheby's: publicaba CABA en propiedades de Bariloche."""
    prop = _resolver(_propiedad(ciudad="CABA", latitud=-41.10, longitud=-71.48))
    assert prop.ciudad is None
    assert prop.extra["ciudad_match"] == CONTRADICHA


def test_la_propiedad_sobrevive_aunque_no_haya_ciudad() -> None:
    """Primer principio: una propiedad valida no desaparece por un dato que
    falta. Solo se vacia el campo que no se puede afirmar."""
    prop = _resolver(_propiedad(titulo="Casa con patio", precio=120000.0,
                                ciudad="Nordelta"))
    assert prop.titulo == "Casa con patio"
    assert prop.precio == 120000.0
    assert prop.ciudad is None
    assert prop.barrio == "Nordelta"


def test_la_provincia_del_catalogo_completa_la_que_falta() -> None:
    prop = _resolver(_propiedad(ciudad="Rosario"))
    assert prop.ciudad == "Rosario"
    assert prop.provincia == "Santa Fe"


def test_sin_ciudad_publicada_no_se_inventa_ninguna() -> None:
    """El barrio si se evalua -puede ser una ciudad escondida-, pero si no
    resuelve no se inventa nada y el barrio se conserva. Queda el rastro de
    que se miro, que es lo que despues permite auditarlo."""
    prop = _resolver(_propiedad(titulo="Casa", barrio="Centro"))
    assert prop.ciudad is None
    assert prop.barrio == "Centro"
    assert prop.extra["ciudad_match"] == NO_ENCONTRADA


def test_sin_ninguna_ubicacion_no_se_mira_nada() -> None:
    prop = _resolver(_propiedad(titulo="Casa", precio=100000.0))
    assert prop.ciudad is None and prop.barrio is None
    assert "ciudad_match" not in prop.extra


def test_un_barrio_que_en_realidad_es_una_ciudad_se_promueve() -> None:
    """Tokko publica la ubicacion en un solo campo, sin decir de que nivel es,
    y el connector la guarda como barrio. Cuando resuelve a una localidad
    censal es una ciudad de verdad escondida donde nadie la busca: son 11.440
    propiedades con "Mar Del Plata", "La Plata", "Rosario" o "Quilmes"."""
    prop = _resolver(_propiedad(barrio="Mar Del Plata"))
    assert prop.ciudad == "Mar del Plata"
    assert prop.barrio is None
    assert prop.extra["ciudad_campo_de_origen"] == "barrio"


def test_un_barrio_de_verdad_se_queda_donde_esta() -> None:
    """El 76% de esos campos son barrios reales. Promoverlos inventaria una
    localidad; dejarlos donde estan conserva el dato."""
    prop = _resolver(_propiedad(barrio="Alberdi"))
    assert prop.ciudad is None
    assert prop.barrio == "Alberdi"


def test_la_promocion_desde_barrio_tambien_respeta_la_coordenada() -> None:
    """El arbitraje no puede saltearse los controles: si la coordenada
    contradice, no se promueve nada."""
    prop = _resolver(_propiedad(barrio="La Plata", latitud=-41.10,
                                longitud=-71.48))
    assert prop.ciudad is None
    assert prop.barrio == "La Plata"
    assert prop.extra["ciudad_match"] == CONTRADICHA


# ------------------------------------------------- versionado del snapshot
def test_el_diff_detecta_lo_que_hace_peligroso_un_reemplazo() -> None:
    """Un catalogo externo no puede cambiar en silencio. Que se elimine un id o
    que una localidad cambie de provincia mueve propiedades de lugar sin que
    nadie las haya tocado, y eso no se nota hasta que la busqueda por ciudad no
    devuelve nada."""
    from scripts.geo_snapshot_diff import comparar

    viejo = {
        "1": {"id": "1", "nombre": "Rosario",
              "provincia": {"nombre": "Santa Fe"}},
        "2": {"id": "2", "nombre": "Vieja", "provincia": {"nombre": "Cordoba"}},
        "3": {"id": "3", "nombre": "Mudada", "provincia": {"nombre": "Cordoba"}},
    }
    nuevo = {
        "1": {"id": "1", "nombre": "Rosario",
              "provincia": {"nombre": "Santa Fe"}},
        "3": {"id": "3", "nombre": "Mudada",
              "provincia": {"nombre": "San Luis"}},
        "4": {"id": "4", "nombre": "Nueva", "provincia": {"nombre": "Salta"}},
    }
    resultado = comparar(viejo, nuevo)
    assert resultado["agregados"] == 1
    assert resultado["eliminados"] == 1
    assert resultado["cambiaron_de_provincia"] == 1
    assert resultado["detalle_mudados"][0]["despues"] == "San Luis"


def test_el_diff_ve_un_renombre_sin_confundirlo_con_una_mudanza() -> None:
    from scripts.geo_snapshot_diff import comparar

    viejo = {"1": {"id": "1", "nombre": "Cordoba",
                   "provincia": {"nombre": "Cordoba"}}}
    nuevo = {"1": {"id": "1", "nombre": "Córdoba",
                   "provincia": {"nombre": "Cordoba"}}}
    resultado = comparar(viejo, nuevo)
    assert resultado["renombrados"] == 1
    assert resultado["cambiaron_de_provincia"] == 0


def test_negarse_a_afirmar_es_rechazo_de_validacion_no_fallo_de_extraccion() -> None:
    """La certificacion los trata distinto y con razon: EXTRACTION_FAILED es un
    defecto nuestro y bloquea; REJECTED_BY_VALIDATION es la validacion haciendo
    su trabajo.

    Caso real: azpropiedades publica "Caseros" en 11 avisos del Gran Buenos
    Aires. La unica Caseros del catalogo esta en Entre Rios, a 238 km, porque
    la de Tres de Febrero no es localidad censal. Afirmarla habria mandado esas
    once propiedades a otra provincia.
    """
    prop = _resolver(_propiedad(barrio="Caseros", latitud=-34.6057,
                                longitud=-58.5608))
    assert prop.ciudad is None
    assert "ciudad" in prop.extra["atributos_descartados"]


def test_un_barrio_comun_no_cuenta_como_dato_rechazado() -> None:
    """La fuente no publico ninguna ciudad: no hay nada que rechazar, y marcar
    un descarte inventaria un problema donde no lo hay."""
    prop = _resolver(_propiedad(barrio="Palermo"))
    assert prop.extra.get("atributos_descartados") is None


def test_promover_un_barrio_a_ciudad_no_es_perder_el_barrio() -> None:
    """Regresion de `roomix:aagaard inmobiliaria`.

    Tokko publica la ubicacion en un solo campo. Cuando dice "Cordoba Capital"
    eso es una ciudad, y dejarla ademas en `barrio` afirmaria un barrio que no
    existe. Pero vaciarlo tampoco es haber fallado al extraerlo: el valor se
    valido contra el catalogo y se rechazo COMO BARRIO.

    Sin esa distincion la certificacion leia 38 promociones correctas como 38
    barrios perdidos, y bloqueaba una inmobiliaria que estaba bien.
    """
    prop = _resolver(_propiedad(barrio="Cordoba Capital"))
    assert prop.ciudad == "Córdoba"
    assert prop.barrio is None
    assert "barrio" in prop.extra["atributos_descartados"]


def test_toda_ciudad_publicada_que_no_se_afirma_queda_como_rechazo() -> None:
    """Un barrio en el campo ciudad, una coordenada que la desmiente y una
    homonima sin contexto son tres motivos distintos para no afirmar, pero los
    tres son la validacion funcionando. Ninguno es un fallo de extraccion, y
    tratarlos como tal bloquea inmobiliarias que estan bien."""
    for ciudad, contexto in (("Palermo", {}),
                             ("CABA", {"latitud": -41.10, "longitud": -71.48}),
                             ("San Pedro", {})):
        prop = _resolver(_propiedad(ciudad=ciudad, **contexto))
        assert prop.ciudad is None, ciudad
        assert "ciudad" in prop.extra["atributos_descartados"], ciudad


def test_si_la_fuente_no_publico_ciudad_no_hay_nada_que_rechazar() -> None:
    prop = _resolver(_propiedad(barrio="Alberdi"))
    assert prop.extra.get("atributos_descartados") is None

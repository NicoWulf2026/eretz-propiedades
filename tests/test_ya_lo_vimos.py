# -*- coding: utf-8 -*-
"""Que el segundo caso idéntico no cueste lo que costó el primero.

El 2026-09-17 la cola paró en `di santo negocios inmobiliarios` con un colapso
de inventario del 100%. Era la firma exacta de `etcheverry propiedades`,
diferida tres días antes: el mismo frontend propio de Tokko, el mismo
`<ul id="propiedades">` vacío que rellena JavaScript. Reconocerlo costó seis
consultas a la fuente que no hacían falta, porque la respuesta ya estaba
escrita.

El banco de firmas existía. Lo que faltaba era consultarlo.

La trampa que este archivo fija: la primera versión del buscador **no encontró**
`etcheverry` desde `di santo`, porque separaba `CERO_ENUMERADAS` de
`CERO_ENUMERADAS_CON_BASELINE` y uno tiene línea base 30 y el otro 0. La línea
base dice cuánto duele, no qué pasó.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import pytest  # noqa: E402

from ya_lo_vimos import (  # noqa: E402
    forma_de_fallo, parecidos, plataforma_del_host,
)


def resultado(mecanismo: str, estrategia: str, enumeradas, base=None,
              declarado=None) -> dict:
    return {
        "publication_mechanism": mecanismo,
        "connector_strategy": estrategia,
        "enumeration_audit": {"enumerated": enumeradas, "baseline": base,
                              "declared_total": declarado},
    }


DI_SANTO = resultado("TOKKO_FRONTEND_PROPIO", "tokko", 0, base=30)
ETCHEVERRY = resultado("TOKKO_FRONTEND_PROPIO", "tokko", 0, base=0)


def test_MUERDE_la_linea_base_no_puede_partir_la_forma_de_fallo():
    """El bug que impidió encontrar el caso para el que se escribió el módulo.

    `di santo` tiene base 30 y `etcheverry` tiene 0, y son el mismo defecto.
    Si estas dos formas vuelven a diferir, el buscador deja de encontrar
    exactamente los pares que existe para encontrar.
    """
    assert forma_de_fallo(DI_SANTO) == forma_de_fallo(ETCHEVERRY)
    assert forma_de_fallo(DI_SANTO) == "CERO_ENUMERADAS"


def test_encuentra_etcheverry_desde_di_santo():
    """La validación completa, sobre los campos reales de los dos casos."""
    todos = {"roomix:di santo": DI_SANTO, "roomix:etcheverry": ETCHEVERRY}
    diferidas = {"roomix:etcheverry": [{
        "componente": "posible_perdida_de_inventario",
        "cuando": "2026-09-14T10:00:00",
        "diagnostico": "frontend propio de Tokko, contenedor vacio",
        "firma_verificada_contra_la_fuente": True}]}
    casos = parecidos("roomix:di santo", DI_SANTO, todos, {}, diferidas)
    assert [c["agencia"] for c in casos] == ["roomix:etcheverry"]
    assert casos[0]["fuerza"] >= 2


def test_una_firma_medida_pesa_mas_que_el_resto():
    """Salió de abrir el sitio; el mecanismo salió de una clasificación previa.

    Si una clasificación heredada pesara igual que una medición, un error de
    clasificación arrastraría al caso nuevo.
    """
    todos = {"a": DI_SANTO, "b": ETCHEVERRY}
    diferidas = {"b": [{"componente": "x", "cuando": "2026-09-14T00:00:00"}]}
    con = parecidos("a", DI_SANTO, todos,
                    {"a": "CONTENEDOR_VACIO_JS", "b": "CONTENEDOR_VACIO_JS"},
                    diferidas)
    sin = parecidos("a", DI_SANTO, todos, {}, diferidas)
    assert con[0]["fuerza"] > sin[0]["fuerza"]


def test_no_empareja_con_agencias_sin_diferida():
    """Sin diagnóstico escrito no hay nada que reutilizar.

    Emparejar con una agencia que también falló pero que nadie diagnosticó
    daría la sensación de haber encontrado algo y no daría ninguna respuesta.
    """
    todos = {"a": DI_SANTO, "b": ETCHEVERRY}
    assert parecidos("a", DI_SANTO, todos, {}, {}) == []


def test_un_caso_distinto_no_se_empareja():
    """Un WordPress con inventario completo no tiene nada que ver.

    Una coincidencia falsa es peor que ninguna: cierra un caso nuevo con la
    explicación de otro.
    """
    otro = resultado("WORDPRESS_REST", "wordpress", 120, base=118)
    todos = {"a": DI_SANTO, "b": otro}
    diferidas = {"b": [{"componente": "extraccion_de_baja_magnitud",
                        "cuando": "2026-09-10T00:00:00"}]}
    assert parecidos("a", DI_SANTO, todos, {}, diferidas) == []


def test_el_colapso_y_el_cero_son_formas_distintas():
    """Enumerar 5 de 300 no es lo mismo que enumerar 0.

    En el primer caso el conector lee y se queda corto; en el segundo no lee
    nada. El arreglo es distinto y la búsqueda no debe mezclarlos.
    """
    colapso = resultado("TOKKO_FRONTEND_PROPIO", "tokko", 5, base=300)
    assert forma_de_fallo(colapso) == "COLAPSO_MAYOR_AL_80"
    assert forma_de_fallo(colapso) != forma_de_fallo(DI_SANTO)


# --------------------------------------------------------------------------
# La señal de plataforma, agregada después y también por un caso real: la cola
# paró en `diaz collins` —`dcnegociosinmobiliarios21.kitepropcrm.com`— y el
# buscador no la emparejó con `cavacini` —`mercedescavacini.kitepropcrm.com`—,
# que corre sobre el mismo SaaS y tiene el mismo defecto de `ambientes`.
# --------------------------------------------------------------------------

DIAZ = {**resultado("LISTADO_HTML", "generic/html_catalog", 10, base=11),
        "official_url": "https://dcnegociosinmobiliarios21.kitepropcrm.com"}
CAVACINI = {**resultado("LISTADO_HTML", "generic/html_catalog", 3, base=54),
            "official_url": "https://mercedescavacini.kitepropcrm.com"}


def test_MUERDE_dos_agencias_del_mismo_saas_se_emparejan():
    todos = {"roomix:diaz": DIAZ, "roomix:cavacini": CAVACINI}
    diferidas = {"roomix:cavacini": [{"componente": "x",
                                      "cuando": "2026-09-14T00:00:00"}]}
    casos = parecidos("roomix:diaz", DIAZ, todos, {}, diferidas)
    assert [c["agencia"] for c in casos] == ["roomix:cavacini"]
    assert casos[0]["fuerza"] >= 3
    assert any("kitepropcrm.com" in r for r in casos[0]["porque"])


@pytest.mark.parametrize("url,esperado", [
    ("https://dcnegociosinmobiliarios21.kitepropcrm.com", "kitepropcrm.com"),
    ("https://mercedescavacini.kitepropcrm.com", "kitepropcrm.com"),
    ("https://aimaropropiedades.tuinmobiliaria.com.ar/", "tuinmobiliaria.com.ar"),
])
def test_un_subdominio_de_plataforma_se_reconoce(url, esperado):
    assert plataforma_del_host(url) == esperado


@pytest.mark.parametrize("url", [
    "https://www.fios.com.ar/",
    "https://www.yacopino.com/",
    "https://disantoni.com",
    "https://www.century21.com.ar/x",
])
def test_MUERDE_un_dominio_propio_no_es_una_plataforma(url):
    """La guarda que evita emparejar medio padrón entre sí.

    Sin ella, `www.fios.com.ar` quedaría en `com.ar` tras sacarle el `www`, y
    cualquier otra agencia argentina "compartiría plataforma" con ella. Una
    señal que empareja con todo no es una señal.
    """
    assert plataforma_del_host(url) is None


def test_dos_dominios_propios_distintos_no_se_emparejan():
    fios = {**resultado("LISTADO_HTML", "generic/html_catalog", 0),
            "official_url": "https://www.fios.com.ar/"}
    yaco = {**resultado("LISTADO_HTML", "generic/html_catalog", 0),
            "official_url": "https://www.yacopino.com/"}
    todos = {"a": fios, "b": yaco}
    diferidas = {"b": [{"componente": "x", "cuando": "2026-09-14T00:00:00"}]}
    casos = parecidos("a", fios, todos, {}, diferidas)
    assert not any("plataforma" in r for c in casos for r in c["porque"])


def test_la_forma_OTRA_no_empareja_con_nada():
    """`OTRA` es el cajón de descarte.

    Dejarla coincidir devolvía nueve precedentes para `diaz collins` que no
    explicaban nada. Una lista larga de coincidencias irrelevantes es peor que
    una vacía: la vacía dice "diagnosticá", la larga hace perder el tiempo.
    """
    uno = resultado("LISTADO_HTML", "generic/html_catalog", 10, base=11)
    otro = resultado("LISTADO_HTML", "generic/html_catalog", 40, base=41)
    assert forma_de_fallo(uno) == forma_de_fallo(otro) == "OTRA"
    todos = {"a": uno, "b": otro}
    diferidas = {"b": [{"componente": "x", "cuando": "2026-09-14T00:00:00"}]}
    assert parecidos("a", uno, todos, {}, diferidas) == []

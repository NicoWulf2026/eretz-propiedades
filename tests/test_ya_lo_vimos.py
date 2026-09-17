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

from ya_lo_vimos import forma_de_fallo, parecidos  # noqa: E402


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

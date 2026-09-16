# -*- coding: utf-8 -*-
"""Inventario y calidad se contestan por separado, y la regla geo no se ensancha.

El caso de referencia es `analia requena`: 143 propiedades enumeradas en dos
corridas idempotentes, `provincia` con `state=EXTRACTED` y `coverage=1.0`, y
`ciudad` enteramente rechazada por validación. La cobertura de la provincia es
perfecta y la provincia está mal. Esa es toda la lección del §32.

Los fixtures son la forma real de `field_coverage` que escribe el certificador.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from gates_independientes import (  # noqa: E402
    data_quality_gate, inventory_gate, vector_de_confianza,
)


def campo(state: str, coverage: float = 1.0) -> dict:
    return {"state": state, "coverage": coverage}


ANALIA_REQUENA = {
    "canonical_agency_id": "roomix:analia requena propiedades",
    "status": "CERTIFIED_COMPLETE",
    "identity_status": "READY",
    "publication_mechanism": "LISTADO_HTML",
    "reasons": ["two complete idempotent runs passed"],
    "enumeration_audit": {"enumerated": 143, "declared_total": None},
    "field_coverage": {
        "provincia": campo("EXTRACTED", 1.0),
        "direccion": campo("EXTRACTED", 1.0),
        "ciudad": campo("REJECTED_BY_VALIDATION", 0.0),
        "precio": campo("EXTRACTED", 1.0),
        "imagenes": campo("EXTRACTED", 1.0),
    },
}


def test_el_inventario_de_analia_requena_pasa():
    """Y tiene que pasar: enumeró las 143 en dos corridas idempotentes.

    Si este gate fallara, la separación no serviría de nada: estaríamos
    castigando el inventario por un problema de campos.
    """
    assert inventory_gate(ANALIA_REQUENA)["gate"] == "PASS"


def test_la_calidad_de_analia_requena_NO_pasa():
    señal = data_quality_gate(ANALIA_REQUENA)
    assert señal["gate"] == "DEGRADED"
    assert "contradiccion geografica" in señal["porque"]


def test_los_dos_gates_dan_distinto_sobre_la_misma_agencia():
    """El §34 en una línea: PASS en uno y FAIL en otro, a la vez.

    Un único estado no puede expresar esto, y por eso `CERTIFIED_COMPLETE`
    se lee hoy como si garantizara los campos.
    """
    assert inventory_gate(ANALIA_REQUENA)["gate"] == "PASS"
    assert data_quality_gate(ANALIA_REQUENA)["gate"] != "PASS"


def test_el_vector_separa_geo_de_inventario():
    """§33: escala por dimensión, no un score global que promedie el problema."""
    vector = vector_de_confianza(ANALIA_REQUENA)
    assert vector["inventory"] == "ALTA"
    assert vector["geo"] == "BAJA"
    assert vector["price"] == "ALTA"


def test_MUERDE_la_regla_geo_no_puede_volver_a_ser_tan_ancha():
    """La primera versión marcaba 135 de 244 agencias, y eso era la pista.

    Medido sobre las 409: `provincia` se rechaza el 0,0% de las veces y
    `direccion` el 0,0%. Así que "provincia perfecta" es casi siempre verdad, y
    una regla que sólo exige eso más "algún campo geográfico rechazado" en
    realidad dice "algún campo geográfico se rechazó".

    Una latitud rechazada es geocodificación, no una provincia mal puesta. Si
    esta agencia volviera a marcarse como contradicción geográfica, la regla se
    ensanchó de nuevo.
    """
    solo_geocodificacion = {
        **ANALIA_REQUENA,
        "field_coverage": {
            "provincia": campo("EXTRACTED", 1.0),
            "direccion": campo("EXTRACTED", 1.0),
            "ciudad": campo("EXTRACTED", 1.0),
            "latitud": campo("REJECTED_BY_VALIDATION", 0.0),
            "longitud": campo("REJECTED_BY_VALIDATION", 0.0),
        },
    }
    señal = data_quality_gate(solo_geocodificacion)
    assert "contradiccion geografica" not in (señal["porque"] or "")
    # Sigue siendo degradada —hay campos rechazados— pero por el motivo
    # correcto, que es lo que permite priorizar después.
    assert señal["gate"] == "DEGRADED"


def test_una_provincia_parcial_no_arma_la_contradiccion():
    """La forma exige provincia **afirmada al 100%**, no simplemente presente.

    Con cobertura parcial no estamos afirmando nada con confianza, así que no
    hay contradicción que denunciar.
    """
    parcial = {
        **ANALIA_REQUENA,
        "field_coverage": {
            "provincia": campo("EXTRACTED", 0.5),
            "ciudad": campo("REJECTED_BY_VALIDATION", 0.0),
        },
    }
    assert "contradiccion geografica" not in (
        data_quality_gate(parcial)["porque"] or "")


def test_una_agencia_sana_pasa_los_dos_gates():
    sana = {
        **ANALIA_REQUENA,
        "field_coverage": {
            "provincia": campo("EXTRACTED", 1.0),
            "ciudad": campo("EXTRACTED", 1.0),
            "precio": campo("EXTRACTED", 1.0),
            "imagenes": campo("EXTRACTED", 1.0),
        },
    }
    assert inventory_gate(sana)["gate"] == "PASS"
    assert data_quality_gate(sana)["gate"] == "PASS"


def test_declarado_mayor_que_enumerado_hunde_el_inventario_no_la_calidad():
    """§28, y la separación otra vez: son problemas de gates distintos."""
    incompleta = {
        **ANALIA_REQUENA,
        "enumeration_audit": {"enumerated": 7, "declared_total": 350},
        "field_coverage": {"provincia": campo("EXTRACTED", 1.0),
                           "ciudad": campo("EXTRACTED", 1.0),
                           "precio": campo("EXTRACTED", 1.0)},
    }
    assert inventory_gate(incompleta)["gate"] == "FAIL"
    assert data_quality_gate(incompleta)["gate"] == "PASS"


def test_un_campo_que_la_fuente_no_publica_no_es_un_defecto_nuestro():
    """`SOURCE_NOT_PROVIDED` no puede contarse igual que un rechazo.

    El primero es la fuente siendo la fuente; el segundo es un valor que
    estaba y refutamos. Mezclarlos convierte el gate de calidad en un medidor
    de lo generosas que son las fuentes.
    """
    sin_barrio = {
        **ANALIA_REQUENA,
        "field_coverage": {"provincia": campo("EXTRACTED", 1.0),
                           "ciudad": campo("EXTRACTED", 1.0),
                           "barrio": campo("SOURCE_NOT_PROVIDED", 0.0),
                           "precio": campo("EXTRACTED", 1.0)},
    }
    assert data_quality_gate(sin_barrio)["gate"] == "PASS"

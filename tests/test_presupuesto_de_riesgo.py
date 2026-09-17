# -*- coding: utf-8 -*-
"""Saber cuánto invalida un cambio antes de hacerlo, no después.

`connectors/texto.py` no menciona ninguna agencia y está en **todas** las
huellas: tocarlo invalida el universo certificado entero. Esa relación no se
adivina leyendo el archivo, y por eso el radio se deriva de
`fingerprint_components()` —la misma función que la cola usa para decidir si un
resultado sigue vigente— en vez de estimarse.

Medido hoy: un cambio a cualquier `shared/*` invalida 255 agencias y 27.054
propiedades, y cuesta **9,5 horas** con dos workers. El número importa en las
dos direcciones: es grande como radio y barato como precio.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from presupuesto_de_riesgo import componentes_de, presupuesto  # noqa: E402


def agencia(conector: str, estrategia: str, enumeradas: int = 100,
            segundos: float = 120.0, estado: str = "CERTIFIED_COMPLETE",
            nombre: str = "x") -> dict:
    return {
        "canonical_agency_id": f"roomix:{nombre}",
        "status": estado,
        "connector": conector,
        "connector_strategy": estrategia,
        "enumeration_audit": {"enumerated": enumeradas},
        "operational_metrics": {"duration_seconds": segundos},
    }


UNIVERSO = [
    agencia("tokko", "tokko", nombre="t1"),
    agencia("tokko", "tokko", nombre="t2"),
    agencia("generico", "generic/sitemap", nombre="g1"),
    agencia("wordpress", "wordpress", nombre="w1"),
]


def test_MUERDE_un_cambio_en_shared_invalida_a_todos():
    """Es el hecho que este script existe para hacer visible.

    Si alguna vez `shared/certifier` dejara de alcanzar al universo entero,
    sería porque se sacó de las huellas, y eso significaría que se puede
    cambiar la certificación sin invalidar nada.
    """
    salida = presupuesto("shared/certifier", UNIVERSO)
    assert salida["agencias_invalidadas"] == len(UNIVERSO)
    assert salida["porcentaje"] == 100.0


def test_un_conector_solo_alcanza_a_los_suyos():
    salida = presupuesto("connector/tokko", UNIVERSO)
    assert salida["agencias_invalidadas"] == 2
    assert salida["propiedades_afectadas"] == 200


def test_una_estrategia_alcanza_menos_que_su_conector():
    """`generic/common` toca todo lo genérico; una estrategia sólo la suya.

    Confundirlos haría parecer que arreglar una estrategia cuesta lo que
    cuesta tocar el genérico entero.
    """
    comunes = presupuesto("generic/common", UNIVERSO)["agencias_invalidadas"]
    propia = presupuesto("strategy/generic/sitemap",
                         UNIVERSO)["agencias_invalidadas"]
    assert propia <= comunes


def test_un_componente_que_nadie_usa_lo_dice_sin_rodeos():
    salida = presupuesto("connector/century21", UNIVERSO)
    assert salida["agencias_invalidadas"] == 0
    assert "NINGUNA CERTIFICACION" in salida["veredicto"]


def test_las_horas_salen_de_la_mediana_y_no_del_promedio():
    """Una agencia de tres horas no puede decidir por las otras cien.

    Con promedio, un solo caso lento hace parecer inviable un cambio que con
    la mediana cuesta la mitad. El sesgo va en la dirección que frena trabajo
    bueno.
    """
    universo = [agencia("tokko", "tokko", segundos=60, nombre=f"t{i}")
                for i in range(9)]
    universo.append(agencia("tokko", "tokko", segundos=10800, nombre="lenta"))
    salida = presupuesto("connector/tokko", universo)
    assert salida["mediana_segundos_por_agencia"] == 60.0
    # Con promedio (1134 s) darian 3,15 h; con mediana, 0,17.
    assert salida["horas_de_recertificacion_1_worker"] < 0.5


def test_identity_pending_no_entra_en_el_radio():
    """Un `IDENTITY_PENDING` no depende del conector.

    Contarlo inflaría el radio con agencias que un cambio de extracción no
    toca, y un radio inflado hace deferir cambios que convenía hacer.
    """
    from presupuesto_de_riesgo import ALCANZABLES
    assert "IDENTITY_PENDING" not in ALCANZABLES


def test_el_conjunto_de_componentes_no_depende_de_la_agencia():
    """Depende sólo del par (conector, estrategia), y por eso se memoiza.

    Sin eso la herramienta tarda minutos: son cientos de agencias por decenas
    de componentes, parseando AST cada vez.
    """
    a = componentes_de(agencia("tokko", "tokko", nombre="uno"))
    b = componentes_de(agencia("tokko", "tokko", nombre="otro"))
    assert a == b and a is b

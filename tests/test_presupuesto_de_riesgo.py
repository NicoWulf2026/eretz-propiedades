# -*- coding: utf-8 -*-
"""Saber cuánto invalida un cambio antes de hacerlo, no después.

`connectors/texto.py` no menciona ninguna agencia y está en **todas** las
huellas: tocarlo invalida el universo certificado entero. Esa relación no se
adivina leyendo el archivo, y por eso el radio se deriva de
`fingerprint_components()` —la misma función que la cola usa para decidir si un
resultado sigue vigente— en vez de estimarse.

Medido: un cambio a cualquier `shared/*` invalida **261 agencias y 27.187
propiedades**, y cuesta **23,9 horas** con dos workers.

Esa cifra fue primero 9,5 h y estaba mal: se calculaba `mediana × cantidad`. La
mediana contesta "¿cuánto tarda una agencia típica?"; el costo de rehacerlas
todas es la **suma**, que además está medida. La corrección la multiplicó por
2,5 y sigue siendo asumible, pero es otra decisión.
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


def test_MUERDE_las_horas_son_la_SUMA_y_no_la_mediana_por_cantidad():
    """El error que este test existe para impedir que vuelva.

    La primera versión calculaba `mediana × cantidad` con el argumento de que
    una agencia de tres horas corre el promedio. Ese argumento vale para
    *"¿cuánto tarda una agencia típica?"* y es exactamente al revés para un
    **total**: si una agencia tarda tres horas, rehacerla cuesta tres horas, y
    la mediana la borra.

    Nueve agencias de un minuto más una de tres horas: rehacerlas todas cuesta
    3,15 h, no 0,17. Sobre las 261 reales la diferencia fue de 9,6 h a 23,9 h.

    Y no hay nada que estimar: las duraciones están medidas.
    """
    universo = [agencia("tokko", "tokko", segundos=60, nombre=f"t{i}")
                for i in range(9)]
    universo.append(agencia("tokko", "tokko", segundos=10800, nombre="lenta"))
    salida = presupuesto("connector/tokko", universo)
    # 9 x 60 + 10800 = 11.340 s = 3,15 h, redondeado a 3,1
    assert salida["horas_de_recertificacion_1_worker"] == 3.1
    # La mediana sigue informándose, pero como lo que es.
    assert salida["mediana_segundos_por_agencia"] == 60.0
    assert salida["agencias_de_mas_de_10_min"] == 1


def test_la_cola_larga_no_se_pierde_en_el_total():
    """Una sola agencia lenta puede dominar el costo, y debe verse.

    Es la diferencia entre decidir con 9,6 h y decidir con 23,9: las 64
    agencias de más de diez minutos aportaban 36,3 de las 47,9 horas reales.
    """
    universo = [agencia("tokko", "tokko", segundos=10, nombre=f"t{i}")
                for i in range(50)]
    universo.append(agencia("tokko", "tokko", segundos=7200, nombre="lenta"))
    salida = presupuesto("connector/tokko", universo)
    assert salida["horas_de_recertificacion_1_worker"] > 2.0


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

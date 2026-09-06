"""Canarios, bulk y long tail: cambia el orden, no el universo."""
from __future__ import annotations

from scripts.run_agency_certification_queue import (CANARIOS_POR_FAMILIA,
                                                    ordenar_para_correr)


def _res(familia=None, status="CERTIFIED_COMPLETE", agotado=False):
    return {"connector_strategy": familia, "status": status,
            "run1": {"presupuesto_agotado": agotado}, "run2": {}}


def test_el_universo_no_cambia():
    """Reordenar no puede perder ni agregar una inmobiliaria."""
    cola = [f"a{i}" for i in range(20)]
    resultados = {"a3": _res("tokko"), "a7": _res("wordpress")}
    assert sorted(ordenar_para_correr(cola, resultados)) == sorted(cola)


def test_una_familia_se_prueba_antes_del_bulk():
    """`alta`, `alma di matteo` y `altos servicios` fueron tres paradas
    seguidas de la misma clase de problema, y cada una costó una ventana. Con
    canarios, una familia rota se descubre en la primera hora."""
    cola = [f"t{i}" for i in range(10)] + ["w1", "nuevo"]
    resultados = {f"t{i}": _res("tokko") for i in range(10)}
    resultados["w1"] = _res("wordpress")

    orden = ordenar_para_correr(cola, resultados)
    canarios = orden[:CANARIOS_POR_FAMILIA + 1]

    # Las dos familias conocidas aparecen antes de agotar tokko.
    assert "w1" in canarios
    assert sum(1 for c in canarios if c.startswith("t")) == CANARIOS_POR_FAMILIA


def test_lo_que_ya_nos_rechaza_va_al_final():
    """Un sitio que nos bloquea no aporta información nueva sobre el código, y
    adelante frena a las que sí."""
    cola = ["bloqueada", "normal", "lenta"]
    resultados = {"bloqueada": _res("tokko", status="BLOCKED_EXTERNAL"),
                  "normal": _res("tokko"),
                  "lenta": _res("wasi", agotado=True)}
    orden = ordenar_para_correr(cola, resultados)

    assert orden[0] == "normal"
    assert set(orden[-2:]) == {"bloqueada", "lenta"}


def test_las_que_nunca_se_certificaron_van_al_bulk():
    """Sin resultado previo no hay familia conocida: el bulk es donde se
    descubre, y adelantarlas no probaría nada."""
    cola = ["conocida", "nueva1", "nueva2"]
    resultados = {"conocida": _res("tokko")}
    orden = ordenar_para_correr(cola, resultados)

    assert orden[0] == "conocida"
    assert set(orden[1:]) == {"nueva1", "nueva2"}


def test_sin_resultados_previos_el_orden_se_conserva():
    """La primera corrida de la vida no tiene nada que ordenar."""
    cola = ["a", "b", "c"]
    assert ordenar_para_correr(cola, {}) == cola

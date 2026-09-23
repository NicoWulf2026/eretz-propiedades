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


def test_una_fuente_que_no_responde_va_al_final():
    """Cuesta MÁS que una que funciona: dos corridas de cien segundos agotando
    reintentos para no traer nada. En el canario se llevó doce minutos por
    delante de las agencias que sí tenían algo que decir sobre el código.

    Que no responda hoy no la saca del universo: se reintenta al final.
    """
    cola = ["viva", "caida"]
    resultados = {
        "viva": _res("tokko"),
        "caida": {"connector_strategy": "generico", "status": "NEEDS_FIX",
                  "run1": {"estado": "ERROR_DISCOVERY"},
                  "run2": {"estado": "ERROR_DISCOVERY"}}}
    assert ordenar_para_correr(cola, resultados) == ["viva", "caida"]


def test_una_sola_corrida_inaccesible_no_manda_al_final():
    """Si una corrida llegó al sitio, el sitio existe: puede haber sido un
    corte de red nuestro, y castigarla sería perder inventario real."""
    cola = ["intermitente", "otra"]
    resultados = {
        "intermitente": {"connector_strategy": "tokko", "status": "NEEDS_FIX",
                         "run1": {"estado": "OK"},
                         "run2": {"estado": "ERROR_DISCOVERY"}},
        "otra": _res("wordpress")}
    orden = ordenar_para_correr(cola, resultados)
    assert orden.index("intermitente") < len(orden)
    assert set(orden) == {"intermitente", "otra"}


# ---------------------------------------------------------------------------
# Excluir una familia detenida: saca esa familia, no la cola.
# ---------------------------------------------------------------------------

def test_MUERDE_excluir_una_familia_deja_pasar_a_las_demas(monkeypatch):
    """De 613 paros STOP, 596 son FAMILIA. Detener todo por uno de ellos
    detiene entre el 53,7 % y el 98,5 % de la cola sin motivo."""
    from scripts import run_agency_certification_queue as modulo
    catalogo = {"a": {"c": "tokko"}, "b": {"c": "wordpress"},
                "c": {"c": "tokko"}, "d": {"c": "generico"}}
    monkeypatch.setattr(modulo, "choose_connector", lambda r: r["c"])
    assert modulo.sin_las_familias(list(catalogo), catalogo, {"tokko"}) == ["b", "d"]


def test_excluir_no_distingue_mayusculas_ni_espacios(monkeypatch):
    from scripts import run_agency_certification_queue as modulo
    catalogo = {"a": {"c": " Tokko "}, "b": {"c": "wordpress"}}
    monkeypatch.setattr(modulo, "choose_connector", lambda r: r["c"])
    assert modulo.sin_las_familias(list(catalogo), catalogo, {"tokko"}) == ["b"]


def test_MUERDE_excluir_una_familia_que_no_esta_no_saca_a_nadie(monkeypatch):
    """El modo de falla caro sería que un nombre mal escrito vaciara la cola
    en silencio; acá se ve que no saca nada, y `main` corta si queda vacía."""
    from scripts import run_agency_certification_queue as modulo
    catalogo = {"a": {"c": "tokko"}, "b": {"c": "wordpress"}}
    monkeypatch.setattr(modulo, "choose_connector", lambda r: r["c"])
    assert modulo.sin_las_familias(list(catalogo), catalogo, {"wasi"}) == ["a", "b"]

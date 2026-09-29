"""discover no vuelve a bajar lo que ya bajo, y la memoria no sobrevive a la llamada."""
from __future__ import annotations

from collections import Counter

import pytest

from connectors.base import ErrorPermanente, ErrorTransitorio, Fuente
from connectors.generico import GenericoConnector, _DescargasDelDescubrimiento


class Contador:
    def __init__(self, paginas: dict[str, str], transitorios: set[str] = frozenset()):
        self.paginas = paginas
        self.transitorios = set(transitorios)
        self.pedidos_por_url: Counter = Counter()
        self.pedidos = 0

    def bajar(self, url: str) -> str:
        self.pedidos_por_url[url] += 1
        self.pedidos += 1
        if url in self.transitorios:
            raise ErrorTransitorio("corte")
        if url not in self.paginas:
            raise ErrorPermanente("http 404")
        return self.paginas[url]


def test_la_memoria_devuelve_lo_bajado_y_repite_el_rechazo_definitivo():
    real = Contador({"https://a.com/x": "hola"})
    memo = _DescargasDelDescubrimiento(real)
    assert memo.bajar("https://a.com/x") == "hola"
    assert memo.bajar("https://a.com/x") == "hola"
    for _ in range(2):
        with pytest.raises(ErrorPermanente):
            memo.bajar("https://a.com/nada")
    assert real.pedidos_por_url == {"https://a.com/x": 1, "https://a.com/nada": 1}


def test_un_error_transitorio_no_se_recuerda():
    real = Contador({}, transitorios={"https://a.com/lento"})
    memo = _DescargasDelDescubrimiento(real)
    for _ in range(2):
        with pytest.raises(ErrorTransitorio):
            memo.bajar("https://a.com/lento")
    assert real.pedidos_por_url["https://a.com/lento"] == 2


def test_las_sumas_llegan_al_descargador_real():
    real = Contador({})
    memo = _DescargasDelDescubrimiento(real)
    memo.pedidos += 3
    assert real.pedidos == 3


def test_discover_no_repite_pedidos_y_suelta_la_memoria_al_terminar():
    vacia = "<html><body><a href='/contacto'>contacto</a></body></html>"
    real = Contador({"https://a.com/": vacia,
                     "https://a.com/inmobiliaria/quienes-somos": vacia})
    conector = GenericoConnector(real)
    fuente = Fuente("roomix:prueba", "prueba", "https://a.com/inmobiliaria/quienes-somos", 1)
    conector.discover(fuente)
    repetidos = {u: n for u, n in real.pedidos_por_url.items() if n > 1}
    assert repetidos == {}
    assert conector.descargador is real
    antes = sum(real.pedidos_por_url.values())
    conector.discover(fuente)
    # Una segunda llamada vuelve a preguntar: la memoria era de la primera.
    assert sum(real.pedidos_por_url.values()) == 2 * antes

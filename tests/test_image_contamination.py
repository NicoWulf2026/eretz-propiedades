"""Una foto de una propiedad no puede estar en dos inmobiliarias."""
from __future__ import annotations

from scripts.image_contamination import contaminantes


def test_el_boton_de_pinterest_no_es_una_foto():
    """Está en 1.169 fichas de trece agencias, y en ninguna llega a la mitad de
    su catálogo: el filtro que mira una sola inmobiliaria no lo ve."""
    sucias = contaminantes({
        "https://pinterest.com/pin/create/button/": ({f"ag{i}" for i in range(13)}, 1169)})
    assert "https://pinterest.com/pin/create/button/" in sucias


def test_la_misma_propiedad_publicada_por_tres_agencias_conserva_sus_fotos():
    """Son 117 grupos medidos. Lo que las separa de la contaminación es cuántas
    fichas toca en cada agencia: una por agencia es una propiedad compartida;
    muchas por agencia es un banner."""
    uso = {"https://cdn/foto-real.jpg": ({"a", "b", "c"}, 3)}
    assert contaminantes(uso) == {}


def test_una_foto_de_una_sola_agencia_no_la_juzga_esta_regla():
    """Para eso está el filtro intra-agencia; esta regla mira el cruce."""
    assert contaminantes({"https://cdn/x.jpg": ({"a"}, 300)}) == {}


def test_el_limite_esta_en_repetirse_adentro_de_un_catalogo():
    # Dos agencias, dos fichas: una por agencia, legítima.
    assert contaminantes({"u": ({"a", "b"}, 2)}) == {}
    # Dos agencias, tres fichas: se repite en alguna, contamina.
    assert "u" in contaminantes({"u": ({"a", "b"}, 3)})


def test_la_evidencia_viaja_con_el_veredicto():
    sucias = contaminantes({"u": ({"a", "b"}, 10)})
    assert sucias["u"]["agencias"] == 2
    assert sucias["u"]["fichas"] == 10
    assert sucias["u"]["motivo"]

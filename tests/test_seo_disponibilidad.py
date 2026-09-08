"""Qué puede llevar una URL canónica sin afirmar nada falso."""
from __future__ import annotations

from scripts.seo_disponibilidad import LARGO_DEL_SLUG, slug_de


def _fila(**cambios):
    base = {"titulo": "Departamento en Venta en Alberdi", "operacion": "venta",
            "tipo_propiedad": "departamento"}
    base.update(cambios)
    return base


def test_la_localidad_entra_solo_si_esta_demostrada():
    """La tentación es `/venta/casa/rosario/<slug>`, y sólo el 16,5 % tiene
    localidad demostrada. Ponerla en las otras cinco sextas partes sería
    publicar geografía inventada en el lugar más difícil de corregir: una URL
    indexada sobrevive al dato que la originó."""
    con = slug_de(_fila(), {"localidad_canonica": "Rosario"})
    sin = slug_de(_fila(), {"localidad_canonica": None,
                            "area_busqueda": {"nivel": "PROVINCIA",
                                              "nombre": "Santa Fe"}})
    assert "rosario" in con
    assert "santa-fe" not in sin
    assert "rosario" not in sin


def test_sin_texto_no_hay_slug_legible():
    """Conviene saber cuántas son, no inventarles un texto."""
    assert slug_de({"titulo": None, "operacion": None,
                    "tipo_propiedad": None}, None) is None


def test_los_acentos_y_la_puntuacion_no_llegan_a_la_url():
    s = slug_de(_fila(titulo="Casa en Venta — Córdoba (¡oportunidad!)"), None)
    assert s == s.lower()
    assert all(c.isalnum() or c == "-" for c in s)
    assert "--" not in s and not s.startswith("-") and not s.endswith("-")


def test_el_slug_respeta_el_largo_elegido():
    """80 se eligió midiendo colisiones: 60 deja 42 % de propiedades
    compartiendo su parte legible, 80 deja 28 %, y de 100 en adelante se
    estanca en 25 % porque esos títulos son genuinamente iguales."""
    largo = slug_de(_fila(titulo="palabra " * 40), None)
    assert len(largo) <= LARGO_DEL_SLUG
    assert LARGO_DEL_SLUG == 80


def test_dos_propiedades_con_el_mismo_titulo_comparten_slug():
    """Y está bien: la URL final lleva el id, que es lo que las distingue. Dos
    unidades del mismo edificio tienen el mismo título de verdad."""
    a = slug_de(_fila(), None)
    b = slug_de(_fila(), None)
    assert a == b

"""El contrato de analytics: qué preguntas se van a poder contestar."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.analytics import (ANALYTICS_VERSION, EVENTOS, LARGO_DE_CONSULTA,
                           limpiar_consulta, normalizar, validar)


def test_cada_evento_declara_que_pregunta_responde():
    """Un contrato de analytics no es una lista de nombres: si un evento no
    responde una pregunta que importa, no debería existir."""
    for nombre, definicion in EVENTOS.items():
        assert definicion.get("responde"), nombre
        assert definicion.get("obligatorios"), nombre


def test_el_area_sin_nivel_no_se_acepta():
    """El nivel es lo único que distingue una ciudad de un municipio. Sin él,
    la pregunta que el evento existe para responder no se puede contestar."""
    ok, problemas = validar({"evento": "busqueda", "consulta": "casa",
                             "resultados": 3, "area_nombre": "La Calera"})
    assert not ok
    assert any("area_nivel" in p for p in problemas)

    ok, _ = validar({"evento": "busqueda", "consulta": "casa", "resultados": 3,
                     "area_nombre": "La Calera", "area_nivel": "MUNICIPIO"})
    assert ok


def test_no_se_aceptan_datos_personales():
    """La lista es explícita a propósito: es más fácil de auditar que una
    regla."""
    ok, problemas = validar({"evento": "ficha_vista", "propiedad_id": "h1",
                             "email": "a@b.com"})
    assert not ok
    assert any("prohibido" in p for p in problemas)


def test_un_campo_no_declarado_se_rechaza():
    """Un dataset con campos que nadie declaró es un dataset que nadie puede
    interpretar después."""
    ok, problemas = validar({"evento": "ficha_vista", "propiedad_id": "h1",
                             "campo_inventado": 1})
    assert not ok
    assert any("no declarado" in p for p in problemas)


def test_falta_un_obligatorio_y_no_se_guarda_a_medias():
    """Un dataset con huecos silenciosos miente más que uno vacío."""
    ok, problemas = validar({"evento": "contacto", "propiedad_id": "h1"})
    assert not ok
    assert any("medio" in p for p in problemas)


def test_la_consulta_se_corta_y_se_limpia():
    """Nadie busca una casa con un párrafo. Un campo largo es donde termina
    pegado un correo, y una vez guardado ya es un dato personal que hay que
    custodiar."""
    assert "@" not in limpiar_consulta("casa en rosario juan@ejemplo.com")
    assert "1156781234" not in limpiar_consulta("depto 11 5678 1234")
    assert len(limpiar_consulta("casa " * 200)) <= LARGO_DE_CONSULTA


def test_normalizar_no_inventa_campos():
    """Nunca agrega lo que no vino: un campo con valor por defecto se lee
    después como si la persona lo hubiera hecho."""
    evento = normalizar({"evento": "ficha_vista", "propiedad_id": "h1"})
    assert set(evento) == {"evento", "propiedad_id", "analytics_version"}
    assert evento["analytics_version"] == ANALYTICS_VERSION


def test_se_puede_contestar_que_busca_la_gente_y_no_encuentra():
    """La pregunta central del producto: el catálogo que falta, dicho por
    quien lo buscó."""
    ok, _ = validar({"evento": "sin_resultados", "consulta": "casa en tandil"})
    assert ok
    assert "resultados" in EVENTOS["busqueda"]["obligatorios"]

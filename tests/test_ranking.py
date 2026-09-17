"""Ranking técnico: lo que se puede defender mirando el dato."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.ranking import (RANKING_VERSION, calidad_de_ubicacion, coincidencia,
                         completitud, ordenar, puntaje)


def _prop(**cambios):
    base = {"id": "h1", "titulo": "Casa en Venta en Rosario",
            "descripcion": "Muy linda", "precio": 100000.0, "moneda": "USD",
            "operacion": "venta", "tipo_propiedad": "casa", "dormitorios": 3,
            "superficie_cubierta": 120.0, "imagenes": ["a"] * 6,
            "geo": {"area_busqueda": {"nivel": "LOCALIDAD", "nombre": "Rosario"},
                    "barrio": {"nombre": "Centro"}, "estado": None}}
    base.update(cambios)
    return base


def test_un_match_en_el_titulo_vale_mas_que_uno_en_la_descripcion():
    """El título lo escribió alguien para describir la propiedad; la
    descripción también menciona el barrio de al lado."""
    en_titulo = coincidencia(_prop(titulo="Casa en Fisherton",
                                   descripcion="cerca de todo",
                                   geo={"area_busqueda": {"nivel": "SIN_AREA"},
                                        "barrio": {}}), "fisherton")
    en_descripcion = coincidencia(_prop(titulo="Casa",
                                        descripcion="a metros de Fisherton",
                                        geo={"area_busqueda": {"nivel": "SIN_AREA"},
                                             "barrio": {}}), "fisherton")
    assert en_titulo > en_descripcion


def test_la_ubicacion_vale_por_su_nivel():
    """Una propiedad con localidad demostrada se puede ubicar; una con área de
    nivel provincia, casi no."""
    def nivel(n):
        return calidad_de_ubicacion(_prop(geo={"area_busqueda": {"nivel": n}}))

    assert nivel("LOCALIDAD") > nivel("MUNICIPIO") > nivel("DEPARTAMENTO") \
        > nivel("PROVINCIA") > nivel("SIN_AREA") - 0.001


def test_un_conflicto_geografico_baja_pero_no_esconde():
    """Sigue siendo una propiedad real; lo que no puede es encabezar una
    búsqueda por ubicación, porque una de las dos ubicaciones está mal."""
    limpia = calidad_de_ubicacion(
        _prop(geo={"area_busqueda": {"nivel": "LOCALIDAD"}, "estado": None}))
    conflicto = calidad_de_ubicacion(
        _prop(geo={"area_busqueda": {"nivel": "LOCALIDAD"},
                   "estado": "GEO_CONFLICT"}))
    assert 0 < conflicto < limpia


def test_la_completitud_mide_cuanto_se_puede_decir_no_cuan_buena_es():
    completa = completitud(_prop())
    incompleta = completitud(_prop(precio=None, dormitorios=None,
                                   superficie_cubierta=None))
    assert completa == 1.0
    assert incompleta < completa


def test_el_precio_no_entra_en_el_ranking():
    """Ordenar por precio es una preferencia de la persona, no una medida de
    calidad: meterlo en el ranking le saca esa decisión."""
    barata = puntaje(_prop(precio=50000.0), "rosario")["total"]
    cara = puntaje(_prop(precio=5000000.0), "rosario")["total"]
    assert barata == cara


def test_el_puntaje_se_puede_explicar():
    """Un ranking que no se puede explicar no se puede corregir: cuando
    alguien pregunte por qué una propiedad salió primera, la respuesta tiene
    que estar en el dato."""
    p = puntaje(_prop(), "rosario")
    assert p["ranking_version"] == RANKING_VERSION
    assert set(p["partes"]) == {"coincidencia", "ubicacion", "completitud",
                                "imagenes"}
    assert abs(sum(p["partes"].values()) - p["total"]) < 0.01


def test_el_orden_es_estable():
    """Sin un desempate estable, dos consultas idénticas devuelven órdenes
    distintos y la paginación repite o saltea filas."""
    filas = [_prop(id=f"h{i}") for i in range(5)]
    una = [f["id"] for f in ordenar(list(filas), "rosario")]
    otra = [f["id"] for f in ordenar(list(reversed(filas)), "rosario")]
    assert una == otra


def test_una_propiedad_sin_nada_igual_puntua_y_no_desaparece():
    """El ranking ordena; nunca filtra."""
    pobre = _prop(titulo=None, precio=None, imagenes=[],
                  geo={"area_busqueda": {"nivel": "SIN_AREA"}})
    ordenadas = ordenar([pobre, _prop()], "rosario")
    assert len(ordenadas) == 2
    assert ordenadas[-1]["ranking"]["total"] >= 0
def test_fast_unicode_fold_preserves_original_semantics():
    import unicodedata
    from api.ranking import _plegar
    for value in ('Córdoba', 'MUÑOZ', 'áéíóú', 'a\u1ab0', 'العربية', 'Straße', 'ASCII', None):
        expected = '' if not isinstance(value, str) else ''.join(
            c for c in unicodedata.normalize('NFD', value) if unicodedata.category(c) != 'Mn').casefold()
        assert _plegar(value) == expected

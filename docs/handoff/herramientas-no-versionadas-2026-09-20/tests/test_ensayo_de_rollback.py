# -*- coding: utf-8 -*-
"""La reversion tiene que devolver la tabla exactamente como estaba.

El ensayo grande corre sobre las 28.251 colisiones reales del dry-run. Estos
tests corren sobre unas pocas filas armadas a mano, para que la propiedad quede
fijada aunque el artefacto no este.
"""
from scripts.ensayo_de_rollback import (CAMPOS, aplicar, base_local, copia,
                                        perdidos, revertir, sembrar)


def _fila(k, no_tocar=(), aporta=()):
    return {"k": k, "clase": "UPDATE", "no_tocar": list(no_tocar),
            "aporta": list(aporta)}


def test_el_update_ingenuo_borra_lo_que_produccion_tenia():
    """Si esto deja de fallar, el ensayo dejo de probar algo."""
    filas = [_fila("a", no_tocar=["ciudad", "barrio"]),
             _fila("b", no_tocar=["direccion"])]
    cx = base_local()
    sembrar(cx, filas)
    antes = copia(cx)
    aplicar(cx, filas, "ingenuo")
    cuenta = perdidos(antes, copia(cx))
    assert cuenta["ciudad"] == 1
    assert cuenta["barrio"] == 1
    assert cuenta["direccion"] == 1


def test_el_update_coalesce_safe_no_borra_nada():
    filas = [_fila("a", no_tocar=["ciudad", "barrio"], aporta=["banos"]),
             _fila("b", no_tocar=["direccion"])]
    cx = base_local()
    sembrar(cx, filas)
    antes = copia(cx)
    aplicar(cx, filas, "coalesce")
    assert perdidos(antes, copia(cx)) == {}


def test_el_coalesce_safe_igual_aporta_lo_que_falta():
    """No perder no puede significar no escribir."""
    filas = [_fila("a", aporta=["banos", "latitud"])]
    cx = base_local()
    sembrar(cx, filas)
    assert cx.execute("select banos from propiedades where k='a'").fetchone()[0] is None
    aplicar(cx, filas, "coalesce")
    assert cx.execute("select banos from propiedades where k='a'").fetchone()[0] == "nuevo:banos"


def test_la_reversion_deja_la_tabla_byte_a_byte_como_estaba():
    filas = [_fila("a", no_tocar=["ciudad"], aporta=["banos"]),
             _fila("b", aporta=["latitud", "provincia"]),
             _fila("c", no_tocar=["superficie_total"])]
    cx = base_local()
    sembrar(cx, filas)
    antes = copia(cx)
    previas = aplicar(cx, filas, "coalesce")
    assert copia(cx) != antes, "el update no cambio nada, no hay que revertir"
    revertir(cx, previas)
    assert copia(cx) == antes


def test_la_imagen_previa_cubre_todas_las_columnas():
    """Un rollback que no anota una columna no la puede devolver."""
    filas = [_fila("a", aporta=["banos"])]
    cx = base_local()
    sembrar(cx, filas)
    previas = aplicar(cx, filas, "coalesce")
    assert len(previas[0]) == 1 + len(CAMPOS)

"""La misma propiedad publicada dos veces."""
from __future__ import annotations

from scripts.property_duplicate_groups import agrupar, firma_de


def _fila(**cambios):
    base = {"latitud": -31.46879, "longitud": -64.27255,
            "tipo_propiedad": "casa", "operacion": "venta",
            "dormitorios": 4, "superficie_cubierta": 189.0,
            "titulo": "Casa en Venta", "precio": 230000.0, "moneda": "USD",
            "source_url": "https://alfa.com.ar/p/1"}
    base.update(cambios)
    return base


def test_dos_inmobiliarias_publicando_la_misma_casa():
    """El caso real: una casa de Córdoba con la misma coordenada, tipo,
    operación, dormitorios, superficie y precio, publicada por `aagaard
    inmobiliaria` y por `platinus bienes raices`. En el portal salía dos veces.
    """
    grupos, resumen = agrupar([
        (_fila(), "roomix:aagaard inmobiliaria", "h1"),
        (_fila(source_url="https://beta.com.ar/p/9"), "roomix:platinus", "h2"),
    ])
    assert len(grupos) == 1
    assert grupos[0]["alcance"] == "ENTRE_INMOBILIARIAS"
    assert len(grupos[0]["miembros"]) == 2
    assert resumen["grupos_entre_inmobiliarias"] == 1
    assert resumen["pares_de_inmobiliarias"] == 1


def test_no_elige_ganador():
    """Cuál de las dos se muestra define quién se lleva el clic: es una
    decisión comercial, no técnica. Borrar una la destruiría antes de que
    nadie la tome."""
    grupos, resumen = agrupar([
        (_fila(), "roomix:alfa", "h1"),
        (_fila(), "roomix:beta", "h2"),
    ])
    assert grupos[0]["ganador_elegido"] is None
    assert resumen["ganadores_elegidos"] == 0
    assert resumen["database_writes"] == 0


def test_la_misma_inmobiliaria_publicando_dos_veces():
    """`hash_dedup` no lo ve porque hashea la URL, y las dos URLs difieren sólo
    en el id de la ficha: `257229-PH-en-Venta-...` y `393830-PH-en-Venta-...`,
    mismo título y mismo precio. Son 397 grupos, más que los 117 entre
    inmobiliarias distintas."""
    grupos, resumen = agrupar([
        (_fila(source_url="https://alfa.com.ar/257229-PH-en-Venta"), "roomix:alfa", "h1"),
        (_fila(source_url="https://alfa.com.ar/393830-PH-en-Venta"), "roomix:alfa", "h2"),
    ])
    assert grupos[0]["alcance"] == "MISMA_INMOBILIARIA"
    assert resumen["grupos_dentro_de_la_misma"] == 1
    assert resumen["grupos_entre_inmobiliarias"] == 0


def test_una_firma_con_nulos_no_es_identidad_sino_ausencia():
    """Agrupar por una firma incompleta juntaba edificios enteros: todas las
    unidades sin dormitorios ni superficie caían en la misma clave."""
    assert firma_de(_fila(dormitorios=None)) is None
    assert firma_de(_fila(superficie_cubierta=None)) is None
    assert firma_de(_fila(latitud=None)) is None
    grupos, resumen = agrupar([
        (_fila(dormitorios=None), "roomix:alfa", "h1"),
        (_fila(dormitorios=None), "roomix:beta", "h2"),
    ])
    assert grupos == []
    assert resumen["con_firma_completa"] == 0
    assert resumen["candidatas"] == 2


def test_coordenadas_distintas_no_se_juntan():
    """Se redondea a 5 decimales (~1,1 m). Eso pierde duplicados reales cuando
    dos inmobiliarias geocodifican distinto, y es a propósito: perder uno es
    mejor que fusionar dos propiedades que no son la misma."""
    grupos, _ = agrupar([
        (_fila(), "roomix:alfa", "h1"),
        (_fila(latitud=-31.46979), "roomix:beta", "h2"),
    ])
    assert grupos == []
    # Una diferencia por debajo del redondeo sí es el mismo punto.
    assert firma_de(_fila(latitud=-31.468790001)) == firma_de(_fila())


def test_una_sola_publicacion_no_es_un_grupo():
    grupos, resumen = agrupar([(_fila(), "roomix:alfa", "h1")])
    assert grupos == []
    assert resumen["con_firma_completa"] == 1
    assert resumen["filas_agrupadas"] == 0


def test_precios_distintos_se_marcan():
    """Una re-publicación a otro precio sin bajar la anterior. Son 297 de los
    514 grupos, así que el precio no puede usarse para decidir identidad."""
    grupos, resumen = agrupar([
        (_fila(precio=260000.0), "roomix:alfa", "h1"),
        (_fila(precio=270000.0), "roomix:alfa", "h2"),
    ])
    assert grupos[0]["precios_distintos"] is True
    assert resumen["grupos_con_precios_distintos"] == 1

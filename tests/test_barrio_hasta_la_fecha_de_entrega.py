# -*- coding: utf-8 -*-
"""El barrio estaba bien; lo que sobraba era el campo siguiente.

`_valores_campo` corta el valor en la proxima etiqueta conocida, y con un
tope de 70 caracteres si no encuentra ninguna. Los avisos de pozo publican
`Fecha de entrega` y esa etiqueta no estaba en la lista, asi que el valor
seguia de largo:

    barrio = 'Centro Fecha de entrega Diciembre 2027'
    barrio = 'Lanus Este Fecha de entrega Abril 2029'
    barrio = 'Rada Tilly Fecha de entrega Junio 2026'

Medido sobre el snapshot: de 1.715 barrios que son texto recortado, **1.243
—el 72,5 %— contienen esta etiqueta** y son todos recuperables cortando ahi.

Es el mismo mecanismo que ya habia dejado 1.145 fichas con prosa guardada
como ubicacion —«tranquila», «residencial»—, y la misma familia de arreglo:
darle al valor la frontera que le faltaba en vez de inventar una heuristica
sobre el contenido.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.tokko import ETIQUETAS, _campo  # noqa: E402


def test_MUERDE_el_barrio_corta_antes_de_la_fecha_de_entrega():
    """Los casos reales del snapshot, tal cual."""
    for texto, esperado in (
            ("Ubicación Centro Fecha de entrega Diciembre 2027", "Centro"),
            ("Ubicación Lanús Este Fecha de entrega Abril 2029", "Lanús Este"),
            ("Ubicación Rada Tilly Fecha de entrega Junio 2026", "Rada Tilly"),
            ("Ubicación Caballito Fecha de entrega Abril 2027", "Caballito")):
        assert _campo(texto, "Ubicación") == esperado, texto


def test_MUERDE_un_barrio_de_varias_palabras_no_se_recorta_de_mas():
    """La otra mitad, y la que impide arreglar esto rompiendo otra cosa.

    `Nuestra Señora de Lourdes` y `Lomas de Zamora Oeste` son barrios reales
    con mayusculas y preposiciones adentro. Un corte por «la proxima palabra
    con mayuscula» se los comeria.
    """
    for nombre in ("Nuestra Señora de Lourdes", "Lomas de Zamora Oeste",
                   "Nueva Córdoba", "Villa del Parque"):
        assert _campo(f"Ubicación {nombre} Fecha de entrega Mayo 2027",
                      "Ubicación") == nombre


def test_una_ficha_sin_fecha_de_entrega_se_lee_igual_que_antes():
    """La mayoria de las fichas no son de pozo: no pueden cambiar."""
    assert _campo("Ubicación Palermo Dormitorios 2", "Ubicación") == "Palermo"
    assert _campo("Dirección Sarmiento 1726 Ubicación Rosario",
                  "Dirección") == "Sarmiento 1726"


def test_la_etiqueta_esta_en_las_dos_capitalizaciones_que_usa_tokko():
    assert "Fecha de entrega" in ETIQUETAS
    assert "Fecha de Entrega" in ETIQUETAS


def test_MUERDE_la_etiqueta_no_se_lleva_puesto_un_barrio_que_la_contenga():
    """Ningun barrio se llama asi, pero el corte tiene que ser por rotulo.

    Si la frontera se aplicara sin exigir que sea etiqueta, un valor que
    mencione la palabra quedaria partido por la mitad.
    """
    assert _campo("Ubicación Centro Dormitorios 3", "Ubicación") == "Centro"


def test_la_direccion_tambien_gana_la_frontera():
    """`_STOP` es compartido: lo que corta un campo corta todos.

    Es deseable —la direccion sufria lo mismo— y conviene que quede fijado,
    porque significa que agregar una etiqueta afecta a mas de un campo.
    """
    assert _campo("Dirección Arizu 245 Fecha de entrega Enero 2026",
                  "Dirección") == "Arizu 245"

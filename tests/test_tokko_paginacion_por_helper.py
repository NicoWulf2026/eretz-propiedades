# -*- coding: utf-8 -*-
"""Tokko cambió cómo arma la url de paginación, y el listado quedó en 20.

El síntoma llegó dos veces seguidas y con el mismo número, que es lo que lo
delató: `aagaard inmobiliaria` declara 295 y enumeramos **20**;
`abriola propiedades` declara 274 y enumeramos **20**. Exactamente veinte es
`POR_PAGINA`, o sea la primera página y nada más.

`aagaard` había cerrado `CERTIFIED_COMPLETE` el 2026-09-09 con **297 y 298**
sobre 315 páginas. O sea que se perdió el 93 % de un inventario que sabíamos
leer.

La causa, leída del HTML de las dos fuentes. El template TFW llamaba así:

    $.ajax('/Propiedades?o=2,2&p=' + current_page)

y `RE_AJAX` sacaba de ahí la query. Hoy llama así:

    $.ajax(tfwListingUrl('', {o: '2,2', p: current_page}))

con el ayudante definido en la misma página:

    function tfwListingUrl(searchQuery, values) {
      const params = new URLSearchParams(searchQuery);
      Object.keys(values).forEach(k => params.set(k, String(values[k])));
      return '?' + tfwRenderQuery(params);
    }

No hay ninguna url literal, así que `query_paginacion` quedaba en `None`. Y en
`fetch_listing` eso cae en `else: break`, que corta después de la primera
página. Veinte.

Comprobado contra la fuente: `…/Propiedades?p=2` devuelve **20 ids nuevos**,
ninguno repetido de la página 1. La paginación funciona; lo que faltaba era
saber pedirla.

Es un cambio del proveedor, no una regresión nuestra, y por eso no aparece en
ningún diff de nuestro código. Pero nos cuesta inventario igual, y de a
familias enteras: son 875 agencias con `connector: tokko` declarado.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.tokko import query_de_paginacion  # noqa: E402

VIEJO = """
  $.ajax('/Propiedades?o=2,2&p=' + current_page)
    .done(function(result){ });
"""

NUEVO = """
  $.ajax(tfwListingUrl('', {o: '2,2', p: current_page}))
    .done(function(result){
        if(result.indexOf("--NoMoreProperties--") != -1){ }
    });
"""

NUEVO_CON_BUSQUEDA = """
  $.ajax(tfwListingUrl('tipo=casa&operacion=venta', {o: '1,1', p: current_page}))
"""

RUIDO = """
  $.ajax('/add_star/'+id).done(function(result){ });
  $.ajax('/remove_star/'+id).done(function(result){ });
  $.ajax('/infowindow_full/'+id).done(function(result) { });
"""


def test_la_forma_vieja_se_sigue_leyendo():
    """No se puede arreglar la nueva rompiendo la que funciona.

    Hay sitios TFW que todavía sirven el template anterior, y son la mayoría
    de las 86 agencias Tokko que hoy cierran bien.
    """
    assert query_de_paginacion(VIEJO) == "/Propiedades?o=2,2&p="


def test_MUERDE_la_forma_nueva_se_reconstruye():
    """El caso `aagaard` y `abriola`, exacto.

    Se reconstruye la query con los valores literales del ayudante y la clave
    de página al final, que es lo que `fetch_listing` concatena con el número.
    """
    assert query_de_paginacion(NUEVO) == "?o=2,2&p="


def test_la_busqueda_previa_se_conserva():
    """El primer argumento del ayudante son filtros ya aplicados.

    Tirarlos cambiaría el conjunto que se pagina: se estaría recorriendo otro
    catálogo que el que la página muestra.
    """
    assert query_de_paginacion(NUEVO_CON_BUSQUEDA) == (
        "?tipo=casa&operacion=venta&o=1,1&p=")


def test_MUERDE_las_llamadas_que_no_son_de_paginacion_no_confunden():
    """`/add_star/`, `/remove_star/` y `/infowindow_full/` están en la página.

    Tomar cualquiera de ellas como query de paginación pediría páginas que no
    existen y devolvería cero, que es peor que el defecto actual: cambiaría
    «enumeramos 20 de 295» por «enumeramos 0».
    """
    assert query_de_paginacion(RUIDO) is None


def test_sin_ninguna_llamada_no_se_inventa_nada():
    assert query_de_paginacion("<html><body>nada</body></html>") is None
    assert query_de_paginacion("") is None


def test_MUERDE_un_ayudante_sin_clave_de_pagina_no_se_usa():
    """Si no hay una clave de página, concatenar el número al final inventaría
    un parámetro. Mejor no paginar que pedir cualquier cosa."""
    sin_pagina = "$.ajax(tfwListingUrl('', {o: '2,2'}))"
    assert query_de_paginacion(sin_pagina) is None


def test_el_orden_de_las_claves_deja_la_pagina_al_final():
    """`fetch_listing` hace `base + ruta + query + str(pagina)`.

    Si la clave de página no quedara última, el número se pegaría al valor
    equivocado.
    """
    revuelto = "$.ajax(tfwListingUrl('', {p: current_page, o: '2,2'}))"
    assert query_de_paginacion(revuelto).endswith("&p=")
    assert "o=2,2" in query_de_paginacion(revuelto)

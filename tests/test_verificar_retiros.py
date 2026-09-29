"""Politica P1: solo se retira con evidencia de muerte en la propia URL."""
from __future__ import annotations

from scripts.verificar_retiros import (AMBIGUA, NO_VERIFICABLE, REMOVED, VIVA,
                                       clasificar)

URL = "https://www.cosapropiedades.com/p/7779042-Departamento-en-Venta-en-Centro"
FICHA = ("<html><head><title>COSA Propiedades - Departamento en Venta en Centro</title></head>"
         "<body><h1>Departamento en Venta en Centro</h1><span>Ref. 7779042</span></body></html>")
PORTADA = "<html><head><title>COSA Propiedades</title></head><body><h1>Bienvenidos</h1></body></html>"


def _c(saltos, cuerpo, titulo="Departamento en Venta en Centro", portada="COSA Propiedades"):
    return clasificar(URL, saltos, cuerpo, titulo, "7779042", portada)[0]


def test_404_y_410_son_muerte():
    assert _c([(404, URL)], "") == REMOVED
    assert _c([(410, URL)], "") == REMOVED


def test_MUERDE_una_ficha_viva_no_se_retira_aunque_falte_del_inventario():
    assert _c([(200, URL)], FICHA) == VIVA


def test_redireccion_permanente_a_la_portada_es_muerte():
    assert _c([(301, URL), (200, "https://www.cosapropiedades.com/")], PORTADA) == REMOVED


def test_redireccion_temporal_a_la_portada_sin_rastro_es_soft404():
    assert _c([(302, URL), (200, "https://www.cosapropiedades.com/")], PORTADA) == REMOVED


def test_MUERDE_redireccion_al_nuevo_slug_de_la_misma_ficha_no_es_muerte():
    nuevo = "https://www.cosapropiedades.com/p/7779042-Departamento-renovado"
    assert _c([(301, URL), (200, nuevo)], FICHA) == VIVA


def test_soft404_por_el_titulo():
    cuerpo = "<html><head><title>Página no encontrada | COSA</title></head><body>Ventas</body></html>"
    assert _c([(200, URL)], cuerpo) == REMOVED


def test_MUERDE_vendida_en_el_menu_no_es_soft404():
    cuerpo = ("<html><head><title>COSA Propiedades</title></head><body><nav>Vendidas Alquiladas</nav>"
              "<p>Propiedad no disponible para visitas los domingos</p></body></html>")
    assert _c([(200, URL)], cuerpo) == AMBIGUA


def test_MUERDE_titulo_generico_sin_redireccion_no_prueba_nada():
    """Muchos sitios usan el mismo <title> en todas sus paginas."""
    cuerpo = "<html><head><title>COSA Propiedades</title></head><body><div>cargando…</div></body></html>"
    assert _c([(200, URL)], cuerpo) == AMBIGUA


def test_bloqueo_o_error_no_afirma_nada():
    assert _c([(403, URL)], "") == NO_VERIFICABLE
    assert _c([(429, URL)], "") == NO_VERIFICABLE
    assert _c([(503, URL)], "") == NO_VERIFICABLE
    assert _c([], "") == NO_VERIFICABLE


def test_todo_tokko_es_un_solo_sitio_para_la_cortesia():
    from scripts.verificar_retiros import grupo_de
    assert grupo_de("https://www.lipovich.com.ar/p/8585467-Departamento-en-Alquiler") == "backend:tokko"
    assert grupo_de("https://www.kaizenpropiedades.com/p/6577090-Terreno") == "backend:tokko"
    assert grupo_de("https://farinainmobiliaria.com.ar/property/100775-2/") == "farinainmobiliaria.com.ar"

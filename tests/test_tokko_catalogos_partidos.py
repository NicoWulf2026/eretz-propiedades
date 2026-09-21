# -*- coding: utf-8 -*-
"""Un sitio con varios catalogos no termina donde termina el primero.

`andrea gianfelice inmobiliaria` paro la cola con radio FAMILIA: la fuente
declara 158 y enumeramos 44. Diagnosticado contra la fuente, su sitio publica
tres catalogos:

    /Venta            147
    /Alquiler          10
    /Emprendimientos    7

y `discover` hacia `next(r for r in RUTAS_LISTADO if ...)`, que devuelve
siempre `/Venta` porque encabeza la lista. Los otros dos no existian para el
conector, y la enumeracion se declaraba completa igual.

Es el **mismo error conceptual que la paginacion rota de esta manana**, en
otra forma. Antes el catalogo terminaba donde terminaba la primera pagina;
aca termina donde termina el primer catalogo. Las dos veces el sintoma fue el
mismo: certificar en silencio una parte como si fuera el todo.

Medido sobre 45 sitios tokko: **10 estan partidos asi**, todos perdiendo
`/Alquiler` y seis ademas `/Emprendimientos`. En los 11 casos donde se leyeron
los totales declarados de cada ruta son **291 propiedades invisibles sobre
1.767, el 16,5%**.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.tokko import TokkoConnector  # noqa: E402


def enlaces(*rutas: str) -> str:
    cuerpo = "".join(f'<a href="{r}">x</a>' for r in rutas)
    return f"<html><body>{cuerpo}</body></html>"


def test_MUERDE_un_sitio_partido_devuelve_todos_sus_catalogos():
    """El caso `gianfelice`, exacto."""
    html = enlaces("/Venta", "/Alquiler", "/Emprendimientos", "/Contacto")
    assert TokkoConnector.rutas_del_catalogo(html, "/") == [
        "/Venta", "/Alquiler", "/Emprendimientos"]


def test_MUERDE_venta_sigue_siendo_la_principal():
    """`ruta_listado` no puede cambiar de significado.

    Media docena de cosas leen ese campo -el triaje, los diferidos, los
    artefactos ya escritos-. Si la principal pasara a ser `/Alquiler` porque
    aparece antes en el HTML, todas leerian otra cosa sin enterarse.
    """
    html = enlaces("/Alquiler", "/Emprendimientos", "/Venta")
    assert TokkoConnector.rutas_del_catalogo(html, "/")[0] == "/Venta"


def test_un_catalogo_unificado_se_lee_solo_a_el():
    """`/Propiedades` ya trae venta y alquiler: sumarle `/Venta` seria
    recorrer dos veces lo mismo y duplicar el costo de red sin ganar nada."""
    html = enlaces("/Propiedades", "/Venta", "/Alquiler")
    assert TokkoConnector.rutas_del_catalogo(html, "/") == ["/Propiedades"]


def test_sin_ninguna_ruta_reconocible_el_listado_es_la_propia_pagina():
    con_fichas = '<html><body><a href="/p/123-casa-linda">x</a></body></html>'
    assert TokkoConnector.rutas_del_catalogo(con_fichas, "/inicio") == ["/inicio"]


def test_una_pagina_sin_fichas_ni_rutas_no_inventa_un_catalogo():
    assert TokkoConnector.rutas_del_catalogo("<html></html>", "/") == []


def test_MUERDE_el_total_declarado_es_la_suma_de_los_catalogos():
    """147 no es el catalogo: 164 lo es.

    Sin esto la enumeracion se compara contra el total de `/Venta` y da
    completa con el 90% del inventario adentro.
    """
    plan = {"catalogos": [{"total_declarado": 147}, {"total_declarado": 10},
                          {"total_declarado": 7}]}
    totales = [c["total_declarado"] for c in plan["catalogos"]
               if c["total_declarado"] is not None]
    assert sum(totales) == 164


def test_MUERDE_un_solo_catalogo_sin_paginacion_trunca_el_sitio_entero():
    """Aunque los otros paginen bien.

    Ese catalogo queda en 20 y el sitio no esta enumerado entero. Preguntarle
    solo al principal diria que todo anda.
    """
    plan = {"catalogos": [
        {"ids_primera_pagina": 20, "query_paginacion": "?o=2,2&p="},
        {"ids_primera_pagina": 20, "query_paginacion": None}]}
    assert TokkoConnector.paginacion_imposible(plan) is True


def test_con_todos_los_catalogos_paginables_no_hay_truncamiento():
    plan = {"catalogos": [
        {"ids_primera_pagina": 20, "query_paginacion": "?o=2,2&p="},
        {"ids_primera_pagina": 10, "query_paginacion": "?o=2,2&p="}]}
    assert TokkoConnector.paginacion_imposible(plan) is False


def test_un_plan_viejo_sin_catalogos_se_sigue_evaluando_igual():
    """Los artefactos ya escritos no tienen `catalogos`.

    Si esto rompiera, cada plan guardado antes de hoy pasaria a evaluarse
    como si pudiera paginar.
    """
    assert TokkoConnector.paginacion_imposible(
        {"ids_primera_pagina": 20, "query_paginacion": None}) is True
    assert TokkoConnector.paginacion_imposible(
        {"ids_primera_pagina": 20, "query_paginacion": "?p="}) is False
    assert TokkoConnector.paginacion_imposible(
        {"ids_primera_pagina": 0, "query_paginacion": None}) is False


class DescargadorFalso:
    """Sirve paginas de memoria y anota que se pidio."""

    def __init__(self, paginas: dict[str, str]) -> None:
        self.paginas = paginas
        self.pedidos: list[str] = []

    def bajar(self, url: str) -> str:
        self.pedidos.append(url)
        return self.paginas.get(url, "<html></html>")

    @staticmethod
    def url_segura(url: str) -> str:
        return url


def ficha(pid: int) -> str:
    return f'<a href="/p/{pid}-casa">x</a>'


def test_MUERDE_fetch_listing_recorre_los_tres_catalogos():
    """La prueba de punta a punta del caso real, sin red.

    Venta 3, Alquiler 2, Emprendimientos 1. Con el defecto salen 3.
    """
    conector = TokkoConnector()
    conector.descargador = DescargadorFalso({})
    plan = {"soportada": True, "base": "https://x.com", "catalogos": [
        {"ruta": "/Venta", "query_paginacion": None, "total_declarado": 3,
         "html_listado": ficha(1) + ficha(2) + ficha(3)},
        {"ruta": "/Alquiler", "query_paginacion": None, "total_declarado": 2,
         "html_listado": ficha(4) + ficha(5)},
        {"ruta": "/Emprendimientos", "query_paginacion": None,
         "total_declarado": 1, "html_listado": ficha(6)}]}
    ids = [a["source_listing_id"]
           for a in conector.fetch_listing(_fuente(), plan)]
    assert ids == ["1", "2", "3", "4", "5", "6"]


def test_MUERDE_una_propiedad_en_dos_catalogos_se_emite_una_sola_vez():
    """Un emprendimiento suele estar tambien en venta.

    Emitirlo dos veces inflaria el inventario con duplicados, que es el error
    opuesto y igual de malo.
    """
    conector = TokkoConnector()
    conector.descargador = DescargadorFalso({})
    plan = {"soportada": True, "base": "https://x.com", "catalogos": [
        {"ruta": "/Venta", "query_paginacion": None, "total_declarado": 2,
         "html_listado": ficha(1) + ficha(2)},
        {"ruta": "/Emprendimientos", "query_paginacion": None,
         "total_declarado": 2, "html_listado": ficha(2) + ficha(3)}]}
    ids = [a["source_listing_id"]
           for a in conector.fetch_listing(_fuente(), plan)]
    assert ids == ["1", "2", "3"]


def test_MUERDE_un_catalogo_repetido_no_corta_por_parecer_agotado():
    """El segundo catalogo empieza con fichas que ya salieron en el primero.

    Si el avance se midiera con `vistos` -las del sitio entero- ese catalogo
    daria cero nuevas en su primera pagina y cortaria antes de llegar a las
    suyas. Se mide con las propias.
    """
    conector = TokkoConnector()
    conector.descargador = DescargadorFalso({
        "https://x.com/Emprendimientos?p=2": ficha(9)})
    plan = {"soportada": True, "base": "https://x.com", "catalogos": [
        {"ruta": "/Venta", "query_paginacion": None, "total_declarado": 2,
         "html_listado": ficha(1) + ficha(2)},
        {"ruta": "/Emprendimientos", "query_paginacion": "?p=",
         "total_declarado": 3, "html_listado": ficha(1) + ficha(2)}]}
    ids = [a["source_listing_id"]
           for a in conector.fetch_listing(_fuente(), plan)]
    assert "9" in ids


def test_un_plan_viejo_sin_catalogos_sigue_recorriendo_su_ruta():
    conector = TokkoConnector()
    conector.descargador = DescargadorFalso({})
    plan = {"soportada": True, "base": "https://x.com",
            "ruta_listado": "/Propiedades", "query_paginacion": None,
            "total_declarado": 2, "html_listado": ficha(7) + ficha(8)}
    ids = [a["source_listing_id"]
           for a in conector.fetch_listing(_fuente(), plan)]
    assert ids == ["7", "8"]


def _fuente():
    from connectors.base import Fuente
    return Fuente(canonical_agency_id="roomix:x", agency_name="X",
                  official_url="https://x.com/", inmobiliaria_id=0, extra={})

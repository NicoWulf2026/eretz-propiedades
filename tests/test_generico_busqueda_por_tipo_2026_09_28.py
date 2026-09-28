"""Plantilla Oestesi/Argencasas (`david rodriguez`, 365 declaradas).

La portada carga el catalogo por tipo con POST a `buscar.php` ({type, page}) y
la ficha abre `<h2>` y cierra `</h1>`. En vivo el 28-09: 365/365 enumeradas;
muestra de 12 con titulo propio, operacion, tipo, precio y fotos. Radio del
cierre tolerante: 0 de 201.
"""
from __future__ import annotations

from connectors.base import ErrorPermanente, Fuente
from connectors.generico import GenericoConnector

BASE = "https://dr.test"
PORTADA = BASE + "/home/"
FUENTE = Fuente("roomix:dr", "DR", PORTADA, 1)
HOME = """<html><form id="searchPropertiesByTypeId" method="post">
<div onclick="buscar('Casa')"><h4>Casa</h4><span>3 Propiedades</span></div>
<div onclick="buscar('Lote')"><h4>Lote</h4><span>1 Propiedades</span></div></form>
<script>function buscar(event){ $("#n"+event).load("buscar.php", { "type": event });
$("#n"+event).on("click", ".pagination a", function (e) { var page = $(this).attr("data-page");
$("#n"+event).load("buscar.php", { "page": page, "type": event }, function () {}); }); }</script></html>"""
PAGINAS = {("Casa", 1): [1, 2], ("Casa", 2): [3], ("Lote", 1): [4]}


class Falso:
    def __init__(self):
        self.formularios = []

    def bajar(self, url):
        if url in (PORTADA, BASE, BASE + "/"):
            return HOME
        raise ErrorPermanente(url)

    def bajar_formulario(self, url, formulario, limite):
        assert url == PORTADA + "buscar.php"
        self.formularios.append(dict(formulario))
        tipo, pagina = formulario["type"], int(formulario.get("page", 1))
        ids = PAGINAS.get((tipo, pagina), [])
        enlaces = "".join(f'<a href="propiedad-detalle.php?id={i}">ver</a>'
                          f'<a href="https://maps.google.com/maps?q=x">mapa</a>' for i in ids)
        paginas = '<ul class="pagination"><a data-page="2">2</a></ul>' if tipo == "Casa" else ""
        return enlaces + paginas


def test_enumera_cada_tipo_y_sus_paginas_por_post() -> None:
    falso = Falso()
    c = GenericoConnector(falso)
    plan = c.discover(FUENTE)
    assert plan["variante"] == "BUSQUEDA_POR_TIPO"
    assert plan["total_declarado"] == 4
    urls = [i["source_url"] for i in c.fetch_listing(FUENTE, plan)]
    assert urls == [f"{PORTADA}propiedad-detalle.php?id={i}" for i in (1, 2, 3, 4)]
    assert {"type": "Casa", "page": 2} in falso.formularios


def test_el_titulo_con_cierre_de_otro_nivel() -> None:
    html = ('<html><head><title>David Propiedades | Agentes inmobiliarios</title></head><body>'
            '<p><h2 style="font-weight:500">Casa en venta en Moron Norte</h1></p>'
            '<h5>Falucho al 745 - Moron Norte</h5></body></html>')
    assert GenericoConnector._titulo_de_la_ficha(html, {}, FUENTE) == "Casa en venta en Moron Norte"

"""Catalogo servido por un Strapi propio del sitio (`diego martin`, 51 propiedades).

El HTML de Next.js no trae propiedades; la url de la API esta en el JavaScript
propio del sitio. Verificado en vivo el 28-09: 51/51 enumeradas y normalizadas
(titulo, operacion, precio y fotos en las 51; coordenadas en 50).
"""
from __future__ import annotations

import json

from connectors.base import ErrorPermanente, Fuente
from connectors.generico import GenericoConnector

BASE = "https://dm.test"
API = "https://dm-api.test/api/propiedades"
FUENTE = Fuente("roomix:dm", "DM", BASE, 1)
MAPA = ('<iframe src="https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3291.1'
        '!2d-58.57777822414619!3d-34.42413144803636!2m3"></iframe>')


def _fila(i: int, **attrs) -> dict:
    base = {"Titulo": f"Casa {i}", "descripcion": "Casa con jardin", "Tipo_de_operacion": "Venta",
            "tipo_de_inmueble": "Casa ", "valor_dolares": "120000", "valor_pesos": None,
            "Ambientes": "c 3 ambientes ", "Dormitorios": "c 2 dormitorios ",
            "Banos": "c 1 baños ", "coordenadas": MAPA, "Localidades": "Tigre",
            "m2_cubiertos": 90, "metros_totales2": None, "Lote": "7.50 x 47",
            "Imagen": {"data": [{"id": 1, "attributes": {"url": f"https://img.test/{i}.jpg"}}]}}
    base.update(attrs)
    return {"id": i, "attributes": base}


class Falso:
    def __init__(self, filas: list[dict], por_pagina: int = 10):
        self.filas, self.por_pagina, self.pedidos = filas, por_pagina, []

    def bajar(self, url: str) -> str:
        self.pedidos.append(url)
        if url == BASE or url == BASE + "/":
            return ('<html><script src="/_next/static/chunks/main.js"></script>'
                    '<script src="/_next/static/chunks/app/page-abc.js"></script></html>')
        if url.endswith("/_next/static/chunks/app/page-abc.js"):
            return f'let r="{API}?".concat(s,"&populate=*&pagination[page]=")'
        if url.startswith(API):
            import re
            pagina = int(re.search(r"pagination\[page\]=(\d+)", url).group(1))
            tam = int(re.search(r"pageSize\]=(\d+)", url).group(1))
            trozo = self.filas[(pagina - 1) * tam: pagina * tam]
            cuantas = -(-len(self.filas) // tam)
            return json.dumps({"data": trozo, "meta": {"pagination": {
                "page": pagina, "pageSize": tam, "pageCount": cuantas, "total": len(self.filas)}}})
        if url.startswith(BASE + "/propiedades/"):
            return '<script src="/_next/static/chunks/app/propiedades/%5Bid%5D/page-x.js"></script>'
        raise ErrorPermanente(url)


def test_descubre_enumera_y_normaliza_el_catalogo_strapi() -> None:
    filas = [_fila(i) for i in range(1, 24)]
    c = GenericoConnector(Falso(filas))
    plan = c.discover(FUENTE)
    assert plan["variante"] == "STRAPI_API" and plan["total_declarado"] == 23
    items = list(c.fetch_listing(FUENTE, plan))
    assert [i["source_url"] for i in items][:2] == [f"{BASE}/propiedades/1", f"{BASE}/propiedades/2"]
    assert len({i["source_listing_id"] for i in items}) == 23
    p = c.normalize(items[0], FUENTE)
    assert (p.titulo, p.operacion, p.tipo_propiedad, p.precio, p.moneda) == (
        "Casa 1", "venta", "casa", 120000.0, "USD")
    assert (p.ambientes, p.dormitorios, p.banos) == (3, 2, 1)
    assert round(p.latitud, 4) == -34.4241 and round(p.longitud, 4) == -58.5778
    assert p.superficie_cubierta == 90 and p.superficie_total is None  # «Lote» es una medida
    assert p.ciudad == "Tigre" and p.imagenes == ["https://img.test/1.jpg"]


def test_una_cota_no_es_un_valor_y_el_peso_lleva_su_moneda() -> None:
    c = GenericoConnector(Falso([]))
    p = c.normalize({"source_listing_id": "9", "source_url": f"{BASE}/propiedades/9",
                     "strapi_objeto": _fila(9, Dormitorios="c 5 o más dormitorios ",
                                            valor_dolares=None, valor_pesos="800000",
                                            coordenadas=None)["attributes"]}, FUENTE)
    assert p.dormitorios is None
    assert (p.precio, p.moneda) == (800000.0, "ARS")
    assert p.latitud is None and "coordenada_de" not in p.extra


def test_sin_la_ruta_publica_de_la_ficha_no_se_adopta() -> None:
    class SinFicha(Falso):
        def bajar(self, url):
            if url.startswith(BASE + "/propiedades/") or url.startswith(BASE + "/propiedad/") \
                    or url.startswith(BASE + "/inmueble/"):
                return "<html>404</html>"
            return super().bajar(url)
    plan = GenericoConnector(SinFicha([_fila(1)])).discover(FUENTE)
    assert plan["variante"] != "STRAPI_API"

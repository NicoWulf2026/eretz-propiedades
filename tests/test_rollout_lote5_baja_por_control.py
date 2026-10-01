"""Lote 5 (LOCAL, 2026-10-01): soft-404 demostrado por control (P1).

`cristian mooswalder` (Tokko, 478 fichas) quedaba NEEDS_FIX por 2 fichas que
el listado sigue enlazando y que redirigen a la portada, igual que un id
inventado. `d amato` (101), por 2 fichas del sitemap que sirven la plantilla
vacia, igual que un id inventado. Medido: 6 agencias / 788 propiedades en
NEEDS_FIX solo por fichas vacias.
"""
from __future__ import annotations

import connectors.base as B
from scripts.run_rollout import _procesar_con, _url_de_control


class _Sitio:
    """Descargador falso: la ficha vacia y el control responden lo que se pida."""

    def __init__(self, titulo_ficha: str, titulo_control: str):
        self.titulo_ficha, self.titulo_control, self.pedidos = titulo_ficha, titulo_control, []

    def bajar(self, url, *a, **k):
        self.pedidos.append(url)
        titulo = self.titulo_control if "999999999" in url else self.titulo_ficha
        return f"<html><head><title>{titulo}</title></head><body>Portada</body></html>"

    def __getattr__(self, nombre):
        return lambda *a, **k: None


class _Conector(B.Connector):
    nombre = "prueba"

    def __init__(self, total: int, vacias: set[int], sitio: _Sitio):
        super().__init__(descargador=sitio)
        self.total, self.vacias = total, vacias

    def discover(self, _fuente):
        return {"variante": "TEST", "soportada": True, "total_declarado": self.total}

    def fetch_listing(self, _fuente, _plan):
        for i in range(1, self.total + 1):
            yield {"source_listing_id": str(1000 + i),
                   "source_url": f"https://alfa.test/p/{1000 + i}-casa", "pagina": 1}

    def normalize(self, crudo, fuente_actual):
        vacia = int(crudo["source_listing_id"]) - 1000 in self.vacias
        extra = {} if vacia else {"precio": 125000.0, "moneda": "USD"}
        return B.PropiedadNormalizada(
            canonical_agency_id=fuente_actual.canonical_agency_id,
            source_listing_id=crudo["source_listing_id"], source_url=crudo["source_url"],
            connector=self.nombre, titulo="Alfa Propiedades" if vacia else f"Casa {crudo['source_listing_id']}",
            inmobiliaria_id=fuente_actual.inmobiliaria_id, **extra)


FUENTE = B.Fuente("roomix:alfa", "Alfa", "https://alfa.test", 7)


def test_la_ficha_vacia_igual_al_control_es_una_baja():
    sitio = _Sitio("Alfa Propiedades - Inicio", "Alfa Propiedades - Inicio")
    r = _procesar_con(_Conector(100, {7, 42}, sitio), FUENTE, 0, True, 60)
    assert r["detalles_obtenidos"] == 98
    assert r["detalles_desaparecidos"] == 2 and r["bajas_demostradas_por_control"] == 2
    assert r["fichas_sin_contenido"] == 0
    assert sum(1 for u in sitio.pedidos if "999999999" in u) == 1   # un control por host


def test_si_el_control_responde_distinto_sigue_siendo_lectura_fallida():
    sitio = _Sitio("Casa en Pilar", "Alfa Propiedades - Inicio")
    r = _procesar_con(_Conector(100, {7}, sitio), FUENTE, 0, True, 60)
    assert r["detalles_desaparecidos"] == 0 and r["fichas_sin_contenido"] == 1


def test_si_las_vacias_son_mayoria_no_se_da_de_baja_ninguna():
    # Un sitio que arma todo en el navegador: todas iguales al control, y
    # aun asi NO son bajas (`paladino`: 43 de 43 cascarones).
    sitio = _Sitio("Alfa Propiedades - Inicio", "Alfa Propiedades - Inicio")
    r = _procesar_con(_Conector(20, set(range(1, 21)), sitio), FUENTE, 0, True, 60)
    assert r["detalles_desaparecidos"] == 0 and r["fichas_sin_contenido"] == 20
    assert not any("999999999" in u for u in sitio.pedidos)


def test_url_de_control():
    assert _url_de_control("https://x.com/p/163683-Casa-en-Venta") == "https://x.com/p/999999999-Casa-en-Venta"
    assert _url_de_control("https://x.com/ficha.php?id=6787754") == "https://x.com/ficha.php?id=999999999"
    assert _url_de_control("https://x.com/propiedad/fragata-pres-sarmiento") == "https://x.com/propiedad/eretz-control-inexistente"
    assert _url_de_control("https://x.com/") is None

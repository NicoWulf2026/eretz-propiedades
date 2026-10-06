"""Xintel/Amaira: la ficha vive en un iframe de ficha.amaira.com.ar (gle 453, duarte 266; 05-10).

La pagina del sitio es un envoltorio sin precio ni schema y el guardian de forma la
rechazaba entera. Se lee la ficha del iframe; la fuente sigue siendo la URL del sitio.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from connectors.base import Checkpoint, Fuente
from connectors.generico import RE_FICHA_AMAIRA, GenericoConnector

URL = "http://www.gleinmobiliaria.com.ar/departamento-en-venta-en-barrio-parque-ficha-gle1241"
AMAIRA = "https://ficha.amaira.com.ar/ficha.php?ficha=gle1241&urlcompleta=" + URL
ENVOLTORIO = ("<html><head><title>Gle - Departamento en venta Barrio Parque 5 ambientes</title></head><body>"
              "<img src='img/logo.png'/><iframe src='" + AMAIRA.replace("&", "&amp;") + "' width='100%'></iframe>"
              + " " * 400 + "</body></html>")
FICHA = ("<html><body><h1>Departamento en venta Barrio Parque 5 ambientes</h1>"
         "<p>Precio venta: U$S 2.400.000</p><ul><li>Operación: Venta</li><li>Localidad: Capital Federal</li>"
         "<li>Barrio: Barrio Parque</li><li>Ambientes: 5 ambientes</li><li>Baños: 4</li></ul>"
         "<img src='https://static.amaira.com.ar/fotos/gle1241_1.jpg'/><img src='https://static.amaira.com.ar/fotos/gle1241_2.jpg'/>"
         "<p>Venta de Departamento 5 AMBIENTES en Barrio Parque, Capital Federal.</p></body></html>")


class _Desc:
    def __init__(self): self.pedidas = []

    def bajar(self, url):
        self.pedidas.append(url)
        return FICHA if "ficha.amaira.com.ar" in url else ENVOLTORIO


def _normalizar():
    d = _Desc()
    g = GenericoConnector(d, Checkpoint(Path(tempfile.mkdtemp()) / "c.json"))
    f = Fuente(canonical_agency_id="roomix:gle negocios e inversiones inmobiliarias", agency_name="Gle",
               official_url="http://www.gleinmobiliaria.com.ar/", inmobiliaria_id=1, detected_platform="UNKNOWN", extra={})
    return g.normalize({"source_listing_id": "gle1241", "source_url": URL}, f), d


def test_MUERDE_se_lee_la_ficha_del_iframe_y_la_fuente_es_la_del_sitio():
    p, d = _normalizar()
    assert p is not None
    assert p.source_url == URL
    assert p.precio == 2400000 and p.moneda == "USD" and p.operacion == "venta"
    assert p.ambientes == 5
    assert any("ficha.amaira.com.ar" in u for u in d.pedidas)


def test_el_patron_acepta_la_ruta_nue_de_duarte():
    html = "<? include(header2.php) ?><iframe src=\"https://ficha.amaira.com.ar/nue/ficha.php?ficha=deh472\"></iframe>"
    assert RE_FICHA_AMAIRA.search(html).group(1).endswith("ficha=deh472")


def test_un_iframe_ajeno_no_se_sigue():
    assert RE_FICHA_AMAIRA.search("<iframe src='https://www.google.com/maps/embed?pb=1'></iframe>") is None

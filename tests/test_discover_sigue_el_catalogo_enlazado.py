# -*- coding: utf-8 -*-
"""Si la fuente registrada YA es `/propiedades`, se dejaba de buscar más hondo.

`fios consultoria` tiene registrado `https://www.fios.com.ar/propiedades`. Esa
página responde 200 con 57 KB de HTML plano, declara 266 y enlaza **14 páginas
`listado.php?…&pagina=N`**. Las fichas —`/propiedad-9871962-venta-casa-…`— no
están ahí: están en las páginas de `listado.php`.

El descubrimiento genérico tenía esta forma:

    listado = base + "/propiedades"
    if ruta_propia != "/propiedades":
        for candidato in [listado] + self._catalogos_enlazados(html, base):
            ...
    else:
        listado = fuente.official_url

O sea: cuando la ruta registrada **era** `/propiedades`, se daba por hecho que
no hacía falta mirar más hondo y se saltaba la exploración entera. Para `fios`
eso significa quedarse con los enlaces de una página que no tiene ninguna
ficha.

La optimización asumía «si la fuente apunta al catálogo, el catálogo está ahí».
Es cierto en la mayoría de los sitios y falso en los que reparten el listado en
una segunda ruta.

`_catalogos_enlazados` ya reconoce `listado` en la ruta. Lo único que faltaba
era dejarlo correr.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import Descargador, Fuente  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

RAIZ_HTML = """<html><title>FIOS</title>
<a href="/propiedades">Propiedades</a>
<a href="/Terreno-en-venta">Terrenos</a>
</html>"""

# La pagina registrada como fuente: declara inventario y enlaza el listado,
# pero no trae una sola ficha.
CATALOGO_HTML = """<html><title>FIOS - Propiedades</title>
<p>266 propiedades</p>
<a href="listado.php?tipo_operacion=1&pagina=1">1</a>
<a href="listado.php?tipo_operacion=1&pagina=2">2</a>
</html>"""

# Donde estan las fichas de verdad.
LISTADO_HTML = """<html><p>263 propiedades</p>
<a href="/propiedad-9871962-venta-casa-1-dormitorio-en-funes">Casa</a>
<a href="/propiedad-9478752-venta-departamento-en-funes">Depto</a>
<a href="/propiedad-1234567-venta-ph-3-ambientes-en-rosario">PH</a>
</html>"""


class DescargadorFalso(Descargador):
    """Sirve las tres páginas y cuenta qué se pidió. Sin red."""

    def __init__(self):
        self.pedidos: list[str] = []

    def bajar(self, url: str, *a, **k) -> str:  # noqa: D102
        self.pedidos.append(url)
        if "listado.php" in url:
            return LISTADO_HTML
        if url.rstrip("/").endswith("/propiedades"):
            return CATALOGO_HTML
        if url.rstrip("/") in ("https://fios.test", "https://fios.test/"):
            return RAIZ_HTML
        # Sitemaps, robots y demas rutas de sondeo: la fuente no las tiene.
        from connectors.base import ErrorPermanente
        raise ErrorPermanente(url)

    def url_segura(self, url: str) -> str:
        return url


def fuente_fios() -> Fuente:
    return Fuente(canonical_agency_id="roomix:fios",
                  agency_name="FIOS Consultoria",
                  official_url="https://fios.test/propiedades")


def test_MUERDE_se_sigue_el_listado_enlazado_desde_el_catalogo():
    """El caso `fios`, exacto.

    La página registrada declara 266 y no tiene fichas. Si el descubrimiento
    se queda ahí, la agencia enumera cero y para la cola con radio FAMILIA,
    que es lo que pasó el 2026-09-17.
    """
    conector = GenericoConnector(DescargadorFalso())
    plan = conector.discover(fuente_fios())
    assert plan["soportada"] is True
    enlaces = plan.get("fichas_home") or plan.get("fichas") or []
    assert any("propiedad-9871962" in u for u in enlaces), enlaces


def test_se_visita_la_ruta_de_listado_y_no_solo_la_registrada():
    conector = GenericoConnector(DescargadorFalso())
    conector.discover(fuente_fios())
    pedidos = conector.descargador.pedidos
    assert any("listado.php" in u for u in pedidos), pedidos


def test_la_exploracion_nueva_no_agrega_una_bajada_de_la_propia_fuente():
    """La optimizacion que se quita no puede convertirse en trabajo de mas.

    Si la ruta registrada ya es `/propiedades`, no se la agrega como candidata:
    volver a bajarla golpearia a la fuente sin aprender nada.

    El numero es 4 y NO es culpa de este cambio: era 4 antes y es 4 despues.
    Son los sondeos previos del propio `discover` -sitemap, proxy de Tokko,
    patron de raiz- que bajan la misma pagina varias veces. Queda anotado como
    lo que es, un desperdicio de presupuesto de cortesia que existe desde antes
    y que merece su propia medicion, no un arreglo de apuro escondido dentro de
    otro.
    """
    conector = GenericoConnector(DescargadorFalso())
    conector.discover(fuente_fios())
    pedidos = [u for u in conector.descargador.pedidos
               if u.rstrip("/").endswith("/propiedades")]
    assert len(pedidos) <= 4, pedidos


def test_MUERDE_entran_TODAS_las_fichas_del_listado_y_no_una():
    """Las tres del listado, no una muestra.

    Si el descubrimiento se quedara con la pagina registrada, serian cero. Si
    mezclara las dos paginas, habria fichas de una y conteos de la otra.
    """
    conector = GenericoConnector(DescargadorFalso())
    plan = conector.discover(fuente_fios())
    enlaces = plan.get("fichas_home") or plan.get("fichas") or []
    for identificador in ("9871962", "9478752", "1234567"):
        assert any(identificador in u for u in enlaces), (identificador, enlaces)

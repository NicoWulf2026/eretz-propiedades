"""Lote 7: CRM TIV Tecnogestion enumerado por su buscador (total declarado + POST)."""
from __future__ import annotations

import re

from connectors.base import ErrorTransitorio, Fuente
from connectors.generico import GenericoConnector as G

BASE = "https://tiv.example"
PORTADA = ("<html><head><meta name='description' content='Agencia CRM Inmobiliario TIV Tecnogestion'>"
           "</head><body><a href='/inmueble/casa-venta-centro-lp101'>destacada</a>"
           "<a href='/buscar/inmuebles/'>Buscar</a></body></html>")


def _tarjetas(ids):
    return "".join(f"<div class='propertyItem'><a href='/inmueble/depto-venta-lp{i}'>x</a></div>"
                   for i in ids)


class Sitio:
    """25 declaradas: 10 en el buscador, 10 y 5 por POST, despues vacio."""

    def __init__(self, total=25, cortar_en=None):
        self.total, self.cortar_en, self.posts = total, cortar_en, []

    def bajar(self, url, *a, **k):
        if url.rstrip("/").endswith("/buscar/inmuebles"):
            return (f"<li><a data-filter='*'>{self.total} inmuebles encontrados.</a></li>"
                    + _tarjetas(range(1, 11)))
        return PORTADA

    def bajar_formulario(self, url, formulario, limite=None):
        assert url == BASE + "/Buscar/CargaMasInmueblesParam"
        pagina = int(formulario["Pagina"])
        self.posts.append(pagina)
        if self.cortar_en == pagina:
            raise ErrorTransitorio("http 500")
        desde = (pagina - 1) * 10 + 1
        return _tarjetas(range(desde, min(desde + 10, self.total + 1)))

    def __getattr__(self, nombre):
        return lambda *a, **k: None


def _enumerar(sitio):
    c = G(descargador=sitio)
    f = Fuente(canonical_agency_id="roomix:tiv", agency_name="tiv", official_url=BASE + "/")
    plan = c.discover(f)
    return c, plan, [x["source_url"] for x in c.fetch_listing(f, plan)]


def test_tiv_enumera_todo_el_buscador_y_no_la_portada_rotativa():
    sitio = Sitio()
    c, plan, urls = _enumerar(sitio)
    assert plan["variante"] == "TIV_BUSQUEDA" and plan["total_declarado"] == 25
    assert len(urls) == len(set(urls)) == 25
    assert all(re.search(r"/inmueble/depto-venta-lp\d+$", u) for u in urls)
    assert sitio.posts == [2, 3, 4] and c.paginacion_interrumpida is False


def test_tiv_un_error_a_mitad_marca_la_paginacion_interrumpida():
    c, plan, urls = _enumerar(Sitio(cortar_en=3))
    assert len(urls) == 20 and c.paginacion_interrumpida is True


def test_sin_marca_tiv_no_se_usa_el_buscador():
    class Otro(Sitio):
        def bajar(self, url, *a, **k):
            return super().bajar(url).replace("CRM Inmobiliario TIV Tecnogestion", "otra cosa")
    _, plan, _ = _enumerar(Otro())
    assert plan.get("variante") != "TIV_BUSQUEDA"


def _og(cadena):
    return ("<meta name='description' content='CRM Inmobiliario TIV Tecnogestion' />"
            f'<meta property="og:title" content="Terreno Lote en Venta. {cadena}" />')


ZONAS = {"resto de la provincia": "Buenos Aires", "g.b.a. zona sur": "Buenos Aires"}


def test_tiv_zona_sale_de_la_cadena_y_la_provincia_del_mapa_del_sitio():
    # `cattaneo`: «La Martona, Cañuelas, Resto de la Provincia».
    assert G._ubicacion_tiv(_og("La Martona, Cañuelas, Resto de la Provincia"), ZONAS) == (
        "La Martona", "Cañuelas", "Buenos Aires", None)


def test_tiv_sin_mapa_del_sitio_la_provincia_queda_vacia():
    assert G._ubicacion_tiv(_og("La Martona, Cañuelas, Resto de la Provincia")) == (
        "La Martona", "Cañuelas", None, None)


def test_tiv_la_zona_no_es_ciudad():
    assert G._ubicacion_tiv(_og("Cañuelas, Resto de la Provincia, Buenos Aires")) == (
        None, "Cañuelas", "Buenos Aires", None)
    # En TIV «Capital Federal» es CABA y el «Buenos Aires» final es el area
    # metropolitana: antes se servia como provincia de Buenos Aires (03-10).
    assert G._ubicacion_tiv(_og("Almagro, Capital Federal, Buenos Aires")) == (
        "Almagro", None, "Ciudad Autónoma de Buenos Aires", None)


def test_tiv_el_mapa_de_zonas_sale_del_selector_del_buscador():
    class ConSelector(Sitio):
        def bajar(self, url, *a, **k):
            cuerpo = super().bajar(url)
            if url.rstrip("/").endswith("/buscar/inmuebles"):
                cuerpo += ("<select><option value=''>UBICACION</option>"
                           "<option value='501'>Ca&#241;uelas, Resto de la Provincia, Buenos Aires, Argentina</option>"
                           "<option value='76'>Ezeiza, G.B.A. Zona Sur, Argentina</option></select>")
            return cuerpo
    _, plan, _ = _enumerar(ConSelector())
    assert plan["tiv_zonas"] == {"resto de la provincia": "Buenos Aires"}


def test_tiv_alquiler_temporario_abreviado():
    html = ("<meta name='description' content='CRM Inmobiliario TIV Tecnogestion' />"
            '<meta property="og:title" content="Casa Chalet en Alq. Temporario. '
            'Alejandro Petion, Cañuelas, Resto de la Provincia" />')
    assert G._ubicacion_tiv(html, ZONAS) == ("Alejandro Petion", "Cañuelas", "Buenos Aires", None)


def test_ubicacion_tiv_del_gba_con_puntos_en_la_zona():
    """og:title real de `coseglia` (02-10): «G.B.A.» trae puntos y la ficha quedaba sin ciudad."""
    from connectors.generico import GenericoConnector
    html = ('<meta property="og:title" content="Departamento en Venta. Concord Pilar, Pilar, G.B.A. Zona Norte" />'
            '<script src="https://cdn.tecnogestion.com.ar/x.js"></script>')
    barrio, ciudad, provincia, _ = GenericoConnector._ubicacion_tiv(html, {'g.b.a. zona norte': 'Buenos Aires'})
    assert (barrio, ciudad, provincia) == ('Concord Pilar', 'Pilar', 'Buenos Aires')
    # G.B.A. es Buenos Aires por definicion: no hace falta el mapa del sitio.
    sin_mapa = GenericoConnector._ubicacion_tiv(html, {})
    assert sin_mapa[:3] == ('Concord Pilar', 'Pilar', 'Buenos Aires')


def test_tiv_argentina_final_no_es_un_tramo():
    assert G._ubicacion_tiv(_og('Pilar, G.B.A. Zona Norte, Argentina'))[:3] == (None, 'Pilar', 'Buenos Aires')


def test_tiv_barrio_localidad_partido_sin_provincia_no_se_adivina():
    assert G._ubicacion_tiv(_og('Villa la Nata, Dique Lujan, Tigre')) is None


def test_tiv_digitos_solo_en_el_barrio():
    assert G._ubicacion_tiv(_og('46 Plaza, Pilar, G.B.A. Zona Norte'))[:3] == ('46 Plaza', 'Pilar', 'Buenos Aires')
    assert G._ubicacion_tiv(_og('Centro, Ruta 8 km 50, Buenos Aires')) is None


def test_tiv_costa_atlantica_sin_mapa_sigue_sin_provincia():
    assert G._ubicacion_tiv(_og('San Bernardo, Costa Atlantica')) is None or G._ubicacion_tiv(_og('San Bernardo, Costa Atlantica'))[2] is None


def test_la_ubicacion_tiv_es_de_la_estrategia_tiv_en_la_huella():
    from scripts.agency_fingerprints import GENERIC_STRATEGY_METHODS
    assert '_ubicacion_tiv' in GENERIC_STRATEGY_METHODS['generic/tiv_busqueda']
    assert not any('_ubicacion_tiv' in v for k, v in GENERIC_STRATEGY_METHODS.items() if k != 'generic/tiv_busqueda')


def test_las_constantes_de_modulo_de_generico_entran_en_la_huella(tmp_path, monkeypatch):
    import scripts.agency_fingerprints as F
    original = (F.ROOT / 'connectors' / 'generico.py').read_text(encoding='utf-8')
    copia = tmp_path / 'connectors'; copia.mkdir()
    (copia / 'generico.py').write_text(original, encoding='utf-8')
    antes = F._selected_nodes(copia / 'generico.py', 'GenericoConnector', set(), set(), module_assigns=True)
    (copia / 'generico.py').write_text(original.replace('RE_TIV_TOTAL = re.compile(', 'RE_TIV_TOTAL = re.compile(r"x" or ', 1), encoding='utf-8')
    despues = F._selected_nodes(copia / 'generico.py', 'GenericoConnector', set(), set(), module_assigns=True)
    assert antes != despues


def test_la_calle_tiv_exige_altura_real_y_no_texto_comercial():
    def og(desc):
        return _og('Pilar, G.B.A. Zona Norte') + f'<meta property="og:description" content="Casa en Venta, ubicado sobre la calle {desc} en Pilar" />'
    assert G._ubicacion_tiv(og('Sarmiento 1300'))[3] == 'Sarmiento 1300'
    assert G._ubicacion_tiv(og('Polonia 0'))[3] is None
    assert G._ubicacion_tiv(og('OPORTUNIDAD AL LAGO - Vistas Casa 600'))[3] is None

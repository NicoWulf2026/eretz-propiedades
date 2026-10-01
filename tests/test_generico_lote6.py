"""Lote 6 (LOCAL, 2026-10-01): paros de la cola con el lote 5 aplicado.

Cada caso reproduce la forma real de la fuente con HTML sintetico minimo.
"""
from __future__ import annotations

from connectors.base import Fuente
from connectors.generico import GenericoConnector as G


class Sitio:
    def __init__(self, html):
        self.html = html

    def bajar(self, *a, **k):
        return self.html

    def __getattr__(self, nombre):
        return lambda *a, **k: None


def _normalizar(html, url, agencia="prueba", por_forma=False):
    base = url.split("/")[0] + "//" + url.split("/")[2]
    return G(descargador=Sitio(html)).normalize(
        {"source_url": url, "source_listing_id": "x", "por_forma": por_forma},
        Fuente(canonical_agency_id="roomix:" + agencia, agency_name=agencia, official_url=base + "/"))


def _ficha(cuerpo, cabeza=""):
    return ("<html><head><title>Local en alquiler | Inmobiliaria</title>" + cabeza + "</head><body>"
            "<h1>Local comercial en alquiler sobre avenida</h1>"
            "<p>Precio: USD 1.500</p><p>Local de 2 ambientes con 1 baño, 50 m2 cubiertos.</p>"
            + "".join(f'<img src="/fotos/{i}.jpg" alt="foto">' for i in range(4))
            + cuerpo + "</body></html>")


# --- bellomo: icono vacio dentro de la celda del rotulo -------------------------

FACTS = ('<dl class="detail-facts">'
         '<div class="detail-fact"><dt><i class="bi bi-tag" aria-hidden="true"></i> Operación</dt><dd>Alquiler</dd></div>'
         '<div class="detail-fact"><dt><i class="bi bi-columns-gap" aria-hidden="true"></i> Ambientes</dt><dd>3</dd></div>'
         '<div class="detail-fact"><dt><i class="bi bi-droplet" aria-hidden="true"></i> Baños</dt><dd>2</dd></div>'
         '<div class="detail-fact"><dt><i class="bi bi-layers" aria-hidden="true"></i> Plantas</dt><dd>2</dd></div>'
         '</dl>')


def test_icono_vacio_en_el_rotulo_no_corre_los_valores():
    p = _normalizar(_ficha(FACTS), "https://bellomo.example/propiedad/local-en-alquiler-colon-p1035")
    assert p is not None
    # Antes: banos=3 (el valor de Ambientes) y ambientes perdido.
    assert (p.ambientes, p.banos) == (3, 2)


# --- bauer: plugin Estatik -----------------------------------------------------

ESTATIK = ("<ul>"
           "<li class='es-entity-field es-property-field es-property-field--bedrooms'>"
           "<span class='es-property-field__label'>Dormitorios<span class='es-property-field__sep'>:</span></span>"
           "<span class='es-property-field__value'>2</span></li>"
           "<li class='es-entity-field es-entity-field--es_neighborhood es-property-field "
           "es-property-field--es_neighborhood es-property-field--default'>"
           "<span class='es-property-field__label'>Barrios <span class='es-property-field__sep'>:</span> </span>"
           "<span class='es-property-field__value es-entity-field__value'>"
           "<a href='/es_neighborhood/liniers/' rel='tag'>Liniers</a></span> </li>"
           "</ul>")


def test_estatik_barrio_por_clase_del_campo():
    p = _normalizar(_ficha(ESTATIK), "https://bauer.example/property/venta-depto-3-ambs/")
    assert p is not None and p.barrio == "Liniers"


def test_estatik_solo_dentro_del_mismo_li():
    # Un campo vacio no toma el valor del <li> siguiente.
    html = ("<ul><li class='es-property-field es-property-field--es_neighborhood'>"
            "<span class='es-property-field__label'>Barrios:</span></li>"
            "<li class='es-property-field es-property-field--area'>"
            "<span class='es-property-field__value'>55 m2</span></li></ul>")
    assert G._campo_estatik(html, "es_neighborhood") is None


# --- de giorgio: el Place de schema.org que ES la ficha ------------------------

def _place(url_del_place):
    return ('<script type="application/ld+json">{"@context": "https://schema.org", "@type": "Place",'
            ' "name": "Oficina 37 m", "url": "' + url_del_place + '",'
            ' "address": {"@type": "PostalAddress", "addressLocality": "Buenos Aires"},'
            ' "geo": {"@type": "GeoCoordinates", "latitude": -34.565068899999999985,'
            ' "longitude": -58.454512299999997537}}</script>')


def test_place_con_la_url_de_la_ficha_aporta_coordenadas_y_localidad():
    url = "https://giorgio.example/property/oficina-37-m-belgrano/"
    p = _normalizar(_ficha("<p>Oficina en alquiler</p>", _place(url)), url)
    assert p is not None
    assert (round(p.latitud, 4), round(p.longitud, 4)) == (-34.5651, -58.4545)
    assert p.ciudad == "Buenos Aires"


def test_place_de_otra_url_sigue_sin_contar():
    # El Place de la oficina (otra url) no es evidencia de la ficha: su
    # localidad no se toma.
    url = "https://giorgio.example/property/oficina-37-m-belgrano/"
    oficina = _place("https://giorgio.example/contacto/").replace("Buenos Aires", "Vicente Lopez")
    p = _normalizar(_ficha("<p>Oficina en alquiler</p>", oficina), url)
    assert p is not None and p.ciudad != "Vicente Lopez"


# --- balsa: fila de detalle de Houzez ------------------------------------------

HOUZEZ = ('<ul class="list-2-cols list-unstyled">'
          '<li class="detail-address"><strong>Domicilio</strong> <span>Machado 740</span></li>'
          '<li class="detail-city"><strong>Ciudad</strong> <span>Partido de la Costa</span></li>'
          '<li class="detail-state"><strong>Provincia/País</strong> <span>Buenos Aires</span></li>'
          '<li class="detail-zip"><strong>Código postal</strong> <span>7111</span></li>'
          '</ul>')


def test_houzez_provincia_por_clase_de_la_fila():
    p = _normalizar(_ficha(HOUZEZ), "https://balsa.example/property/2-ambientes-cochera-san-bernardo/")
    assert p is not None
    assert (p.ciudad, p.provincia) == ("Partido de la Costa", "Buenos Aires")


def test_houzez_direccion_con_icon_pin_sin_codigo_postal_ni_comuna():
    linea = ('<address class="item-address mb-2" role="contentinfo">'
             '<i class="houzez-icon icon-pin me-1" aria-hidden="true"></i>'
             'Pampa y Cabildo, La Pampa, Belgrano, Buenos Aires, Comuna 13, '
             'Ciudad Autónoma de Buenos Aires, C1428CPD, Argentina</address>')
    p = _normalizar(_ficha(linea), "https://giorgio.example/property/oficina-37-m-belgrano/")
    assert p is not None
    assert p.provincia == "Ciudad Autónoma de Buenos Aires"
    assert p.ciudad == "Buenos Aires"


def test_houzez_icon_pin_de_la_oficina_en_la_cabecera_no_cuenta():
    cabecera = ('<div class="header-contact header-contact-2"><div class="header-contact-left">'
                '<i class="houzez-icon icon-pin ms-1"></i></div><div class="header-contact-right">'
                '<div>La Pampa 2326</div><div>C.A.B.A.</div></div></div>')
    p = _normalizar(_ficha(cabecera), "https://giorgio.example/property/oficina-37-m-belgrano/")
    assert p is not None and p.direccion is None and p.ciudad is None


# --- aranoa: Synapsis, rotulo en negrita dentro de su celda --------------------

SYNAPSIS = ('<p style="float:left;"><strong>Localidad:</strong></p> '
            '<p style="float:left;">Don Torcuato</p> '
            '<p style="float:left;"><strong>Provincia:</strong></p> '
            '<p style="float:left;">Buenos Aires</p>')


def test_par_rotulado_con_el_rotulo_en_negrita():
    p = _normalizar(_ficha(SYNAPSIS), "https://aranoa.example/ficha.php?prop=369")
    assert p is not None
    assert (p.ciudad, p.provincia) == ("Don Torcuato", "Buenos Aires")


# --- caian / benitez ullo: CRM TIV Tecnogestion --------------------------------

TIV = ("<meta name='description' content='Caian Negocios Inmobiliarios CRM Inmobiliario TIV Tecnogestion' />"
       "<meta property=\"og:title\" content=\"Departamento en Venta. Almagro, Capital Federal, Buenos Aires\" />"
       "<meta property=\"og:description\" content=\"Departamento en Venta, 1 dormitorio, ubicado sobre la calle "
       "Billinghurst 200 en Almagro, Capital Federal, Buenos Aires\" />")


def test_tiv_ubicacion_del_og_title():
    p = _normalizar(_ficha("<p>Departamento en venta</p>", TIV),
                    "https://caian.example/inmueble/departamento-venta-2-ambientes-almagro-lp816957")
    assert p is not None
    assert (p.barrio, p.ciudad, p.provincia) == ("Almagro", "Capital Federal", "Buenos Aires")
    assert p.direccion == "Billinghurst 200"


def test_og_title_con_la_misma_forma_sin_firma_del_crm_no_cuenta():
    sin_firma = TIV.replace("CRM Inmobiliario TIV Tecnogestion", "")
    assert G._ubicacion_tiv(sin_firma) is None


def test_tiv_exige_provincia_al_final():
    otra = TIV.replace("Capital Federal, Buenos Aires\" />", "Capital Federal, Oferta\" />", 1)
    assert G._ubicacion_tiv(otra) is None


# --- bartolini: forma de ficha con id y sufijo fijo ----------------------------

def test_ficha_con_id_y_sufijo_propiedad_inmobiliaria():
    assert G._es_ficha_url(
        "https://bartolini.example/terreno-venta-mar-del-plata_407229_propiedad-inmobiliaria.html")
    # Las categorias del mismo sitio no tienen id.
    assert not G._es_ficha_url("https://bartolini.example/departamento-en-venta.html")
    assert not G._es_ficha_url("https://bartolini.example/propiedad-en-alquiler-por-temporada.html")

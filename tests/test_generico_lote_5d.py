# -*- coding: utf-8 -*-
"""Lote 5d de `generico` (2026-09-25), dos casos medidos en los paquetes:

- `forchino`: 19 fichas reales (precio, operacion, 20 fotos) rechazadas por
  forma: las fotos solo estan como enlace del visor
  (`<a href="fotos/imagen_…jpeg" class="popup-image">`) y como
  `background-image`; el `<img>` del carrusel esta comentado.
- `fernandez marull` y `crestale`: 59 enlaces señuelo de Cloudflare
  (`/cdn-cgi/content?id=…`, articulos inventados para bots) enumerados como
  fichas.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors import base as B  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

URL = "https://alfa.test/propiedad.php?id=410"
RELLENO = "<p>" + "Contacto, horarios y redes de la inmobiliaria. " * 12 + "</p>"


class Falso(B.Descargador):
    def __init__(self, html: str):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.html = html

    def bajar(self, url: str) -> str:
        return self.html


def _normalizar(html: str):
    c = GenericoConnector(descargador=Falso(html))
    f = B.Fuente(canonical_agency_id="roomix:alfa propiedades", agency_name="Alfa Propiedades",
                 official_url="https://alfa.test/", inmobiliaria_id=1)
    return c.normalize({"source_url": URL, "source_listing_id": "410", "por_forma": True}, f)


def _ficha(fotos: str) -> str:
    return ("<html><body><main><h1>Departamento en venta en Rosario</h1>"
            "<p>Venta. 2 dormitorios, 1 baño, cochera. Precio USD 135.000</p>"
            f"{fotos}{RELLENO}</main></body></html>")


VISOR = "".join(f'<a href="fotos/imagen_2026_{i}.jpeg" class="gal-link popup-image"></a>'
                for i in range(1, 6))


def test_MUERDE_las_fotos_que_solo_estan_en_el_visor_confirman_la_ficha():
    p = _normalizar(_ficha('<img src="img/logo.png">' + VISOR))
    assert p is not None
    assert "https://alfa.test/fotos/imagen_2026_3.jpeg" in p.imagenes


def test_con_fotos_propias_el_visor_no_agrega_duplicados():
    propias = "".join(f'<img src="fotos/chica_{i}.jpg">' for i in range(1, 5))
    grandes = "".join(f'<a href="fotos/grande_{i}.jpg"></a>' for i in range(1, 5))
    p = _normalizar(_ficha(propias + grandes))
    assert p is not None
    assert not any("grande_" in u for u in p.imagenes)


def test_un_enlace_que_no_es_imagen_no_es_foto():
    enlaces = "".join(f'<a href="propiedad.php?id={i}">ver</a>' for i in range(5))
    assert _normalizar(_ficha(enlaces)) is None


def test_MUERDE_un_enlace_senuelo_de_cloudflare_no_es_ficha():
    """Entraban por las tarjetas recuperadas, que no preguntan la forma."""
    senuelo = "/cdn-cgi/content?id=C77_YNYOi.UtOHVmrAOlPwVNJgTtcrdBH3XLMAZG79o-1790342374.7814023"
    html = ('<html><body>'
            f'<div class="property-card"><a href="{senuelo}">Chronobiology: The Rhythms of Life</a></div>'
            '<div class="property-card"><a href="/propiedad/casa-en-venta-en-rosario-123">'
            'Casa en venta</a></div></body></html>')
    fichas = GenericoConnector._fichas_en(html, "https://alfa.test/propiedades")
    assert not any("/cdn-cgi/" in u for u in fichas)
    assert "https://alfa.test/propiedad/casa-en-venta-en-rosario-123" in fichas


def test_un_compartir_con_la_foto_en_la_query_no_es_foto():
    compartir = "".join(
        f'<a href="https://pinterest.com/pin/create/button/?media=https://alfa.test/f{i}.jpg">p</a>'
        for i in range(5))
    assert _normalizar(_ficha(compartir)) is None


# --- ambientes que la ficha solo dice en el titulo ---------------------------
# 156 fichas `generico` en 21 agencias (`bardi` 40, `blanco` 33): «Casa de 5
# Ambientes en Remedios de Escalada.» y el cuerpo rotula dormitorios y banos
# pero no ambientes. Las 46 que discrepan con el cuerpo son titulos de varias
# unidades («Casa de 3 amb. + depto. de 2 amb.»): ahi el cuerpo suma y manda.

def _ficha_titulo(titulo: str, cuerpo: str = "") -> str:
    # El titulo fuera del cuerpo principal, como en `bardi`.
    return (f"<html><body><header><h1>{titulo}</h1></header><main>"
            "<p>Venta. Precio USD 260.000</p>"
            '<div><p class="text-sm">Baños</p><p class="text-sm">3</p></div>'
            '<div><p class="text-sm">Dormitorios</p><p class="text-sm">3</p></div>'
            f"{cuerpo}"
            f"{VISOR}{RELLENO}</main></body></html>")


def test_MUERDE_los_ambientes_del_titulo_cuando_el_cuerpo_no_los_dice():
    p = _normalizar(_ficha_titulo("Casa de 5 Ambientes en Remedios de Escalada."))
    assert p.ambientes == 5


def test_el_cuerpo_manda_sobre_el_titulo():
    p = _normalizar(_ficha_titulo(
        "Casa de 5 Ambientes", '<div><p class="text-sm">Ambientes</p><p class="text-sm">4</p></div>'))
    assert p.ambientes == 4


def test_un_titulo_de_varias_unidades_no_dice_los_ambientes():
    for titulo in ("Casa de 3 amb. + depto. de 2 amb. en venta",
                   "Casa de 3 amb. con monoambiente en venta",
                   "2 casas de 4 y 5 amb. en venta",
                   "Edificio en block de 3 ambientes"):
        assert _normalizar(_ficha_titulo(titulo)).ambientes is None, titulo


def test_MUERDE_addressNeighborhood_llega_como_barrio_para_que_la_geografia_decida():
    """`fenix`: addressLocality «Capital» (departamento), addressNeighborhood
    «Posadas» (localidad). Sin leer el barrio, la geografia no tenia con que."""
    import json as _json
    ld = {"@context": "https://schema.org", "@type": "Residence", "name": "Casa en venta",
          "address": {"@type": "PostalAddress", "addressLocality": "Capital",
                      "addressRegion": "Misiones", "addressNeighborhood": "Posadas"}}
    html = ('<html><head><script type="application/ld+json">' + _json.dumps(ld) +
            '</script></head><body><main><h1>Casa en venta</h1>'
            '<p>Venta. 3 dormitorios, 2 baños. Precio USD 100.000</p>' + VISOR + RELLENO +
            '</main></body></html>')
    p = _normalizar(html)
    assert (p.ciudad, p.barrio, p.provincia) == ("Capital", "Posadas", "Misiones")


def test_un_barrio_que_repite_la_ciudad_no_se_afirma():
    import json as _json
    ld = {"@type": "Residence", "name": "Casa", "address": {
        "addressLocality": "Rosario", "addressRegion": "Santa Fe", "addressNeighborhood": "Rosario"}}
    html = ('<html><head><script type="application/ld+json">' + _json.dumps(ld) +
            '</script></head><body><main><h1>Casa en venta</h1>'
            '<p>Venta. 3 dormitorios. Precio USD 100.000</p>' + VISOR + RELLENO +
            '</main></body></html>')
    assert _normalizar(html).barrio is None


# --- contador de visitas pegado a la descripcion ------------------------------
# `ferrari` (149 de 157), `bottega` (22 de 30), `diaz collins`: la descripcion
# termina en «627 Visitas al momento» y nuestra propia visita lo sube a 628, asi
# que la segunda corrida nunca es igual a la primera: NEEDS_FIX no idempotente.

def test_MUERDE_el_contador_de_visitas_no_es_parte_de_la_descripcion():
    cuerpo = ('<h3>Descripción</h3><p>Departamento de un dormitorio al frente, luminoso, '
              'con balcón y cocina integrada. 627 Visitas al momento</p>')
    p = _normalizar(_ficha(cuerpo + VISOR))
    assert p.descripcion.endswith("cocina integrada.")
    assert "Visitas" not in p.descripcion


# --- titulo de la API Xintel ----------------------------------------------------
# `bondar`: la API compone el titulo y representa el cero de ambientes a veces
# como «0 ambientes» y a veces como «monoambiente ambientes», con o sin
# entidades HTML: las dos corridas nunca coinciden (NEEDS_FIX no idempotente).

def test_MUERDE_el_titulo_xintel_es_el_mismo_en_las_dos_formas_del_cero():
    import test_connectors as TC
    a = TC._xintel_con(titulo="Departamento en venta Primera Secci&oacute;n 0 ambientes")
    b = TC._xintel_con(titulo="Departamento en venta Primera Sección monoambiente ambientes")
    assert a.titulo == b.titulo == "Departamento en venta Primera Sección"


def test_un_titulo_xintel_con_ambientes_reales_se_conserva():
    import test_connectors as TC
    assert TC._xintel_con(titulo="Oficina en alquiler Sexta Secci&oacute;n 3 ambientes").titulo == \
        "Oficina en alquiler Sexta Sección 3 ambientes"


# --- propiedades similares del tema RealHomes -----------------------------------
# `fernando villalba`: la parcela de 1,3 ha salia con 4 dormitorios y la casona
# con 16, alternando entre corridas: eran las «Habitaciones» de las tarjetas
# `rh_prop_card--similar`, elegidas al azar en cada carga.

def test_MUERDE_las_tarjetas_similares_de_realhomes_no_son_la_ficha():
    similares = ('<section class="rh_property__similar_properties">'
                 '<article class="rh_prop_card rh_prop_card--similar">'
                 '<h3><a href="/property/otra/">Otra casa</a></h3>'
                 '<div class="rh_prop_card__meta"><h4>Habitaciones</h4><div><span class="figure">16</span></div></div>'
                 '</article></section>')
    html = ('<html><body><h1>VENTA-Parcela de 1,3 hectareas</h1><main>'
            '<p>Venta. Parcela de 1,3 hectáreas. Precio USD 90.000</p>' + VISOR + RELLENO +
            similares + '</main></body></html>')
    p = _normalizar(html)
    assert p.dormitorios is None


def test_MUERDE_el_tooltip_de_una_tarjeta_relacionada_no_es_el_tipo():
    """`berrueta`: «3 AMBIENTES AL FRENTE» quedaba como cochera por el
    <span class="card__highlights__tooltip">Cochera</span> de una relacionada."""
    relacionadas = ('<section id="propiedades"><h2>Propiedades Relacionadas</h2>'
                    '<div class="ficha__related swiper-container"><a class="card" href="/propiedad/1">'
                    '<p class="card__title">3 AMBIENTES CON COCHERA</p>'
                    '<span class="card__highlights__tooltip">Cochera</span></a></div></section>')
    html = ('<html><body><main><h2>3 AMBIENTES AL FRENTE - OPORTUNIDAD</h2>'
            '<p>Venta USD 100.000. 3 ambientes, 2 dormitorios.</p>' + VISOR + RELLENO +
            relacionadas + '</main></body></html>')
    assert _normalizar(html).tipo_propiedad != "cochera"


def test_MUERDE_el_tipo_como_parrafo_de_la_ficha_y_sin_cochera_no_es_tipo():
    html = ('<html><body><main><h2>3 AMBIENTES AL FRENTE - OPORTUNIDAD</h2>'
            '<div class="highlights"><p class="highlights__text">Departamentos</p></div>'
            '<div class="highlights"><p class="highlights__text">Sin cochera</p></div>'
            '<p>Venta USD 100.000. 3 ambientes, 2 dormitorios.</p>' + VISOR + RELLENO +
            '</main></body></html>')
    assert _normalizar(html).tipo_propiedad == "departamento"


# --- la operacion como etiqueta suelta ------------------------------------------
# `cantale` (<span class="rounded-full …">Venta</span>) y `altos`
# (<span class="tag tag--op">Venta</span>): sin «En», que es lo que la regla
# anterior exigia para no confundirla con el menu. El menu va en <a>.

def _ficha_op(badges: str) -> str:
    return ('<html><body><nav><a href="/listing?purpose=sale">Venta</a>'
            '<a href="/listing?purpose=rent">Alquiler</a></nav><main>'
            '<h2>Lote 866 x 3418 orientacion este</h2>' + badges +
            '<p>Precio USD 45.000. Lote de 866 m2.</p>' + VISOR + RELLENO + '</main></body></html>')


def test_MUERDE_la_etiqueta_suelta_de_operacion_fuera_del_menu():
    p = _normalizar(_ficha_op('<span class="rounded-full bg-blue-600"> Venta </span>'))
    assert p.operacion == "venta"


def test_dos_operaciones_sueltas_no_se_elige_ninguna():
    p = _normalizar(_ficha_op('<span class="tag">Venta</span><div class="tab">Alquiler</div>'))
    assert p.operacion is None


# --- direccion y barrio como pares rotulo/valor --------------------------------
# `bardi` (90 fichas): <p>Dirección</p><p>Av. Rosales 515</p> y
# <p>Barrio</p><p>Remedios de Escalada, Lanús, Buenos Aires</p>, sin ubicacion.

def test_MUERDE_direccion_y_barrio_en_pares_rotulo_valor():
    pares = ('<div><p class="text-gray-500">Dirección</p><p class="text-sm">Av. Rosales 515</p></div>'
             '<div><p class="text-gray-500">Barrio</p>'
             '<p class="text-sm">Remedios de Escalada, Lanús, Buenos Aires</p></div>')
    p = _normalizar(_ficha(pares + VISOR))
    assert p.direccion == "Av. Rosales 515"
    assert (p.barrio, p.ciudad, p.provincia) == ("Remedios de Escalada", "Lanús", "Buenos Aires")


def test_un_barrio_que_repite_la_ciudad_del_par_no_se_afirma_y_ubicacion_no_es_barrio():
    pares = ('<div><p>Ubicación</p><p>Frente</p></div>'
             '<div><p>Barrio</p><p>Lomas De Zamora, Lomas de Zamora, Buenos Aires</p></div>')
    p = _normalizar(_ficha(pares + VISOR))
    assert (p.barrio, p.ciudad) == (None, "Lomas de Zamora")


def test_MUERDE_el_rotulo_de_descripcion_dentro_de_un_enlace_de_acordeon():
    """`alianza` (27 fichas): <h4><a href="#collapseTwo">Descripción</a></h4> y
    una lista de ambientes; se guardaba el eslogan del meta, descartado por
    compartido, y la agencia quedaba NEEDS_FIX."""
    bloque = ('<div class="panel-heading"><h4 class="panel-title"> '
              '<a data-parent="#accordion" href="#collapseTwo">Descripción</a> </h4></div>'
              '<div id="collapseTwo"><div class="panel-body"><ul><li>Living</li><li>Comedor</li>'
              '<li>Cocina</li><li>Baño</li><li>Patio Mediano</li></ul></div></div>')
    html = ('<html><head><meta name="description" content="Alianza Real Estate. Inmobiliaria '
            'ubicada en santa fe, Venta y alquiler de inmuebles"></head><body><main>'
            '<h2>Castelli 900</h2><p>Venta. Precio U$S 210000</p>' + bloque + VISOR + RELLENO +
            '</main></body></html>')
    p = _normalizar(html)
    assert "Living" in (p.descripcion or "") and "Patio Mediano" in p.descripcion
    assert "Inmobiliaria ubicada" not in p.descripcion


def test_MUERDE_una_ficha_con_id_titulada_como_categoria_no_es_contenedora():
    """`fogliese`: «Lotes En Venta Zona Turistica Temática» en
    /propiedad/186944_lotes-en-venta-…/ con 6 relacionadas."""
    relacionadas = "".join(f'<a href="/propiedad/{1000 + i}_casa-en-venta/">Casa {i}</a>' for i in range(6))
    html = ('<html><body><main><h1>Lotes En Venta Zona Turistica Temática</h1>'
            '<p>Venta. Lotes desde USD 20.000</p>' + relacionadas + '</main></body></html>')
    url = "https://alfa.test/propiedad/186944_lotes-en-venta-zona-turistica-tematica/"
    assert not GenericoConnector._es_pagina_contenedora(html, url)
    assert GenericoConnector._es_pagina_contenedora(html, "https://alfa.test/lotes-en-venta/")


def test_una_taxonomia_de_wordpress_no_es_ficha():
    html = ('<html><body><div class="property-card"><a href="/estado-propiedad/venta">Venta</a></div>'
            '<div class="property-card"><a href="/propiedad/casa-en-venta-en-rosario-123">Casa</a></div>'
            '</body></html>')
    fichas = GenericoConnector._fichas_en(html, "https://alfa.test/propiedades")
    assert not any("/estado-propiedad/" in u for u in fichas)


def test_MUERDE_la_descripcion_en_el_contenedor_property_description():
    """`fios` (122 de 276 fichas sin descripcion): <div class="property-description
    propiedad-detalles"><div class="show-more"><p>… sin rotulo."""
    bloque = ('<!-- Property Description --><div class="property-description propiedad-detalles">'
              '<!-- Details --><div class="show-more"><p> Venta de casa ubicada sobre calle '
              'Sarmiento al 3900, en Funes, dentro de un entorno residencial consolidado.</p></div></div>'
              '<!-- Features --><h3>Características</h3><ul><li>Pileta</li></ul>')
    html = ('<html><head><meta name="description" content="FIOS Consultoría Inmobiliaria, '
            'propiedades en venta y alquiler en Rosario y zona."></head><body><main>'
            '<h1>VENTA CASA 1 DORMITORIO</h1><p>Venta. Precio USD 199.000</p>' + bloque + VISOR +
            RELLENO + '</main></body></html>')
    p = _normalizar(html)
    assert (p.descripcion or "").startswith("Venta de casa ubicada sobre calle Sarmiento")
    assert "Características" not in p.descripcion


def test_cinco_amb_sin_punto_tambien_es_una_cantidad():
    """`cocciolo`: «Amplio departamento de 5 amb Uso profesional o vivienda»."""
    assert GenericoConnector._ambientes_del_titulo(
        "Amplio departamento de 5 amb Uso profesional o vivienda") == 5
    assert GenericoConnector._ambientes_del_titulo("Casa con ambos patios") is None


def test_un_emprendimiento_en_plural_no_toma_tipo_ni_conteos_del_menu():
    """`alagna`: /emprendimientos/edificio-en-dorrego-1400 salia «casa» con 3
    dormitorios -el menu del sitio y una unidad de la tabla-."""
    html = ("<html><head><title>Edificio en Dorrego 1400</title></head><body>"
            "<nav><a href='/venta/casas'>Casas</a></nav><main>"
            "<h1>Edificio en Dorrego 1400</h1>"
            "<p>Descripcion: edificio con departamentos de 1 y 2 dormitorios, "
            "3 ambientes, cocheras.</p><p>Dormitorios: 3</p>"
            "<p>Precio U$S 76.050</p></main></body></html>")
    c = GenericoConnector(descargador=Falso(html + RELLENO))
    f = B.Fuente(canonical_agency_id="roomix:alagna", agency_name="Alagna",
                 official_url="https://a.test/", inmobiliaria_id=1)
    p = c.normalize({"source_listing_id": "57931",
                     "source_url": "https://a.test/emprendimientos/edificio-en-dorrego-1400-57931"},
                    f)
    assert p is not None
    assert p.tipo_propiedad is None
    assert (p.dormitorios, p.ambientes, p.banos) == (None, None, None)


def test_fichas_que_navegan_por_onclick_se_enumeran():
    """`aris`: doce `<li onclick="location.href='ficha.php?ficha=ARI…'">`."""
    html = ("<ul>" + "".join(
        f"<li onclick=\"location.href='ficha.php?ficha=ARI{n}'\" class='col-sm-6'>"
        f"<img src='x{n}.jpg'><p>Departamento en venta U$S 100.000</p></li>"
        for n in (2829, 3092)) +
        "<li onclick=\"location.href='contacto.php'\">Contacto</li></ul>")
    fichas = GenericoConnector._fichas_en(html, "https://aris.test")
    assert "https://aris.test/ficha.php?ficha=ARI2829" in fichas
    assert "https://aris.test/ficha.php?ficha=ARI3092" in fichas
    assert not any("contacto" in f for f in fichas)


def test_og_article_solo_no_veta_una_ficha_con_precio_operacion_y_fotos():
    """`gandino galetto`: og:type=article en sus 12 fichas reales."""
    html = '<meta property="og:type" content="article">'
    texto = "Casa en venta Ambrosetti 300 USD 130.000 3 dormitorios 2 banos"
    fotos = ["a.jpg", "b.jpg", "c.jpg"]
    assert GenericoConnector._confirma_ficha(html, texto, 130000.0, fotos)
    # Una nota con schema de articulo sigue afuera.
    nota = html + '<script type="application/ld+json">{"@type": "BlogPosting"}</script>'
    assert not GenericoConnector._confirma_ficha(nota, texto, 130000.0, fotos)
    # Y sin precio con moneda tambien.
    assert not GenericoConnector._confirma_ficha(html, "Nota: casas en venta", None, fotos)


def test_schema_con_precio_y_operacion_alcanza_con_una_foto():
    """`benitez`: una foto en el HTML (la del JSON-LD `Product`)."""
    texto = "Departamento 1 dormitorio en venta USD 65.000"
    assert GenericoConnector._confirma_ficha("", texto, 65000.0, ["a.jpg"], tipo_ld="Product")
    assert not GenericoConnector._confirma_ficha("", texto, 65000.0, ["a.jpg"])
    assert not GenericoConnector._confirma_ficha("", texto, 65000.0, [], tipo_ld="Product")


def test_propiedad_inexistente_se_anota_como_baja_de_la_ficha():
    """`d uva`: las 9 fichas del sitemap responden 200 «Propiedad inexistente.»."""
    c = GenericoConnector(descargador=Falso("Propiedad inexistente."))
    f = B.Fuente(canonical_agency_id="roomix:d uva", agency_name="D Uva",
                 official_url="https://duva.test/", inmobiliaria_id=1)
    assert c.normalize({"source_url": "https://duva.test/propiedades/calle-eolo-53/",
                        "source_listing_id": "53"}, f) is None
    assert c.errores and c.errores[-1]["etapa"] == "detalle_permanente"
    c = GenericoConnector(descargador=Falso("<p>Hola</p>"))
    assert c.normalize({"source_url": "https://duva.test/propiedades/x-1/",
                        "source_listing_id": "1"}, f) is None
    assert not c.errores


def test_los_filtros_del_catalogo_como_ruta_no_son_fichas():
    """`cuini`: el menu enlaza /propiedades-venta/tipo/casa-1/dormitorios/..."""
    html = ('<nav><a href="propiedades-venta/tipo/casa-1/">Casa</a>'
            '<a href="propiedades-alquiler/tipo/departamento-2/dormitorios/1-dormitorio-8/">1 dorm</a></nav>'
            '<a class="propiedad" href="propiedad/1681/italia-27-bis/"><h3>Italia 27 bis</h3></a>')
    fichas = GenericoConnector._fichas_en(html, "https://cuini.test")
    assert fichas == ["https://cuini.test/propiedad/1681/italia-27-bis/"]


def test_la_pagina_n_del_listado_no_es_una_ficha():
    html = ('<a href="propiedades/pagina-2/">2</a><a href="propiedades/page/3/">3</a>'
            '<a class="propiedad" href="propiedad/1681/italia-27-bis/">Italia</a>')
    assert GenericoConnector._fichas_en(html, "https://cuini.test") == [
        "https://cuini.test/propiedad/1681/italia-27-bis/"]


class FalsoPorUrl(B.Descargador):
    def __init__(self, paginas: dict):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.paginas = paginas

    def bajar(self, url: str) -> str:
        return self.paginas.get(url, "")


def test_catalogos_gemelos_dan_la_operacion_que_la_ficha_no_dice():
    """`bottai`: la operacion solo esta en `inmuebles_list_Venta_…`/`…_Alquiler_…`."""
    base = "https://bottai.test"
    home = ('<a href="inmuebles_list_Venta_x_0">Venta</a>'
            '<a href="inmuebles_list_Alquiler_x_0">Alquiler</a>')
    paginas = {
        base + "/inmuebles_list_Venta_x_0": '<a href="propiedad.php?id=1">a</a><a href="propiedad.php?id=3">c</a>',
        base + "/inmuebles_list_Alquiler_x_0": '<a href="propiedad.php?id=2">b</a><a href="propiedad.php?id=3">c</a>',
    }
    c = GenericoConnector(descargador=FalsoPorUrl(paginas))
    mapa, fichas = c._catalogos_por_operacion(home, base, None)
    assert mapa == {base + "/propiedad.php?id=1": "venta", base + "/propiedad.php?id=2": "alquiler"}
    assert [op for _, op in fichas] == ["venta", "alquiler"]
    # Sin el gemelo no se asigna nada.
    assert c._catalogos_por_operacion(home.split("</a>")[0] + "</a>", base, None) == ({}, [])


def test_signo_pesos_con_dolares_detras_es_usd():
    """`ente`: «Price $990,000 / DOLARES»."""
    html = ("<html><head><title>CASA BARRIO DALVIAN</title></head><body><main>"
            "<h1>CASA BARRIO DALVIAN</h1><p>Price $990,000 / DOLARES En Venta</p>"
            "<p>3 dormitorios 2 baños</p>"
            "<img src='/f/1.jpg'><img src='/f/2.jpg'><img src='/f/3.jpg'>"
            "</main></body></html>" + RELLENO)
    p = _normalizar(html)
    assert p is not None and (p.precio, p.moneda) == (990000.0, "USD")


def test_similares_y_destacadas_de_inspiry_no_son_la_ficha():
    """`gonzalez theyler`: el precio «Consultar» de la ficha y los USD de la barra lateral."""
    from connectors.generico import cuerpo_principal
    html = ('<h1>URQUIZA Y ENTRE RIOS</h1><span class="price">Consultar</span>'
            '<aside class="sidebar"><section class="similar-properties meta-item-half">'
            'CASA A RECICLAR $49,000 Dolares</section></aside>'
            '<section class="widget clearfix Inspiry_Featured_Properties_Widget">$188,000</section>')
    cuerpo = cuerpo_principal(html)
    assert "Consultar" in cuerpo and "49,000" not in cuerpo and "188,000" not in cuerpo


def test_el_tipo_rotulado_manda_sobre_el_menu():
    """`gonzalez theyler`: menu «Venta Casa Departamento…» y rotulo «Oficina / Local»."""
    html = ("<html><head><title>URQUIZA Y ENTRE RIOS</title></head><body><main>"
            "<p>Venta Casa Departamento Oficina / Local Cochera</p>"
            "<h1>URQUIZA Y ENTRE RIOS</h1><p>USD 90.000 venta</p>"
            '<span class="meta-item-label">Tipo Propiedad</span>'
            '<span class="meta-item-value">Venta Oficina / Local</span>'
            "<img src='/f/1.jpg'><img src='/f/2.jpg'><img src='/f/3.jpg'>"
            "</main></body></html>" + RELLENO)
    p = _normalizar(html)
    assert p is not None and p.tipo_propiedad == "local"


def test_sin_h1_el_titulo_es_el_h2_que_nombra_la_propiedad():
    """`candoli`: <title> es el nombre de la agencia y el h2 describe la ficha."""
    from connectors.base import Fuente
    f = Fuente(canonical_agency_id="roomix:candoli", agency_name="Candoli Propiedades",
               official_url="https://c.test/", inmobiliaria_id=1)
    html = ("<title>Candoli Propiedades</title>"
            "<h2>Complejo turistico en venta a metros del mar, Camet Norte</h2>"
            "<h2>Propiedades en venta destacadas del mes</h2>")
    assert GenericoConnector._titulo_de_la_ficha(html, {}, f) == (
        "Complejo turistico en venta a metros del mar, Camet Norte")
    con_h1 = "<title>Candoli Propiedades</title><h1>Casa en Mar del Plata</h1>" + html
    assert GenericoConnector._titulo_de_la_ficha(con_h1, {}, f) == "Casa en Mar del Plata"


def test_un_conteo_rotulado_no_es_el_chip_del_tipo():
    """`candoli`: «Cocheras: 1» en un complejo turistico no lo vuelve cochera."""
    assert GenericoConnector._tipo_en_la_ficha("<span>Cocheras: 1</span><span>Amb. 2</span>") is None
    assert GenericoConnector._tipo_en_la_ficha("<span>Departamentos</span>") == "departamento"


def test_terravirtual_la_ficha_es_barra_ficha_md5():
    """`blangiforti`/`g calvo`: /propiedades/ficha/<md5> sirve el listado."""
    h = "020361f6469f2e2127550b960d9df335"
    html = (f'<a href="https://b.test/propiedades/ficha/{h}">a</a>'
            f'<a href="https://b.test//ficha/{h}">b</a>')
    assert GenericoConnector._fichas_en(html, "https://b.test") == [f"https://b.test/ficha/{h}"]


def test_los_ordenes_del_listado_con_operacion_no_son_fichas():
    """`fandino`: /propiedades/venta_mas-nuevas y nueve mas."""
    html = "".join(f'<a href="/propiedades/{o}">x</a>' for o in (
        "venta_destacadas", "alquiler_precio-menor-a-mayor", "venta_mas-viejas"))
    html += '<a href="/propiedades/venta_casa-en-funes-123">Casa</a>'
    fichas = GenericoConnector._fichas_en(html, "https://f.test")
    assert not any(o in f for f in fichas for o in ("destacadas", "precio-menor", "mas-viejas"))

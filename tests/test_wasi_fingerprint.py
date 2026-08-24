# -*- coding: utf-8 -*-
"""Tests del fingerprint de Wasi.

Wasi pone el mismo software abajo de dominios y marcas distintas, asi que lo
que se persigue aca es el error de clasificacion: dar por Wasi a un sitio que
no lo es -y mandarlo a un connector que devolvera cero-, o no reconocer uno que
si lo es porque le borraron la marca.

Todo con HTML fijo, tomado del que sirven sitios Wasi reales y recortado.
Ningun test toca la red.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.wasi_fingerprint import (bundle_white_label, campos_de_ficha,  # noqa: E402
                                      es_ficha,
                                      fingerprint, id_de_ficha,
                                      inventario_declarado, url_canonica)


# --------------------------------------------------------------- fixtures HTML
WASI_COMPLETO = """
<html><head>
<meta name="author" content="Wasi.co">
<meta name="Designer" content="www.wasi.co">
<link rel="shortcut icon" href="https://images.wasi.co/empresas/b2022081010.png">
</head><body>
<ul class="navbar-nav">
 <li><a class="dropdown-item" href="https://x.com/s/casa/ventas?id_property_type=1&amp;business_type%5B0%5D=for_sale">Casa (63)</a></li>
 <li><a class="dropdown-item" href="https://x.com/s/ph/ventas?id_property_type=4&amp;business_type%5B0%5D=for_sale">Ph (4)</a></li>
 <li><a class="dropdown-item" href="https://x.com/s/casa/alquileres?id_property_type=1&amp;business_type%5B0%5D=for_rent">Casa (5)</a></li>
</ul>
<a href="/casa-venta-cordoba/10293325">ficha</a>
<div class="blq_precio">Precio de alquiler
  <span class="">$1.100.000<span class="type-rent"> Mensual</span></span> Pesos Argentinos</div>
<a href="/main-contactenos.htm">Contactenos</a>
<img src="https://image.wasi.co/eyJidWNrZXQiOiJzdGF0aWN3In0=">
<a href="/search?business_type%5B0%5D=for_sale&amp;page=2&amp;lax_business_type=1">2</a>
<script>var lang_locale = "es_AR"; var city_label = "Cordoba"; var iso_country = "AR";</script>
<script src="https://x.com/js/v1/pro27b/global.min.js?v11787407572"></script>
<script src="https://x.com/js/app.js?v11787407572"></script>
<script src="https://x.com/js/lazyload.min.js?v11787407572"></script>
<footer>Powered by: <a href="https://wasi.co">wasi.co</a></footer>
</body></html>
"""

# El mismo producto con la marca borrada: sin metas, sin CDN, sin pie. Es el
# caso que decide si la deteccion sirve o si solo sabe leer un logo.
WASI_SIN_MARCA = """
<html><head><title>Inmobiliaria Ejemplo</title></head><body>
<a class="dropdown-item" href="/s/casa/ventas?id_property_type=1&amp;business_type%5B0%5D=for_sale">Casa (12)</a>
<script src="/js/v1/pro18/global.min.js?v11787434749"></script>
<script src="/js/app.js?v11787434749"></script>
<script src="/js/webp.js?v11787434749"></script>
</body></html>
"""

NO_WASI_WORDPRESS = """
<html><head><link href="/wp-content/themes/inmo/style.css"></head><body>
<a href="/propiedades/casa-en-venta-123">Casa</a>
<script src="/wp-includes/js/jquery.js"></script>
<script src="/js/app.js?v12345678"></script>
</body></html>
"""

NO_WASI_TOKKO = """
<html><head><link href="https://static.tokkobroker.com/tfw/css/estilo.css"></head>
<body><img src="https://static.tokkobroker.com/logos/33648/abc.png">
<a href="/p/111-Casa-en-Venta-en-Cordoba">1</a>
<a href="/Propiedades">Propiedades</a>
<script>var jqxhr = $.ajax("?q=&currency=ANY&operation=&p=")</script>
</body></html>
"""


# ------------------------------------------------------------- senales fuertes
def test_una_senal_fuerte_sola_confirma_wasi():
    """Cada una la sirve la plataforma; ninguna la escribe la inmobiliaria."""
    for html in (
            '<meta name="author" content="Wasi.co">',
            '<meta name="Designer" content="www.wasi.co">',
            '<img src="https://images.wasi.co/inmuebles/b1095313.jpeg">',
            '<img src="https://image.wasi.co/eyJidWNrZXQiOiJzdGF0aWN3In0=">'):
        r = fingerprint(html)
        assert r["es_wasi"] and r["confianza"] == "alta", html


def test_un_enlace_suelto_al_cdn_no_es_la_senal():
    """La senal es el CDN CON su ruta de fotos. Enlazar wasi.co no convierte a
    nadie en cliente de Wasi."""
    r = fingerprint('<a href="https://wasi.co">nuestra plataforma</a>')
    assert not r["es_wasi"]


# -------------------------------------------------------------- reglas fragiles
def test_la_palabra_wasi_sola_no_alcanza():
    """Es la regla que se quiso evitar: cualquier pagina que hable de la
    plataforma quedaria clasificada como si corriera sobre ella."""
    r = fingerprint("<p>Migramos desde wasi el ano pasado</p>")
    assert not r["es_wasi"]
    assert r["confianza"] == "insuficiente"
    assert r["senales_debiles"] == ["texto_wasi"]


def test_una_sola_senal_media_no_alcanza_y_dos_si():
    una = fingerprint('<div class="blq_precio">$100</div>')
    assert not una["es_wasi"] and una["confianza"] == "insuficiente"

    dos = fingerprint('<div class="blq_precio">$100</div>'
                      '<a href="/main-contactenos.htm">c</a>')
    assert dos["es_wasi"] and dos["confianza"] == "media"


# ------------------------------------------------- independencia de la marca
def test_detecta_wasi_aunque_borren_la_marca():
    """La senal que sostiene el caso dificil: el juego de scripts white-label no
    menciona wasi en ninguna parte, asi que sobrevive a que la inmobiliaria
    saque metas, CDN y pie de pagina."""
    assert "wasi" not in WASI_SIN_MARCA.lower()
    r = fingerprint(WASI_SIN_MARCA, "https://inmobiliariaejemplo.com.ar")
    assert r["es_wasi"] and r["confianza"] == "alta"
    assert r["senales_fuertes"] == ["bundle_white_label"]
    assert r["plan"] == "pro18" and r["build"] == "11787434749"


def test_el_bundle_exige_que_los_scripts_compartan_build():
    """Un /js/app.js suelto lo tiene medio internet. Lo que identifica al
    producto es que global.min.js y sus hermanos lleven el MISMO build."""
    assert bundle_white_label(WASI_SIN_MARCA)
    assert bundle_white_label(
        '<script src="/js/v1/pro18/global.min.js?v11787434749"></script>'
        '<script src="/js/app.js?v99999999"></script>') is None
    assert bundle_white_label('<script src="/js/app.js?v11787434749"></script>') is None


def test_el_dominio_no_decide_la_plataforma():
    """Una inmobiliaria con dominio propio que corre sobre Wasi sigue siendo su
    web oficial; el hostname es una senal mas, nunca el atajo."""
    propio = fingerprint(WASI_COMPLETO, "https://inmobiliariaejemplo.com.ar")
    hospedado = fingerprint(WASI_COMPLETO, "https://agra.inmo.co")
    assert propio["es_wasi"] and hospedado["es_wasi"]
    assert "host_wasi" in hospedado["senales_medias"]
    assert "host_wasi" not in propio["senales_medias"]


def test_estar_en_inmo_co_solo_no_confirma():
    """Es del hostname: si fuera suficiente, la deteccion volveria a depender
    del dominio, que es justo lo que no puede hacer."""
    r = fingerprint("<html><body>hola</body></html>", "https://agra.inmo.co")
    assert not r["es_wasi"]


# ----------------------------------------------- no romper lo ya clasificado
def test_otras_plataformas_no_dan_positivo():
    """Si el fingerprint tomara estos, se llevaria puesta la clasificacion de
    802 fuentes Tokko y 186 WordPress ya confirmadas por sus connectors."""
    for html in (NO_WASI_TOKKO, NO_WASI_WORDPRESS):
        r = fingerprint(html, "https://algunainmobiliaria.com.ar")
        assert not r["es_wasi"], r
        assert not r["senales_fuertes"] and len(r["senales_medias"]) < 2


def test_el_negativo_tambien_deja_evidencia():
    """Un negativo sin motivo no se puede auditar despues."""
    r = fingerprint(NO_WASI_WORDPRESS)
    assert r["motivo"]
    assert set(r) >= {"senales_fuertes", "senales_medias", "senales_debiles"}


# --------------------------------------------------------- inventario del menu
def test_el_inventario_declarado_no_cuenta_dos_veces_el_mismo_filtro():
    """El mismo filtro aparece dos veces con dos etiquetas -"Chalet (15)" y
    "Chalet En Venta (15)"-. Contando etiquetas, cuatro sitios declaraban
    exactamente el doble de lo que su sitemap enumeraba, y ese 0,5 clavado
    parecia un sitemap incompleto cuando era el contador inflado."""
    doble = (
        '<a class="dropdown-item" href="/s/chalet/ventas?id_property_type=3'
        '&amp;business_type%5B0%5D=for_sale">Chalet (15)</a>'
        '<a class="dropdown-item" href="/s/chalet/ventas?id_property_type=3'
        '&amp;business_type%5B0%5D=for_sale">Chalet En Venta (15)</a>')
    assert inventario_declarado(doble)["total"] == 15


def test_el_inventario_declarado_separa_por_operacion():
    d = inventario_declarado(WASI_COMPLETO)
    assert d["por_operacion"] == {"for_sale": 67, "for_rent": 5}
    assert d["total"] == 72


def test_sin_menu_no_se_inventa_un_total():
    """Un campo ausente es None, nunca un cero que despues parece medicion."""
    assert inventario_declarado("<html></html>")["total"] is None


# ------------------------------------------------------------- rutas de ficha
def test_la_ficha_se_reconoce_por_su_ruta():
    """/<slug>/<id>: ese id es el codigo que la propia ficha muestra, asi que no
    hay que fabricar ningun identificador."""
    assert es_ficha("/casa-venta-cordoba/10293325")
    assert id_de_ficha("https://x.com/casa-venta-cordoba/10293325") == "10293325"


def test_no_se_confunden_listados_ni_recursos_con_fichas():
    for no in ("/s/casa/ventas", "/search?page=2", "/main-contactenos.htm",
               "/js/app.js", "/asesores", "/", "/casa-venta/123"):
        assert not es_ficha(no), no
        assert id_de_ficha(no) is None, no


# ------------------------------------------------- identidad: la url canonica
FICHA_DOS_SLUGS = """
<html><head>
<meta property="og:url" content="https://dicasoli.com.ar/apartamento-venta-moron/5444177">
<script type="application/ld+json">
{"@context":"http://www.schema.org","@type":"house",
 "url":"https://dicasoli.com.ar/departamento-venta-moron/5444177"}
</script>
</head><body></body></html>
"""


def test_la_misma_propiedad_bajo_dos_slugs_entra_con_una_sola_url():
    """El sitemap la publica como /apartamento-... y el listado como
    /departamento-..., con el mismo id. En dicasoli.com.ar pasa en 106 de 243
    fichas. Como `hash_dedup` lleva la url adentro, enumerar por un camino en
    una corrida y por el otro en la siguiente crearia dos filas de la misma
    propiedad, invisibles para el indice unico."""
    pedida = "https://dicasoli.com.ar/apartamento-venta-moron/5444177"
    canon = url_canonica(FICHA_DOS_SLUGS, pedida)
    assert canon == "https://dicasoli.com.ar/departamento-venta-moron/5444177"
    # Se entre por donde se entre, la identidad es la misma.
    otra = "https://dicasoli.com.ar/departamento-venta-moron/5444177"
    assert url_canonica(FICHA_DOS_SLUGS, otra) == canon
    assert id_de_ficha(canon) == id_de_ficha(pedida) == "5444177"


def test_og_url_no_sirve_de_canonica():
    """Devuelve la url que uno pidio, asi que no distingue nada."""
    assert "og:url" in FICHA_DOS_SLUGS
    assert url_canonica(FICHA_DOS_SLUGS, "https://dicasoli.com.ar/x/1") != \
        "https://dicasoli.com.ar/apartamento-venta-moron/5444177"


def test_sin_canonica_declarada_se_conserva_la_pedida():
    """Inventar una url seria peor que quedarse con la que se uso para llegar."""
    pedida = "https://x.com/casa-venta-cordoba/10293325"
    assert url_canonica("<html></html>", pedida) == pedida


# --------------------------------------------------------- lectura de la ficha
FICHA_WASI = """
<html><body>
<div class="blq_precio">Precio de venta
  <span class="">USD 185.000<span class="type-sale"></span></span> Dolares</div>
<h3>Detalles del inmueble :</h3>
<div><span>Pais:</span><span>Argentina</span></div>
<div><span>Region:</span><span>Buenos Aires</span></div>
<div><span>Ciudad:</span><span>Merlo</span></div>
<div><span>Zona:</span><span>San Antonio De Padua</span></div>
<div><span>Codigo:</span><span>10094868</span></div>
<div><span>Area Construida:</span><span>84 m&sup2;</span></div>
<div><span>Area Terreno:</span><span>100 m&sup2;</span></div>
<div><span>Dormitorios:</span><span>2</span></div>
<div><span>Garaje:</span><span>1</span></div>
<div><span>Numero de plantas:</span><span>2</span></div>
<div><span>Tipo de inmueble:</span><span>Casa</span></div>
<div><span>Tipo de negocio:</span><span>Venta</span></div>
</body></html>
"""


def test_la_ficha_se_lee_del_html_servido():
    """Si esto no sale, no hay via barata: habria que abrir un navegador."""
    c = campos_de_ficha(FICHA_WASI)
    assert c["precio"] == 185000 and c["moneda"] == "USD"
    assert c["operacion"] == "Venta" and c["tipo_propiedad"] == "Casa"
    assert c["codigo"] == "10094868"
    assert c["ciudad"] == "Merlo" and c["provincia"] == "Buenos Aires"
    assert c["barrio"] == "San Antonio De Padua"
    assert c["superficie_cubierta"] == 84 and c["superficie_total"] == 100
    assert c["dormitorios"] == 2 and c["cocheras"] == 1


def test_la_cantidad_de_plantas_no_es_la_superficie():
    """El JSON-LD de la ficha manda la cantidad de plantas en `floorSize`. En un
    duplex de 84 m2 con dos plantas, leerlo como superficie registra "2 m2": un
    numero plausible, y por eso nadie lo notaria despues."""
    c = campos_de_ficha(FICHA_WASI)
    assert c["plantas"] == 2
    assert c["superficie_cubierta"] == 84
    assert c["superficie_cubierta"] != c["plantas"]


def test_un_cero_no_es_una_medicion():
    """Wasi escribe 0 donde no cargaron el dato. Un "0 m2 cubiertos" es un campo
    vacio disfrazado, y ya se colo una vez por esta misma via en Century 21."""
    c = campos_de_ficha(
        '<div><span>Area Construida:</span><span>0 m&sup2;</span></div>')
    assert c["superficie_cubierta"] is None


def test_un_campo_ausente_queda_en_none_y_no_se_infiere():
    c = campos_de_ficha('<div><span>Ciudad:</span><span>Salta</span></div>')
    assert c["ciudad"] == "Salta"
    assert c["banos"] is None and c["superficie_cubierta"] is None
    assert c["precio"] is None and c["moneda"] is None


def test_los_dolares_se_escriben_a_la_americana_y_los_pesos_a_la_argentina():
    """La misma pagina usa las dos convenciones: "$620.000" para pesos y
    "US$110,000" para dolares. Aplicar una sola convertia 110.000 dolares en
    110: un precio bien formado y equivocado por tres ordenes de magnitud."""
    usd = campos_de_ficha(
        '<div class="blq_precio">Precio de venta'
        '<span class="">US$110,000</span> Dolares Americanos</div>')
    assert usd["precio"] == 110000 and usd["moneda"] == "USD"

    ars = campos_de_ficha(
        '<div class="blq_precio">Precio de venta'
        '<span class="">$620.000</span> Pesos Argentinos</div>')
    assert ars["precio"] == 620000 and ars["moneda"] == "ARS"

    # Y un decimal de verdad sigue siendo un decimal.
    dec = campos_de_ficha(
        '<div class="blq_precio">Precio de venta<span>US$1,250,000.50</span></div>')
    assert dec["precio"] == 1250000.50


def test_la_moneda_sale_del_bloque_de_precio():
    pesos = campos_de_ficha(
        '<div class="blq_precio">Precio de alquiler'
        '<span>$1.100.000</span> Pesos Argentinos</div>')
    assert pesos["moneda"] == "ARS" and pesos["precio"] == 1100000
    # Y sin "Tipo de negocio" la operacion todavia sale del propio bloque.
    assert pesos["operacion"] == "Alquiler"


# ------------------------------------- integracion con el detector de plataforma
def _dp():
    import importlib.util
    ruta = ROOT / "scripts" / "detect_platform.py"
    spec = importlib.util.spec_from_file_location("detect_platform", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wasi_le_gana_a_laravel_que_es_el_framework_de_abajo():
    """El white-label de Wasi corre sobre Laravel. Si gana el framework, la
    fuente queda etiquetada LARAVEL y se la manda a parsear HTML a ciegas
    teniendo un sitemap completo al lado."""
    dp = _dp()
    html = WASI_SIN_MARCA + '<meta name="csrf-token" content="abc">'
    plataforma, estrategia, conf = dp.detectar_plataforma(
        {"html": html, "texto": html, "titulo": "", "url": "https://ejemplo.com"})
    assert plataforma == "WASI"
    assert estrategia == dp.SITEMAP
    assert conf >= 0.9


def test_wasi_no_va_a_api_direct_porque_su_api_pide_credenciales():
    """api.wasi.co existe pero exige id_company y wasi_token, que el sitio
    publico no expone. Prometer una API que despues pide credenciales manda al
    connector a una puerta cerrada."""
    dp = _dp()
    c = dp.clasificar({"html": WASI_COMPLETO, "texto": WASI_COMPLETO,
                       "titulo": "", "url": "https://ejemplo.com"})
    assert c["detected_platform"] == "WASI"
    assert c["strategy"] != dp.API_DIRECT


def test_mencionar_wasi_ya_no_clasifica_como_wasi():
    """La regla vieja era `wasi\\.co|wasiapp` sobre todo el HTML: tomaba por
    cliente a cualquier pagina que apenas enlazara la plataforma."""
    dp = _dp()
    html = '<a href="https://wasi.co/precios">conoce wasi</a><link href="/wp-content/x.css">'
    plataforma, _, _ = dp.detectar_plataforma(
        {"html": html, "texto": html, "titulo": "", "url": "https://ejemplo.com"})
    assert plataforma != "WASI"


def test_la_cobertura_se_juzga_contra_una_cota_alcanzable():
    """La suma del menu cuenta una vez por operacion, asi que una propiedad en
    venta y en permuta figura dos veces y el total nunca se alcanza: tres
    fuentes enteras quedaban ENUMERACION_INCOMPLETA teniendo todo su
    inventario. La operacion mas grande si es una cota inferior real, porque
    dentro de una operacion cada propiedad aparece una sola vez."""
    d = inventario_declarado(WASI_COMPLETO)
    piso = max(d["por_operacion"].values())
    assert d["total"] == 72          # cota superior, inalcanzable si hay solapamiento
    assert piso == 67                # cota inferior, siempre alcanzable
    assert piso <= d["total"]


def test_leer_la_ficha_no_puede_costar_casi_un_segundo():
    """El patron arrancaba en cada ">" del documento y retrocedia: 0,87 s por
    ficha de 66 KB. A 170 fichas por fuente y 39 fuentes es una hora de CPU
    pura, y en el canary se veia como si la red estuviera lenta. El margen es
    amplio a proposito: mide el orden de magnitud, no el milisegundo."""
    import time
    fila = ("<li><strong>Ciudad:</strong> Merlo</li>"
            "<li><strong>Area Construida:</strong> 84 m2</li>"
            "<div class='x'>texto de relleno sin rotulos ni dos puntos</div>")
    html = "<html><body>" + fila * 400 + "</body></html>"
    assert len(html) > 40_000
    t = time.perf_counter()
    c = campos_de_ficha(html)
    tardo = time.perf_counter() - t
    assert c["ciudad"] == "Merlo" and c["superficie_cubierta"] == 84
    assert tardo < 1.0, f"tardo {tardo:.2f}s"


def test_la_foto_del_asesor_no_es_la_foto_de_la_propiedad():
    """El CDN de Wasi separa por carpeta lo que no es la propiedad: /empresas/
    es el logo, /perfiles/ la foto del asesor y /publicidad/ un banner. Una sola
    foto de perfil aparecia en 261 fichas de la misma inmobiliaria."""
    fuente = (ROOT / "connectors" / "wasi.py").read_text(encoding="utf-8")
    for carpeta in ("/empresas/", "/perfiles/", "/publicidad/"):
        assert carpeta in fuente, carpeta


# ------------------------------------------- segunda capa de la compuerta DB
def test_la_compuerta_deja_pasar_la_ficha_y_frena_el_listado():
    """El connector ya filtra por forma de ficha. Esta es la segunda capa: con
    WordPress la primera tambien alcanzaba "en teoria" y entraron 56 paginas de
    busqueda igual."""
    from scripts.write_eligibility import motivo_rechazo
    for url, lid in (
            ("https://bartuccipropiedades.com/departamento-alquiler-centro-moreno/10123642",
             "10123642"),
            ("https://agra.inmo.co/terreno-venta-lunlunta-maipu/9718827", "9718827")):
        assert motivo_rechazo({"source_url": url, "source_listing_id": lid}) is None

    for url, lid in (("https://x.com/s/casa/ventas", "casa"),
                     ("https://x.com/s/ventas", "ventas"),
                     ("https://x.com/main-contactenos.htm", "contactenos")):
        assert motivo_rechazo({"source_url": url, "source_listing_id": lid})


def test_una_ficha_que_cuelga_del_buscador_no_es_una_busqueda():
    """laroccapropiedades.com publica cada propiedad en
    /busqueda/ver/8693745-2/. La regla rechazaba 88 fichas reales -verificado:
    esa url sirve "Mario Bravo al 600", una direccion-. Lo que identifica a la
    ficha es que la ruta termina en un id largo."""
    from scripts.write_eligibility import motivo_rechazo
    assert motivo_rechazo({
        "source_url": "https://www.laroccapropiedades.com/busqueda/ver/8693745-2/",
        "source_listing_id": "8693745"}) is None


def test_pero_la_pagina_de_resultados_se_sigue_frenando():
    """El resguardo no puede aflojarse: fueron 56 paginas de busqueda las que
    entraron por WordPress la vez anterior."""
    from scripts.write_eligibility import motivo_rechazo
    for url, lid in (("https://x.com/buscar-propiedades/", "buscar"),
                     ("https://x.com/busqueda/casas-en-venta/", "casas"),
                     ("https://x.com/search/results/page-2/", "2"),
                     ("https://x.com/buscar/", "buscar")):
        assert motivo_rechazo({"source_url": url,
                               "source_listing_id": lid}) == "busqueda", url


def test_la_capa_nueva_no_rompe_las_urls_de_tokko():
    """Tokko publica /p/<id>-<slug>: la regla de listado de Wasi no puede
    tocarla o se caerian 91.000 propiedades ya validadas."""
    from scripts.write_eligibility import motivo_rechazo
    assert motivo_rechazo({
        "source_url": "https://www.abppropiedades.com.ar/p/8693171-Departamento-en-Venta",
        "source_listing_id": "8693171"}) is None


# ------------------------------------------------------------------- artefacto
def test_el_censo_de_wasi_conserva_la_evidencia_de_cada_fuente():
    ruta = Path(r"D:\INMO CAPITAL\WASI_DISCOVERY.jsonl")
    if not ruta.exists():
        pytest.skip("todavia no se genero")
    filas = [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]
    assert filas
    for f in filas:
        assert f.get("familia")
        if f.get("es_wasi"):
            # Ninguna fuente se declara Wasi sin decir con que senal.
            assert f["senales_fuertes"] or len(f["senales_medias"]) >= 2
            # Y ninguna promete connector sin tener algo que enumerar: es el
            # error que hizo dar por recuperables 57 fuentes WordPress que
            # despues devolvieron cero.
            if f.get("connector"):
                assert f.get("enumerated_unique")
                assert f.get("enumeration_method")
                assert f.get("coverage_status")

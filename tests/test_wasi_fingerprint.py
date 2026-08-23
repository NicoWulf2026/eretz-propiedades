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

from scripts.wasi_fingerprint import (bundle_white_label, es_ficha,  # noqa: E402
                                      fingerprint, id_de_ficha,
                                      inventario_declarado)


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
                assert f.get("enumerables")

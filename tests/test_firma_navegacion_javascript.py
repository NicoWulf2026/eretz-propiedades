# -*- coding: utf-8 -*-
"""La firma que explica por qué 39 agencias cierran sin inventario.

Los fixtures son el marcado real de `davidrodriguezprop.com/home/` reducido a
lo que decide: la navegación por `location.href`, el POST del listado, y el
contenedor que rellena JavaScript. No se nombra ninguna etiqueta HTML dentro
de un comentario con sus símbolos, porque las expresiones regulares del módulo
capturarían el comentario en lugar del contenido —ya pasó dos veces—.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from firma_navegacion_javascript import (  # noqa: E402
    RECUPERABLES, clasificar_html, endpoints_post, rutas_en_href,
    rutas_en_javascript, tercero,
)

BASE = "https://davidrodriguezprop.com/home/"

# El caso real: la única navegación propia vive adentro de un script.
REAL = """
<html><head><title>David Propiedades</title>
<link href="assets/css/rw-style.css" rel="stylesheet">
<link href="favicon.ico" rel="icon">
</head><body>
<a href="#">Inicio</a>
<a href="javascript:goToPropiedades()">Propiedades</a>
<a href="mailto:info@davidrodriguezprop.com">Escribinos</a>
<a href="https://www.oestesi.com">Hecho por</a>
<span>159 Propiedades</span>
<script src="assets/js/custom.js"></script>
<script>
function goToIndex() { window.location.href = "index.php"; }
function goToPropiedades() { window.location.href = "propiedades.php"; }
function goToContacto() { window.location.href = "contacto.html"; }
function buscar(event) {
  $("#notification" + event).load("buscar.php", { "type": event });
}
function searchProperties(page, city) {
  $.ajax({ type: "POST", url: "searchProperties.php", data: { "page": page } });
}
</script>
</body></html>
"""

# El mismo sitio si la navegación estuviera escrita donde el descubridor mira.
SANO = REAL.replace('<a href="javascript:goToPropiedades()">Propiedades</a>',
                    '<a href="propiedades.php">Propiedades</a>')


def test_las_rutas_del_catalogo_no_estan_en_ningun_href():
    """El descubridor de hoy cosecha `href` y acá no hay ni uno propio.

    Es la mitad del defecto: no falla al leer el catálogo, falla antes, al no
    tener a dónde ir.
    """
    assert rutas_en_href(REAL, BASE) == []


def test_la_ruta_del_catalogo_si_esta_en_location_href():
    """Y la otra mitad: la ruta existe, escrita en un lugar que no miramos."""
    encontradas = rutas_en_javascript(REAL, BASE)
    assert BASE + "propiedades.php" in encontradas
    assert BASE + "index.php" in encontradas


def test_el_caso_real_se_clasifica_por_la_navegacion_invisible():
    """El desenlace completo sobre el marcado real, sin salir a la red.

    Importa cuál de las cinco firmas gana: el sitio también pide el listado
    por POST y también tiene un contenedor vacío, pero lo que hay que arreglar
    primero es la ruta que no vemos. Si ganara `CATALOGO_POR_POST`, el arreglo
    apuntaría a un endpoint al que todavía no sabemos llegar.
    """
    señal = clasificar_html(REAL, BASE)
    assert señal["firma"] == "NAVEGACION_SOLO_JAVASCRIPT"
    assert señal["rutas_por_href"] == 0
    assert BASE + "propiedades.php" in señal["rutas_solo_en_javascript"]


def test_sin_rutas_de_catalogo_en_el_javascript_la_firma_es_otra():
    """`contacto.html` en un `location.href` no es un catálogo.

    Sin esta distinción cualquier sitio con un botón de contacto hecho en
    JavaScript entraría en la firma y la mediría de más.
    """
    solo_contacto = REAL.replace('window.location.href = "propiedades.php"',
                                 'window.location.href = "gracias.html"')
    solo_contacto = solo_contacto.replace(
        'window.location.href = "index.php"', 'window.location.href = "x.html"')
    assert clasificar_html(solo_contacto, BASE)["firma"] != \
        "NAVEGACION_SOLO_JAVASCRIPT"


def test_el_listado_se_pide_por_post_y_los_dos_endpoints_aparecen():
    endpoints = endpoints_post(REAL)
    assert "buscar.php" in endpoints, "el `.load` del listado"
    assert "searchProperties.php" in endpoints, "el `$.ajax` con type POST"


def test_un_asset_no_es_navegacion():
    """Sin este filtro el sitio parecería tener rutas propias y no tiene.

    Las dos únicas `href` propias del marcado real son una hoja de estilo y un
    ícono; contarlas convertiría la firma en invisible.
    """
    assert all(not r.endswith((".css", ".ico"))
               for r in rutas_en_href(REAL, BASE))


def test_no_confunde_navegacion_hacia_afuera_con_ruta_propia():
    afuera = """<script>window.location.href = "https://www.zonaprop.com.ar/x";
    location.href = "https://otro.com/propiedades";</script>"""
    assert rutas_en_javascript(afuera, BASE) == []


def test_no_se_marca_una_api_de_terceros_donde_no_la_hay():
    assert tercero(REAL) is None


def test_reconoce_la_api_de_tokko_cuando_esta():
    """El caso `facundo furne`: web a medida que consume Tokko del navegador.

    Es una firma distinta y por eso un arreglo distinto: acá no hay ninguna
    ruta propia que descubrir.
    """
    con_tokko = '<script src="/js/tokko-api.js"></script><div>Cargando</div>'
    assert tercero(con_tokko) == "TOKKO"


def test_MUERDE_si_la_navegacion_estuviera_en_href_no_habria_firma():
    """Prueba que el test detecta el bug: quitá el bug y la señal se apaga.

    Un test que da lo mismo con y sin el defecto no prueba nada. Acá el mismo
    marcado con la navegación escrita en un `href` normal deja de disparar la
    firma, porque el descubridor de hoy ya la encontraría solo.
    """
    assert rutas_en_href(SANO, BASE) == [BASE + "propiedades.php"]
    # Con el sitio sano el descubridor ve la ruta solo, así que no hay ninguna
    # ruta de catálogo que viva únicamente en el JavaScript, y la firma se
    # apaga: pasa a nombrar cómo se pide el listado, que es el defecto que
    # queda. Con el sitio real, no.
    assert clasificar_html(SANO, BASE)["firma"] == "CATALOGO_POR_POST"
    assert clasificar_html(REAL, BASE)["firma"] == "NAVEGACION_SOLO_JAVASCRIPT"


def test_un_perfil_de_portal_NUNCA_es_inventario_recuperable():
    """El falso positivo que la primera corrida sí produjo.

    `buscainmueble.com/inmobiliarias/<slug>` también esconde su catálogo en un
    `location.href` —apunta al `/List` del portal—, y por eso la regla, tal
    como estaba escrita, lo contaba como recuperable. Recuperable para el
    portal. Tres de los siete "recuperables" de la primera medición eran esto,
    y prometían inventario que no es de la agencia.
    """
    portal = REAL.replace(
        'window.location.href = "propiedades.php"',
        'window.location.href = '
        '"https://www.buscainmueble.com/inmobiliarias/analia-verga/List"')
    señal = clasificar_html(
        portal, "https://www.buscainmueble.com/inmobiliarias/analia-verga")
    assert señal["firma"] == "FUENTE_ES_PORTAL_AJENO"
    assert señal["firma"] not in RECUPERABLES


def test_el_corte_de_portal_va_antes_que_cualquier_firma_tecnica():
    """El orden importa y no es cosmético.

    El mismo marcado, servido desde un portal y desde un dominio propio, tiene
    que dar dos desenlaces distintos: uno se arregla en el registro de fuentes
    y el otro en el conector. Si la firma técnica ganara, el portal entraría a
    la ventana semántica a que le escribamos un conector.
    """
    propio = clasificar_html(REAL, BASE)
    ajeno = clasificar_html(REAL, "https://www.buscainmueble.com/inmobiliarias/x")
    assert propio["firma"] == "NAVEGACION_SOLO_JAVASCRIPT"
    assert ajeno["firma"] == "FUENTE_ES_PORTAL_AJENO"


def test_un_sitemap_con_fichas_gana_a_cualquier_firma_tecnica():
    """El caso `franchi inmobiliaria`, y es la reparación más barata que hay.

    WordPress con el tema Houzez: su tipo `property` no está expuesto en REST
    —`/wp-json/wp/v2/property` da 404— así que el conector de WordPress no ve
    una sola propiedad y la agencia cierra con cero. Su `property-sitemap.xml`
    lista 91 fichas.

    Cuando el catálogo ya está publicado en un sitemap no hay que escribir
    extractor ni descubrir rutas: hay que enrutar a `generic/sitemap`, que
    existe y la usan 21 agencias. Por eso gana incluso sobre el marcado real
    de `david rodriguez`, que por lo demás dispararía la firma del JavaScript.
    """
    señal = clasificar_html(REAL, BASE, fichas_sitemap=91,
                            sitemap="https://x/property-sitemap.xml")
    assert señal["firma"] == "SITEMAP_CON_FICHAS"
    assert señal["fichas_en_sitemap"] == 91


def test_un_sitemap_casi_vacio_no_cuenta_como_catalogo():
    """Dos fichas sueltas no son un catálogo, y prometerlo sería peor que nada."""
    señal = clasificar_html(REAL, BASE, fichas_sitemap=2, sitemap="https://x/s.xml")
    assert señal["firma"] == "NAVEGACION_SOLO_JAVASCRIPT"


@pytest.mark.parametrize("firma", sorted(RECUPERABLES))
def test_las_firmas_recuperables_no_necesitan_navegador(firma):
    """Nombrarlas aparte es el punto del §25.

    Estas tres se resuelven con HTTP plano. Meterlas en la misma bolsa que
    `API_DE_TERCEROS` haría que 39 agencias esperen una ventana de navegador
    que no necesitan.
    """
    assert firma in ("SITEMAP_CON_FICHAS", "NAVEGACION_SOLO_JAVASCRIPT",
                     "CATALOGO_POR_POST")

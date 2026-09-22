# -*- coding: utf-8 -*-
"""Una foto sin extension en el nombre sigue siendo una foto.

`_imagenes_de` exigia que la url terminara en `.jpg`, `.png`, `.webp` o
`.avif`. El 2026-09-21 eso costo 46 propiedades reales en dos agencias, con
dos formas distintas de la misma causa:

  - `chambouleyron gestion inmobiliaria` publica `<img src="uploads/foto341-1">`
    —sin extension y sin cabecera `Content-Type`—. Las bajé: son JPEG de 380 a
    520 KB. Sus 16 fichas traian precio y operacion y se descartaron por no
    llegar a `FOTOS_MINIMAS`.
  - `corporacion inmobiliaria` publica
    `<img src='https://gvamax.ar/serverdata/554/Fotos/Fi158411.554'>`. Ahi
    fallaban DOS cosas: la comilla simple, que la expresion no contemplaba, y
    el sufijo `.554` —el id de la agencia—. Sus 30 fichas se perdieron, y lo
    que si entraba eran cinco piezas de adorno.

La regla nueva no afloja parejo: lo que sale de un `src` de `<img>` es una
imagen por construccion y no necesita extension; lo que se pesca del texto
suelto no tiene esa garantia y la sigue necesitando.

Un respaldo por `Content-Type` no servia: el servidor de `chambouleyron` no
manda ninguno y el de `corporacion` manda `image/jpeg`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import (FOTOS_MINIMAS, GenericoConnector,  # noqa: E402
                                 _url_del_atributo)

FICHA = "https://x.test/p/1"


def imgs(html: str, url: str = FICHA) -> list[str]:
    return GenericoConnector._imagenes_de(html, url)


def test_MUERDE_el_caso_chambouleyron_sin_extension():
    """16 fichas con precio y operacion, descartadas por no tener fotos."""
    html = ('<img src="uploads/foto341-1" /><img src="uploads/foto341-2" />'
            '<img src="uploads/foto341-3" />')
    salida = imgs(html, "https://chambopropiedades.com/product.php?id=341")
    assert len(salida) == 3
    assert salida[0].endswith("/uploads/foto341-1")
    assert len(salida) >= FOTOS_MINIMAS


def test_MUERDE_el_caso_corporacion_comilla_simple_y_sufijo_numerico():
    html = ("<img class='img-responsive ' "
            "src='https://gvamax.ar/serverdata/554/Fotos/Fi158411.554'>"
            "<img class='x' src='https://gvamax.ar/serverdata/554/Fotos/Fi158412.554'>")
    salida = imgs(html)
    assert salida == ["https://gvamax.ar/serverdata/554/Fotos/Fi158411.554",
                      "https://gvamax.ar/serverdata/554/Fotos/Fi158412.554"]


def test_MUERDE_el_texto_suelto_SIGUE_exigiendo_extension():
    """La mitad que no se afloja. Una url cualquiera en el cuerpo no es una
    foto: sin esta puerta entraria cualquier enlace."""
    assert imgs("mira https://cdn.test/algo/sin-extension y nada mas") == []
    assert imgs("mira https://cdn.test/algo/foto.jpg y nada mas") == [
        "https://cdn.test/algo/foto.jpg"]


def test_MUERDE_el_adorno_se_sigue_filtrando():
    """Aflojar la extension no puede abrir la puerta a logos e iconos."""
    html = ('<img src="/images/logo-new.jpg"><img src="/images/favicon.png">'
            '<img src="https://api.whatsapp.com/x.png"><img src="/img/avatar">')
    assert imgs(html) == []


# --- el nombre con espacios, que el arreglo anterior destapaba -------------

def test_MUERDE_un_nombre_con_espacio_no_se_parte():
    """`cometto` publica `IMG_3859 (1).JPG`. Con `.split()[0]` quedaba
    `IMG_3859`, que devuelve 404.

    Mientras se exigia extension el estropicio no se notaba, porque la url
    truncada se caia sola. Al dejar de exigirla habria empezado a entrar una
    url rota: lo vi probando contra la pagina real, no despues.
    """
    assert _url_del_atributo("images/propiedades/IMG_3859 (1).JPG") == \
        "images/propiedades/IMG_3859 (1).JPG"
    salida = imgs('<img src="images/propiedades/IMG_3859 (1).JPG">')
    # `urljoin` resuelve la ruta relativa contra `/p/`, no contra la raiz.
    assert salida == ["https://x.test/p/images/propiedades/IMG_3859 (1).JPG"]


def test_MUERDE_un_descriptor_de_srcset_si_se_saca():
    """`foto.jpg 2x` lleva un descriptor de densidad, no un nombre con
    espacio. Se reconoce por su forma y no por asumir que siempre hay uno."""
    assert _url_del_atributo("foto.jpg 2x") == "foto.jpg"
    assert _url_del_atributo("/a/foto.png 1024w") == "/a/foto.png"


def test_el_valor_se_limpia_y_el_vacio_no_rompe():
    assert _url_del_atributo("  /a/foto.png  ") == "/a/foto.png"
    assert _url_del_atributo("") == ""
    assert _url_del_atributo(None) == ""


def test_no_se_duplica_una_foto_escrita_de_dos_maneras():
    html = ('<img src="https://x.test/a/foto.jpg">'
            '<img data-src="https://x.test/a/foto.jpg">')
    assert len(imgs(html)) == 1

# -*- coding: utf-8 -*-
r"""Un `</script` sin su `>` no puede llevarse la pagina entera.

`ceciliasarro.com.ar` publica esto en su cabecera:

    <script src="...recaptcha/api.js" async defer></script </head>

El cierre esta escrito `</script ` SIN el `>`. Cualquier navegador lo tolera.
La expresion que sacaba los bloques buscaba un `>` inmediato, no lo
encontraba, y seguia tragando hasta el SIGUIENTE `</script>` del documento: se
llevo 228.176 bytes de una vez. De 237.888 bytes de html, el texto visible
quedo en **212 caracteres**, y sus 51 fichas -que traen el precio en el html,
`<p class="price"> <span> U$S </span> 45000 </p>`- se descartaron por parecer
vacias.

La regla estaba escrita en TRECE lugares del repo y ya habian divergido: dos
usaban `</\1\s*>` y once `</\1>`. Ninguna de las dos variantes salva este
caso, asi que copiar la que ya existia en otro archivo no habria alcanzado.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.texto import sin_bloques_no_textuales  # noqa: E402

# La estructura del caso real: cierre roto, el contenido en el medio, y otro
# `<script>` mas abajo que es donde iba a parar el barrido.
PAGINA_ROTA = ('<head><script src="r.js" async defer></script </head>'
               '<body><p>PRECIO U$D 45.000</p><p>3 dormitorios</p>'
               '<script>var x=1;</script></body>')


def texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", sin_bloques_no_textuales(html)).split())


def test_MUERDE_el_caso_cecilia_sarro():
    """Si esto se rompe, una pagina entera vuelve a valer 212 caracteres."""
    assert texto(PAGINA_ROTA) == "PRECIO U$D 45.000 3 dormitorios"


def test_MUERDE_las_dos_variantes_viejas_fallaban_este_caso():
    """Deja constancia de por que no alcanzaba con copiar la tolerante.

    Las dos dejan el texto en CERO, no solo la estricta.
    """
    for patron in (r"<(script|style)[^>]*>.*?</\1>",
                   r"<(script|style)[^>]*>.*?</\1\s*>"):
        sin = re.sub(patron, " ", PAGINA_ROTA, flags=re.S | re.I)
        assert " ".join(re.sub(r"<[^>]+>", " ", sin).split()) == ""


def test_un_documento_normal_se_limpia_igual_que_antes():
    assert texto('<p>a</p><script>x=1</script><p>b</p>') == "a b"
    assert texto('<p>a</p><style>.x{color:red}</style><p>b</p>') == "a b"
    assert texto('<p>a</p><SCRIPT>x</SCRIPT><p>b</p>') == "a b"


def test_el_cierre_con_espacio_tambien():
    """`</script >` es valido y la variante estricta ya lo perdia."""
    assert texto('<p>a</p><script>x=1</script ><p>b</p>') == "a b"


def test_dos_bloques_seguidos_no_se_comen_lo_del_medio():
    assert texto('<script>1</script><p>a</p><script>2</script><p>b</p>') == "a b"


def test_un_script_sin_cerrar_no_borra_el_resto_de_golpe():
    """Sin cierre no hay nada que sacar: el contenido queda, que es preferible
    a perderlo. La conducta no cambia respecto de antes."""
    assert "b" in texto('<p>a</p><script>x=1<p>b</p>')


def test_html_vacio_o_nulo():
    assert sin_bloques_no_textuales("") == ""
    assert sin_bloques_no_textuales(None) == ""


def _copias_en(archivo: Path) -> list[str]:
    fuente = archivo.read_text(encoding="utf-8")
    return re.findall(r"<\(script\|style\)[^\"']{0,40}", fuente)


def test_MUERDE_ningun_conector_conserva_su_copia_de_la_regla():
    """La regla vivia en trece lugares y ya habian divergido en dos formas.

    Los conectores son los que deciden que se extrae, asi que ahi la copia
    propia no puede volver: si alguien agrega una, este test falla.
    """
    for nombre in ("generico.py", "wordpress.py", "tokko.py", "wasi.py",
                   "century21.py"):
        archivo = RAIZ / "connectors" / nombre
        if not archivo.exists():
            continue
        assert not _copias_en(archivo), (
            f"{nombre} volvio a escribir la regla en vez de usar "
            f"`sin_bloques_no_textuales`")

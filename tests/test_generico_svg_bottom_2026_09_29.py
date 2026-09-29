"""Un <path id="bottom"> de un icono SVG no es el bloque de relacionadas (`cometto`)."""
from __future__ import annotations

from connectors.generico import cuerpo_principal

CABECERA = ('<header><a class="menu"><svg viewBox="0 0 800 600">'
            '<path d="M300,220 L540,220" id="top"></path>'
            '<path d="M300,210 C300,210 520,210" id="bottom"></path></svg></a></header>')
FICHA = ('<div class="property-detail-info-list"><ul>'
         '<li><label>Precio: USD </label> <span>48000</span></li></ul></div>')


def test_el_icono_svg_no_corta_la_ficha():
    principal = cuerpo_principal(f"<html><body>{CABECERA}{FICHA}</body></html>")
    assert "48000" in principal


def test_un_bloque_real_con_id_bottom_si_corta():
    vecina = '<div id="bottom"><li><label>Precio: USD </label> <span>99000</span></li></div>'
    principal = cuerpo_principal(f"<html><body>{CABECERA}{FICHA}{vecina}</body></html>")
    assert "48000" in principal and "99000" not in principal

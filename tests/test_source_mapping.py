# -*- coding: utf-8 -*-
"""Tests del mapa tecnologico y de la re-auditoria historica.

Lo que se cuida aca es el error caro: mandar una fuente al conector equivocado,
o declarar scrapeable un sitio que no lo es. Ambas cosas se descubren tarde,
despues de haber escrito el scraper.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dp = _load("detect_platform")
rh = _load("reaudit_historical")


def sitio(html="", texto=None, titulo="", http=200, url="https://alfa.com.ar"):
    return {"html": html, "texto": texto if texto is not None else html,
            "titulo": titulo, "http": http, "url": url}


# ------------------------------------------------------- deteccion de familia
def test_tokko_se_detecta_y_va_a_su_conector():
    c = dp.clasificar(sitio('<script src="https://tokkobroker.com/w.js"></script>'))
    assert c["detected_platform"] == "TOKKO"
    assert c["strategy"] == dp.TOKKO_CONNECTOR


def test_tokko_sobre_wordpress_va_a_tokko_no_a_wordpress():
    """El caso que justifica el orden de deteccion: si gana el CMS, la fuente
    termina en el conector equivocado y el scraper no encuentra inventario."""
    c = dp.clasificar(sitio('<link href="/wp-content/x.css">'
                            '<script src="//tokkobroker.com/w.js"></script>'))
    assert c["detected_platform"] == "TOKKO"
    assert c["strategy"] == dp.TOKKO_CONNECTOR


def test_wordpress_solo_usa_su_api():
    c = dp.clasificar(sitio('<link href="/wp-content/themes/x/style.css">'))
    assert c["detected_platform"] == "WORDPRESS"
    assert c["strategy"] == dp.WORDPRESS_API


def test_nextjs_expone_json_embebido():
    c = dp.clasificar(sitio('<script id="__NEXT_DATA__">{"props":{}}</script>'))
    assert c["detected_platform"] == "NEXTJS"
    assert c["json_embedded"] is True


def test_api_propia_gana_a_recorrer_html():
    """Una API estructurada ahorra el parser entero: es la estrategia mas barata."""
    c = dp.clasificar(sitio('<a href="/propiedades">ver</a>'
                            '<script>fetch("/api/propiedades/listado")</script>'))
    assert "/api/propiedades/listado" in c["detected_api"]
    assert c["strategy"] == dp.API_DIRECT


def test_sitemap_evita_recorrer_el_sitio_a_ciegas():
    c = dp.clasificar(sitio('<h1>Inmobiliaria Alfa</h1>'), sitemap_propiedades=True)
    assert c["strategy"] == dp.SITEMAP


def test_sitio_propio_con_listados_es_ssr_no_revision_manual():
    """Sin plataforma conocida pero con inventario en el HTML servido: se
    parsea. Mandarlo a revision manual desperdiciaria una fuente lista."""
    c = dp.clasificar(sitio('<h1>Alfa</h1><a href="/propiedades/venta">Ver</a>'))
    assert c["detected_platform"] == "UNKNOWN"
    assert c["strategy"] == dp.SSR_HTML


def test_spa_sin_contenido_servido_requiere_navegador():
    html = '<div id="root"></div>' + '<script src="/a.js"></script>' * 12
    c = dp.clasificar(sitio(html, texto=""))
    assert c["requires_js"] is True
    assert c["strategy"] == dp.JS_BROWSER


def test_wix_con_json_embebido_no_necesita_navegador():
    c = dp.clasificar(sitio('<script src="https://static.wixstatic.com/a.js"></script>'
                            '<script type="application/ld+json">{}</script>'))
    assert c["detected_platform"] == "WIX"
    assert c["requires_js"] is False


def test_sitio_vacio_no_inventa_plataforma():
    assert dp.detectar_plataforma(sitio("", texto="", titulo="")) == (None, None, 0.0)


def test_clasificar_es_determinista():
    s = sitio('<link href="/wp-content/x.css"><a href="/propiedades">p</a>')
    assert dp.clasificar(s) == dp.clasificar(dict(s))


# ------------------------------------------------------------------ prioridad
def test_una_familia_grande_y_barata_es_lo_primero_que_conviene_construir():
    assert dp.prioridad(dp.TOKKO_CONNECTOR, 300) == "P0"


def test_una_familia_de_dos_sitios_no_justifica_un_conector_propio():
    assert dp.prioridad(dp.SSR_HTML, 2) == "P3"


def test_el_navegador_es_siempre_lo_ultimo():
    assert dp.prioridad(dp.JS_BROWSER, 500) == "P3"


def test_unknown_no_se_cuenta_como_conector_en_la_cobertura():
    """UNKNOWN son sitios propios, uno distinto por inmobiliaria. Contarlo como
    familia prometeria una cobertura que ningun conector entrega."""
    src = (ROOT / "scripts" / "map_scrape_sources.py").read_text(encoding="utf-8")
    bloque = src[src.index("cobertura acumulada") - 600:]
    assert 'k != "UNKNOWN"' in src
    assert "grupos" in bloque


# ------------------------------------------------- re-auditoria historica
def fila(**kw):
    base = {"canonical_agency_id": "a1", "canonical_name": "Alfa Propiedades",
            "nombre_original": "Alfa Propiedades", "scrapeability_status": None,
            "status": "OFFICIAL_WEB_AMBIGUOUS", "candidate_urls": [], "tipo": "INMOBILIARIA",
            "zonas_observadas": [], "matricula": [], "red_franquicia": None}
    base.update(kw)
    return base


def test_el_universo_sale_de_los_artefactos_no_de_una_lista_fija():
    src = (ROOT / "scripts" / "reaudit_historical.py").read_text(encoding="utf-8")
    assert "agency_web_directory.jsonl" in src
    assert "NO_SCRAPEABLES" in src and "ESTADOS_WEB_NO_RESUELTOS" in src


def test_no_se_reauditan_las_que_ya_estaban_listas():
    assert "SCRAPE_SOURCE_READY" not in rh.NO_SCRAPEABLES


def test_las_urls_se_reusan_no_se_buscan():
    """Sin buscador: si no quedo ninguna URL guardada, la entidad no se toca."""
    assert rh.urls_reutilizables(fila()) == []
    f = fila(selected_domain="https://alfa.com.ar",
             candidate_urls=[{"url": "https://otra.com.ar"}])
    assert rh.urls_reutilizables(f)[0] == "https://alfa.com.ar"


def test_el_dominio_elegido_va_antes_que_una_candidata_dudosa():
    f = fila(candidate_urls=[{"url": "https://dudosa.com"}],
             selected_domain="https://alfa.com.ar", previous_url="https://vieja.com.ar")
    assert rh.urls_reutilizables(f) == ["https://alfa.com.ar", "https://vieja.com.ar",
                                        "https://dudosa.com"]


def test_no_se_repite_la_misma_url_por_diferencias_de_barra():
    f = fila(selected_domain="https://alfa.com.ar/", previous_url="https://alfa.com.ar")
    assert len(rh.urls_reutilizables(f)) == 1


def test_un_sitio_bloqueado_no_se_confunde_con_uno_muerto():
    assert rh.clasificar_sitio(sitio(http=403), "u")[0] == rh.BLOCKED
    assert rh.clasificar_sitio(sitio(http=404), "u")[0] == rh.INACTIVE
    assert rh.clasificar_sitio(sitio(http=500), "u")[0] == rh.ERROR


def test_un_portal_no_es_una_fuente_propia():
    st = sitio('<a href="/propiedades">x</a>', url="https://www.zonaprop.com.ar/alfa")
    assert rh.clasificar_sitio(st, st["url"])[0] == rh.UNSUPPORTED


def test_una_red_social_tampoco_es_una_fuente_propia():
    st = sitio('<a href="/propiedades">x</a>', url="https://facebook.com/alfaprop")
    assert rh.clasificar_sitio(st, st["url"])[0] == rh.UNSUPPORTED


def test_un_dominio_estacionado_no_es_una_web_viva():
    st = sitio("<html>" + "x" * 600 + "</html>", texto="This domain is for sale")
    assert rh.clasificar_sitio(st, "https://alfa.com.ar")[0] == rh.INACTIVE


def test_un_sitio_que_hoy_publica_inventario_se_rescata():
    """El punto entero de la pasada: el veredicto viejo no envejece con el sitio."""
    st = sitio("<html>" + "<a href='/propiedades/venta'>Ver</a>" * 30 + "</html>")
    assert rh.clasificar_sitio(st, "https://alfa.com.ar")[0] == rh.READY


def test_vivo_no_alcanza_para_rescatar_una_url_nunca_confirmada():
    """Promover a READY una candidata ambigua solo porque responde le adjudica a
    una inmobiliaria la web de otra. Eso es peor que dejarla afuera."""
    assert rh.necesita_identidad(fila()) is True
    assert rh.necesita_identidad(fila(selected_domain="https://alfa.com.ar")) is False


def test_una_entidad_sin_ninguna_url_se_reporta_no_se_inventa():
    r = rh.procesar(fila())
    assert r["new_status"] == rh.ERROR
    assert r["url"] is None
    assert "no hay ninguna URL" in r["evidence"]["motivo"]


def test_el_artefacto_lleva_los_campos_pedidos():
    r = rh.procesar(fila())
    for campo in ("inmobiliaria_id", "nombre", "url", "old_status", "new_status",
                  "evidence", "checked_at", "detector_version"):
        assert campo in r


def test_el_estado_viejo_se_conserva_para_poder_comparar():
    r = rh.procesar(fila(scrapeability_status="SCRAPE_SOURCE_BLOCKED"))
    assert r["old_status"] == "SCRAPE_SOURCE_BLOCKED"


# ------------------------------------------------------------ costo cero
@pytest.mark.parametrize("modulo", ["detect_platform", "map_scrape_sources",
                                    "reaudit_historical"])
def test_ningun_modulo_de_esta_fase_toca_una_search_api(modulo):
    """La fase entera es gratuita: ningun buscador pago puede colarse."""
    src = (ROOT / "scripts" / f"{modulo}.py").read_text(encoding="utf-8").lower()
    for pago in ("tavily", "serper", "exa.ai", "s.jina.ai", "api_key",
                 "brave_search", "googleapis.com/customsearch"):
        assert pago not in src, f"{modulo} menciona {pago}"

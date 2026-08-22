# -*- coding: utf-8 -*-
"""Tests del universo consolidado de fuentes.

El error que estos tests persiguen no es un crash: es apuntar un scraper al
sitio equivocado. Una fuente mal adjudicada no falla -devuelve propiedades, y
son de otra empresa-, asi que solo se descubre auditando el resultado.
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
vi = _load("verify_ready_identity")
dm = _load("deepen_manual_review")


def sitio(html="", texto=None, titulo="", http=200, url="https://alfa.com.ar"):
    return {"html": html, "texto": texto if texto is not None else html,
            "titulo": titulo, "http": http, "url": url}


def ent(nombre="Alfa Propiedades", ciudad="Rosario", provincia="Santa Fe"):
    return {"nombre_original": nombre, "ciudad": ciudad, "provincia": provincia,
            "tipo": "INMOBILIARIA", "zonas_observadas": [], "matricula": [],
            "telefono": None, "email": None, "direccion": None, "red_franquicia": None}


# ------------------------------------------------- formas de ruta en host ajeno
def test_una_ruta_geografica_no_identifica_a_ninguna_inmobiliaria():
    assert vi.forma_de_ruta("https://portal.com.ar/provincia-de-buenos-aires/x",
                            "Alfa Propiedades") == "GEOGRAFICA_O_RAIZ"


def test_una_ficha_de_una_propiedad_no_es_una_fuente():
    """Aunque el aviso sea de esta inmobiliaria, desde una ficha suelta no se
    puede enumerar su inventario."""
    assert vi.forma_de_ruta("https://choza.ai/property/34237",
                            "Alfa Propiedades") == "FICHA_DE_UNA_PROPIEDAD"


def test_un_registro_del_colegio_no_publica_inventario():
    assert vi.forma_de_ruta("https://colegioinmobiliario.org.ar/listado-de-infractores.asp",
                            "Alfa") == "REGISTRO_INSTITUCIONAL"
    assert vi.forma_de_ruta("https://martillerosmoron.org.ar/colegiado.php?col=2332",
                            "Alfa") == "REGISTRO_INSTITUCIONAL"


def test_un_perfil_white_label_si_identifica_a_la_inmobiliaria():
    for url, nombre in (("https://inmoup.com.ar/438-de-lucia", "De Lucia Propiedades"),
                        ("https://mapaprop.com/office/norberto-gonzalez-propiedades",
                         "Norberto Gonzalez Propiedades"),
                        ("https://inmobusqueda.com/abalsamopropiedades",
                         "A Balsamo Propiedades")):
        assert vi.forma_de_ruta(url, nombre) == "PERFIL_PROPIO", url


def test_el_perfil_se_reconoce_aunque_la_plataforma_no_lo_anuncie():
    """Varias plataformas cuelgan el perfil de la raiz, sin /inmobiliaria/
    adelante. Exigir el prefijo descartaria fuentes white-label validas."""
    assert vi.slug_lleva_el_nombre("https://portal.com/abalsamopropiedades",
                                   "A Balsamo Propiedades")
    assert not vi.slug_lleva_el_nombre("https://portal.com/quienes-somos",
                                       "A Balsamo Propiedades")


# --------------------------------------------------- adjudicacion equivocada
def test_el_dominio_de_otra_inmobiliaria_del_mismo_host_la_delata():
    """A DANPROP se le habia adjudicado inmobiliariabertero.com.ar. Nadie
    registra el dominio de un competidor."""
    dueno = vi.host_lleva_el_nombre_de_otro(
        "inmobiliariabertero.com.ar", "DANPROP - Broker Inmobiliario",
        ["DANPROP - Broker Inmobiliario", "Inmobiliaria Bertero"])
    assert dueno == "Inmobiliaria Bertero"


def test_el_dueno_del_dominio_no_se_denuncia_a_si_mismo():
    assert vi.host_lleva_el_nombre_de_otro(
        "inmobiliariabertero.com.ar", "Inmobiliaria Bertero",
        ["Inmobiliaria Bertero", "Otra Propiedades"]) is None


def test_que_el_portal_nombre_a_la_inmobiliaria_no_prueba_que_sea_su_sitio():
    """El defecto que este test congela: una pagina de busqueda por zona
    mencionaba a la inmobiliaria y el score la daba por buena. Los portales
    listan a todo el mundo; solo la ruta o el dominio adjudican."""
    html = "<h1>Propiedades en Villa Urquiza</h1> Estudio Monaco Propiedades Buenos Aires"
    st = sitio(html, titulo="Inmobiliaria Bertero - Villa Urquiza",
               url="https://inmobiliariabertero.com.ar/buenos-aires/villa-urquiza")
    estado, ev = vi.clasificar_identidad(
        ent("Estudio Monaco Propiedades", "Villa Urquiza", "Buenos Aires"),
        st, st["url"], "GEOGRAFICA_O_RAIZ", None)
    assert estado == vi.AJENA


def test_el_dominio_propio_sobrevive_a_cualquier_forma_de_ruta():
    html = "<h1>Alfa Propiedades</h1> Rosario Santa Fe inmobiliaria"
    st = sitio(html, titulo="Alfa Propiedades", url="https://alfapropiedades.com.ar/venta/")
    estado, ev = vi.clasificar_identidad(ent(), st, st["url"], "GEOGRAFICA_O_RAIZ", None)
    assert estado == vi.VERIFIED
    assert ev["dominio_propio"] is True


def test_los_cuatro_estados_de_identidad_existen():
    assert {vi.VERIFIED, vi.ALTA, vi.AMBIGUA, vi.AJENA} == {
        "IDENTITY_VERIFIED", "IDENTITY_HIGH_CONFIDENCE",
        "IDENTITY_AMBIGUOUS", "IDENTITY_WRONG_ENTITY"}


# --------------------------------------------------------- segunda pagina
def test_la_home_ofrece_el_candidato_no_se_adivina_la_ruta():
    """Los candidatos salen de links que la home muestra: no se golpean rutas
    inventadas contra un sitio ajeno."""
    html = '<a href="/propiedades">Propiedades</a><a href="/contacto">Contacto</a>'
    cands = dm.links_de(html, "https://alfa.com.ar")
    assert cands and cands[0][1] == "https://alfa.com.ar/propiedades"
    assert all("contacto" not in u for _, u in cands)


def test_no_se_sale_del_dominio():
    html = '<a href="https://zonaprop.com.ar/propiedades">ver</a>'
    assert dm.links_de(html, "https://alfa.com.ar") == []


def test_las_redes_y_los_archivos_no_son_candidatos():
    html = ('<a href="https://facebook.com/alfa">fb</a>'
            '<a href="/folleto-propiedades.pdf">pdf</a>')
    assert dm.links_de(html, "https://alfa.com.ar") == []


def test_el_listado_explicito_gana_al_link_generico():
    html = ('<a href="/buscar">Buscar</a><a href="/propiedades">Propiedades</a>')
    cands = dm.links_de(html, "https://alfa.com.ar")
    assert cands[0][1].endswith("/propiedades")


def test_una_segunda_pagina_con_inventario_recupera_la_fuente():
    combinado = sitio('<a href="/propiedad/123">Casa</a><a href="/propiedades">todas</a>')
    assert dp.clasificar(combinado)["has_listings"] is True


def test_una_segunda_pagina_sin_inventario_no_recupera_nada():
    combinado = sitio("<h1>Contacto</h1><p>Escribinos</p>")
    c = dp.clasificar(combinado)
    assert c["has_listings"] is False
    assert c["strategy"] == dp.MANUAL_REVIEW


def test_la_profundidad_esta_acotada_a_una_pagina():
    src = (ROOT / "scripts" / "deepen_manual_review.py").read_text(encoding="utf-8")
    assert "candidatos[0]" in src           # una sola, la mejor
    assert src.count("aud.bajar(") == 2     # home + una interna, nada mas


# ------------------------------------------------ el detector no cambia
def test_la_segunda_pagina_usa_el_mismo_detector_que_las_1992():
    """Sin criterios paralelos: la reclasificacion corre dp.clasificar igual."""
    src = (ROOT / "scripts" / "deepen_manual_review.py").read_text(encoding="utf-8")
    assert "dp.clasificar(" in src
    assert "DETECTOR_VERSION" not in src.replace("detector_version", "")


def test_un_href_relativo_cuenta_como_listado():
    """Exigir barra inicial volvia invisibles los sitios PHP que escriben
    href="propiedades.php". Eran fuentes listas contadas como sin inventario."""
    assert dp.tiene_listados(sitio('<a href="propiedades.php">Ver</a>'))
    assert dp.tiene_listados(sitio('<a href="./inmuebles.html">Ver</a>'))
    assert dp.tiene_listados(sitio('<a href="?seccion=alquileres">Ver</a>'))


def test_el_nombre_del_dominio_no_cuenta_como_listado():
    """'amilicipropiedades.com' contiene 'propiedades' y no es un listado."""
    assert not dp.tiene_listados(sitio("<p>amilicipropiedades.com</p>"))


# ------------------------------------------------- universo consolidado
def test_el_mapa_incorpora_las_rescatadas_y_excluye_las_ajenas():
    src = (ROOT / "scripts" / "map_scrape_sources.py").read_text(encoding="utf-8")
    assert "historical_scrapeability_reaudit.jsonl" in src
    assert "ready_identity_audit.jsonl" in src
    assert "IDENTITY_WRONG_ENTITY" in src and "IDENTITY_AMBIGUOUS" in src


def test_una_rescatada_que_ya_estaba_no_se_agrega_dos_veces():
    src = (ROOT / "scripts" / "map_scrape_sources.py").read_text(encoding="utf-8")
    bloque = src[src.index("rescatadas = 0"):src.index("excluidas: set")]
    assert "if cid in ya:" in bloque and "continue" in bloque
    assert "ya.add(cid)" in bloque


def test_el_mapa_no_duplica_fuentes():
    dd = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA") / "scrape_source_technology_map.jsonl"
    if not dd.exists():
        pytest.skip("el mapa todavia no se genero")
    ids = [json.loads(l)["canonical_agency_id"]
           for l in dd.open(encoding="utf-8") if l.strip()]
    assert len(ids) == len(set(ids))


def test_el_mapa_consolidado_es_determinista():
    s = sitio('<link href="/wp-content/x.css"><a href="propiedades.php">p</a>')
    assert dp.clasificar(s, True) == dp.clasificar(dict(s), True)

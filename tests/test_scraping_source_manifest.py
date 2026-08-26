#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El manifest decide que entra a la mision de scraping.

Dos errores que este artefacto no puede cometer, porque los dos se pagan
despues: marcar lista una fuente cuya URL no esta demostrada -y scrapear al
competidor equivocado-, y dar por inexistente una web que simplemente no
buscamos todavia.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_scraping_source_manifest import fila  # noqa: E402


def base(**kw):
    b = {"canonical_name": "Alfa Propiedades", "city": "rosario",
         "province": "Santa Fe", "eretz_id": 10, "status": "OFFICIAL_WEB_AMBIGUOUS"}
    b.update(kw)
    return b


def test_lista_para_scraping_pide_dominio_y_sondeo_tecnico():
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://alfa.com.ar",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {})
    assert f["ready_for_scraping"] is True
    assert f["official_domain"] == "https://alfa.com.ar"


def test_sin_dominio_demostrado_no_esta_lista():
    """Aunque el sondeo tecnico diga que el sitio se puede leer: si no sabemos
    de quien es, leerlo le atribuye a alguien el inventario de otro."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_AMBIGUOUS",
                              "discovered_domain": None,
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {})
    assert f["ready_for_scraping"] is False


def test_identidad_debil_no_habilita_scraping():
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_AMBIGUOUS",
                              "discovered_domain": "https://dudoso.com",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {})
    assert f["ready_for_scraping"] is False


def test_bloqueada_no_esta_lista():
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://alfa.com.ar",
                              "scrapeability_status": "SCRAPE_SOURCE_BLOCKED"}, {})
    assert f["ready_for_scraping"] is False


def test_lo_no_resuelto_queda_pendiente_de_buscar():
    """PENDING no es NOT_FOUND: que falte proveedor de busqueda no demuestra que
    la inmobiliaria no tenga web."""
    for estado in ("SEARCH_API_PENDING", "NO_EXISTING_WEB_DATA",
                   "SEARCH_SECOND_PASS_REQUIRED", "OFFICIAL_WEB_AMBIGUOUS"):
        f = fila("ag-1", base(status=estado), None, {})
        assert f["needs_external_search"] is True, estado
        assert f["ready_for_scraping"] is False


def test_la_resuelta_con_dominio_ya_no_necesita_buscar():
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_HIGH_CONFIDENCE",
                              "discovered_domain": "https://alfa.com.ar",
                              "needs_external_search": False}, {})
    assert f["needs_external_search"] is False


def test_el_candidato_no_confirmado_se_conserva():
    """No se publica como web oficial, pero no se tira: es la evidencia que
    permite retomar el caso sin volver a buscar."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_AMBIGUOUS",
                              "discovered_domain": None,
                              "candidato_no_confirmado": "https://quizas.com",
                              "veto_del_scoring": "31 puntos"}, {})
    assert f["candidato_no_confirmado"] == "https://quizas.com"
    assert f["official_domain"] is None
    assert f["veto_del_scoring"]


def test_la_fila_lleva_lo_que_la_proxima_mision_necesita():
    f = fila("ag-1", base(), None, {"red_franquicia": "RE/MAX"})
    for campo in ("canonical_agency_id", "canonical_name", "city", "province",
                  "franchise", "source_origin", "identity_status",
                  "scrapeability_status", "needs_external_search",
                  "ready_for_scraping", "manifest_version"):
        assert campo in f, campo
    assert f["franchise"] == "RE/MAX"


def test_un_perfil_en_un_portal_no_es_una_fuente():
    """choza.ai figura como web oficial de 42 agencias. Leerlo le atribuiria a
    una el inventario de las otras 41.

    El write gate ya lo rechazaba aguas abajo, pero entre marcarla lista aca y
    que el gate la descarte hay una corrida entera golpeando un portal ajeno."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://choza.ai/property/34237",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             "EXTERNAL_PORTAL_PROFILE", 42)
    assert f["ready_for_scraping"] is False
    assert f["perfil_en_portal_ajeno"] is True


def test_el_portal_deja_a_la_agencia_pendiente_de_busqueda():
    """Su web propia no se descarto: nunca se encontro. Vuelve a la cola."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://choza.ai/property/1",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             "EXTERNAL_PORTAL_PROFILE", 42)
    assert f["needs_external_search"] is True


def test_un_host_compartido_por_muchas_es_portal_aunque_nadie_lo_clasifique():
    """Los portales nuevos no estan en ninguna lista de nombres. Se cuentan las
    agencias que cuelgan del host, que es lo que no se puede falsificar."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://portalnuevo.com/x",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             None, 9)
    assert f["ready_for_scraping"] is False
    assert f["perfil_en_portal_ajeno"] is True


def test_dos_agencias_en_un_host_no_alcanzan_para_llamarlo_portal():
    """Dos oficinas de la misma firma comparten dominio y eso es normal."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://alfa.com.ar",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             "OFFICIAL_WEB", 2)
    assert f["ready_for_scraping"] is True
    assert f["perfil_en_portal_ajeno"] is False


def test_la_pagina_de_la_oficina_en_su_propia_red_si_es_suya():
    """century21.com.ar/oficina/X es de esa oficina. No cae en la regla."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://century21.com.ar/oficina/33",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             "OFFICIAL_OFFICE_PAGE", 2)
    assert f["ready_for_scraping"] is True


def test_una_web_que_no_es_del_rubro_tampoco_es_fuente():
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://tiendaderopa.com",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {},
             "NOT_A_REAL_ESTATE_WEB", 1)
    assert f["ready_for_scraping"] is False


def test_sin_informacion_de_plataforma_se_comporta_como_antes():
    """La firma vieja tiene que seguir andando: los 8 tests anteriores la usan."""
    f = fila("ag-1", base(), {"official_web_status": "OFFICIAL_WEB_VERIFIED",
                              "discovered_domain": "https://alfa.com.ar",
                              "scrapeability_status": "SCRAPE_SOURCE_READY"}, {})
    assert f["ready_for_scraping"] is True
    assert f["perfil_en_portal_ajeno"] is False

# -*- coding: utf-8 -*-
"""Tests del verificador de webs oficiales.

Todos los casos que el encargo marco como peligrosos, porque el riesgo de esta
fase no es no encontrar la web: es asignar la equivocada y que parezca un dato
bueno.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


w = _load("agency_web_discovery")


def ent(nombre, **kw):
    base = {"stable_id": "roomix:x", "nombre_original": nombre,
            "nombre_normalizado": nombre.lower(), "tipo": "INMOBILIARIA",
            "red_franquicia": None, "zonas_observadas": [], "matricula": []}
    base.update(kw)
    return base


def C(url, titulo="", texto="", http=200, origen="busqueda"):
    return w.Candidata(url=url, titulo=titulo, texto=texto, http=http, origen=origen)


# ------------------------------------------------- portales y redes
def test_un_portal_nunca_es_web_oficial():
    for url in ("https://www.zonaprop.com.ar/inmobiliaria-alfa",
                "https://www.argenprop.com/alfa", "https://roomix.ai/x",
                "https://www.instagram.com/alfaprop", "https://facebook.com/alfaprop"):
        assert w.es_portal(url), url


def test_el_portal_no_se_asigna_aunque_sea_la_unica_candidata():
    v = w.verificar(ent("Alfa Propiedades"),
                    [C("https://www.zonaprop.com.ar/alfa", "Alfa Propiedades", "Alfa Propiedades")])
    assert v.estado == w.NOT_FOUND
    assert v.official_web is None


def test_un_dominio_propio_si_se_asigna():
    v = w.verificar(ent("Alfa Propiedades"),
                    [C("https://alfapropiedades.com.ar", "Alfa Propiedades", "Alfa Propiedades Rosario")])
    assert v.estado in (w.VERIFIED, w.HIGH_CONFIDENCE)
    assert w.dominio(v.official_web) == "alfapropiedades.com.ar"


# ------------------------------------------------- franquicias
def test_el_dominio_de_la_red_no_es_la_web_de_la_oficina():
    """El error facil: remax.com.ar para las 191 oficinas."""
    v = w.verificar(ent("RE/MAX Ultra", tipo="OFICINA_FRANQUICIA", red_franquicia="RE/MAX"),
                    [C("https://www.remax.com.ar", "RE/MAX Argentina", "RE/MAX")])
    assert v.official_web is None
    assert any("dominio de red sin oficina" in c for c in v.contras)


def test_la_pagina_de_oficina_se_guarda_aparte():
    v = w.verificar(ent("RE/MAX Ultra", tipo="OFICINA_FRANQUICIA", red_franquicia="RE/MAX"),
                    [C("https://www.remax.com.ar/oficinas/ultra", "RE/MAX Ultra", "RE/MAX Ultra")])
    assert v.estado == w.NO_SITE
    assert v.official_office_page.endswith("/oficinas/ultra")
    assert v.official_web is None


def test_la_oficina_con_dominio_propio_conserva_ambas_cosas():
    v = w.verificar(
        ent("RE/MAX Ultra", tipo="OFICINA_FRANQUICIA", red_franquicia="RE/MAX",
            zonas_observadas=["rosario"]),
        [C("https://www.remax.com.ar/oficinas/ultra", "RE/MAX Ultra", "oficina"),
         C("https://remaxultra.com.ar", "RE/MAX Ultra Rosario", "RE/MAX Ultra Rosario")])
    assert v.official_office_page is not None
    assert v.official_web is not None


def test_distingue_dominio_de_red_de_pagina_de_oficina():
    assert not w.es_pagina_de_oficina("https://remax.com.ar")
    assert not w.es_pagina_de_oficina("https://remax.com.ar/es")
    assert w.es_pagina_de_oficina("https://remax.com.ar/oficinas/ultra")


# ------------------------------------------------- falsos positivos
def test_dos_homonimas_con_dominios_distintos_quedan_ambiguas():
    """Dos inmobiliarias del mismo apellido en provincias distintas."""
    v = w.verificar(ent("Gonzalez Propiedades"),
                    [C("https://gonzalezpropiedades.com.ar", "Gonzalez Propiedades", "Gonzalez Propiedades"),
                     C("https://gonzalez-propiedades.com", "Gonzalez Propiedades", "Gonzalez Propiedades")])
    assert v.estado == w.AMBIGUOUS
    assert v.official_web is None


def test_un_dominio_estacionado_no_cuenta():
    v = w.verificar(ent("Alfa Propiedades"),
                    [C("https://alfapropiedades.com.ar", "Alfa", "Este dominio en venta - sedo.com")])
    assert v.estado != w.VERIFIED
    assert any("estacionado" in c for c in v.contras)


def test_un_sitio_caido_es_inactive_y_conserva_el_dominio_en_la_evidencia():
    v = w.verificar(ent("Alfa Propiedades"),
                    [C("https://alfapropiedades.com.ar", http=503)])
    assert v.estado == w.INACTIVE
    assert any("503" in c for c in v.contras)


def test_un_200_sin_relacion_no_alcanza():
    """HTTP 200 no demuestra propiedad."""
    v = w.verificar(ent("Alfa Propiedades"),
                    [C("https://ferreteriadonjose.com.ar", "Ferreteria Don Jose", "tornillos")])
    assert v.official_web is None
    assert v.estado == w.NOT_FOUND


def test_el_rubro_solo_no_identifica():
    """`propiedades` e `inmobiliaria` las comparten todas."""
    assert w.tokens_distintivos("Inmobiliaria Propiedades Negocios") == set()


# ------------------------------------------------- verified
def test_la_matricula_alcanza_para_verified():
    v = w.verificar(ent("Flores Propiedades", matricula=["CMCPSI 5770"]),
                    [C("https://floresprop.com.ar", "Flores Propiedades",
                       "Flores Propiedades CMCPSI 5770 Rosario")])
    assert v.estado == w.VERIFIED
    assert any("matricula" in s for s in v.senales)


def test_nombre_completo_mas_localidad_alcanza_para_verified():
    v = w.verificar(ent("Vanzini Propiedades", zonas_observadas=["rosario centro"]),
                    [C("https://vanzini.com.ar", "Vanzini Propiedades",
                       "Vanzini Propiedades en Rosario")])
    assert v.estado == w.VERIFIED


def test_sin_confirmacion_independiente_queda_en_alta_confianza_no_verified():
    v = w.verificar(ent("Vanzini Propiedades"),
                    [C("https://vanzini.com.ar", "Vanzini Propiedades", "Vanzini Propiedades")])
    assert v.estado == w.HIGH_CONFIDENCE


# ------------------------------------------------- artefacto
def test_la_fila_de_salida_es_determinista_y_completa():
    e = ent("Alfa Propiedades", raw_agent_ids=["a", "b"], clasificacion_eretz="HIGH_CONFIDENCE_NEW")
    cands = [C("https://alfa.com.ar", "Alfa Propiedades", "Alfa Propiedades")]
    f1 = w.fila_de_salida(e, w.verificar(e, cands), cands)
    f2 = w.fila_de_salida(e, w.verificar(e, cands), cands)
    assert f1 == f2
    for campo in ("canonical_agency_id", "official_web_status", "confidence",
                  "evidence", "reason", "verifier_version", "roomix_agent_ids"):
        assert campo in f1, campo


def test_reanudable_no_repite_entidades_resueltas(tmp_path):
    p = tmp_path / "agency_web_directory.jsonl"
    p.write_text('{"canonical_agency_id": "roomix:alfa"}\n', encoding="utf-8")
    assert w.cargar_hechas(p) == {"roomix:alfa"}
    assert w.cargar_hechas(tmp_path / "no-existe.jsonl") == set()

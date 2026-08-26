#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cuando el nombre y la pagina discrepan, mandan los ojos.

`verificar()` decide por nombre y dominio: no abre la pagina. El scoring si la
lee. El canario mostro los dos errores que mas caro salen, y los dos venian de
creerle al nombre:

  A.MAGGIO PROPIEDADES    -> VERIFIED con puntaje -100
  A. ZACCARDI Propiedades -> VERIFIED apuntando a una pagina de creditos
                             hipotecarios, con 31 puntos sobre 70

Una URL equivocada es peor que ninguna: una casilla vacia se nota y alguien la
completa; una URL falsa parece un dato bueno y contamina todo lo que venga
despues.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.identity_scoring import (UMBRAL_ALTA, UMBRAL_VERIFIED,  # noqa: E402
                                      Puntaje, Señal)
from scripts.resolve_web_candidates import aplicar_veto  # noqa: E402


def puntaje(total: int, *negativas: str) -> Puntaje:
    p = Puntaje()
    p.total = total
    for clave in negativas:
        p.negativas.append(Señal(clave, -100, ""))
    return p


def fila(estado: str = "OFFICIAL_WEB_VERIFIED") -> dict:
    return {"discovered_domain": "https://ejemplo.com.ar",
            "official_web_status": estado, "reason": "por nombre"}


def test_verified_necesita_llegar_al_umbral():
    """70 puntos no es un numero decorativo."""
    r = aplicar_veto(fila(), puntaje(UMBRAL_VERIFIED))
    assert r["official_web_status"] == "OFFICIAL_WEB_VERIFIED"
    assert r["discovered_domain"] == "https://ejemplo.com.ar"


def test_verified_por_nombre_con_puntaje_bajo_se_degrada():
    """El caso ABP: 49 puntos alcanzan para sospechar, no para afirmar."""
    r = aplicar_veto(fila(), puntaje(49))
    assert r["official_web_status"] == "OFFICIAL_WEB_HIGH_CONFIDENCE"
    assert r["discovered_domain"] == "https://ejemplo.com.ar"
    assert str(UMBRAL_VERIFIED) in r["veto_del_scoring"]


def test_por_debajo_de_alta_el_dominio_no_se_publica():
    """El caso ZACCARDI: 31 puntos sobre una pagina de creditos. El dominio no
    puede ocupar el lugar de una web oficial, pero tampoco se tira: queda como
    candidato para que la evidencia no se pierda."""
    r = aplicar_veto(fila(), puntaje(31))
    assert r["official_web_status"] == "OFFICIAL_WEB_AMBIGUOUS"
    assert r["discovered_domain"] is None
    assert r["candidato_no_confirmado"] == "https://ejemplo.com.ar"


def test_otro_rubro_rechaza_aunque_el_nombre_coincida():
    """"Lopez Propiedades" en una tienda de ropa no es una inmobiliaria."""
    r = aplicar_veto(fila(), puntaje(-100, "otro_rubro"))
    assert r["official_web_status"] == "CANDIDATE_REJECTED_OTHER_ENTITY"
    assert r["discovered_domain"] is None


def test_una_nota_sobre_la_inmobiliaria_no_es_su_sitio():
    r = aplicar_veto(fila(), puntaje(-100, "es_una_nota"))
    assert r["official_web_status"] == "CANDIDATE_REJECTED_OTHER_ENTITY"
    assert r["discovered_domain"] is None
    assert "nota" in r["veto_del_scoring"]


def test_sin_evidencia_a_favor_no_se_asigna_dominio():
    """Cero puntos es cero evidencia. Que el dominio se parezca al nombre no
    demuestra identidad."""
    r = aplicar_veto(fila(), puntaje(0))
    assert r["official_web_status"] == "OFFICIAL_WEB_AMBIGUOUS"
    assert r["discovered_domain"] is None


def test_el_veto_no_toca_lo_que_no_asigno_dominio():
    r = aplicar_veto({"discovered_domain": None,
                      "official_web_status": "OFFICIAL_WEB_INACTIVE"}, puntaje(-19))
    assert r["official_web_status"] == "OFFICIAL_WEB_INACTIVE"
    assert "veto_del_scoring" not in r


def test_high_confidence_conserva_su_umbral():
    r = aplicar_veto(fila("OFFICIAL_WEB_HIGH_CONFIDENCE"), puntaje(UMBRAL_ALTA))
    assert r["official_web_status"] == "OFFICIAL_WEB_HIGH_CONFIDENCE"
    assert r["discovered_domain"] == "https://ejemplo.com.ar"


def test_not_found_no_se_concluye_sin_haber_buscado():
    """Agotar los candidatos guardados no es haber buscado. PENDING != NOT_FOUND."""
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "resolve_web_candidates.py").read_text(encoding="utf-8")
    assert 'salida["official_web_status"] = "SEARCH_API_PENDING"' in src
    assert 'OFFICIAL_WEB_NOT_FOUND' in src
    # y el runner nunca escribe NOT_FOUND como conclusion propia
    assert 'salida["official_web_status"] = "OFFICIAL_WEB_NOT_FOUND"' not in src

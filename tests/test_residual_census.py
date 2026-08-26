#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El censo de lo que falta separa "no la supimos leer" de "nadie la miro".

De las 861 fuentes sin cubrir, 142 no son webs propias -no hay inventario
propio que ingerir- y 342 nunca pasaron por un connector. Confundir las dos
cosas lleva a escribir un connector para un problema que no existe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_residual_census import main  # noqa: E402


def escribir(ruta: Path, filas: list[dict]) -> Path:
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
                    encoding="utf-8")
    return ruta


def correr(tmp_path, residual, plataformas, extra=()):
    r = escribir(tmp_path / "residual.jsonl", residual)
    p = escribir(tmp_path / "plataformas.jsonl", plataformas)
    salida = tmp_path / "censo.jsonl"
    argv = sys.argv
    sys.argv = ["build_residual_census.py", "--residual", str(r),
                "--plataformas", str(p), "--salida", str(salida), *extra]
    try:
        assert main() == 0
    finally:
        sys.argv = argv
    if not salida.exists():
        return []
    return [json.loads(l) for l in salida.open(encoding="utf-8") if l.strip()]


def test_la_que_nadie_miro_entra(tmp_path):
    filas = correr(
        tmp_path,
        [{"canonical_agency_id": "a", "domain": "https://alfa.com.ar/x",
          "connector_status": "NO_INTENTADA", "eretz_id": 7, "platform": "UNKNOWN"}],
        [{"canonical_agency_id": "a", "web_kind": "OFFICIAL_WEB"}])
    assert len(filas) == 1
    assert filas[0]["official_url"] == "https://alfa.com.ar"   # el origen, sin la ruta
    assert filas[0]["connector_candidato"] == "generico"
    assert filas[0]["eretz_id"] == 7


def test_un_perfil_en_un_portal_no_entra(tmp_path):
    """No tiene inventario propio que ingerir: el catalogo es del portal."""
    filas = correr(
        tmp_path,
        [{"canonical_agency_id": "a", "domain": "https://choza.ai/a",
          "connector_status": "NO_INTENTADA"}],
        [{"canonical_agency_id": "a", "web_kind": "EXTERNAL_PORTAL_PROFILE"}])
    assert filas == []


def test_una_web_que_no_es_inmobiliaria_tampoco(tmp_path):
    filas = correr(
        tmp_path,
        [{"canonical_agency_id": "a", "domain": "https://laguiaonline.com.ar/b",
          "connector_status": "NO_INTENTADA"}],
        [{"canonical_agency_id": "a", "web_kind": "NOT_A_REAL_ESTATE_WEB"}])
    assert filas == []


def test_no_se_repite_lo_que_ya_esta_en_otro_censo(tmp_path):
    ya = escribir(tmp_path / "otro.jsonl", [{"canonical_agency_id": "a"}])
    filas = correr(
        tmp_path,
        [{"canonical_agency_id": "a", "domain": "https://alfa.com.ar",
          "connector_status": "NO_INTENTADA"},
         {"canonical_agency_id": "b", "domain": "https://beta.com.ar",
          "connector_status": "NO_INTENTADA"}],
        [{"canonical_agency_id": "a", "web_kind": "OFFICIAL_WEB"},
         {"canonical_agency_id": "b", "web_kind": "OFFICIAL_WEB"}],
        extra=("--excluir", str(ya)))
    assert [f["canonical_agency_id"] for f in filas] == ["b"]


def test_sin_eretz_id_igual_se_censa_pero_queda_marcado(tmp_path):
    """Se descubre, se normaliza y se mide; simplemente no se escribe todavia.
    Inventar un id produciria filas que no pertenecen a ninguna inmobiliaria."""
    filas = correr(
        tmp_path,
        [{"canonical_agency_id": "a", "domain": "https://alfa.com.ar",
          "connector_status": "NO_INTENTADA", "eretz_id": None}],
        [{"canonical_agency_id": "a", "web_kind": "OFFICIAL_WEB"}])
    assert len(filas) == 1 and filas[0]["eretz_id"] is None

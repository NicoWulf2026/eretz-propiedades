#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El informe tiene que contar el universo que el pipeline proceso.

La version anterior armaba el universo mirando que carpetas habia en el disco y
quedandose con la corrida de numero mas alto de cada una. Esa heuristica leia
tres carpetas que no aportan nada al write set y se perdia tres que si, con lo
cual el informe describia un universo que nunca existio. Un informe que no
coincide con el pipeline es peor que no tener informe: da confianza sobre un
numero equivocado.

Ahora deriva todo de los artefactos y de una sola lista de entradas. Estos tests
vigilan las dos cosas: que la fuente de verdad sea esa, y que los numeros que
imprime sean los que estan en los artefactos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import mission_report  # noqa: E402
from scripts.input_universe import ENTRADAS, OBLIGATORIAS, contar  # noqa: E402

FUENTE = (Path(__file__).resolve().parents[1] / "scripts"
          / "mission_report.py").read_text(encoding="utf-8")
INFORME = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\mission_report.log")

# El write set de cuando faltaban dos rollouts. No puede volver a aparecer.
CONTEO_VIEJO = "159,858"


def numero(texto: str, etiqueta: str) -> int:
    m = re.search(re.escape(etiqueta) + r"[^0-9]*([0-9][0-9,\.]*)", texto)
    assert m, "el informe no trae %r" % etiqueta
    return int(m.group(1).replace(",", "").replace(".", ""))


# --- de que se alimenta -----------------------------------------------------

def test_el_universo_sale_de_la_lista_canonica_no_del_disco():
    assert "from scripts.input_universe import" in FUENTE
    # y no de volver a adivinar carpetas para armar el universo
    assert "todas_props" not in FUENTE


def test_las_trece_entradas_estan_contempladas():
    for carpeta, _, _ in ENTRADAS:
        assert carpeta in mission_report.CARPETAS


def test_las_dos_que_se_habian_perdido_estan():
    for obligatoria in OBLIGATORIAS:
        assert obligatoria in mission_report.CARPETAS


def test_cuenta_el_balde_de_duplicados():
    """Las 428 propiedades que se descartaban por hash repetido no aparecian en
    ninguna categoria. Si el informe no las mira, la reconciliacion no cierra."""
    assert "DUPLICADO_EN_ENTRADA.jsonl" in mission_report.ARTEFACTOS_SALIDA


def test_no_hay_conteos_viejos_escritos_a_mano():
    for viejo in ("159858", "159,858", "174164", "174,164"):
        assert viejo not in FUENTE, "hay un conteo viejo hardcodeado: %s" % viejo


def test_el_write_set_se_recorre_en_streaming():
    """800 MB cargados en una lista fue un MemoryError que ademas dejo el
    artefacto anterior en cero."""
    assert "def recorrer(" in FUENTE
    assert "yield json.loads" in FUENTE


# --- contra los artefactos reales -------------------------------------------

def test_el_informe_reproduce_el_universo_de_las_entradas():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert numero(texto, "UNIVERSO_ANALIZADO (suma):") == sum(contar().values())


def test_el_informe_declara_las_trece_entradas():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert numero(texto, "familias de entrada declaradas:") == len(ENTRADAS)
    for carpeta, _, _ in ENTRADAS:
        assert carpeta in texto


def test_ninguna_corrida_queda_sin_origen():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert numero(texto, "corridas SIN ORIGEN identificado:") == 0


def test_las_invariantes_del_write_set_cierran():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert "[FALLA]" not in texto
    for inv in ("DB_WRITE_ELIGIBLE == HASHES_UNICOS",
                "DB_WRITE_ELIGIBLE == URLS_UNICAS",
                "MULTI_AGENCY_URLS_IN_WRITE_SET == 0"):
        assert inv in texto


def test_el_informe_no_reporta_el_write_set_viejo():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert CONTEO_VIEJO not in texto


def test_bustamante_quedo_del_lado_correcto():
    if not INFORME.exists():
        pytest.skip("todavia no se genero el informe")
    texto = INFORME.read_text(encoding="utf-8", errors="replace")
    assert "eretz_id 1028: 3137" in texto.replace(",", "")
    assert "eretz_id 651:" not in texto

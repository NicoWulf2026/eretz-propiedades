#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La simulacion de bajas tiene que poder equivocarse en voz alta.

Una propiedad que hoy no aparece no es una baja. Antes de encender la regla hay
que saber cuantas desactivaria y cuantas de esas reaparecieron; y para que esos
dos numeros signifiquen algo, las ausencias tienen que ser comparables entre si.

Las de las primeras corridas se anotaron con la clave vieja del checkpoint -el
id del listado- y mezclarlas no da error: da 173 candidatas a baja que no
existen, porque ninguna clave vieja coincide nunca con una propiedad de hoy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_deletions import RE_HASH, main  # noqa: E402

HASH_A = "a" * 32
HASH_B = "b" * 32


def rollout(tmp_path, nombre, corridas):
    d = tmp_path / nombre
    d.mkdir(parents=True, exist_ok=True)
    for n, (props, aus) in corridas.items():
        (d / f"properties_run{n}.jsonl").write_text(
            "".join(json.dumps({"hash_dedup": h}) + "\n" for h in props),
            encoding="utf-8")
        (d / f"absences_run{n}.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in aus), encoding="utf-8")
    return d


def correr(tmp_path, nombre, umbral=3):
    salida = tmp_path / "dry.jsonl"
    argv = sys.argv
    sys.argv = ["evaluate_deletions.py", "--raiz", str(tmp_path),
                "--rollouts", nombre, "--umbral", str(umbral),
                "--salida", str(salida)]
    try:
        assert main() == 0
    finally:
        sys.argv = argv
    return [json.loads(l) for l in salida.open(encoding="utf-8") if l.strip()]


def test_la_clave_vieja_no_se_mezcla(tmp_path):
    """El id del listado no es un hash: parece ausente para siempre."""
    assert not RE_HASH.match("7797368")
    assert RE_HASH.match(HASH_A)

    rollout(tmp_path, "VIEJO", {
        "1": ([HASH_A], []),
        "2": ([HASH_A], [{"hash_dedup": "7797368", "ausencias_consecutivas": 9}]),
    })
    assert correr(tmp_path, "VIEJO") == []


def test_la_que_llega_al_umbral_es_candidata(tmp_path):
    rollout(tmp_path, "TRES", {
        "1": ([HASH_A, HASH_B], []),
        "2": ([HASH_A], [{"hash_dedup": HASH_B, "ausencias_consecutivas": 3,
                          "canonical_agency_id": "ag-1"}]),
    })
    filas = correr(tmp_path, "TRES")
    assert len(filas) == 1 and filas[0]["hash_dedup"] == HASH_B
    assert filas[0]["reaparecio_en"] == []


def test_la_que_reaparecio_no_es_una_baja(tmp_path):
    """Es la prueba de que la ausencia no significaba lo que parecia."""
    rollout(tmp_path, "VUELVE", {
        "1": ([HASH_A, HASH_B], []),
        "2": ([HASH_A], [{"hash_dedup": HASH_B, "ausencias_consecutivas": 3,
                          "canonical_agency_id": "ag-1"}]),
        "3": ([HASH_A, HASH_B], []),
    })
    filas = correr(tmp_path, "VUELVE")
    assert len(filas) == 1 and filas[0]["reaparecio_en"] == ["3"]


def test_las_corridas_se_comparan_como_numeros(tmp_path):
    """Con strings, la corrida 10 seria "anterior" a la 3 y una reaparicion
    tardia pasaria inadvertida."""
    corridas = {str(n): ([HASH_A], []) for n in range(1, 10)}
    corridas["3"] = ([HASH_A], [{"hash_dedup": HASH_B,
                                 "ausencias_consecutivas": 3,
                                 "canonical_agency_id": "ag-1"}])
    corridas["10"] = ([HASH_A, HASH_B], [])
    rollout(tmp_path, "DIEZ", corridas)
    filas = correr(tmp_path, "DIEZ")
    assert filas and filas[0]["reaparecio_en"] == ["10"]


def test_debajo_del_umbral_no_se_desactiva_nada(tmp_path):
    rollout(tmp_path, "UNA", {
        "1": ([HASH_A, HASH_B], []),
        "2": ([HASH_A], [{"hash_dedup": HASH_B, "ausencias_consecutivas": 1,
                          "canonical_agency_id": "ag-1"}]),
    })
    assert correr(tmp_path, "UNA") == []

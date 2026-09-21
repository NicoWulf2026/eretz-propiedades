# -*- coding: utf-8 -*-
"""Que la comparacion entre corridas no confunda contenido con marcas.

El riesgo de esta herramienta es el opuesto al habitual: si no ignorara las
marcas de corrida, informaria que cambiaron LAS 200 fichas -porque `_run`
lleva la hora- y seria inutil justo cuando hace falta. Y si ignorara de mas,
taparia el cambio real.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.que_cambio_entre_corridas import (buscar_paquete,  # noqa: E402
                                               campos_distintos, comparar)


def escribir(paquete: Path, nombre: str, filas: list[dict]) -> None:
    paquete.mkdir(parents=True, exist_ok=True)
    with (paquete / nombre).open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")


def ficha(url: str, **campos):
    base = {"source_url": url, "precio": 1000, "imagenes": ["a.jpg"],
            "_run": "2026-09-21T12:36:12", "_cambio": "SIN_CAMBIOS",
            "provenance": {"connector": "tokko", "run": "12:36"}}
    base.update(campos)
    return base


def test_MUERDE_las_marcas_de_corrida_no_son_un_cambio():
    """`_run` y `provenance` cambian siempre. Si contaran, las 200 fichas de
    `castro y compania` habrian figurado como modificadas y el informe no
    habria servido para nada."""
    a = ficha("u1")
    b = ficha("u1", _run="2026-09-21T12:55:31", _cambio="MODIFICADA",
              provenance={"connector": "tokko", "run": "12:55"})
    assert campos_distintos(a, b) == []


def test_MUERDE_un_cambio_de_contenido_si_se_ve():
    a = ficha("u1", imagenes=["a.jpg", "b.jpg"])
    b = ficha("u1", _run="otra", imagenes=["c.jpg"])
    assert campos_distintos(a, b) == ["imagenes"]


def test_el_caso_real_de_castro_y_compania(tmp_path: Path):
    """200 fichas, una sola con la galeria reemplazada: lo que de verdad paso
    el 2026-09-21. El resto solo difiere en las marcas."""
    r1 = [ficha(f"u{i}") for i in range(200)]
    r2 = [ficha(f"u{i}", _run="2026-09-21T12:55:31",
                provenance={"connector": "tokko", "run": "12:55"})
          for i in range(200)]
    r2[7]["imagenes"] = ["nueva1.jpg", "nueva2.jpg"]
    r2[7]["fingerprint"] = "8b880972"
    escribir(tmp_path, "properties_run1.jsonl", r1)
    escribir(tmp_path, "properties_run2.jsonl", r2)
    r = comparar(tmp_path)
    assert r["run1"] == 200 and r["run2"] == 200
    assert r["solo_en_run1"] == [] and r["solo_en_run2"] == []
    assert len(r["cambiadas"]) == 1
    assert r["cambiadas"][0]["url"] == "u7"
    assert r["cambiadas"][0]["campos"] == ["fingerprint", "imagenes"]


def test_MUERDE_las_urls_que_una_corrida_no_vio_se_nombran(tmp_path: Path):
    """El intercambio 1 por 1 de `alagna`: lo que faltaba no era el numero,
    era la url."""
    escribir(tmp_path, "properties_run1.jsonl", [ficha("se-fue"), ficha("queda")])
    escribir(tmp_path, "properties_run2.jsonl", [ficha("llego"), ficha("queda")])
    r = comparar(tmp_path)
    assert r["solo_en_run1"] == ["se-fue"]
    assert r["solo_en_run2"] == ["llego"]
    assert r["cambiadas"] == []


def test_un_paquete_sin_archivos_no_explota(tmp_path: Path):
    r = comparar(tmp_path)
    assert r == {"run1": 0, "run2": 0, "solo_en_run1": [],
                 "solo_en_run2": [], "cambiadas": []}


def test_buscar_paquete_por_parte_del_nombre(tmp_path: Path):
    (tmp_path / "abc123").mkdir()
    (tmp_path / "abc123" / "run1.json").write_text(
        json.dumps({"canonical_agency_id": "roomix:castro y compania real estate"}),
        encoding="utf-8")
    assert buscar_paquete("castro y compania", tmp_path).name == "abc123"
    assert buscar_paquete("no existe", tmp_path) is None


def test_un_run1_ilegible_no_corta_la_busqueda(tmp_path: Path):
    (tmp_path / "aaa").mkdir()
    (tmp_path / "aaa" / "run1.json").write_text("{roto", encoding="utf-8")
    (tmp_path / "bbb").mkdir()
    (tmp_path / "bbb" / "run1.json").write_text(
        json.dumps({"canonical_agency_id": "roomix:alagna propiedades"}),
        encoding="utf-8")
    assert buscar_paquete("alagna", tmp_path).name == "bbb"

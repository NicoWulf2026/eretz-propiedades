# -*- coding: utf-8 -*-
"""El gate mira sólo lo que se volvió a certificar, con el criterio del gate."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.comparar_con_linea_base import main, recertificadas_desde


def _escribir(ruta: Path, filas) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")


def _fila(agencia, url, **campos):
    return {"canonical_agency_id": agencia, "source_url": url, **campos}


def test_solo_cuentan_las_agencias_recertificadas_desde_la_hora(tmp_path):
    _escribir(tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl", [
        {"canonical_agency_id": "a", "checked_at": "2026-09-24T10:00:00"},
        {"canonical_agency_id": "b", "checked_at": "2026-09-24T12:00:00"},
        {"canonical_agency_id": "a", "checked_at": "2026-09-24T09:00:00"}])
    assert recertificadas_desde(tmp_path, "2026-09-24T11:39:00") == {"b"}


def test_MUERDE_un_campo_perdido_en_una_agencia_recertificada_se_reporta(tmp_path):
    _escribir(tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl", [
        {"canonical_agency_id": "b", "checked_at": "2026-09-24T12:00:00"},
        {"canonical_agency_id": "c", "checked_at": "2026-09-24T08:00:00"}])
    _escribir(tmp_path / "base.jsonl", [
        _fila("b", "https://b.test/p/1", precio=100, operacion="venta"),
        _fila("c", "https://c.test/p/1", precio=1)])
    _escribir(tmp_path / "agencies" / "x" / "properties_run2.jsonl", [
        _fila("b", "https://b.test/p/1", precio=100)])
    _escribir(tmp_path / "agencies" / "y" / "properties_run2.jsonl", [
        _fila("c", "https://c.test/p/1")])  # c no se recertifico: no cuenta
    salida = tmp_path / "gate.json"
    main(["--linea-base", str(tmp_path / "base.jsonl"), "--desde",
          "2026-09-24T11:39:00", "--cert", str(tmp_path), "--salida", str(salida)])
    reporte = json.loads(salida.read_text(encoding="utf-8"))
    assert reporte["agencias_recertificadas"] == 1
    assert reporte["por_campo"]["operacion"] == {"UNEXPLAINED_LOSS": 1}
    assert "precio" not in reporte["por_campo"]


def _con_dos_perdidas(tmp_path):
    _escribir(tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl", [
        {"canonical_agency_id": "b", "checked_at": "2026-09-24T12:00:00"}])
    _escribir(tmp_path / "base.jsonl", [
        _fila("b", "https://b.test/p/1", precio=100, operacion="venta"),
        _fila("b", "https://b.test/p/2", precio=200, operacion="alquiler")])
    _escribir(tmp_path / "agencies" / "x" / "properties_run2.jsonl", [
        _fila("b", "https://b.test/p/1", precio=100),
        _fila("b", "https://b.test/p/2", precio=200)])


def _correr(tmp_path):
    salida = tmp_path / "gate.json"
    main(["--linea-base", str(tmp_path / "base.jsonl"), "--desde",
          "2026-09-24T11:39:00", "--cert", str(tmp_path), "--salida", str(salida)])
    return json.loads(salida.read_text(encoding="utf-8"))


def test_una_perdida_revisada_con_evidencia_deja_de_estar_pendiente(tmp_path):
    _con_dos_perdidas(tmp_path)
    _escribir(tmp_path / "REVISADAS.jsonl", [
        {"agency": "b", "url": "b.test/p/2", "field": "operacion",
         "kind": "UNEXPLAINED_LOSS", "veredicto": "CORRECCION",
         "evidencia": "la ficha dice «alquilada», no ofrece alquiler"}])
    reporte = _correr(tmp_path)
    assert reporte["status"] == "REVIEW_REQUIRED"  # el gate dice lo que vio
    assert reporte["pendientes_de_revision"] == 1
    assert reporte["revisadas"] == {"CORRECCION": 1}
    assert [p["url"] for p in reporte["pendientes"]] == ["b.test/p/1"]


def test_MUERDE_una_revision_sin_evidencia_o_de_otro_campo_no_cuenta(tmp_path):
    _con_dos_perdidas(tmp_path)
    _escribir(tmp_path / "REVISADAS.jsonl", [
        {"agency": "b", "url": "b.test/p/2", "field": "operacion",
         "kind": "UNEXPLAINED_LOSS", "veredicto": "CORRECCION"},
        {"agency": "b", "url": "b.test/p/1", "field": "precio",
         "kind": "UNEXPLAINED_LOSS", "veredicto": "CORRECCION", "evidencia": "x"}])
    reporte = _correr(tmp_path)
    assert reporte["pendientes_de_revision"] == 2
    assert reporte["revisadas"] == {}

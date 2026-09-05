"""El quality gate: de dónde sale el diagnóstico de un campo ausente."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.property_quality_gate import GATE_VERSION, cobertura_por_agencia


def _paquete(tmp_path: Path, agencia: str, campos: dict) -> Path:
    carpeta = tmp_path / agencia.replace(":", "_").replace(" ", "_")
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "certification.json").write_text(json.dumps(
        {"canonical_agency_id": agencia, "field_coverage": campos},
        ensure_ascii=False), encoding="utf-8")
    return carpeta


def test_haberlo_extraido_prueba_que_la_fuente_lo_publica(tmp_path):
    """La señal de origen falla hacia el "no lo publica", y eso exonera al parser.

    `alpha inmobiliaria` figura con `source_provided: 0` en `descripcion` y con
    las 127 descripciones extraídas. Leyendo sólo la señal, cualquier ficha
    suya sin descripción salía como `SOURCE_NOT_PROVIDED` —"no hay nada que
    arreglar"— sobre un campo que la fuente evidentemente publica.

    Eran 128 de 290 exoneraciones, el 44 %.
    """
    _paquete(tmp_path, "roomix:alpha", {
        "descripcion": {"source_provided": 0, "normalized_present": 127},
    })
    cobertura = cobertura_por_agencia(tmp_path)

    assert cobertura["roomix:alpha"]["descripcion"] is True


def test_un_campo_que_nunca_se_extrajo_ni_se_vio_sigue_exonerado(tmp_path):
    """La corrección no puede convertir todo en defecto nuestro.

    Si la fuente no lo publicaba y nunca se extrajo, `SOURCE_NOT_PROVIDED` es
    la verdad y no hay nada que arreglar.
    """
    _paquete(tmp_path, "roomix:beta", {
        "barrio": {"source_provided": 0, "normalized_present": 0},
    })
    cobertura = cobertura_por_agencia(tmp_path)

    assert cobertura["roomix:beta"]["barrio"] is False


def test_sin_paquete_no_se_inventa_diagnostico(tmp_path):
    """Sin certificación no se sabe, y decirlo es parte del contrato."""
    assert cobertura_por_agencia(tmp_path) == {}
    assert cobertura_por_agencia(tmp_path / "no-existe") == {}


def test_un_paquete_ilegible_no_tumba_el_gate(tmp_path):
    """Un JSON roto es una agencia sin diagnóstico, no una corrida caída."""
    roto = tmp_path / "roto"
    roto.mkdir()
    (roto / "certification.json").write_text("{no es json", encoding="utf-8")
    _paquete(tmp_path, "roomix:sana", {
        "precio": {"source_provided": 10, "normalized_present": 10}})

    cobertura = cobertura_por_agencia(tmp_path)
    assert cobertura == {"roomix:sana": {"precio": True}}


def test_un_paquete_sin_field_coverage_no_deja_agencia_fantasma(tmp_path):
    """153 de 200 paquetes no tienen `field_coverage` —son los que no
    encontraron inventario—. Registrarlos con un diccionario vacío haría creer
    que esa agencia tiene diagnóstico y que ningún campo se publica."""
    _paquete(tmp_path, "roomix:vacia", {})
    assert "roomix:vacia" not in cobertura_por_agencia(tmp_path)


def test_el_gate_no_escribe_en_ninguna_base(tmp_path, monkeypatch, capsys):
    """La barrera de autorización: el gate es una lectura y un artefacto."""
    db = tmp_path / "p.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (row_json text, canonical_id text, "
                     "hash_dedup text, status text)")
    fila = {"source_url": "https://alfa.com.ar/p/1", "hash_dedup": "h1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "operacion": "venta", "tipo_propiedad": "casa",
            "precio": 100000.0, "moneda": "USD", "ciudad": "Rosario"}
    conexion.execute("insert into rows values (?,?,?,?)",
                     (json.dumps(fila), "roomix:alfa", "h1", "CANDIDATE"))
    conexion.commit()
    conexion.close()
    solo_lectura = db.stat().st_mtime

    salida = tmp_path / "out"
    salida.mkdir()
    paquetes = tmp_path / "paquetes"
    paquetes.mkdir()

    import sys
    from scripts import property_quality_gate as gate
    monkeypatch.setattr(sys, "argv", [
        "gate", "--db", str(db), "--paquetes", str(paquetes),
        "--salida", str(salida)])
    assert gate.main() == 0

    resumen = json.loads(
        (salida / "PROPERTY_QUALITY_GATE_SUMMARY.json").read_text(encoding="utf-8"))
    assert resumen["database_writes"] == 0
    assert resumen["propiedades_evaluadas"] == 1
    assert db.stat().st_mtime == solo_lectura

    filas = [json.loads(l) for l in
             (salida / "PROPERTY_QUALITY_GATE.jsonl").read_text(
                 encoding="utf-8").splitlines()]
    assert len(filas) == 1
    # Una fila por propiedad, no un agregado: un número resumido no se puede
    # discutir, una fila sí.
    assert filas[0]["hash_dedup"] == "h1"
    assert filas[0]["gate_version"] == GATE_VERSION
    assert filas[0]["origen_del_diagnostico"] == "sin_paquete_de_certificacion"
    # Sin ciudad no hay filtro por ciudad, pero la propiedad existe igual.
    assert "FICHA" in filas[0]["alcances"] and "LISTADO" in filas[0]["alcances"]
    assert "MAPA" not in filas[0]["alcances"]


def test_la_base_por_defecto_es_la_canonica_del_manifiesto():
    """Una snapshot vieja clavada en el default ya hizo que el certificador
    midiera contra un universo al que le faltaban 13.023 candidatas. El default
    no puede ser una ruta escrita a mano."""
    fuente = Path("scripts/property_quality_gate.py").read_text(encoding="utf-8")
    assert 'default=str(base_canonica())' in fuente
    assert "PREINGESTION_REBUILD_20260903" not in fuente

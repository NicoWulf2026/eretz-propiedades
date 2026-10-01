"""backlog_de_lote: familias por firma exacta + plataforma, ordenadas por impacto."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import backlog_de_lote as b  # noqa: E402


def _jsonl(ruta: Path, filas):
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")


def _paro(agencia, firma, componente="extraccion_transversal_de_atributos", radio="FAMILIA",
          cuando="2026-10-01T10:00:00"):
    return {"canonical_agency_id": agencia, "decision": "STOP", "pendiente_de_resolucion": True,
            "componente_sospechoso": componente, "radio_estimado": radio,
            "firma_del_patron": firma, "connector_strategy": "generic/sitemap", "cuando": cuando}


def _armar(tmp_path, paros, diferidas=(), resultados=(), paquetes=()):
    _jsonl(tmp_path / "AGENCY_DEFECT_QUEUE.jsonl", paros)
    _jsonl(tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl", diferidas)
    _jsonl(tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl", resultados)
    for i, (agencia, run, cobertura) in enumerate(paquetes):
        d = tmp_path / "agencies" / f"p{i}"
        d.mkdir(parents=True)
        (d / "run1.json").write_text(json.dumps({"canonical_agency_id": agencia, **run}), encoding="utf-8")
        (d / "field_coverage.json").write_text(json.dumps(cobertura), encoding="utf-8")
    return tmp_path


def test_un_bug_compartido_de_muchas_agencias_va_antes_que_sitios_chicos(tmp_path):
    paros = [_paro(f"roomix:grande {i}", "f_compartida") for i in range(20)]
    paros += [_paro(f"roomix:chica {i}", f"f_unica_{i}") for i in range(5)]
    falla = {"provincia": {"state": "EXTRACTION_FAILED", "extraction_failed": 10,
                           "source_provided": 10, "normalized_present": 0}}
    paquetes = [(f"roomix:grande {i}", {}, falla) for i in range(20)]
    paquetes += [(f"roomix:chica {i}", {}, {"provincia": {**falla["provincia"], "extraction_failed": 40}})
                 for i in range(5)]
    filas = b.backlog(_armar(tmp_path, paros, paquetes=paquetes))
    assert filas[0]["firma"] == "f_compartida" and filas[0]["n_agencias"] == 20
    assert filas[0]["propiedades"] == 200


def test_falso_cero_va_primero_aunque_sea_una_agencia(tmp_path):
    paros = [_paro(f"roomix:a{i}", "f_campos") for i in range(6)]
    paros.append(_paro("roomix:cero", "f_cero", componente="posible_perdida_de_inventario"))
    filas = b.backlog(_armar(tmp_path, paros))
    assert filas[0]["firma"] == "f_cero" and filas[0]["clase"] == 1


def test_un_paro_que_la_realidad_cerro_no_entra(tmp_path):
    paros = [_paro("roomix:arreglada", "f1", cuando="2026-10-01T10:00:00")]
    resultados = [{"canonical_agency_id": "roomix:arreglada", "status": "CERTIFIED_COMPLETE",
                   "checked_at": "2026-10-01T12:00:00"}]
    assert b.backlog(_armar(tmp_path, paros, resultados=resultados)) == []


def test_la_plataforma_solo_sale_de_la_lista_cerrada(tmp_path):
    paros = [_paro("roomix:x", "f1"), _paro("roomix:y", "f1")]
    diferidas = [{"canonical_agency_id": "roomix:x", "componente": "extraccion_transversal_de_atributos",
                  "diagnostico": "tema Houzez, address icon-pin"},
                 {"canonical_agency_id": "roomix:y", "componente": "extraccion_transversal_de_atributos",
                  "diagnostico": "un CMS propio que nadie conoce"}]
    filas = b.backlog(_armar(tmp_path, paros, diferidas=diferidas))
    assert {f["plataforma"] for f in filas} == {"Houzez", None}


def test_diferidas_automaticas_y_humanas_quedan_contadas(tmp_path):
    paros = [_paro("roomix:x", "f1"), _paro("roomix:y", "f1"), _paro("roomix:z", "f1")]
    c = "extraccion_transversal_de_atributos"
    diferidas = [{"canonical_agency_id": "roomix:x", "componente": c, "diagnostico": "visto"},
                 {"canonical_agency_id": "roomix:y", "componente": c, "diagnostico": "copia",
                  "diferida_por_precedente": True}]
    (f,) = b.backlog(_armar(tmp_path, paros, diferidas=diferidas))
    assert (f["diferidas_humanas"], f["diferidas_automaticas"], f["sin_diferida"]) == (1, 1, 1)
    assert f["diagnostico"] == "visto"

"""kpi_de_la_cola: las horas paradas cuentan en el reloj."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kpi_de_la_cola as k  # noqa: E402


def _jsonl(ruta, filas):
    ruta.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")


def test_hora_de_reloj_cuenta_las_horas_paradas_y_la_demora_del_paro(tmp_path):
    res = [{"canonical_agency_id": f"roomix:a{i}", "status": "CERTIFIED_COMPLETE",
            "checked_at": f"2026-10-01T10:{i:02d}:00", "operational_metrics": {"properties": 10, "requests": 22},
            "network": {"requests_run2": 11}} for i in range(6)]
    res.append({"canonical_agency_id": "roomix:p", "status": "NEEDS_FIX", "checked_at": "2026-10-01T10:30:00"})
    _jsonl(tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl", res)
    _jsonl(tmp_path / "AGENCY_DEFECT_QUEUE.jsonl", [
        {"decision": "STOP", "canonical_agency_id": "roomix:p", "componente_sospechoso": "c",
         "cuando": "2026-10-01T10:30:00"},
        {"decision": "STOP", "canonical_agency_id": "roomix:q", "componente_sospechoso": "c",
         "cuando": "2026-10-01T10:40:00"}])
    _jsonl(tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl", [
        {"canonical_agency_id": "roomix:p", "componente": "c", "cuando": "2026-10-01T10:50:00",
         "diferida_por_precedente": True}])
    r = k.kpi(datetime(2026, 10, 1, 10), datetime(2026, 10, 1, 14), tmp_path)
    # 7 resoluciones en 4 h de reloj, una sola hora con trabajo.
    assert r["resoluciones_por_hora_de_reloj"] == 1.75 and r["resoluciones_por_hora_activa"] == 7
    assert r["horas_sin_resultados"] == 3
    assert r["paro_a_liberacion_min_mediana"] == 20 and r["paros_sin_liberar"] == 1
    assert r["propiedades_certificadas"] == 60 and r["parte_segunda_corrida"] == 0.5

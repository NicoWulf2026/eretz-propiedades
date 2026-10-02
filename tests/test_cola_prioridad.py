"""con_prioridad: adelanta una lista explicita, con motivo y vencimiento; el universo no cambia."""
from __future__ import annotations

import json

from scripts.run_agency_certification_queue import PRIORIDAD_DE_COLA, con_prioridad

COLA = ["roomix:a", "roomix:b", "roomix:c", "roomix:d"]


def _archivo(tmp_path, **datos):
    (tmp_path / PRIORIDAD_DE_COLA).write_text(json.dumps(datos), encoding="utf-8")


def test_adelanta_en_su_orden_sin_perder_ni_repetir(tmp_path):
    _archivo(tmp_path, motivo="falsos CERTIFIED TIV", hasta="2026-10-04T00:00:00",
             agencias=["roomix:c", "roomix:x", "roomix:a"])
    assert con_prioridad(COLA, tmp_path, "2026-10-02T08:00:00") == [
        "roomix:c", "roomix:a", "roomix:b", "roomix:d"]


def test_vencido_sin_motivo_o_sin_archivo_no_toca_la_cola(tmp_path):
    assert con_prioridad(COLA, tmp_path, "2026-10-02T08:00:00") == COLA
    _archivo(tmp_path, motivo="x", hasta="2026-10-01T00:00:00", agencias=["roomix:d"])
    assert con_prioridad(COLA, tmp_path, "2026-10-02T08:00:00") == COLA
    _archivo(tmp_path, motivo="", hasta="2026-10-04T00:00:00", agencias=["roomix:d"])
    assert con_prioridad(COLA, tmp_path, "2026-10-02T08:00:00") == COLA
    (tmp_path / PRIORIDAD_DE_COLA).write_text("{roto", encoding="utf-8")
    assert con_prioridad(COLA, tmp_path, "2026-10-02T08:00:00") == COLA

"""La metrica de beta separa lo critico del backlog nacional (pedido del usuario 02-10)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / "scripts")]

import metrica_beta as M  # noqa: E402


def test_un_needs_fix_honesto_con_la_huella_vigente_cierra_la_critica(monkeypatch):
    monkeypatch.setattr(M.F, "strategy_fingerprint", lambda c, s: "nueva")
    ult = {
        "roomix:a": {"strategy_fingerprint": "nueva", "status": "NEEDS_FIX", "checked_at": "2026-10-02T14:00:00",
                     "run1": {"enumeradas": 100}, "operational_metrics": {"duration_seconds": 1000}},
        "roomix:b": {"strategy_fingerprint": "vieja", "status": "CERTIFIED_COMPLETE",
                     "checked_at": "2026-10-01T10:00:00", "run1": {"enumeradas": 20}},
    }
    c = M.criticas(ult, ["roomix:a", "roomix:b", "roomix:c"], datetime(2026, 10, 2, 5, 53), {"b": 300})
    assert (c["cerradas"], c["abiertas"]) == (1, 2)
    # El COMPLETE falso enumeraba 20; lo que falta se mide con lo declarado.
    assert c["abiertas_detalle"]["b"] == 300
    assert c["segundos_por_ficha_mediana"] == 10.0
    assert c["horas_de_la_mas_larga"] == round(300 * 10 / 3600, 1)


def test_el_gate_solo_cuenta_como_sin_explicar_lo_que_no_tiene_clase_aceptada(tmp_path):
    archivo = tmp_path / "c.jsonl"
    filas = [{"clase_beta": "KNOWN_DEBT"}, {"clase_beta": "CORRECTION_OF_OLD_BAD_DATA"},
             {"clase_beta": "REAL_BETA_BLOCKER"}, {}]
    archivo.write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
    g = M.gate(archivo)
    assert g["sin_explicar"] == 2
    assert M.gate(tmp_path / "no_existe.jsonl") == {"archivo": None}


def test_el_checkpoint_de_otro_regimen_no_se_suma(tmp_path):
    for w, n in ((0, 10), (1, 20), (2, 999)):
        (tmp_path / f"AGENCY_CERTIFICATION_PROGRESS.w{w}.json").write_text(
            json.dumps({"pending_count": n}), encoding="utf-8")
    assert M.pendientes_de_la_cola(tmp_path, 2) == 30

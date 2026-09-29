"""El regimen de workers se decide midiendo (politica P5, 29-09)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from regimen_de_workers import FORMATO, decidir  # noqa: E402

AHORA = datetime(2026, 9, 30, 12, 0, 0)
BASE = {"agencias": 200, "horas_activas": 25, "por_hora_activa": 8.0,
        "bloqueo": 0.075, "paros_por_agencia": 0.14}
SANOS = {"memoria": 50.0, "cpu": 40.0}


def _midiendo(**cambios):
    return lambda desde, hasta: dict(BASE, **cambios)


def _en_prueba(horas=7):
    return {"workers": 3, "prueba": "en_curso", "linea_base": BASE,
            "desde": (AHORA - timedelta(hours=horas)).strftime(FORMATO)}


def test_con_linea_base_suficiente_se_prueba_con_tres():
    nuevo = decidir({}, AHORA, _midiendo(), SANOS)
    assert nuevo["workers"] == 3 and nuevo["prueba"] == "en_curso"


def test_sin_linea_base_no_se_prueba_nada():
    assert decidir({}, AHORA, _midiendo(agencias=10), SANOS) is None


def test_la_prueba_no_se_juzga_antes_de_tiempo():
    assert decidir(_en_prueba(horas=2), AHORA, _midiendo(por_hora_activa=1.0), SANOS) is None


def test_tres_que_mejora_se_aprueba():
    nuevo = decidir(_en_prueba(), AHORA, _midiendo(por_hora_activa=11.0), SANOS)
    assert nuevo["workers"] == 3 and nuevo["prueba"] == "aprobada"


def test_MUERDE_tres_que_no_mejora_lo_bastante_vuelve_a_dos():
    nuevo = decidir(_en_prueba(), AHORA, _midiendo(por_hora_activa=8.4), SANOS)
    assert nuevo["workers"] == 2 and "throughput" in nuevo["motivo"]


def test_MUERDE_mas_bloqueos_vuelve_a_dos_aunque_sea_mas_rapido():
    nuevo = decidir(_en_prueba(), AHORA, _midiendo(por_hora_activa=12.0, bloqueo=0.20), SANOS)
    assert nuevo["workers"] == 2 and "bloqueo" in nuevo["motivo"]


def test_MUERDE_mas_paros_vuelve_a_dos():
    nuevo = decidir(_en_prueba(), AHORA, _midiendo(por_hora_activa=12.0, paros_por_agencia=0.40), SANOS)
    assert nuevo["workers"] == 2 and "paros" in nuevo["motivo"]


def test_MUERDE_sin_memoria_vuelve_a_dos_enseguida():
    nuevo = decidir(_en_prueba(horas=1), AHORA, _midiendo(), {"memoria": 95.0, "cpu": 10.0})
    assert nuevo["workers"] == 2


def test_una_prueba_rechazada_no_se_repite_enseguida():
    vigente = {"workers": 2, "prueba": "rechazada",
               "rechazada_en": (AHORA - timedelta(days=2)).strftime(FORMATO)}
    assert decidir(vigente, AHORA, _midiendo(), SANOS) is None
    vigente["rechazada_en"] = (AHORA - timedelta(days=8)).strftime(FORMATO)
    assert decidir(vigente, AHORA, _midiendo(), SANOS)["workers"] == 3

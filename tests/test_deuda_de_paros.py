# -*- coding: utf-8 -*-
"""Que la lista de «lo que falta» no mezcle lo que ya se resolvio solo.

`AGENCY_DEFECT_QUEUE.jsonl` escribe `pendiente_de_resolucion: True` al crear
la entrada y no la actualiza nunca. Medido el 2026-09-21: de 113 entradas STOP
marcadas abiertas, 18 son de agencias que ya certificaron despues. `altos
servicios inmobiliarios` paro el 2026-09-05 y certifico el 2026-09-21.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.deuda_de_paros import deuda, la_realidad_lo_cerro  # noqa: E402


def paro(cuando="2026-09-05T10:00:00", agencia="roomix:a", comp="x"):
    return {"canonical_agency_id": agencia, "componente_sospechoso": comp,
            "decision": "STOP", "pendiente_de_resolucion": True, "cuando": cuando}


def resultado(status="CERTIFIED_COMPLETE", cuando="2026-09-21T10:00:00",
              agencia="roomix:a"):
    return {"canonical_agency_id": agencia, "status": status, "checked_at": cuando}


def test_MUERDE_certificar_despues_cierra_el_paro():
    """`altos servicios inmobiliarios`: paro el 05, certifico el 21."""
    assert la_realidad_lo_cerro(paro(), resultado()) is True


def test_MUERDE_certificar_ANTES_no_cierra_nada():
    """Romperse despues de haber certificado es exactamente el caso que hay
    que seguir viendo. Sin la comparacion de fechas, esto quedaria cerrado."""
    assert la_realidad_lo_cerro(
        paro(cuando="2026-09-21T10:00:00"),
        resultado(cuando="2026-09-05T10:00:00")) is False


def test_un_needs_fix_posterior_no_cierra():
    assert la_realidad_lo_cerro(paro(), resultado(status="NEEDS_FIX")) is False


def test_los_tres_terminales_buenos_cierran():
    for s in ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
              "NO_INVENTORY_CONFIRMED"):
        assert la_realidad_lo_cerro(paro(), resultado(status=s)) is True


def test_BLOCKED_EXTERNAL_no_cierra():
    """Que la fuente nos rechace no es que el defecto se haya resuelto."""
    assert la_realidad_lo_cerro(paro(), resultado(status="BLOCKED_EXTERNAL")) is False


def test_sin_resultado_no_se_cierra():
    assert la_realidad_lo_cerro(paro(), None) is False


def test_sin_fecha_no_se_puede_decidir_y_queda_abierto():
    assert la_realidad_lo_cerro(paro(cuando=""), resultado()) is False
    assert la_realidad_lo_cerro(paro(), resultado(cuando="")) is False


def escribir(base: Path, nombre: str, filas):
    with (base / nombre).open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")


def test_la_deuda_separa_las_tres_poblaciones(tmp_path: Path):
    escribir(tmp_path, "AGENCY_DEFECT_QUEUE.jsonl", [
        paro(agencia="roomix:cerrada", comp="c1"),
        paro(agencia="roomix:viva_firmada", comp="c2"),
        paro(agencia="roomix:viva_sin_firma", comp="c3"),
    ])
    escribir(tmp_path, "AGENCY_CERTIFICATION_RESULTS.jsonl", [
        resultado(agencia="roomix:cerrada"),
        resultado(agencia="roomix:viva_firmada", status="NEEDS_FIX"),
        resultado(agencia="roomix:viva_sin_firma", status="NEEDS_FIX"),
    ])
    escribir(tmp_path, "AGENCY_DEFECTS_DIFERIDOS.jsonl", [
        {"canonical_agency_id": "roomix:viva_firmada", "componente": "c2"},
    ])
    d = deuda(tmp_path)
    assert d["abiertos_en_el_archivo"] == 3
    assert len(d["cerrados_por_la_realidad"]) == 1
    assert len(d["vivos"]) == 2
    assert len(d["sin_firma"]) == 1
    assert d["sin_firma"][0][0][0] == "roomix:viva_sin_firma"


def test_sin_archivos_no_explota(tmp_path: Path):
    d = deuda(tmp_path)
    assert d["abiertos_en_el_archivo"] == 0
    assert d["vivos"] == [] and d["sin_firma"] == []

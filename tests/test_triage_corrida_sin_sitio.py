# -*- coding: utf-8 -*-
"""Una corrida que no llego al sitio no es un inventario inestable.

`drovetta` (2026-09-25 01:44): la corrida 1 enumero 192 fichas; la 2 recibio
HTTP 500 en el descubrimiento (8,9 s) y no vio ninguna. La regla «una de las
corridas no pudo llegar al sitio → CONTINUE, radio AGENCIA» existia, pero la
rama de propiedades faltantes se evaluaba antes y paraba la familia `tokko`
entera por «inventario inestable». A los minutos el sitio respondia 200.
"""
from __future__ import annotations

from scripts.defect_triage import CONTINUE, RADIO_AGENCIA, STOP, clasificar


def _drovetta(estado2="ERROR_DISCOVERY", detalle2="http 500"):
    return {
        "canonical_agency_id": "roomix:drovetta propiedades",
        "status": "NEEDS_FIX", "connector": "tokko", "connector_strategy": "tokko",
        "reasons": ["one or both runs did not finish with connector state OK",
                    "run inventories differ", "second run is not idempotent",
                    "inventory collapsed by more than 80% against baseline",
                    "zero inventory was not exhaustively proven"],
        "run1": {"estado": "OK", "enumeradas": 192, "total_declarado": 192},
        "run2": {"estado": estado2, "detalle": detalle2, "enumeradas": 0},
        "comparison": {"run1_urls": 192, "run2_urls": 0, "missing_in_run2": 192,
                       "new_in_run2": 0, "same_url_set": False, "idempotent": False},
    }


def test_MUERDE_la_segunda_corrida_sin_sitio_no_para_la_familia():
    v = clasificar(_drovetta())
    assert v["decision"] == CONTINUE
    assert v["radio_estimado"] == RADIO_AGENCIA
    assert v["componente_sospechoso"] == "fuente_inaccesible"


def test_si_la_segunda_corrida_llego_al_sitio_sigue_parando():
    r = _drovetta(estado2="OK", detalle2=None)
    r["run2"]["enumeradas"] = 150
    r["comparison"].update(run2_urls=150, missing_in_run2=42)
    assert clasificar(r)["decision"] == STOP

# -*- coding: utf-8 -*-
"""Una fecha para 6.597 agencias que esperan cosas distintas no es una fecha.

La ETA agregada daba **2027-04-20**. Separada por población, el bulk actual
cierra el **2026-10-11**: siete meses de diferencia, y la culpa no era del
cálculo sino de la mezcla.

De las 6.597 del universo, **4.267 no tienen entrada en el registro de fuentes**.
No esperan caudal de scraping —esperan que alguien les descubra una fuente, que
es otro proceso y hoy no está corriendo—. Dividirlas por `agencias
certificadas/hora` produce una fecha que además se *mueve* cuando mejora un
caudal que no las toca, que es la peor propiedad posible en una estimación.

Donde no hay un proceso midiéndose, la respuesta honesta es `SIN_ETA` con el
motivo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from operacion_reporte import eta_por_poblacion  # noqa: E402

REND = {"certified_throughput_agencias_nuevas_por_hora": 1.3}


def montar(tmp_path: Path, *, con_fuente: int = 2330, universo: int = 6597,
           terminales: int = 194, identidad: int = 140,
           navegador: int = 11, cola: int = 767,
           pendientes_cola: int = 766) -> tuple[Path, Path]:
    cert, datos = tmp_path / "cert", tmp_path / "datos"
    cert.mkdir(); datos.mkdir()

    resultados = []
    for i in range(terminales):
        resultados.append({"canonical_agency_id": f"roomix:t{i}",
                           "status": "CERTIFIED_COMPLETE"})
    for i in range(identidad):
        resultados.append({"canonical_agency_id": f"roomix:i{i}",
                           "status": "IDENTITY_PENDING"})
    (cert / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in resultados), encoding="utf-8")

    registro = []
    for i in range(con_fuente):
        registro.append({"canonical_agency_id": f"roomix:f{i}",
                         "requires_js": i < navegador})
    (datos / "scrape_source_technology_map.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in registro), encoding="utf-8")

    (cert / "AGENCY_CERTIFICATION_PROGRESS.json").write_text(
        json.dumps({"universe": universo, "queue_size": cola,
                    "pending_count": pendientes_cola}), encoding="utf-8")
    return cert, datos


def test_MUERDE_el_universo_completo_no_recibe_una_fecha(tmp_path):
    """La corrección entera en un assert.

    4.267 agencias sin registro de fuente no pueden entrar en una división por
    `agencias/hora`. Si alguna vez esto devuelve `fecha_estimada`, volvimos a
    prometer una fecha que nadie puede cumplir.
    """
    cert, datos = montar(tmp_path)
    salida = eta_por_poblacion(cert, datos, REND)
    universo = salida["ETA_FULL_UNIVERSE"]
    assert universo["estado"] == "SIN_ETA"
    assert "fecha_estimada" not in universo
    assert universo["sin_registro_de_fuente"] == 6597 - 2330


def test_el_bulk_actual_si_recibe_fecha(tmp_path):
    """Es la única población con un proceso corriendo y midiéndose."""
    cert, datos = montar(tmp_path)
    bulk = eta_por_poblacion(cert, datos, REND)["ETA_CURRENT_BULK"]
    assert bulk["pendientes"] == 766
    assert "fecha_estimada" in bulk


def test_el_backlog_de_identidad_no_recibe_fecha(tmp_path):
    """Están frenadas ANTES del scraping.

    Certificar más rápido no las mueve, así que su fecha no depende del caudal
    que se estaría usando para calcularla.
    """
    salida = eta_por_poblacion(*montar(tmp_path), REND)["ETA_IDENTITY_BACKLOG"]
    assert salida["pendientes"] == 140
    assert salida["estado"] == "SIN_ETA"


def test_las_que_piden_navegador_dicen_que_su_ritmo_es_cero_por_decision(tmp_path):
    """La distinción no es cosmética.

    "Sin capacidad" invita a comprar una máquina; "prohibido por el §25 mientras
    el bulk corre" invita a abrir la ventana cuando corresponda.
    """
    salida = eta_por_poblacion(*montar(tmp_path), REND)["ETA_READY_BROWSER"]
    assert salida["pendientes"] == 11
    assert salida["estado"] == "SIN_ETA"
    assert "por decision" in salida["porque"]


def test_sin_caudal_ninguna_poblacion_inventa_una_fecha(tmp_path):
    """Con cero agencias nuevas por hora, cualquier fecha sería inventada."""
    cert, datos = montar(tmp_path)
    salida = eta_por_poblacion(cert, datos,
                               {"certified_throughput_agencias_nuevas_por_hora": 0})
    assert salida["ETA_CURRENT_BULK"]["estado"] == "SIN_ETA"
    assert salida["ETA_READY_STATIC"]["estado"] == "SIN_ETA"


def test_las_poblaciones_no_se_solapan_de_manera_absurda(tmp_path):
    """`READY_STATIC` descuenta lo terminal, lo bloqueado y lo de navegador.

    Sumarlas sin descontar daría más pendientes que agencias registradas, que
    es la clase de número que hace desconfiar de todo el tablero.
    """
    salida = eta_por_poblacion(*montar(tmp_path), REND)
    assert salida["ETA_READY_STATIC"]["pendientes"] == 2330 - 194 - 140 - 11

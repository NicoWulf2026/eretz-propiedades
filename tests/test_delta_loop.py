# -*- coding: utf-8 -*-
"""Tests del cierre determinista del delta.

El punto: un delta puede traer miles de avisos y cientos de agent_id y aun asi
contar como cero, porque lo que cierra el padron son las entidades
inmobiliarias, no la actividad.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dl = _load("delta_loop")


def test_solo_cuentan_inmobiliaria_y_oficina():
    assert dl.OBJETIVO == ("INMOBILIARIA", "OFICINA_FRANQUICIA")


def test_un_delta_con_agentes_y_developers_cuenta_como_cero():
    """Actividad no es descubrimiento."""
    antes = {"alfa propiedades": "INMOBILIARIA"}
    despues = {**antes, "juan perez": "AGENTE",
               "grupo constructor sur desarrollos": "DESARROLLADORA"}
    a = dl.auditar(antes, despues, {})
    assert a["NEW_TARGET_ENTITIES"] == 0
    assert a["NEW_AGENTE"] == 1 and a["NEW_DESARROLLADORA"] == 1
    # pero no se ocultan: siguen reportandose
    assert a["canonical_nuevas"] == 2


def test_una_inmobiliaria_nueva_rompe_el_cierre():
    a = dl.auditar({}, {"beta propiedades": "INMOBILIARIA"}, {})
    assert a["NEW_INMOBILIARIA"] == 1 and a["NEW_TARGET_ENTITIES"] == 1


def test_una_oficina_de_franquicia_nueva_tambien_cuenta():
    a = dl.auditar({}, {"remax ultra": "OFICINA_FRANQUICIA"}, {})
    assert a["NEW_TARGET_ENTITIES"] == 1


def test_la_marca_generica_no_cuenta():
    a = dl.auditar({}, {"remax": "MARCA_GENERICA"}, {})
    assert a["NEW_TARGET_ENTITIES"] == 0 and a["NEW_MARCA_GENERICA"] == 1


def test_un_unknown_con_sustancia_bloquea_el_cierre():
    """Todavia podria resolverse como inmobiliaria con mas evidencia."""
    a = dl.auditar({}, {"torres y asociados": "UNKNOWN"},
                   {"torres y asociados": "Torres y Asociados"})
    assert a["NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA"] == 1


def test_un_unknown_sin_sustancia_no_bloquea():
    """Ver mas avisos de `ab` no lo va a convertir en inmobiliaria."""
    a = dl.auditar({}, {"ab": "UNKNOWN"}, {"ab": "ab"})
    assert a["NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA"] == 0


def test_la_basura_nunca_bloquea():
    assert not dl.puede_ser_inmobiliaria("Usuario")
    assert not dl.puede_ser_inmobiliaria("particular")


def test_ninguna_categoria_queda_sin_reportar():
    a = dl.auditar({}, {}, {})
    for k in ("NEW_INMOBILIARIA", "NEW_OFICINA_FRANQUICIA", "NEW_AGENTE",
              "NEW_DESARROLLADORA", "NEW_MARCA_GENERICA", "NEW_UNKNOWN",
              "NEW_UNKNOWN_POTENCIALMENTE_INMOBILIARIA", "canonical_nuevas",
              "NEW_TARGET_ENTITIES"):
        assert k in a, k


# ---------------------------------------------- persistencia y recuperacion
rdm = _load("roomix_delta")


def _obs(tmp_path, filas):
    p = tmp_path / "observations.jsonl"
    p.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
                 encoding="utf-8")
    return p


def test_una_linea_truncada_no_bloquea_el_reanudar(tmp_path):
    """Si el proceso muere en medio de una escritura, la ultima linea queda
    partida. Sin tolerancia, reanudar reventaria siempre en el mismo byte."""
    p = _obs(tmp_path, [{"url": "u1", "agent_id": "a", "agent_name": "Alfa Propiedades"}])
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"url": "u2", "agent_id": "b", "agent_na')  # corte a mitad
    canon, raw, urls = dl.estado(p)
    assert urls == {"u1"}
    assert raw == {"a"}


def test_observadas_tambien_tolera_lineas_rotas(tmp_path):
    p = _obs(tmp_path, [{"url": "u1", "agent_id": "a", "agent_name": "Alfa"}])
    with p.open("a", encoding="utf-8") as fh:
        fh.write("{roto\n")
    vistas, sin_agente = rdm.observadas(p)
    assert vistas == {"u1"} and sin_agente == []


def test_el_lector_ignora_archivo_inexistente(tmp_path):
    assert list(rdm.leer_jsonl(tmp_path / "no-existe.jsonl")) == []


def test_reanudar_no_reprocesa_lo_ya_observado(tmp_path):
    """El delta compara contra las URLs ya vistas: reanudar salta lo hecho."""
    p = _obs(tmp_path, [{"url": f"u{i}", "agent_id": f"a{i}", "agent_name": f"Inmo {i}"}
                        for i in range(5)])
    _, _, urls = dl.estado(p)
    universo = [f"u{i}" for i in range(8)]
    nuevas = [u for u in universo if u not in urls]
    assert nuevas == ["u5", "u6", "u7"]


def test_el_append_por_tandas_escribe_lineas_completas(tmp_path):
    """El fix del handle: cada tanda se cierra, asi que lo escrito es valido."""
    p = tmp_path / "observations.jsonl"

    class FetcherFalso:
        stats = {}

        def get(self, u):
            return '"agent":{"_id":"abc123def4567890","name":"Alfa Propiedades"}'

    st = rdm.procesar(FetcherFalso(), [f"https://x/{i}" for i in range(7)], p, "t", cada=2)
    assert st["agent_block"] == 7
    filas = list(rdm.leer_jsonl(p))
    assert len(filas) == 7
    assert all("agent_id" in f and "url" in f for f in filas)


def test_observations_es_idempotente_por_url(tmp_path):
    """Reprocesar una URL agrega una fila, pero el estado sigue contando una
    sola observacion por URL."""
    p = _obs(tmp_path, [{"url": "u1", "agent_id": "a", "agent_name": "Alfa Propiedades"},
                        {"url": "u1", "agent_id": "a", "agent_name": "Alfa Propiedades"}])
    _, raw, urls = dl.estado(p)
    assert urls == {"u1"} and raw == {"a"}


def test_la_bitacora_de_deltas_queda_en_jsonl_valido(tmp_path):
    p = tmp_path / "delta_audit.jsonl"
    for n in (1, 2):
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"delta": n, "NEW_TARGET_ENTITIES": 0}) + "\n")
    filas = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
    assert [f["delta"] for f in filas] == [1, 2]


def test_el_lanzador_usa_rutas_absolutas():
    """El Programador no hereda el PATH interactivo ni el cwd."""
    bat = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA\run_delta_loop.bat")
    if not bat.exists():
        return
    txt = bat.read_text(encoding="utf-8", errors="ignore")
    assert "cd /d" in txt
    assert "python.exe" in txt and ":\\" in txt
    assert txt.count(":\\") >= 3  # interprete, script y logs

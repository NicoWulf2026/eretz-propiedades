# -*- coding: utf-8 -*-
"""NEXT-001: el último append no es necesariamente el resultado más nuevo.

Codex lo dejó descrito y confirmado por implementación, y sin resolver:

- `agency_certifier.py :: read_jsonl` saltea el `ValueError` de una línea
  inválida **en silencio**;
- `run_agency_certification_queue.py :: latest_results` y
  `backfill_strategy_fingerprints.py :: latest_results` toman el **último
  append por agencia, sin ordenar ni comparar `checked_at`**.

Con dos workers escribiendo el mismo archivo, el orden de append no es el orden
temporal. Y una línea truncada por un `Stop-Process -Force` —que ya pasó en
este proyecto— desaparece sin dejar rastro, dejando elegido un cierre viejo.

**Medido antes de escribir una línea de esto**, sobre el ledger real de 2.501
filas: 0 JSON inválido, 0 filas sin `canonical_agency_id`, 0 agencias donde el
último append no es el `checked_at` más nuevo, 0 grupos agencia+`checked_at`
con más de un `status`. Los 35 grupos duplicados que Codex no había
caracterizado difieren **sólo** en huella, esquema y métricas: son
reescrituras del backfill, no evidencia en conflicto.

O sea: **el riesgo es real en el código y todavía no ocurrió en los datos.**
Esto es endurecimiento, no reparación, y por eso no bloqueaba relanzar la cola.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from ledger_de_certificacion import (Ambiguo, LineaInvalida,  # noqa: E402
                                     leer_ledger, resultado_vigente,
                                     vigentes_por_agencia)


def fila(agencia="roomix:a", cuando="2026-09-20T10:00:00", estado="NEEDS_FIX",
         **extra) -> dict:
    return {"canonical_agency_id": agencia, "checked_at": cuando,
            "status": estado, **extra}


# --------------------------------------------------------------------------
# Seleccion temporal
# --------------------------------------------------------------------------

def test_MUERDE_el_append_fuera_de_orden_no_gana():
    """El corazón de NEXT-001.

    Dos workers escriben el mismo archivo. El que terminó después puede haber
    empezado antes, y su `checked_at` ser más viejo. Tomar el último append
    elige el resultado equivocado.
    """
    filas = [fila(cuando="2026-09-20T12:00:00", estado="CERTIFIED_COMPLETE"),
             fila(cuando="2026-09-20T09:00:00", estado="NEEDS_FIX")]
    elegido = resultado_vigente(filas)
    assert elegido["checked_at"] == "2026-09-20T12:00:00"
    assert elegido["status"] == "CERTIFIED_COMPLETE"


def test_en_orden_normal_gana_el_ultimo():
    filas = [fila(cuando="2026-09-20T09:00:00", estado="NEEDS_FIX"),
             fila(cuando="2026-09-20T12:00:00", estado="CERTIFIED_COMPLETE")]
    assert resultado_vigente(filas)["status"] == "CERTIFIED_COMPLETE"


def test_una_fila_sin_fecha_no_puede_ganarle_a_una_fechada():
    """Sin fecha no hay forma de saber si es más nueva. No se adivina."""
    filas = [fila(cuando="2026-09-20T09:00:00", estado="CERTIFIED_COMPLETE"),
             fila(cuando=None, estado="NEEDS_FIX")]
    assert resultado_vigente(filas)["status"] == "CERTIFIED_COMPLETE"


def test_una_fecha_invalida_se_trata_como_ausente():
    filas = [fila(cuando="2026-09-20T09:00:00", estado="CERTIFIED_COMPLETE"),
             fila(cuando="ayer a la tarde", estado="NEEDS_FIX")]
    assert resultado_vigente(filas)["status"] == "CERTIFIED_COMPLETE"


def test_offsets_equivalentes_son_el_mismo_instante():
    """`10:00-03:00` y `13:00Z` son el mismo momento.

    Compararlos como texto los ordena mal y produce una ambigüedad que no
    existe.
    """
    filas = [fila(cuando="2026-09-20T13:00:00+00:00", estado="A"),
             fila(cuando="2026-09-20T10:00:00-03:00", estado="A")]
    assert resultado_vigente(filas)["status"] == "A"


# --------------------------------------------------------------------------
# Ambiguedad: no elegir a dedo
# --------------------------------------------------------------------------

def test_MUERDE_dos_resultados_distintos_en_el_mismo_instante_son_ambiguos():
    """No se elige arbitrariamente un COMPLETE entre dos evidencias distintas.

    Es la instrucción textual de Codex, y es la parte que separa un arreglo de
    un encubrimiento: ante evidencia contradictoria, la respuesta correcta es
    decirlo, no quedarse con la que más gusta.
    """
    filas = [fila(cuando="2026-09-20T10:00:00", estado="CERTIFIED_COMPLETE"),
             fila(cuando="2026-09-20T10:00:00", estado="NEEDS_FIX")]
    with pytest.raises(Ambiguo) as excepcion:
        resultado_vigente(filas)
    assert "CERTIFIED_COMPLETE" in str(excepcion.value)
    assert "NEEDS_FIX" in str(excepcion.value)


def test_el_mismo_instante_con_el_mismo_veredicto_NO_es_ambiguo():
    """Los 35 grupos reales del ledger: refresh de métricas, no conflicto.

    Difieren en `strategy_fingerprint`, `fingerprint_schema_version` y
    `operational_metrics`, y coinciden en `status` y en lo enumerado. Tratarlos
    como ambiguos pararía la cola por 35 casos benignos, que es el modo de
    falla caro de una regla demasiado estricta.
    """
    filas = [fila(cuando="2026-09-20T10:00:00", estado="CERTIFIED_COMPLETE",
                  strategy_fingerprint="vieja", fingerprint_schema_version=3),
             fila(cuando="2026-09-20T10:00:00", estado="CERTIFIED_COMPLETE",
                  strategy_fingerprint="nueva", fingerprint_schema_version=5)]
    elegido = resultado_vigente(filas)
    # Gana el ultimo append, que es la reescritura mas reciente.
    assert elegido["strategy_fingerprint"] == "nueva"


def test_el_mismo_instante_con_distinto_enumerado_tambien_es_ambiguo():
    """Dos corridas que vieron inventarios distintos no son un refresh."""
    filas = [fila(cuando="2026-09-20T10:00:00", estado="CERTIFIED_COMPLETE",
                  enumeration_audit={"enumerated": 30}),
             fila(cuando="2026-09-20T10:00:00", estado="CERTIFIED_COMPLETE",
                  enumeration_audit={"enumerated": 12})]
    with pytest.raises(Ambiguo):
        resultado_vigente(filas)


# --------------------------------------------------------------------------
# Corrupcion: fallar cerrado
# --------------------------------------------------------------------------

def test_MUERDE_una_linea_invalida_no_se_saltea_en_silencio(tmp_path):
    """El modo de falla que `read_jsonl` tiene hoy.

    Una línea truncada por un `Stop-Process -Force` —que ya ocurrió en este
    proyecto— desaparece, y el cierre viejo queda elegido como si nada hubiera
    pasado. Un resultado que no se pudo leer no es un resultado que no existe.
    """
    ruta = tmp_path / "ledger.jsonl"
    ruta.write_text(json.dumps(fila()) + "\n" + '{"canonical_agency_id": "rot',
                    encoding="utf-8")
    with pytest.raises(LineaInvalida) as excepcion:
        leer_ledger(ruta)
    assert "2" in str(excepcion.value)  # dice QUE linea


def test_se_puede_leer_tolerando_y_enterandose(tmp_path):
    """Tolerar está permitido; tolerar **en silencio**, no.

    Algunos lectores generales necesitan seguir con lo que haya. Lo que no
    puede pasar es que nadie se entere: el conteo de inválidas vuelve siempre.
    """
    ruta = tmp_path / "ledger.jsonl"
    ruta.write_text(json.dumps(fila()) + "\n" + "{roto\n", encoding="utf-8")
    filas, invalidas = leer_ledger(ruta, estricto=False)
    assert len(filas) == 1
    assert invalidas == [2]


def test_una_fila_que_no_es_objeto_tambien_es_invalida(tmp_path):
    """`read_jsonl` acepta cualquier JSON: un `5` suelto entra como fila.

    Después `row["canonical_agency_id"]` revienta con un TypeError a mil líneas
    de distancia del archivo que lo causó.
    """
    ruta = tmp_path / "ledger.jsonl"
    ruta.write_text("5\n[1,2]\n" + json.dumps(fila()) + "\n", encoding="utf-8")
    filas, invalidas = leer_ledger(ruta, estricto=False)
    assert len(filas) == 1 and invalidas == [1, 2]


def test_una_fila_sin_agencia_es_invalida(tmp_path):
    ruta = tmp_path / "ledger.jsonl"
    ruta.write_text(json.dumps({"checked_at": "2026-09-20T10:00:00"}) + "\n",
                    encoding="utf-8")
    _, invalidas = leer_ledger(ruta, estricto=False)
    assert invalidas == [1]


def test_un_archivo_que_no_existe_no_es_corrupcion(tmp_path):
    filas, invalidas = leer_ledger(tmp_path / "no-esta.jsonl", estricto=False)
    assert filas == [] and invalidas == []


# --------------------------------------------------------------------------
# La vista por agencia, que es lo que consumen la cola y el backfill
# --------------------------------------------------------------------------

def test_vigentes_por_agencia_separa_bien(tmp_path):
    ruta = tmp_path / "ledger.jsonl"
    lineas = [fila("roomix:a", "2026-09-20T09:00:00", "NEEDS_FIX"),
              fila("roomix:b", "2026-09-20T09:30:00", "CERTIFIED_COMPLETE"),
              fila("roomix:a", "2026-09-20T11:00:00", "CERTIFIED_COMPLETE")]
    ruta.write_text("".join(json.dumps(x) + "\n" for x in lineas),
                    encoding="utf-8")
    vigentes, problemas = vigentes_por_agencia(ruta)
    assert vigentes["roomix:a"]["status"] == "CERTIFIED_COMPLETE"
    assert vigentes["roomix:b"]["status"] == "CERTIFIED_COMPLETE"
    assert problemas == {}


def test_una_agencia_ambigua_no_contamina_a_las_demas(tmp_path):
    """Una agencia con evidencia contradictoria se reporta y se excluye.

    No se elige por ella, y tampoco se tira el resto del padrón: el §11 pide
    conservar lo que sí se puede afirmar.
    """
    ruta = tmp_path / "ledger.jsonl"
    lineas = [fila("roomix:a", "2026-09-20T10:00:00", "CERTIFIED_COMPLETE"),
              fila("roomix:a", "2026-09-20T10:00:00", "NEEDS_FIX"),
              fila("roomix:b", "2026-09-20T09:30:00", "CERTIFIED_COMPLETE")]
    ruta.write_text("".join(json.dumps(x) + "\n" for x in lineas),
                    encoding="utf-8")
    vigentes, problemas = vigentes_por_agencia(ruta)
    assert "roomix:a" not in vigentes
    assert "roomix:a" in problemas
    assert vigentes["roomix:b"]["status"] == "CERTIFIED_COMPLETE"


def test_el_ledger_real_de_hoy_no_tiene_ninguno_de_estos_problemas():
    """La medición que ordenó la prioridad, fijada como test.

    Si algún día este test se pone en rojo, el riesgo dejó de ser teórico y
    NEXT-001 pasa de endurecimiento a reparación urgente.
    """
    ruta = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
                r"\AGENCY_CERTIFICATION_RESULTS.jsonl")
    if not ruta.exists():
        pytest.skip("el ledger real no esta en esta maquina")
    _, invalidas = leer_ledger(ruta, estricto=False)
    vigentes, problemas = vigentes_por_agencia(ruta)
    assert invalidas == [], f"lineas invalidas: {invalidas[:5]}"
    assert problemas == {}, f"agencias ambiguas: {list(problemas)[:5]}"
    assert len(vigentes) > 300

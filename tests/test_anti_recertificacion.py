# -*- coding: utf-8 -*-
"""Una agencia ya diagnosticada no se vuelve a certificar, pero no para siempre.

Medido con replay sobre 24 h de historial real: 350 certificaciones, 19 de
trabajo nuevo y 331 repeticiones. La política evita 229 de esas repeticiones
sobre 48 agencias, y baja el día de 41,6 h de worker a 22,8.

Lo que estos tests cuidan es el otro lado: que no se convierta en un permiso
eterno. `baron inmobiliaria` pasó de enumerar 0 a 182 sin que tocáramos una
línea; una fuente cambia sola, y un diagnóstico viejo no puede tapar eso.

Dos de los casos de abajo son defectos que este archivo no atrapaba y que el
replay encontró antes de activar nada: `diferidos()` no copiaba la fecha -así
que en producción ninguna diferida habría valido, aunque los tests pasaran- y
el TTL se medía contra la firma en vez de contra la última mirada -así que una
diferida vieja mandaba a recertificar en cada pasada, para siempre-.
"""
import json
import time

import pytest

from scripts.run_agency_certification_queue import (TTL_CRITICO_HORAS,
                                                    TTL_DIFERIDA_HORAS,
                                                    diferida_vigente,
                                                    diferidos,
                                                    is_current_result)
from scripts.agency_fingerprints import FINGERPRINT_SCHEMA_VERSION

HUELLA = "8c6a84314619"


def cuando(horas_atras: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - horas_atras * 3600))


def diferida(componente="extraccion_transversal_de_atributos",
             radio="FAMILIA", horas=1.0):
    return [{"componente": componente, "radio": radio,
             "diagnostico": "verificado contra la fuente", "cuando": cuando(horas)}]


def resultado(status="NEEDS_FIX", huella=HUELLA, connector="generico",
              strategy="generic/html_catalog"):
    return {"status": status, "connector": connector,
            'fingerprint_schema_version': FINGERPRINT_SCHEMA_VERSION,
            "connector_strategy": strategy, "strategy_fingerprint": huella,
            "certifier_version": "agency_certifier_v1"}


@pytest.fixture
def huella_fija(monkeypatch):
    """La huella del codigo actual, fijada para que el test no dependa de ella."""
    monkeypatch.setattr(
        "scripts.run_agency_certification_queue.strategy_fingerprint",
        lambda c, s: HUELLA)
    monkeypatch.setattr('scripts.agency_fingerprints.strategy_fingerprint', lambda c, s: HUELLA)


# --- A: el caso que motiva todo -----------------------------------------

def test_A_diagnosticada_con_misma_huella_y_ttl_vigente_no_se_repite(huella_fija):
    """Las 53 agencias que costaban 10,4 h por arranque."""
    assert is_current_result(resultado(), {}, diferida()) is True


# --- B: si el codigo cambio, hay que rehacerla --------------------------

def test_B_huella_distinta_se_recertifica(huella_fija):
    """El diagnostico valia para OTRO codigo. Certifica de nuevo."""
    assert is_current_result(resultado(huella="otra"), {}, diferida()) is False


# --- C: sin firma, comportamiento de siempre ----------------------------

def test_C_sin_diferida_se_recertifica(huella_fija):
    assert is_current_result(resultado(), {}, None) is False


def test_C_bis_diferida_sin_firma_no_alcanza(huella_fija):
    """Una diferida sin componente no dice QUE defecto se miro."""
    floja = [{"diagnostico": "algo", "cuando": cuando(1)}]
    assert is_current_result(resultado(), {}, floja) is False


# --- D: el TTL vence ----------------------------------------------------

def test_D_diferida_vencida_se_recertifica(huella_fija):
    vieja = diferida(horas=TTL_DIFERIDA_HORAS + 1)
    assert is_current_result(resultado(), {}, vieja) is False


def test_D_bis_diferida_sin_fecha_no_vale(huella_fija):
    """Sin fecha no se puede saber si vencio, y entonces no vale.

    Una diferida sin `cuando` valdria para siempre, que es exactamente lo que
    el TTL viene a impedir.
    """
    sin_fecha = [{"componente": "extraccion_transversal_de_atributos",
                  "radio": "FAMILIA", "diagnostico": "x"}]
    assert is_current_result(resultado(), {}, sin_fecha) is False


# --- E y F: las criticas duran menos ------------------------------------

def test_E_firma_critica_dentro_de_su_ttl_no_se_repite(huella_fija):
    critica = diferida("inventario_inestable_entre_corridas",
                       horas=TTL_CRITICO_HORAS - 2)
    assert is_current_result(resultado(), {}, critica) is True


def test_F_firma_critica_vencida_se_recertifica(huella_fija):
    """24 h, no 72: si el diagnostico envejece mal, se publica algo falso."""
    critica = diferida("inventario_inestable_entre_corridas",
                       horas=TTL_CRITICO_HORAS + 1)
    assert is_current_result(resultado(), {}, critica) is False


def test_F_bis_una_critica_vence_antes_que_una_normal(huella_fija):
    """A las 48 h: la normal sigue vigente, la critica no."""
    horas = 48
    normal = diferida("extraccion_transversal_de_atributos", horas=horas)
    critica = diferida("posible_perdida_de_inventario", horas=horas)
    assert is_current_result(resultado(), {}, normal) is True
    assert is_current_result(resultado(), {}, critica) is False


# --- G: lo terminal no se toca ------------------------------------------

def test_G_una_terminal_sigue_comportandose_como_antes(huella_fija):
    assert is_current_result(resultado(status="CERTIFIED_COMPLETE"), {}) is True


def test_G_bis_identity_pending_sigue_por_version_del_certificador():
    r = {"status": "IDENTITY_PENDING", "certifier_version": "agency_certifier_v1"}
    assert is_current_result(r, {}) is True


# --- H: un crash se recupera --------------------------------------------

def test_H_un_runner_error_se_vuelve_a_intentar(huella_fija):
    """RUNNER_ERROR no es terminal ni diagnosticable: hay que reintentar."""
    roto = resultado(status="RUNNER_ERROR")
    assert is_current_result(roto, {}, diferida()) is False


def test_H_bis_un_resultado_sin_huella_no_se_salta(huella_fija):
    """Sin huella no se puede comprobar que el codigo sea el mismo."""
    sin_huella = resultado(huella=None)
    assert is_current_result(sin_huella, {}, diferida()) is False


# --- el ayudante, por separado ------------------------------------------

def test_varias_firmas_alcanza_con_que_una_este_vigente():
    """Una agencia puede tener varias diferidas; basta una sin vencer."""
    mezcla = (diferida("extraccion_transversal_de_atributos", horas=200)
              + diferida("imagenes_compartidas", horas=1))
    assert diferida_vigente({}, mezcla) is True


def test_todas_vencidas_no_vale_ninguna():
    mezcla = (diferida("extraccion_transversal_de_atributos", horas=200)
              + diferida("imagenes_compartidas", horas=300))
    assert diferida_vigente({}, mezcla) is False


# --- I: el TTL cuenta desde la ultima mirada, no desde la firma ---------

def test_I_diferida_vieja_pero_mirada_hace_poco_sigue_vigente(huella_fija):
    """El caso que costaba 14,6 h por dia.

    Una diferida de hace 200 h con una corrida de hace 2 h: ya miramos, y lo
    que vimos fue lo mismo. Volver a mirar ahora no agrega nada.
    """
    previa = resultado() | {"checked_at": cuando(2)}
    assert is_current_result(previa, {}, diferida(horas=200)) is True


def test_I_bis_si_hace_mucho_que_no_miramos_se_recertifica(huella_fija):
    """La diferida no caduca sola, pero la mirada si."""
    previa = resultado() | {"checked_at": cuando(TTL_DIFERIDA_HORAS + 1)}
    assert is_current_result(previa, {}, diferida(horas=200)) is False


def test_I_ter_la_critica_se_mira_tres_veces_mas_seguido(huella_fija):
    """A las 48 h de la ultima mirada: la normal aguanta, la critica no."""
    previa = resultado() | {"checked_at": cuando(48)}
    normal = diferida("extraccion_transversal_de_atributos", horas=200)
    critica = diferida("posible_perdida_de_inventario", horas=200)
    assert is_current_result(previa, {}, normal) is True
    assert is_current_result(previa, {}, critica) is False


def test_I_quater_una_fecha_futura_no_renueva_el_ttl(huella_fija):
    """Un reloj adelantado no puede regalar vigencia indefinida."""
    previa = resultado() | {"checked_at": cuando(-500)}
    assert is_current_result(previa, {}, diferida(horas=200)) is False


def test_I_quinquies_sin_checked_at_se_cae_a_la_fecha_de_la_firma(huella_fija):
    """Los resultados viejos no traen `checked_at`, y valen como antes."""
    assert is_current_result(resultado(), {}, diferida(horas=1)) is True
    assert is_current_result(resultado(), {}, diferida(horas=200)) is False


# --- J: la fecha tiene que llegar hasta aca ------------------------------

def test_J_diferidos_conserva_la_fecha(tmp_path):
    """Sin esto, el TTL no puede vencer nunca ni valer nunca.

    El defecto estaba: `diferidos()` proyectaba diagnostico, componente y
    radio, y descartaba `cuando`. Entonces toda diferida llegaba sin fecha,
    `diferida_vigente` la rechazaba, y el cambio no ahorraba una sola hora
    aunque los quince tests de arriba pasaran.
    """
    linea = json.dumps({"canonical_agency_id": "roomix:alguna",
                        "diagnostico": "verificado contra la fuente",
                        "componente": "imagenes_compartidas",
                        "radio": "FAMILIA",
                        "cuando": "2026-09-14T10:00:00"}, ensure_ascii=False)
    (tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        linea + chr(10), encoding="utf-8")
    fuera = diferidos(tmp_path)["roomix:alguna"][0]
    assert fuera["cuando"] == "2026-09-14T10:00:00"
    assert fuera["componente"] == "imagenes_compartidas"


def test_J_bis_una_diferida_sin_fecha_en_disco_llega_vacia(tmp_path):
    """Las diferidas escritas antes del TTL no traen fecha, y no deben valer."""
    linea = json.dumps({"canonical_agency_id": "roomix:otra",
                        "diagnostico": "x", "componente": "c", "radio": "FAMILIA"},
                       ensure_ascii=False)
    (tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        linea + chr(10), encoding="utf-8")
    fuera = diferidos(tmp_path)["roomix:otra"]
    assert fuera[0]["cuando"] == ""
    assert diferida_vigente({}, fuera) is False

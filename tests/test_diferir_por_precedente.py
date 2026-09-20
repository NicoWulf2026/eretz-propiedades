# -*- coding: utf-8 -*-
"""Automatizar un diagnóstico ajeno sólo cuando es EL MISMO, no uno parecido.

La cola se detiene ante un defecto transversal y no arranca hasta que alguien
escribe una diferida firmada. Eso es correcto y cuesta una persona por paro: el
2026-09-20 paró cuatro veces en cinco horas.

Pero medido sobre las 93 agencias en `NEEDS_FIX`, **76 ya tienen diferida** y de
las 17 que no, **13 tienen una firma ya vista** en otra agencia diferida. Tres
de cada cuatro paros pendientes son el mismo problema que alguien ya miró
contra la fuente.

Lo peligroso de automatizar esto es obvio, así que los límites son el
contenido de este archivo: una firma parecida no alcanza, una diferida
automática no justifica otra, `variante_no_soportada` nunca, y nada se difiere
si el defecto ya está resuelto.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import diferir_por_precedente as modulo  # noqa: E402


def montar(tmp_path: Path, defectos: list[dict], diferidas: list[dict],
           resultados: list[dict], monkeypatch) -> None:
    (tmp_path / "AGENCY_DEFECT_QUEUE.jsonl").write_text(
        "".join(json.dumps(d) + "\n" for d in defectos), encoding="utf-8")
    (tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        "".join(json.dumps(d) + "\n" for d in diferidas), encoding="utf-8")
    (tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in resultados), encoding="utf-8")
    monkeypatch.setattr(modulo, "CERT", tmp_path)
    monkeypatch.setattr(modulo, "DIFERIDAS",
                        tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl")
    monkeypatch.setattr(modulo, "COLA_DE_DEFECTOS",
                        tmp_path / "AGENCY_DEFECT_QUEUE.jsonl")


def defecto(agencia, componente="perdida_de_inventario", radio="FAMILIA",
            firma="abc123"):
    return {"canonical_agency_id": agencia,
            "componente_sospechoso": componente, "radio_estimado": radio,
            "firma_del_patron": firma}


def diferida(agencia, componente="perdida_de_inventario", radio="FAMILIA",
             automatica=False):
    fila = {"canonical_agency_id": agencia, "componente": componente,
            "radio": radio, "diagnostico": "mirado contra la fuente",
            "cuando": "2026-09-19T10:00:00"}
    if automatica:
        fila["diferida_por_precedente"] = True
    return fila


def resultado(agencia, status="NEEDS_FIX"):
    return {"canonical_agency_id": agencia, "status": status,
            "checked_at": "2026-09-20T10:00:00"}


def test_MUERDE_una_firma_identica_con_precedente_humano_se_difiere(tmp_path, monkeypatch):
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    candidatas = modulo.candidatas()
    assert [c["agencia"] for c in candidatas] == ["roomix:b"]
    assert candidatas[0]["precedente"]["agencia"] == "roomix:a"


def test_MUERDE_una_firma_PARECIDA_no_alcanza(tmp_path, monkeypatch):
    """El límite más importante de todos.

    Mismo componente y mismo radio, otra firma. La firma incluye conector,
    estrategia, huella de código y razones: si difiere, el defecto puede ser
    otro y heredarle el diagnóstico sería inventar.
    """
    montar(tmp_path,
           [defecto("roomix:a", firma="abc123"),
            defecto("roomix:b", firma="abc124")],
           [diferida("roomix:a")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    assert modulo.candidatas() == []


def test_MUERDE_una_diferida_automatica_no_justifica_otra(tmp_path, monkeypatch):
    """Dos saltos desde un diagnóstico humano ya no son ese diagnóstico.

    Encadenarlos convierte una decisión en una cadena de suposiciones, y al
    final nadie miró nada.
    """
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a", automatica=True)],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    assert modulo.candidatas() == []


def test_MUERDE_variante_no_soportada_nunca_se_difiere(tmp_path, monkeypatch):
    """Su firma agrupa causas que no tienen nada que ver.

    Medido: una sola firma junta una SPA de React, jQuery contra la API de
    SOM, un 200 con cuerpo vacío, una url desconocida y un `/buscador`.
    """
    montar(tmp_path,
           [defecto("roomix:a", componente="variante_no_soportada"),
            defecto("roomix:b", componente="variante_no_soportada")],
           [diferida("roomix:a", componente="variante_no_soportada")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    assert modulo.candidatas() == []


def test_MUERDE_un_defecto_YA_RESUELTO_no_se_difiere(tmp_path, monkeypatch):
    """La cola de defectos es un registro de eventos, no de problemas abiertos.

    Sin este filtro la herramienta escribía diferidas para defectos resueltos:
    de las seis primeras candidatas reales, cuatro estaban en
    `CERTIFIED_COMPLETE` —`abriola` con 263 propiedades, recertificada esa
    misma mañana—.

    Cuarta vez que este proyecto confunde un rastro con un estado.
    """
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a")],
           [resultado("roomix:a"),
            resultado("roomix:b", status="CERTIFIED_COMPLETE")], monkeypatch)
    assert modulo.candidatas() == []


def test_no_se_difiere_dos_veces_la_misma_agencia(tmp_path, monkeypatch):
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a"), diferida("roomix:b")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    assert modulo.candidatas() == []


def test_el_radio_del_precedente_tiene_que_ser_el_mismo(tmp_path, monkeypatch):
    """No se extrapola de un radio chico a uno grande.

    Un defecto que alguien miró como AGENCIA no autoriza a saltear un paro de
    radio FAMILIA, que es una afirmación mucho más fuerte.
    """
    montar(tmp_path,
           [defecto("roomix:a", radio="AGENCIA"),
            defecto("roomix:b", radio="FAMILIA")],
           [diferida("roomix:a", radio="AGENCIA")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    assert modulo.candidatas() == []


def test_el_diagnostico_heredado_conserva_la_procedencia(tmp_path, monkeypatch):
    """Quién y cuándo lo diagnosticó tiene que quedar escrito.

    Una diferida que no dice de dónde salió es indistinguible de una que
    alguien escribió mirando, y esa diferencia es todo.
    """
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    texto = modulo.texto(modulo.candidatas()[0])
    assert "POR PRECEDENTE" in texto
    assert "roomix:a" in texto
    assert "2026-09-19T10:00:00" in texto
    assert "no afirma que la agencia este bien" in texto.lower()


def test_no_convierte_un_defecto_en_un_exito(tmp_path, monkeypatch):
    """Una diferida dice «esto ya se miró», no «esto está bien».

    El estado de certificación no lo toca nadie acá, y el texto lo dice.
    """
    montar(tmp_path,
           [defecto("roomix:a"), defecto("roomix:b")],
           [diferida("roomix:a")],
           [resultado("roomix:a"), resultado("roomix:b")], monkeypatch)
    texto = modulo.texto(modulo.candidatas()[0])
    assert "sigue en needs_fix" in texto.lower()
    assert "CERTIFIED" not in texto

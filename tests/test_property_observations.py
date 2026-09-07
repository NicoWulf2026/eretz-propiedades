"""El registro de qué se vio y cuándo: sin esto el ciclo de vida no existe."""
from __future__ import annotations

import json

from scripts.property_observations import (ARCHIVO, leer, observacion,
                                           registrar, transiciones)


def _paquete(tmp_path, hashes_run1, hashes_run2=None):
    (tmp_path / "properties_run1.jsonl").write_text(
        "".join(json.dumps({"hash_dedup": h}) + "\n" for h in hashes_run1),
        encoding="utf-8")
    (tmp_path / "properties_run2.jsonl").write_text(
        "".join(json.dumps({"hash_dedup": h}) + "\n"
                for h in (hashes_run2 if hashes_run2 is not None else hashes_run1)),
        encoding="utf-8")
    return tmp_path


def _resultado(estado="OK", cuando="2026-09-07T10:00:00"):
    return {"canonical_agency_id": "roomix:alfa", "checked_at": cuando,
            "run1": {"estado": estado}, "run2": {"estado": estado}}


def test_una_enumeracion_no_confiable_no_produce_ausencias(tmp_path):
    """Si la corrida no terminó OK, lo que no se vio no estuvo ausente: no se
    lo buscó. Contarlo sería fabricar bajas a partir de nuestros fallos."""
    paquete = _paquete(tmp_path, ["a", "b"])
    assert observacion(paquete, _resultado("ERROR_DISCOVERY")) is None
    assert observacion(paquete, _resultado("VARIANTE_NO_SOPORTADA")) is None
    assert observacion(paquete, _resultado("OK")) is not None


def test_se_usa_la_union_de_las_dos_corridas(tmp_path):
    """Una propiedad que apareció en una corrida y no en la otra ESTUVO.
    Exigir las dos convertiría una lectura intermitente en una baja."""
    paquete = _paquete(tmp_path, ["a", "b"], ["a", "c"])
    o = observacion(paquete, _resultado())
    assert o["vistas"] == 3
    assert o["hashes"] == ["a", "b", "c"]


def test_el_registro_es_append_only(tmp_path):
    """Cada pasada borraba la evidencia de la anterior: por eso el ciclo de
    vida no se podía activar nunca, por muchas pasadas que se hicieran."""
    paquete = _paquete(tmp_path / "p", ["a"]) if (tmp_path / "p").mkdir() is None else None
    salida = tmp_path / "out"
    assert registrar(paquete, _resultado(cuando="2026-09-01T10:00:00"), salida)
    _paquete(paquete, ["a", "b"])
    assert registrar(paquete, _resultado(cuando="2026-09-02T10:00:00"), salida)

    filas = leer(salida / ARCHIVO)["roomix:alfa"]
    assert len(filas) == 2
    assert [f["vistas"] for f in filas] == [1, 2]


def test_volver_importa_mas_que_desaparecer():
    """Si las que desaparecen reaparecen seguido, el umbral para dar una por
    inactiva tiene que ser más alto —y ese número no se puede elegir sin
    medirlo."""
    m = transiciones([{"hashes": ["a", "b", "c"]},
                      {"hashes": ["a", "b"]},
                      {"hashes": ["a", "b", "c"]}])
    assert m["desapariciones"] == 1
    assert m["reapariciones"] == 1
    assert m["tasa_de_reaparicion"] == 1.0


def test_con_una_sola_observacion_no_se_puede_medir_nada():
    """Y decirlo es parte del resultado: un cero aquí se leería como "nada
    desaparece"."""
    m = transiciones([{"hashes": ["a"]}])
    assert m["suficiente_para_medir"] is False
    assert "desapariciones" not in m


def test_una_ausencia_puntual_no_es_una_baja():
    """La regla que ordena el ciclo de vida, medida: la propiedad que faltó una
    vez y volvió no acumula ausencias."""
    m = transiciones([{"hashes": ["a"]}, {"hashes": []}, {"hashes": ["a"]}])
    assert m["ausentes_al_final"] == 0
    assert m["ausencia_consecutiva_maxima"] == 0

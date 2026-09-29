"""La cobertura geografica sale de la fila servida, sin perder lo demostrado por un vacio."""
from __future__ import annotations

from scripts import api_snapshot as S


def _fila(**campos):
    return dict({"hash_dedup": "h", "connector": "generico", "canonical_agency_id": "roomix:x",
                 "ciudad": None, "barrio": None, "provincia": "Santa Fe",
                 "latitud": None, "longitud": None}, **campos)


def test_sin_cambio_de_geografia_se_usa_la_cobertura_del_artefacto(monkeypatch):
    llamadas = []
    monkeypatch.setattr(S, "cobertura_de_fila", lambda *a, **k: llamadas.append(a) or {})
    vieja = {"localidad_canonica": "Rosario"}
    fila = _fila(ciudad="Rosario")
    assert S._cobertura_de_la_fila_servida(vieja, fila, dict(fila, titulo="otro"), "h", {}, {}) == (vieja, None)
    assert llamadas == []


def test_la_lectura_fresca_con_otra_localidad_manda(monkeypatch):
    monkeypatch.setattr(S, "cobertura_de_fila",
                        lambda *a, **k: {"localidad_canonica": "Funes", "estado_geografico": None})
    cobertura, motivo = S._cobertura_de_la_fila_servida(
        {"localidad_canonica": "Rosario"}, _fila(ciudad="Rosario"), _fila(barrio="Funes"), "h", {}, {})
    assert cobertura["localidad_canonica"] == "Funes" and motivo == "recalculada"


def test_un_vacio_no_borra_una_localidad_demostrada(monkeypatch):
    monkeypatch.setattr(S, "cobertura_de_fila",
                        lambda *a, **k: {"localidad_canonica": None, "estado_geografico": None})
    vieja = {"localidad_canonica": "Rosario"}
    assert S._cobertura_de_la_fila_servida(
        vieja, _fila(ciudad="Rosario"), _fila(barrio="Parque Field"), "h", {}, {}) == (vieja, "localidad_conservada")


def test_un_conflicto_nuevo_si_se_impone(monkeypatch):
    conflicto = {"localidad_canonica": None, "estado_geografico": "GEO_CONFLICT"}
    monkeypatch.setattr(S, "cobertura_de_fila", lambda *a, **k: conflicto)
    assert S._cobertura_de_la_fila_servida(
        {"localidad_canonica": "Rosario"}, _fila(ciudad="Rosario"), _fila(provincia="Cordoba"),
        "h", {}, {}) == (conflicto, "recalculada")


def test_gana_la_localidad_que_la_preingestion_no_tenia(monkeypatch):
    monkeypatch.setattr(S, "cobertura_de_fila",
                        lambda *a, **k: {"localidad_canonica": "Villa Carlos Paz", "estado_geografico": None})
    cobertura, _ = S._cobertura_de_la_fila_servida(
        {"localidad_canonica": None}, _fila(), _fila(ciudad="Villa Carlos Paz"), "h", {}, {})
    assert cobertura["localidad_canonica"] == "Villa Carlos Paz"

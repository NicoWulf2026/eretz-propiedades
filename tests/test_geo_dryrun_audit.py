"""Cuáles de las propuestas de ciudad se pueden escribir."""
from __future__ import annotations

import json

from scripts.geo_dryrun_audit import (APTA, DEBIL, SIN_CORROBORAR,
                                      clasificar, corroborada)


def _propuesta(origen="barrio", match="EXACT_CANONICAL",
               provincia_publicada=None, ciudad="Villa del Parque",
               provincia_propuesta="Río Negro"):
    return {"hash_dedup": "h1",
            "source_url": "https://afianzar.com.ar/p/1",
            "publicado": {"ciudad": None, "barrio": "Villa del Parque",
                          "provincia": provincia_publicada},
            "propuesto": {"ciudad": ciudad, "provincia": provincia_propuesta},
            "evidencia": {"match": match, "campo_de_origen": origen}}


def test_un_barrio_de_caba_no_es_una_localidad_de_rio_negro():
    """El caso que abrió el artefacto: `Villa del Parque` —barrio de CABA, con
    `Melincué al 2600`, una calle de CABA— propuesto como localidad de Río
    Negro. Lo único que lo sostiene es que el nombre existe en el catálogo.

    El plan ya lo había anticipado: GeoRef no cataloga barrios, y el caso
    `Alberdi` está documentado justamente como la razón para no hacer esto.
    """
    assert clasificar(_propuesta()) == SIN_CORROBORAR
    assert not corroborada(_propuesta())


def test_la_provincia_publicada_por_la_fuente_corrobora():
    """No es el nombre solo: la fuente dijo en qué provincia está."""
    fila = _propuesta(provincia_publicada="Buenos Aires")
    assert corroborada(fila)
    assert clasificar(fila) == APTA


def test_la_coordenada_y_el_contexto_corroboran():
    """Los dos matches que ya traen evidencia propia además del nombre."""
    assert clasificar(_propuesta(match="COORDINATE_SUPPORTED")) == APTA
    assert clasificar(_propuesta(match="CONTEXT_MATCH")) == APTA


def test_una_ciudad_publicada_sin_corroborar_no_se_confunde_con_un_barrio():
    """Que la fuente lo publique en el campo `ciudad` es más que publicarlo en
    `barrio`, pero sigue sin corroborar. Se cuenta aparte para poder decidir
    sobre cada caso y no sobre el promedio de los dos."""
    assert clasificar(_propuesta(origen="ciudad")) == DEBIL


def test_perder_la_ciudad_no_pierde_la_propiedad():
    """Por contrato la propiedad sigue teniendo ficha y sigue en el listado;
    lo único que pierde es el filtro por ciudad. La asimetría es la razón de
    todo el criterio: una ciudad falsa no se nota y no se revierte sola."""
    from scripts.property_contract import alcances
    permitidos, razones = alcances({
        "source_url": "https://afianzar.com.ar/p/1", "hash_dedup": "h1",
        "canonical_agency_id": "roomix:afianzar", "titulo": "Depto en Venta",
        "operacion": "venta", "tipo_propiedad": "departamento",
        "precio": 100000.0, "moneda": "USD", "ciudad": None})
    assert "FICHA" in permitidos and "LISTADO" in permitidos
    assert "FILTRO_LOCALIDAD" not in permitidos
    assert any("localidad" in r for r in razones)


def test_la_auditoria_no_escribe_en_ninguna_base(tmp_path, monkeypatch):
    entrada = tmp_path / "dryrun.jsonl"
    entrada.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in (
        _propuesta(),
        _propuesta(provincia_publicada="Buenos Aires"),
        _propuesta(origen="ciudad"),
    )) + "\n", encoding="utf-8")
    salida = tmp_path / "out"
    salida.mkdir()

    import sys
    from scripts import geo_dryrun_audit as auditoria
    monkeypatch.setattr(sys, "argv", ["auditoria", "--dryrun", str(entrada),
                                      "--salida", str(salida)])
    assert auditoria.main() == 0

    resumen = json.loads((salida / "CIUDAD_DRYRUN_AUDIT_SUMMARY.json")
                         .read_text(encoding="utf-8"))
    assert resumen["database_writes"] == 0
    assert resumen["propuestas_auditadas"] == 3
    assert resumen["aptas_para_escritura"] == 1
    assert resumen["no_aptas"] == 2

    filas = [json.loads(l) for l in (salida / "CIUDAD_DRYRUN_AUDIT.jsonl")
             .read_text(encoding="utf-8").splitlines()]
    assert [f["apta_para_escritura"] for f in filas] == [False, True, False]
    assert all(f["writes"] is False for f in filas)

"""Caracteristicas que el extractor ya lee llegan normalizadas, sin inventar ni aceptar rotulos pegados."""
from __future__ import annotations

from scripts.caracteristicas import antiguedad, caracteristicas_de


def test_valores_reales_de_los_paquetes_se_normalizan():
    c = caracteristicas_de({"cocheras": 1.0, "plantas": 2, "expensas": 125000.0, "orientacion": "Norte",
                            "disposicion": "Contrafrente", "condicion": "Muy bueno", "situacion": "Vacía",
                            "apto_credito": True, "referencia": "HHO7996019", "antiguedad": "40 Años",
                            "modificado_en_fuente": "2026-10-07T15:42:59"})
    assert c["cocheras"] == 1 and c["plantas"] == 2
    assert c["expensas"] == {"monto": 125000.0, "moneda": None}
    assert c["orientacion"] == "Norte" and c["disposicion"] == "Contrafrente"
    assert c["condicion"] == "Muy bueno" and c["situacion"] == "Vacia"
    assert c["apto_credito"] is True and c["codigo_en_fuente"] == "HHO7996019"
    assert c["antiguedad"] == {"anios": 40}
    assert c["modificado_en_fuente"] == "2026-10-07T15:42:59"
    assert c["procedencia"]["origen"] == "extraido_de_la_ficha"


def test_MUERDE_un_rotulo_pegado_al_siguiente_no_es_un_valor():
    c = caracteristicas_de({"disposicion": "Frente Número De Piso De La Unidad", "orientacion": "Oeste :",
                            "situacion": "Vacía Número De Piso De L", "condicion": "muy_bueno"})
    assert "disposicion" not in c and "situacion" not in c
    assert c["orientacion"] == "Oeste" and c["condicion"] == "Muy bueno"


def test_no_se_infiere_ni_se_acepta_fuera_de_rango():
    assert antiguedad("A Estrenar") == {"a_estrenar": True}
    assert antiguedad("En Construcción") == {"en_construccion": True}
    assert antiguedad("1500 Años") is None
    c = caracteristicas_de({"cocheras": 2.5, "plantas": 0, "expensas": 0.0, "apto_credito": False})
    assert c == {}


def test_sin_nada_publicable_no_hay_bloque():
    assert caracteristicas_de(None) == {} and caracteristicas_de({"via": "rest"}) == {}


def test_el_documento_de_la_api_lleva_las_caracteristicas_de_la_fila():
    from scripts.api_contract import fila_de_api
    doc = fila_de_api({"hash_dedup": "h1", "source_url": "https://a.com.ar/p/1", "canonical_agency_id": "roomix:a",
                       "titulo": "Casa", "extra": {"cocheras": 2, "orientacion": "Norte :"}}, None, ["LISTADO"])
    assert doc["caracteristicas"]["cocheras"] == 2 and doc["caracteristicas"]["orientacion"] == "Norte"

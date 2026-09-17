"""Elegir entre dos lecturas de la misma propiedad."""
from __future__ import annotations

import json

from scripts.property_freshest import (CAMPOS_FUSIONABLES, CIERRES_CONFIABLES,
                                       fusionar, mas_frescas)

CAMPOS = ("operacion", "banos", "ciudad", "barrio", "superficie_total")


def test_la_fresca_manda_donde_trae_valor():
    """Corrió con el código de hoy: `agostini` tiene 360 propiedades con
    `operacion` en su certificación y 9 en la preingestión."""
    vieja = {"operacion": None, "banos": 2}
    fresca = {"operacion": "venta", "banos": 3}
    assert fusionar(vieja, fresca, CAMPOS)["operacion"] == "venta"
    assert fusionar(vieja, fresca, CAMPOS)["banos"] == 3


def test_lo_que_la_fresca_no_leyo_se_completa_con_la_vieja():
    """Son extractores DISTINTOS, no dos versiones del mismo. El refresco crudo
    recuperaba 679 superficies y a la vez perdía 177 baños en casas y
    departamentos: no leerlo no es haberlo leído y encontrado que no estaba."""
    vieja = {"banos": 2, "superficie_total": 180.0}
    fresca = {"banos": None, "superficie_total": None, "operacion": "venta"}
    m = fusionar(vieja, fresca, CAMPOS)
    assert m["banos"] == 2
    assert m["superficie_total"] == 180.0
    assert m["operacion"] == "venta"


def test_un_rechazo_anotado_gana_al_valor_viejo():
    """Volver al viejo desharía la decisión de la validación. El guardián vio
    el valor y lo rechazó."""
    vieja = {"banos": 2}
    fresca = {"banos": None,
              "extra": {"atributos_descartados": "banos_en_un_terreno"}}
    assert fusionar(vieja, fresca, CAMPOS)["banos"] is None


def test_el_barrio_que_se_mudo_a_ciudad_no_vuelve():
    """"Cordoba Capital" estaba en `barrio`, el resolver la reconoció como
    ciudad y la movió. El valor no se perdió: cambió de dimensión, y
    restaurarlo dejaría la misma cadena en los dos campos."""
    vieja = {"barrio": "Cordoba Capital"}
    fresca = {"barrio": None, "ciudad": "Córdoba",
              "extra": {"atributos_descartados": "barrio"}}
    m = fusionar(vieja, fresca, CAMPOS)
    assert m["barrio"] is None
    assert m["ciudad"] == "Córdoba"


def test_varios_rechazos_en_el_mismo_registro():
    """El connector los anota separados por coma."""
    vieja = {"banos": 2, "ciudad": "X"}
    fresca = {"banos": None, "ciudad": None,
              "extra": {"atributos_descartados": "banos_en_un_terreno,ciudad"}}
    m = fusionar(vieja, fresca, CAMPOS)
    assert m["banos"] is None and m["ciudad"] is None


def test_sin_version_fresca_no_se_toca_nada():
    vieja = {"operacion": "venta", "banos": 2}
    assert fusionar(vieja, None, CAMPOS) == vieja


def test_la_identidad_no_se_fusiona():
    """`hash_dedup` y `source_url` definen a la propiedad: cambiarlos sería
    otra propiedad, no la misma más nueva."""
    assert "hash_dedup" not in CAMPOS_FUSIONABLES
    assert "source_url" not in CAMPOS_FUSIONABLES
    assert "canonical_agency_id" not in CAMPOS_FUSIONABLES
    vieja = dict(hash_dedup='original', source_url='https://own.test/p/1',
                 canonical_agency_id='own', source_listing_id='1', titulo='Casa vieja')
    fresca = dict(hash_dedup='changed', source_url='https://other.test/p/2',
                  canonical_agency_id='other', source_listing_id='2', titulo='Casa nueva')
    merged = fusionar(vieja, fresca, CAMPOS_FUSIONABLES)
    for field in ('hash_dedup', 'source_url', 'canonical_agency_id', 'source_listing_id'):
        assert merged[field] == vieja[field]
    assert merged['titulo'] == fresca['titulo']


def test_accepted_zero_is_not_replaced_with_historical_nonzero():
    assert fusionar({'banos': 3, 'precio': 99}, {'banos': 0, 'precio': 0},
                   CAMPOS_FUSIONABLES)['banos'] == 0
    assert fusionar({'precio': 99}, {'precio': 0}, CAMPOS_FUSIONABLES)['precio'] == 0


def test_solo_se_leen_paquetes_que_cerraron_bien(tmp_path):
    """Un paquete de una corrida que falló tiene datos parciales, y preferirlos
    cambiaría datos completos por incompletos."""
    for estado in ("CERTIFIED_COMPLETE", "NEEDS_FIX"):
        carpeta = tmp_path / estado
        carpeta.mkdir()
        (carpeta / "certification.json").write_text(json.dumps({
            "canonical_agency_id": f"roomix:{estado}", "status": estado,
            "checked_at": "2026-09-07T10:00:00"}), encoding="utf-8")
        (carpeta / "properties_run1.jsonl").write_text(
            json.dumps({"hash_dedup": f"h-{estado}", "operacion": "venta"}) + "\n",
            encoding="utf-8")

    frescas = mas_frescas(tmp_path)
    assert "h-CERTIFIED_COMPLETE" in frescas
    assert "h-NEEDS_FIX" not in frescas
    assert "NEEDS_FIX" not in CIERRES_CONFIABLES


def test_entre_dos_paquetes_gana_la_certificacion_mas_nueva(tmp_path):
    """Es la única regla que no depende del orden en que se lean los
    archivos."""
    for cuando, valor in (("2026-09-01T10:00:00", "vieja"),
                          ("2026-09-07T10:00:00", "nueva")):
        carpeta = tmp_path / valor
        carpeta.mkdir()
        (carpeta / "certification.json").write_text(json.dumps({
            "canonical_agency_id": "roomix:alfa",
            "status": "CERTIFIED_COMPLETE", "checked_at": cuando}),
            encoding="utf-8")
        (carpeta / "properties_run1.jsonl").write_text(
            json.dumps({"hash_dedup": "h1", "titulo": valor}) + "\n",
            encoding="utf-8")

    assert mas_frescas(tmp_path)["h1"]["titulo"] == "nueva"

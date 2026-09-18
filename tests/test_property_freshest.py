"""Elegir entre dos lecturas de la misma propiedad."""
from __future__ import annotations

import json

import pytest

from scripts.property_freshest import (CAMPOS_FUSIONABLES, CIERRES_CONFIABLES,
                                       _leer, fusionar, mas_frescas)


@pytest.mark.parametrize('invalid', ['{not valid JSON', '[]', 'null'])
def test_corrupt_certified_rows_cannot_silently_become_a_smaller_complete_batch(tmp_path, invalid):
    source = tmp_path / 'properties.jsonl'
    content = json.dumps({'hash_dedup': 'valid'}) + '\n' + invalid + '\n'
    source.write_text(content, encoding='utf-8')
    with pytest.raises(ValueError, match='row 2') as error:
        _leer(source)
    assert invalid not in str(error.value)
    assert source.read_text(encoding='utf-8') == content

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


def test_unknown_current_offer_does_not_revive_a_historical_price():
    merged = fusionar({'precio': 99000, 'moneda': 'USD'},
                     {'precio': None, 'moneda': None}, CAMPOS_FUSIONABLES)
    assert merged['precio'] is None and merged['moneda'] is None


def test_new_amount_cannot_borrow_old_currency():
    merged = fusionar({'precio': 99000, 'moneda': 'USD'},
                     {'precio': 0, 'moneda': None}, CAMPOS_FUSIONABLES)
    assert merged['precio'] == 0 and merged['moneda'] is None


def test_explicit_commercial_and_editorial_absences_win_over_old_offer():
    old = {'operacion': 'venta', 'imagenes': ['old.jpg'], 'descripcion': 'Oferta anterior', 'banos': 2}
    fresh = {'operacion': None, 'imagenes': [], 'descripcion': None, 'banos': None}
    merged = fusionar(old, fresh, CAMPOS_FUSIONABLES)
    assert merged['operacion'] is None and merged['imagenes'] == [] and merged['descripcion'] is None
    assert merged['banos'] == 2


def test_sparse_structural_patch_does_not_erase_unmentioned_offer():
    merged = fusionar({'precio': 99000, 'moneda': 'USD'}, {'banos': 2}, CAMPOS_FUSIONABLES)
    assert merged['precio'] == 99000 and merged['moneda'] == 'USD'


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


@pytest.mark.parametrize('second_title', ['Casa', 'Otra casa'])
def test_equal_timestamp_never_selects_conflicting_data_by_filesystem_order(tmp_path, second_title):
    for name, title in [('z-first', 'Casa'), ('a-second', second_title)]:
        folder = tmp_path / name
        folder.mkdir()
        (folder / 'certification.json').write_text(json.dumps({
            'status': 'CERTIFIED_COMPLETE', 'checked_at': '2026-09-18T10:00:00'
        }), encoding='utf-8')
        (folder / 'properties_run1.jsonl').write_text(json.dumps({
            'hash_dedup': 'same', 'titulo': title
        }) + '\n', encoding='utf-8')
    if second_title != 'Casa':
        with pytest.raises(ValueError, match='Conflicting property evidence'):
            mas_frescas(tmp_path)
    else:
        assert mas_frescas(tmp_path)['same']['titulo'] == 'Casa'


def _package(folder, when, title):
    folder.mkdir()
    (folder / 'certification.json').write_text(json.dumps({
        'status': 'CERTIFIED_COMPLETE', 'checked_at': when}), encoding='utf-8')
    (folder / 'properties_run1.jsonl').write_text(json.dumps({
        'hash_dedup': 'same', 'titulo': title}) + '\n', encoding='utf-8')


def test_explicit_offsets_order_instants_not_timestamp_text(tmp_path):
    _package(tmp_path / 'a', '2026-09-18T10:00:00-03:00', 'newer')
    _package(tmp_path / 'b', '2026-09-18T12:00:00Z', 'older')
    result = mas_frescas(tmp_path)['same']
    assert result['titulo'] == 'newer'
    assert result['_certificado_en'] == '2026-09-18T13:00:00+00:00'


def test_same_instant_in_different_offsets_still_detects_conflict(tmp_path):
    _package(tmp_path / 'a', '2026-09-18T10:00:00-03:00', 'Casa')
    _package(tmp_path / 'b', '2026-09-18T13:00:00Z', 'Otra casa')
    with pytest.raises(ValueError, match='Conflicting property evidence'):
        mas_frescas(tmp_path)


def test_missing_timezone_is_not_invented_to_order_conflicting_packages(tmp_path):
    _package(tmp_path / 'a', '2026-09-18T10:00:00', 'Casa')
    _package(tmp_path / 'b', '2026-09-18T13:00:00Z', 'Otra casa')
    with pytest.raises(ValueError, match='mixed known and unknown timezones'):
        mas_frescas(tmp_path)


@pytest.mark.parametrize('when', [None, '', 'not-a-date', '2026-09-18', '2026-99-18T10:00:00'])
def test_certified_status_without_valid_time_cannot_claim_newer_evidence(tmp_path, when):
    _package(tmp_path / 'invalid', when, 'Casa')
    with pytest.raises(ValueError, match='valid checked_at'):
        mas_frescas(tmp_path)


@pytest.mark.parametrize('invalid', ['{not valid JSON', '[]', 'null'])
def test_corrupt_certificate_cannot_silently_hide_its_evidence(tmp_path, invalid):
    _package(tmp_path / 'invalid', '2026-09-18T10:00:00', 'Casa')
    (tmp_path / 'invalid/certification.json').write_text(invalid, encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid certification JSON|must be an object') as error:
        mas_frescas(tmp_path)
    assert invalid not in str(error.value)

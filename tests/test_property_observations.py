"""El registro de qué se vio y cuándo: sin esto el ciclo de vida no existe."""
from __future__ import annotations

import json

import pytest

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


def test_continuing_absence_counts_each_observation_not_only_disappearance():
    result = transiciones([{'hashes': ['a', 'b']}, {'hashes': ['b']},
                           {'hashes': ['b']}, {'hashes': ['b']}])
    assert result['desapariciones'] == 1
    assert result['ausentes_al_final'] == 1
    assert result['ausencia_consecutiva_maxima'] == 3


def test_reappearance_resets_streak_before_a_new_disappearance():
    result = transiciones([{'hashes': ['a']}, {'hashes': []}, {'hashes': []},
                           {'hashes': ['a']}, {'hashes': []}])
    assert result['desapariciones'] == 2
    assert result['reapariciones'] == 1
    assert result['ausencia_consecutiva_maxima'] == 1


@pytest.mark.parametrize('flag,value', [('paginacion_interrumpida', True),
    ('presupuesto_agotado', True), ('enumeracion_completa', False)])
def test_ok_with_incomplete_enumeration_cannot_generate_absence(tmp_path, flag, value):
    package = _paquete(tmp_path, ['a'])
    certificate = _resultado()
    certificate['run2'][flag] = value
    assert observacion(package, certificate) is None


@pytest.mark.parametrize('invalid', ['not JSON', 'null', '[]',
                                     '{"hash_dedup": null}', '{"hash_dedup": true}'])
def test_corrupt_observation_run_does_not_append_partial_seen_set(tmp_path, invalid):
    package = _paquete(tmp_path, ['a', 'b'])
    (package / 'properties_run2.jsonl').write_text(invalid + '\n', encoding='utf-8')
    output = tmp_path / 'output'
    with pytest.raises(ValueError):
        registrar(package, _resultado(), output)
    assert not (output / ARCHIVO).exists()


def test_missing_observation_run_does_not_append_partial_seen_set(tmp_path):
    package = _paquete(tmp_path, ['a', 'b'])
    (package / 'properties_run2.jsonl').unlink()
    with pytest.raises(ValueError, match='run is missing'):
        registrar(package, _resultado(), tmp_path / 'output')


def test_declared_observation_count_is_checked_before_registration(tmp_path):
    package = _paquete(tmp_path, ['a'])
    certificate = _resultado()
    certificate['run2']['detalles_obtenidos'] = 2
    with pytest.raises(ValueError, match='count does not match'):
        registrar(package, certificate, tmp_path / 'output')


@pytest.mark.parametrize('field,value', [('canonical_agency_id', None),
    ('canonical_agency_id', True), ('checked_at', None), ('checked_at', 'not a date')])
def test_missing_identity_or_time_does_not_get_fabricated(tmp_path, field, value):
    package = _paquete(tmp_path, ['a'])
    certificate = _resultado()
    certificate[field] = value
    with pytest.raises(ValueError):
        registrar(package, certificate, tmp_path / 'output')


def _observation(when, hashes):
    return {'canonical_agency_id': 'roomix:alfa', 'observado_en': when,
            'hashes': hashes, 'vistas': len(hashes)}


def _registry(tmp_path, rows):
    path = tmp_path / ARCHIVO
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    return path


@pytest.mark.parametrize('invalid', ['not JSON', None, [],
    {'canonical_agency_id': 'roomix:alfa', 'hashes': [True], 'vistas': 1},
    _observation('2026-09-18T10:00:00', ['a', 'a']),
    {**_observation('2026-09-18T10:00:00', ['a']), 'vistas': 2}])
def test_corrupt_registry_cannot_silently_remove_observations(tmp_path, invalid):
    path = _registry(tmp_path, [_observation('2026-09-17T10:00:00', ['a']), invalid])
    original = path.read_bytes()
    with pytest.raises(ValueError):
        leer(path)
    assert path.read_bytes() == original


def test_replayed_same_instant_is_not_an_extra_absence(tmp_path):
    rows = [_observation('2026-09-18T10:00:00-03:00', ['a']),
            _observation('2026-09-18T13:00:00Z', ['a'])]
    assert len(leer(_registry(tmp_path, rows))['roomix:alfa']) == 1


def test_same_instant_conflicting_seen_sets_are_not_order_dependent(tmp_path):
    rows = [_observation('2026-09-18T10:00:00-03:00', ['a']),
            _observation('2026-09-18T13:00:00Z', ['b'])]
    with pytest.raises(ValueError, match='Conflicting observations'):
        leer(_registry(tmp_path, rows))


def test_registry_orders_explicit_instants_not_iso_text(tmp_path):
    rows = [_observation('2026-09-18T10:00:00-03:00', ['new']),
            _observation('2026-09-18T12:00:00Z', ['old'])]
    assert [row['hashes'] for row in leer(_registry(tmp_path, rows))['roomix:alfa']] == [['old'], ['new']]


def test_unknown_registry_timezone_is_not_guessed(tmp_path):
    rows = [_observation('2026-09-18T10:00:00', ['a']),
            _observation('2026-09-18T13:00:00Z', ['a'])]
    with pytest.raises(ValueError, match='mixed known and unknown timezones'):
        leer(_registry(tmp_path, rows))

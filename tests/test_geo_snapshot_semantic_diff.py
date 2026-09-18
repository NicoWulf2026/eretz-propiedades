from copy import deepcopy

import pytest

from scripts.geo_snapshot_diff import JERARQUIAS, comparar


@pytest.mark.parametrize('campo', JERARQUIAS)
def test_changed_parent_id_is_not_hidden_by_equal_name(campo):
    old = {'1': {'id': '1', 'nombre': 'Lugar', campo: {'id': '01', 'nombre': 'Igual'}}}
    new = deepcopy(old)
    new['1'][campo]['id'] = '02'
    result = comparar(old, new)
    assert result['renombrados'] == 0
    assert result['cambios_de_jerarquia'] == 1
    assert result['detalle_jerarquias'][0]['despues']['id'] == '02'
    if campo == 'provincia':
        assert result['cambiaron_de_provincia'] == 1


@pytest.mark.parametrize('campo', ['centroide', 'geometria', 'categoria', 'nuevo_atributo'])
def test_other_changed_attributes_are_reported(campo):
    old = {'1': {'id': '1', 'nombre': 'Lugar', campo: {'lat': -34, 'lon': -58}}}
    new = deepcopy(old)
    new['1'][campo] = {'lat': -35, 'lon': -58}
    result = comparar(old, new)
    assert result['otros_cambios'] == 1
    assert result['detalle_otros_cambios'][0]['campo'] == campo
    assert result['cambios_de_jerarquia'] == 0


def test_missing_attribute_is_distinct_from_explicit_null():
    result = comparar({'1': {'id': '1'}}, {'1': {'id': '1', 'centroide': None}})
    assert result['otros_cambios'] == 1
    assert result['detalle_otros_cambios'][0]['presente_antes'] is False


@pytest.mark.parametrize('malformed', ['', [], 0, False])
def test_malformed_parent_context_fails_instead_of_hiding_change(malformed):
    with pytest.raises(ValueError, match='context must'):
        comparar({'1': {'id': '1', 'provincia': malformed}}, {'1': {'id': '1'}})


def test_equal_reference_has_no_semantic_changes_and_is_not_mutated():
    rows = {'1': {'id': '1', 'nombre': 'Lugar', 'provincia': {'id': '01'},
                  'centroide': {'lat': -34, 'lon': -58}}}
    before = deepcopy(rows)
    result = comparar(rows, deepcopy(rows))
    assert result['cambios_de_jerarquia'] == result['otros_cambios'] == 0
    assert rows == before

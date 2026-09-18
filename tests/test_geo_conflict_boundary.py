from scripts.api_contract import fila_de_api
from scripts.property_contract import evaluar


def test_detected_conflict_does_not_reaffirm_province_or_locality():
    row = dict(hash_dedup='h', source_url='https://agency.test/p/1',
               canonical_agency_id='agency', titulo='Casa',
               provincia='Ciudad Autónoma de Buenos Aires', ciudad='CABA',
               latitud=-34.9, longitud=-58.0)
    geo = dict(estado_geografico='GEO_CONFLICT', provincia_canonica=row['provincia'],
               localidad_canonica='CABA', localidad_id='02',
               area_busqueda=dict(nivel='PROVINCIA', nombre=row['provincia']),
               conflicto=dict(publicado=row['provincia'], geometrico='Buenos Aires'))
    verdict = evaluar(row, geo=geo)
    assert verdict['publicable'] is True
    assert {'FICHA', 'LISTADO'} <= set(verdict['alcances'])
    assert 'AREA_BUSQUEDA' not in verdict['alcances']
    assert 'FILTRO_LOCALIDAD' not in verdict['alcances']
    assert 'MAPA' not in verdict['alcances']
    assert verdict['estados_de_campo']['provincia'] == 'REJECTED_BY_VALIDATION'
    doc = fila_de_api(row, geo, ['FICHA', 'LISTADO', 'AREA_BUSQUEDA', 'FILTRO_LOCALIDAD'])
    assert doc['geo']['provincia']['nombre'] is None
    assert doc['geo']['localidad']['nombre'] is None
    assert doc['geo']['area_busqueda']['nivel'] == 'SIN_AREA'
    assert doc['geo']['estado'] == 'GEO_CONFLICT'
    assert doc['latitud'] is doc['longitud'] is None
    assert geo['provincia_canonica'] == row['provincia']  # evidence is not mutated
    assert geo['conflicto']['geometrico'] == 'Buenos Aires'


def test_new_row_conflict_cannot_be_overridden_by_old_coverage_artifact():
    row = dict(hash_dedup='h', source_url='https://agency.test/p/1',
               canonical_agency_id='agency', titulo='Casa real',
               extra={'geo_conflicto': {'publicado': {'provincia': 'CABA', 'localidad': 'La Plata'}}})
    old_geo = dict(provincia_canonica='CABA', localidad_canonica='La Plata',
                   area_busqueda=dict(nivel='LOCALIDAD', nombre='La Plata'))
    doc = fila_de_api(row, old_geo, ['FICHA', 'LISTADO', 'AREA_BUSQUEDA', 'MAPA'])
    assert doc['geo']['estado'] == 'GEO_CONFLICT'
    assert doc['geo']['provincia']['nombre'] is None
    assert doc['geo']['localidad']['nombre'] is None
    assert doc['alcances'] == ['FICHA', 'LISTADO']
    verdict = evaluar(row, geo=old_geo)
    assert verdict['publicable']
    assert verdict['estados_de_campo']['provincia'] == 'REJECTED_BY_VALIDATION'
    assert 'AREA_BUSQUEDA' not in verdict['alcances']

"""Public read policy, also applied to snapshots produced before geo hardening."""
from copy import deepcopy


def public_document(document: dict) -> dict:
    geo = document.get('geo') or {}
    if geo.get('estado') != 'GEO_CONFLICT':
        return document
    result = deepcopy(document)
    for dimension in ('provincia', 'departamento', 'municipio', 'localidad'):
        result['geo'][dimension] = {'nombre': None, 'id': None, 'procedencia': 'UNKNOWN',
                                   'rechazo': 'GEO_CONFLICT'}
    result['geo']['area_busqueda'] = {'nivel': 'SIN_AREA', 'nombre': None,
                                    'id': None, 'origen': 'sin_area'}
    result['latitud'] = result['longitud'] = None
    result['alcances'] = [scope for scope in result.get('alcances', [])
                          if scope not in ('MAPA', 'FILTRO_LOCALIDAD', 'AREA_BUSQUEDA')]
    return result

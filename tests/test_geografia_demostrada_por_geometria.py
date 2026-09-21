# -*- coding: utf-8 -*-
"""El municipio que la geometria demuestra y no se publicaba.

Medido antes del cambio: 36.718 propiedades tenian su municipio demostrado
por la geometria oficial de GeoRef y la columna `municipio` del snapshot
estaba vacia en las **57.665 filas**. Cero, no pocas. Eso es el
`municipality: null` que aparecio en el QA de browser.

La regla que lo causaba es correcta **para la localidad** y ahi se conserva:
el sondeo de 36.552 puntos da `localidad_determinable_por_coordenada: 0`,
porque `/ubicacion` no expone capa de localidad. Resolverla por coordenada
obligaria al centroide mas cercano, que si es inventar geografia.

Para municipio y departamento no: `/ubicacion` responde por **contencion en
el poligono oficial**. Que un punto caiga dentro del partido de Avellaneda no
es una inferencia, es una medicion.

Lo que estos tests protegen es que aflojar para municipio **no** afloje para
localidad, y que nada quede promovido en silencio.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.api_contract import _procedencia  # noqa: E402
from scripts.geo_coverage_audit import POR_GEOMETRIA, POR_NOMBRE  # noqa: E402


def test_MUERDE_un_municipio_por_geometria_dice_que_salio_de_ahi():
    """Publicar 33.003 municipios nuevos sin decir de donde vienen seria
    promoverlos en silencio."""
    geo = {"municipio_canonico": "Avellaneda",
           "procedencia_de_dimensiones": {"municipio": POR_GEOMETRIA}}
    assert _procedencia(geo, "municipio") == "GEO_GEOMETRY"


def test_un_municipio_por_nombre_se_distingue_del_de_geometria():
    """Las dos cosas son ciertas y no son la misma."""
    geo = {"municipio_canonico": "Rosario",
           "procedencia_de_dimensiones": {"municipio": POR_NOMBRE}}
    assert _procedencia(geo, "municipio") == "SOURCE_LOCALITY"
    assert POR_NOMBRE != POR_GEOMETRIA


def test_MUERDE_una_dimension_vacia_no_hereda_la_procedencia_de_otra():
    """Devolver la procedencia de otra cosa es peor que no devolver nada.

    Una fila sin municipio con `procedencia: GEO_GEOMETRY` afirmaria que la
    geometria demostro un valor que no esta.
    """
    geo = {"municipio_canonico": None, "departamento_canonico": "Rosario",
           "procedencia_de_dimensiones": {"departamento": POR_GEOMETRIA}}
    assert _procedencia(geo, "municipio") == "UNKNOWN"


def test_sin_geo_la_procedencia_es_desconocida_y_no_explota():
    assert _procedencia(None, "municipio") == "UNKNOWN"
    assert _procedencia({}, "departamento") == "UNKNOWN"


def test_un_registro_viejo_sin_procedencia_no_miente():
    """Los artefactos escritos antes de este cambio no traen el campo.

    Inventarles `SOURCE_LOCALITY` los presentaria como mejor evidenciados de
    lo que estan.
    """
    assert _procedencia({"municipio_canonico": "Avellaneda"},
                        "municipio") == "UNKNOWN"


def test_MUERDE_la_localidad_no_se_resuelve_por_coordenada():
    """La regla que NO se afloja, y la razon medida de por que.

    Si alguien extiende el criterio de municipio a localidad, esto muerde:
    `localidad_canonica` sale del nombre corroborado o no sale.
    """
    fuente = (RAIZ / "scripts" / "geo_coverage_audit.py").read_text(
        encoding="utf-8")
    # La localidad se escribe SOLO desde `prop.ciudad` con corroboracion.
    assert '"localidad_canonica": prop.ciudad if corroborada else None' in fuente
    # Y la geometria nunca la ASIGNA. Se busca la asignacion, no la palabra:
    # el bloque la menciona en un comentario que explica justamente por que
    # no se toca, y un test que se rompe con un comentario no mide nada.
    bloque = fuente.split("procedencia: dict")[1][:1200]
    for asignacion in ("localidad_canonica =", "prop.ciudad =",
                       "localidad_id ="):
        assert asignacion not in bloque, asignacion


def test_MUERDE_en_conflicto_geografico_no_se_publica_nada_por_geometria():
    """Si la coordenada contradice la provincia publicada, su municipio
    tampoco sirve: mandaria a buscar en la provincia equivocada.

    Es la diferencia entre los 36.718 demostrables y los 33.003 publicados:
    los 3.715 de conflicto quedan afuera a proposito.
    """
    fuente = (RAIZ / "scripts" / "geo_coverage_audit.py").read_text(
        encoding="utf-8")
    bloque = fuente.split("procedencia: dict")[1][:1200]
    assert "elif muni_geo and not conflicto:" in bloque
    assert "elif depto_geo and not conflicto:" in bloque

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La aritmetica de inmuebles tiene que correr para TODAS las familias.

`revisar` vivia solo adentro de `generico.py`. Tokko, Wasi, WordPress y
Century21 nunca pasaban por ahi: `aagaard.com.ar` -Tokko- cerro
CERTIFIED_COMPLETE con un departamento de 95 m2 cubiertos y 50.000.000 m2 de
terreno, cincuenta kilometros cuadrados, y la ficha lo muestra asi.

Se movio a la construccion de `PropiedadNormalizada` por la misma razon por la
que la guardia de `discover` se movio al runner: una guardia por connector deja
justo el camino que nadie miro.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import PropiedadNormalizada  # noqa: E402


def _propiedad(**campos) -> PropiedadNormalizada:
    base = dict(canonical_agency_id="roomix:x", source_listing_id="1",
                source_url="https://x.com.ar/p/1", connector="tokko")
    return PropiedadNormalizada(**{**base, **campos})


def test_ninguna_familia_esquiva_la_aritmetica_de_inmuebles():
    """El caso real de `aagaard`, que es Tokko y no pasaba por el guardian."""
    p = _propiedad(tipo_propiedad="departamento", superficie_cubierta=95.0,
                   superficie_total=50_000_000.0)
    assert p.superficie_total is None
    assert p.superficie_cubierta == 95.0
    assert "superficie_total_absurda_para_el_tipo" in p.extra["atributos_descartados"]


def test_el_motivo_viaja_con_el_dato():
    """Sin el motivo, la propiedad aparece sin superficie y no se distingue de
    una que la fuente no publica."""
    p = _propiedad(tipo_propiedad="terreno", dormitorios=3, banos=2)
    descartados = p.extra["atributos_descartados"]
    assert "dormitorios_en_un_terreno" in descartados
    assert "banos_en_un_terreno" in descartados
    assert p.dormitorios is None and p.banos is None


def test_lo_que_es_coherente_no_se_toca():
    p = _propiedad(tipo_propiedad="casa", superficie_total=600.0,
                   superficie_cubierta=180.0, dormitorios=3, ambientes=5)
    assert p.superficie_total == 600.0
    assert p.dormitorios == 3
    assert "atributos_descartados" not in p.extra


def test_un_campo_grande_en_el_campo_sigue_siendo_correcto():
    """Cincuenta hectareas de campo son 500.000 m2 y es el dato real. La regla
    mira el tipo, no el numero."""
    p = _propiedad(tipo_propiedad="campo", superficie_total=500_000.0)
    assert p.superficie_total == 500_000.0


def test_aplicarla_dos_veces_no_cambia_nada():
    """`generico` la sigue llamando antes de construir. Sobre datos ya limpios
    `revisar` no descarta nada, asi que no se duplica el motivo."""
    p = _propiedad(tipo_propiedad="terreno", dormitorios=3)
    antes = p.extra["atributos_descartados"]
    p._aplicar_coherencia()
    assert p.extra["atributos_descartados"] == antes


def test_no_pisa_los_descartes_que_ya_traia_el_connector():
    p = _propiedad(tipo_propiedad="terreno", dormitorios=3,
                   extra={"atributos_descartados": "ambientes"})
    descartados = p.extra["atributos_descartados"].split(",")
    assert "ambientes" in descartados
    assert "dormitorios_en_un_terreno" in descartados

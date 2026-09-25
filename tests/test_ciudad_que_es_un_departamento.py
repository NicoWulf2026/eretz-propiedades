"""Una «ciudad» publicada que en realidad es el departamento de la localidad.

`fenixxweb.com` (Posadas) publica en su JSON-LD
`addressLocality: "Capital"` y `addressNeighborhood: "Posadas"`, y en la ficha
«Posadas, Capital»: Capital es el DEPARTAMENTO de Misiones y Posadas la
localidad. «Capital» sola no resuelve —el departamento tiene varias
localidades— y las 512 fichas quedaban sin ciudad.

Se acepta la localidad publicada como barrio solo si resuelve exacta en la
provincia y su departamento es literalmente lo que se publicó como ciudad.
"""
from __future__ import annotations

from connectors.base import Connector, PropiedadNormalizada


def _propiedad(**cambios):
    base = dict(canonical_agency_id="roomix:fenix", source_listing_id="1",
                source_url="https://fenix.test/p/1", connector="generico")
    base.update(cambios)
    return PropiedadNormalizada(**base)


def test_MUERDE_la_localidad_del_departamento_publicado_como_ciudad():
    p = _propiedad(ciudad="Capital", barrio="Posadas", provincia="Misiones")
    Connector._resolver_geografia(p)
    assert p.ciudad == "Posadas"
    assert p.geo["localidad"]["id"] == "54028030"
    assert p.barrio is None


def test_si_el_departamento_no_coincide_no_se_promueve_el_barrio():
    p = _propiedad(ciudad="Centro", barrio="Posadas", provincia="Misiones")
    Connector._resolver_geografia(p)
    assert p.ciudad is None


def test_sin_barrio_capital_sola_sigue_sin_afirmarse():
    p = _propiedad(ciudad="Capital", provincia="Misiones")
    Connector._resolver_geografia(p)
    assert p.ciudad is None


def test_una_capital_que_resuelve_no_cambia():
    p = _propiedad(ciudad="Cordoba Capital", barrio="Nueva Cordoba", provincia="Cordoba")
    Connector._resolver_geografia(p)
    assert p.ciudad == "Córdoba"
    assert p.barrio == "Nueva Cordoba"

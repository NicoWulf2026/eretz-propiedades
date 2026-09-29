"""inspiry-real-places escribe la longitud como «lang» (`gonzalez theyler`, 41 de 44)."""
from __future__ import annotations

from connectors.generico import RE_COORD


def test_lang_es_la_longitud_cuando_trae_una_coordenada() -> None:
    m = RE_COORD.search('var propertyMarkerInfo = {"lat":"-32.9425739","lang":"-60.64003819999999","icon":"x"}')
    assert m and (float(m.group(1)), float(m.group(2))) == (-32.9425739, -60.64003819999999)


def test_lang_como_idioma_no_es_una_coordenada() -> None:
    assert RE_COORD.search('{"lat":"-32.94","lang":"es"}') is None

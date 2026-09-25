"""Un sitio Tokko TFW sin plataforma registrada no se lee con generico.

`fjlujan.com.ar` y `cbdestino.com.ar` son la plantilla web estandar de Tokko
(static.tokkobroker.com/tfw), pero no tienen registro en el directorio de
plataformas y el catalogo los mandaba a `generico`: fj lujan enumeraba 2 de
sus ~113 fichas y cb destino 21 de ~500. Con el conector Tokko, 3/3 fichas OK
en las dos (25-09).
"""
from __future__ import annotations

import pytest

from connectors.base import ErrorTransitorio, Fuente
from scripts import agency_certifier as ac

FUENTE = Fuente(canonical_agency_id="roomix:fj lujan propiedades", agency_name="FJ Lujan",
                official_url="https://www.fjlujan.com.ar", inmobiliaria_id=1)
TFW = ('<script src="https://static.tokkobroker.com/tfw/js/utils.eb8929bff3ac.js"></script>'
       '<img src="https://static.tokkobroker.com/tfw_images/542_FJ%20Lujan/logo.jpg">')


def _portada(monkeypatch, html=None, error=None):
    def bajar(self, url):
        if error:
            raise error
        return html
    monkeypatch.setattr(ac.AuditDownloader, "bajar", bajar)


def test_MUERDE_una_portada_tfw_se_lee_con_tokko(monkeypatch):
    _portada(monkeypatch, TFW)
    assert ac.conector_por_la_portada("generico", FUENTE, 0.0) == "tokko"


def test_una_portada_sin_tfw_sigue_en_generico(monkeypatch):
    _portada(monkeypatch, '<link href="https://static.tokkobroker.com/pictures/1_a.jpg">')
    assert ac.conector_por_la_portada("generico", FUENTE, 0.0) == "generico"


def test_un_conector_declarado_no_se_cambia(monkeypatch):
    _portada(monkeypatch, TFW)
    assert ac.conector_por_la_portada("wordpress", FUENTE, 0.0) == "wordpress"


@pytest.mark.parametrize("error", [ErrorTransitorio("timeout"), ValueError("x")])
def test_si_la_portada_no_responde_manda_el_catalogo(monkeypatch, error):
    _portada(monkeypatch, error=error)
    assert ac.conector_por_la_portada("generico", FUENTE, 0.0) == "generico"

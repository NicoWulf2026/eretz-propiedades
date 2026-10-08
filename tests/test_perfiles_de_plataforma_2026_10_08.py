"""Un perfil dentro de una plataforma multi-agencia no es la web de la inmobiliaria.

08-10: `hogarfe inmobiliaria` tenia cargado `waichatt.com/inmobiliarias/hogar-fe` y
`estudio inmobiliario dos santos` `patagonprop.com/pt/corretor/...`. El conector
generico lee el sitemap desde la raiz del host, que en una plataforma es el de
TODAS sus inmobiliarias: hogarfe junto 235 fichas y ninguna estaba en su sitemap
propio; dos santos llego a servirse con 12 fichas de otras agencias (Ciocale,
verificado en la fuente). Una sola agencia por host en el padron no alcanza para
la senal estructural, asi que la plataforma va por nombre.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.reclassify_portal_profiles import OFICIAL, PERFIL_PORTAL, clasificar  # noqa: E402


def test_MUERDE_los_perfiles_de_plataforma_no_son_web_propia() -> None:
    for url, nombre in (
            ("https://waichatt.com/inmobiliarias/hogar-fe", "HogarFe Inmobiliaria"),
            ("https://patagonprop.com/pt/corretor/estudio-inmobiliario-dos-santos-goncalves",
             "Estudio inmobiliario Dos Santos"),
            ("https://buscainmueble.com/inmobiliarias/analia-verga-propiedades",
             "Analia Verga Propiedades")):
        assert clasificar(url, {}, nombre)[0] == PERFIL_PORTAL, url


def test_la_web_propia_de_esas_mismas_agencias_sigue_siendo_oficial() -> None:
    assert clasificar("https://hogarfe.com.ar", {}, "HogarFe Inmobiliaria")[0] == OFICIAL
    assert clasificar("https://www.dossantos-goncalves.com.ar", {},
                      "Estudio inmobiliario Dos Santos")[0] == OFICIAL

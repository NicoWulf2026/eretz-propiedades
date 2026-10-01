"""Lote 5 (LOCAL, 2026-10-01): fichas Wix y el tope de descarga.

`lucas liprandi` (Wix, CMS «Properties»): 71 fichas en el sitemap y las 71
fallaban -931 KB por pagina contra un tope de 800 KB, y cada una se bajaba
tres veces porque el exceso se trataba como error transitorio-.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import connectors.base as base
from connectors.base import Descargador, ErrorTransitorio, Fuente
from connectors.generico import GenericoConnector as G

FIX = Path(__file__).parent / "fixtures" / "cloud_bridge" / "wix" / "liprandi_ficha.html"
URL = "https://www.lucasliprandiinmobiliaria.com.ar/properties/casa-en-venta-en-ascochinga"


def _normalizar(html: str):
    class Fijo:
        def bajar(self, *a, **k):
            return html

        def __getattr__(self, nombre):
            return lambda *a, **k: None

    return G(descargador=Fijo()).normalize(
        {"source_url": URL, "source_listing_id": "1"},
        Fuente(canonical_agency_id="roomix:lucas liprandi servicios inmobiliarios",
               agency_name="Lucas Liprandi", official_url="https://www.lucasliprandiinmobiliaria.com.ar/"))


def test_ficha_wix_real_completa_la_ubicacion():
    p = _normalizar(FIX.read_text(encoding="utf-8"))
    assert p is not None
    assert (p.ciudad, p.provincia) == ("Ascochinga", "Córdoba")
    assert (p.precio, p.moneda, p.operacion) == (280000.0, "USD", "venta")
    assert (p.dormitorios, p.banos) == (3, 2)


def _wix(*textos: str) -> str:
    comps = {f"comp-{i}": {"html": f"<p>{t}</p>"} for i, t in enumerate(textos)}
    datos = {"platform": {"ssrPropsUpdates": [comps]}}
    return f'<script type="application/json" id="wix-warmup-data">{json.dumps(datos)}</script>'


def test_dos_ubicaciones_distintas_no_afirman_ninguna():
    assert G._ubicacion_wix(_wix("Ascochinga, Córdoba, Argentina", "Ascochinga, Córdoba, Argentina")) \
        == "Ascochinga, Córdoba, Argentina"
    assert G._ubicacion_wix(_wix("Ascochinga, Córdoba, Argentina", "Mendiolaza, Córdoba, Argentina")) is None


@pytest.mark.parametrize("texto", ["Ruta 5 km 12, Córdoba, Argentina", "Córdoba",
                                   "Ascochinga, Argentina", "Hola, mundo, Argentina"])
def test_solo_la_forma_localidad_provincia_argentina(texto):
    assert G._ubicacion_wix(_wix(texto)) is None


class _Respuesta(io.BytesIO):
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_una_respuesta_mayor_al_tope_no_se_reintenta(monkeypatch):
    llamadas = []

    def falso_urlopen(req, timeout=None, context=None):
        llamadas.append(req.full_url)
        return _Respuesta(b"x" * 5000)

    monkeypatch.setattr(base, "secure_urlopen", falso_urlopen)
    d = Descargador(limite_bytes=1000, reintentos=3)
    d.limitador.esperar = lambda host: None
    with pytest.raises(ErrorTransitorio, match="tope"):
        d.bajar("https://ejemplo.com.ar/ficha")
    assert len(llamadas) == 1


def test_el_tope_por_defecto_admite_una_ficha_wix():
    assert Descargador().limite_bytes >= 1_000_000

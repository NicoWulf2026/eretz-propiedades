# -*- coding: utf-8 -*-
"""Identidad compartida y propiedades del exterior (2026-09-28).

- Dos agencias con la MISMA web oficial no se fusionan ni se atribuye el
  inventario: revision de identidad (terminal, no frena la cola).
- Una propiedad publicada fuera de Argentina se conserva, se marca
  PRESERVED_NOT_PUBLISHED (politica ARGENTINA_ONLY, 28-09) y no se le
  inventa geografia argentina.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from connectors import base as B  # noqa: E402
from connectors.exterior import PRESERVED_NOT_PUBLISHED, evidencia_de_exterior  # noqa: E402


def _registro(url: str) -> dict:
    return {"resolution": {"resolution_status": "RESOLVED", "eretz_id": 1},
            "live": {"validation_status": "VALIDATED"},
            "source": {"official_url": url}, "platform": {"web_kind": "OFFICIAL_WEB"},
            "directory": {}, "verificada": {}}


def test_MUERDE_la_misma_web_en_dos_agencias_va_a_revision_de_identidad(tmp_path):
    import agency_certifier as AC
    catalogo = {
        "roomix:martinez negocios inmobiliarios": _registro("https://www.inmueblesmartinez.com.ar/"),
        "roomix:martinez propiedades": _registro("https://www.inmueblesmartinez.com.ar"),
        "roomix:otra": _registro("https://otra.test/"),
    }
    resultado = AC.certify("roomix:martinez propiedades", catalogo, tmp_path, tmp_path / "x.db")
    assert resultado["status"] == "IDENTITY_PENDING"
    assert resultado["reasons"][0].startswith("IDENTITY_REVIEW")
    assert "martinez negocios inmobiliarios" in resultado["reasons"][0]


def test_una_plataforma_con_una_ruta_por_agencia_no_es_web_compartida():
    import agency_certifier as AC
    catalogo = {"roomix:a": _registro("https://proppies.app/inmobiliarias/a-1"),
                "roomix:b": _registro("https://proppies.app/inmobiliarias/b-2")}
    assert AC.webs_compartidas(catalogo) == {}


def test_evidencia_de_exterior_conservadora():
    no_es_argentina = lambda _t: False  # noqa: E731
    assert evidencia_de_exterior(ciudad="CIUDAD DE MIAMI",
                                 es_localidad_argentina=no_es_argentina)["pais"] == "US"
    assert evidencia_de_exterior(ciudad="Punta del Este",
                                 es_localidad_argentina=no_es_argentina)["pais"] == "UY"
    assert evidencia_de_exterior(
        titulo="Alquiler Temporal en Sorrento Italia Costa Amalfitana")["pais"] == "IT"
    # Medidos en los paquetes: barrio de Rosario, calles y un barrio rosarino.
    for titulo in ("Casa en Venta en España y Hospitales - Mitre 3222",
                   "Casa en venta en Uruguay al 200", "Casa en venta en Italia al 2700",
                   "Casa en Venta en Sorrento - Asamblea al 612"):
        assert evidencia_de_exterior(titulo=titulo) is None, titulo
    assert evidencia_de_exterior(ciudad="Florida") is None
    assert evidencia_de_exterior(pais="AR", ciudad="Rosario") is None


def test_MUERDE_miami_no_es_un_barrio_de_buenos_aires():
    prop = B.PropiedadNormalizada(
        canonical_agency_id="roomix:blanco propiedades", source_listing_id="12617",
        source_url="https://b.test/propiedades/miami", connector="generico",
        titulo="Depto 3 Amb en Hyde Beach - Miami", ciudad="CIUDAD DE MIAMI",
        provincia="Buenos Aires", precio=450000.0, moneda="USD")
    fuente = B.Fuente("roomix:blanco propiedades", "Blanco", "https://b.test", 1,
                      extra={"province": "Buenos Aires"})
    B.Connector.completar_ubicacion(B.Connector.__new__(B.Connector), prop, fuente)
    assert prop.extra["publicacion_exterior"] == PRESERVED_NOT_PUBLISHED
    assert prop.extra["politica_publica"] == "ARGENTINA_ONLY"
    assert prop.extra["pais_publicado"] == "US"
    assert prop.ciudad is None and prop.barrio is None and prop.provincia is None
    assert prop.extra["ciudad_publicada"] == "CIUDAD DE MIAMI"
    assert prop.extra["provincia_publicada"] == "Buenos Aires"
    assert prop.precio == 450000.0  # la propiedad se conserva entera
    assert "ciudad" in prop.extra["atributos_descartados"]


def test_una_propiedad_argentina_no_cambia():
    prop = B.PropiedadNormalizada(
        canonical_agency_id="roomix:x", source_listing_id="1", source_url="https://x.test/1",
        connector="generico", titulo="Casa en Rosario", ciudad="Rosario", provincia="Santa Fe")
    B.Connector.completar_ubicacion(B.Connector.__new__(B.Connector), prop,
                                    B.Fuente("roomix:x", "X", "https://x.test", 1))
    assert "publicacion_exterior" not in prop.extra
    assert prop.ciudad == "Rosario"

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La cortesia adaptativa tiene que correr por el camino que se usa de verdad.

El runner bajaba la velocidad ante un 403 en `except Bloqueado`. Casi ningun
connector propaga esa excepcion: la absorben, la anotan en `errores` y
devuelven `None`. O sea que la rama existia, estaba comentada y probada, y no
corria nunca en produccion: el reintento diferido volvia a pedirle al sitio a la
misma velocidad que habia provocado el bloqueo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import Fuente, LimitadorDeRitmo  # noqa: E402
from scripts.run_rollout import _procesar_con, ceder_ritmo_del_host  # noqa: E402

FUENTE = Fuente(canonical_agency_id="roomix:prueba", agency_name="Prueba",
                official_url="https://ejemplo.com.ar", inmobiliaria_id=1,
                detected_platform="generico", extra={})


class DescargadorConLimitador:
    def __init__(self, limitador):
        self.limitador = limitador

    def hubo_contacto(self, url):
        return True


class ConnectorQueAbsorbeElBloqueo:
    """Lo que hacen casi todos: anotar el bloqueo y devolver `None`."""

    nombre = "generico"

    def __init__(self, limitador):
        self.descargador = DescargadorConLimitador(limitador)
        self.errores: list[dict] = []
        self.pedidas = 0

    def discover(self, fuente):
        return {"variante": "LISTADO_HTML", "soportada": True,
                "total_declarado": None}

    def fetch_listing(self, fuente, plan):
        return [{"source_listing_id": "1",
                 "source_url": "https://ejemplo.com.ar/p/1", "pagina": 1}]

    def identify_deleted_or_inactive(self, fuente, vistos, fuente_respondio):
        return []

    def normalize(self, aviso, fuente):
        self.pedidas += 1
        self.errores.append({"etapa": "detalle", "clase": "Bloqueado",
                             "detalle": "http 403"})
        return None


def test_el_bloqueo_absorbido_tambien_baja_la_velocidad():
    """El connector devuelve `None` y anota el bloqueo. Antes de este arreglo
    el runner difería la ficha sin ceder ritmo, y el reintento salía a la misma
    velocidad que había provocado el 403."""
    limitador = LimitadorDeRitmo(0.001)
    con = ConnectorQueAbsorbeElBloqueo(limitador)

    resultado = _procesar_con(con, FUENTE, max_fichas=0, observacion=True)

    assert resultado["intervalo_cedido"] is not None
    assert limitador.intervalo_de("ejemplo.com.ar") > 0.001


def test_un_fallo_transitorio_no_baja_la_velocidad():
    """Ceder ritmo ante cualquier `None` castigaría a un sitio sano por un
    corte de red. Solo el bloqueo dice "vas muy rápido"."""
    limitador = LimitadorDeRitmo(0.001)
    con = ConnectorQueAbsorbeElBloqueo(limitador)

    def transitorio(aviso, fuente):
        con.errores.append({"etapa": "detalle", "clase": "ErrorTransitorio",
                            "detalle": "timeout"})
        return None

    con.normalize = transitorio
    resultado = _procesar_con(con, FUENTE, max_fichas=0, observacion=True)

    assert resultado.get("intervalo_cedido") is None
    assert limitador.intervalo_de("ejemplo.com.ar") == 0.001


def test_se_frena_al_host_que_se_quejo_y_a_nadie_mas():
    """El limitador lo comparten todos los hilos: frenarlo entero castigaría a
    las inmobiliarias que no se quejaron."""
    limitador = LimitadorDeRitmo(0.5)
    con = ConnectorQueAbsorbeElBloqueo(limitador)

    nuevo = ceder_ritmo_del_host(
        con, FUENTE, {"source_url": "https://lento.com.ar/p/1"})

    assert nuevo > 0.5
    assert limitador.intervalo_de("lento.com.ar") == nuevo
    assert limitador.intervalo_de("otra.com.ar") == 0.5


def test_el_bloqueo_propagado_cede_una_vez_y_despues_abandona():
    """La otra rama: el connector que SI propaga `Bloqueado`. La primera vez es
    una queja de ritmo y se difiere; si vuelve a cortar despues de haber bajado
    la velocidad, ahi si es una negativa."""
    from connectors.base import Bloqueado

    limitador = LimitadorDeRitmo(0.001)
    con = ConnectorQueAbsorbeElBloqueo(limitador)

    def corta(aviso, fuente):
        raise Bloqueado("http 403")

    con.normalize = corta
    resultado = _procesar_con(con, FUENTE, max_fichas=0, observacion=True)

    assert resultado["intervalo_cedido"] is not None
    assert limitador.intervalo_de("ejemplo.com.ar") > 0.001


def test_un_plan_sin_total_declarado_no_hace_estallar_la_corrida():
    """`total_declarado` es opcional: la mayoría de los sitios no lo declara.
    Leerlo con corchetes acoplaba la corrida a que TODOS los caminos de TODOS
    los discover pusieran la clave, y el retorno temprano `NO_ES_WASI` no la
    ponía: `alderinmobiliaria.com` dejó de servir su sitio, el runner tiró
    KeyError y paró las dos colas."""
    limitador = LimitadorDeRitmo(0.001)
    con = ConnectorQueAbsorbeElBloqueo(limitador)
    con.discover = lambda fuente: {"variante": "NO_ES_WASI", "soportada": False}

    resultado = _procesar_con(con, FUENTE, max_fichas=0, observacion=True)

    assert resultado["total_declarado"] is None
    assert resultado["estado"] == "VARIANTE_NO_SOPORTADA"

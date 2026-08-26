#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El apellido compartido no alcanza para declarar duplicada a una empresa.

El clasificador de conflictos cross-agency deduce "misma empresa cargada dos
veces en el padron" de tres cosas: mismo dominio, mismas palabras distintivas
del nombre, host no compartido. Con esa regla, los dos Bustamante quedaron
catalogados SAME_AGENCY_DUPLICATED_IN_ERETZ y sus 3.137 avisos retenidos fuera
del write set esperando que alguien decidiera "cual de los dos ids conserva
ERETZ".

La investigacion del padron demostro que la pregunta no tenia respuesta porque
estaba mal planteada: son dos inmobiliarias distintas, en mercados que no se
tocan, y el sitio es de una sola. Lo que fallaba era la premisa, no la eleccion.

Dos homonimas dan exactamente la misma señal que una empresa duplicada. Lo unico
que las separa es evidencia verificada a mano, y por eso, cuando existe, tiene
que pesar mas que el parecido del nombre.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.resolve_cross_agency import (CLARO, SAME_AGENCY,  # noqa: E402
                                          dueno_por_misatribucion, host)

RESOLUCION = Path(r"D:\INMO CAPITAL\CROSS_AGENCY_RESOLUTION.jsonl")
DOMINIO = "bustamantepropiedades.com"


def claim(cid, eid):
    return {"canonical_agency_id": cid, "inmobiliaria_id": eid,
            "provenance": {"agency_name": cid.split(":")[-1]}}


def test_refutado_uno_el_que_queda_es_el_dueno():
    agencias = {"roomix:bustamante propiedades": claim("roomix:bustamante propiedades", 1028)}
    dueno, motivo = dueno_por_misatribucion(
        agencias, {"roomix:bustamante inmobiliaria"})
    assert dueno is not None
    assert dueno["inmobiliaria_id"] == 1028
    assert "no pertenece" in motivo


def test_sin_evidencia_verificada_no_desempata():
    """Si a nadie se le probo nada, esto no opina: el conflicto sigue su curso
    normal y puede terminar en SAME_AGENCY o en AMBIGUO, como antes."""
    agencias = {"a": claim("a", 1), "b": claim("b", 2)}
    assert dueno_por_misatribucion(agencias, set())[0] is None


def test_si_quedan_dos_reclamantes_no_adjudica():
    """Descartar a uno de tres no resuelve nada: adjudicar ahi seria elegir por
    descarte, que es justo lo que este pipeline no hace."""
    agencias = {"a": claim("a", 1), "b": claim("b", 2)}
    assert dueno_por_misatribucion(agencias, {"c"})[0] is None


def test_el_host_se_compara_normalizado():
    """El sitio en disputa aparece con www en los avisos y sin www en el
    directorio; si no se normaliza, la evidencia no se encuentra."""
    assert host("https://www.bustamantepropiedades.com/12629-casa") == DOMINIO
    assert host("https://bustamantepropiedades.com/") == DOMINIO


def test_las_3137_dejaron_de_estar_retenidas():
    if not RESOLUCION.exists():
        import pytest
        pytest.skip("todavia no se regenero la resolucion")
    filas = [json.loads(l) for l in RESOLUCION.open(encoding="utf-8")
             if DOMINIO in l]
    assert filas, "el dominio tiene que seguir apareciendo en la resolucion"
    assert all(f["categoria"] == CLARO for f in filas)
    assert all(f["liberable"] for f in filas)
    # Adjudicadas a la que opera en Tigre/Nordelta, que es la que el sitio nombra.
    assert {f["eretz_id_owner"] for f in filas} == {1028}
    # Y el reclamante refutado queda asentado, no borrado.
    assert all(f["descartados_por_evidencia"] == ["roomix:bustamante inmobiliaria"]
               for f in filas)
    assert not any(f["categoria"] == SAME_AGENCY for f in filas)

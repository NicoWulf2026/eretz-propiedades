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

import pytest

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


def test_las_3137_quedaron_del_lado_correcto():
    """Lo que importa no es en que etapa se resuelve, sino donde terminan.

    Al principio se resolvian en la etapa cross-agency: las dos fichas
    reclamaban las mismas urls y el desempate las adjudicaba a 1028. Despues el
    write gate paso a rechazar antes toda propiedad cuyo par (agencia, host)
    figura como atribucion refutada, asi que las copias de 651 ya no llegan a
    disputar nada. Es mas preciso: no estan en disputa, ya se sabe de quien no
    son.

    Por eso este test mira el write set y no la resolucion intermedia. La
    garantia es la misma y no depende de por donde pase.
    """
    import json as _json
    ws = Path(r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    if not ws.exists():
        pytest.skip("todavia no se genero el write set")
    por_id = {}
    with ws.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            if DOMINIO not in linea:
                continue
            r = _json.loads(linea)
            por_id[r.get("inmobiliaria_id")] = por_id.get(r.get("inmobiliaria_id"), 0) + 1
    assert por_id == {1028: 3137}, por_id


def test_a_la_desplazada_no_le_queda_ni_una():
    """651 no tiene que aparecer con ninguna propiedad de ese sitio, ni una."""
    import json as _json
    ws = Path(r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    if not ws.exists():
        pytest.skip("todavia no se genero el write set")
    with ws.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            if DOMINIO in linea:
                r = _json.loads(linea)
                assert r.get("canonical_agency_id") != "roomix:bustamante inmobiliaria"


def test_lo_rechazado_queda_documentado_con_su_motivo():
    """No se descarta en silencio: queda con estado propio y su agencia."""
    import json as _json
    ruta = Path(r"D:\INMO CAPITAL\WEB_NO_PROPIA.jsonl")
    if not ruta.exists():
        pytest.skip("todavia no se genero el artefacto")
    n = 0
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            if DOMINIO not in linea:
                continue
            r = _json.loads(linea)
            if r.get("canonical_agency_id") == "roomix:bustamante inmobiliaria":
                assert r.get("db_write_status") == "SITIO_PROBADO_AJENO"
                n += 1
    assert n > 0, "las copias refutadas tienen que quedar registradas"

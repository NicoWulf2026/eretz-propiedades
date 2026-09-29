#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lo que los inventarios certificados saben y la preingestion del 03-09 no.

La snapshot servida sale de las filas CANDIDATE de la preingestion, que se
construyo el 3 de septiembre desde los artefactos del scraping legacy. Los
paquetes de certificacion posteriores solo le refrescaban CAMPOS a esas filas
(`property_freshest`). Medido el 29-09 sobre 362 agencias con cierre
certificado vigente:

- 10.172 propiedades certificadas que la preingestion no tiene: 52 agencias
  certificadas no tenian NINGUNA propiedad servida (5.019 filas de `generico`).
- 5.877 son el MISMO aviso con URL nueva: Tokko rehace el slug cuando cambia el
  titulo (`/p/7779042-...`), el hash cambia y el refresco no llegaba nunca.
- 2.607 servidas ya no estan en el inventario COMPLETO vigente de su agencia.
  Muestra de 30 en vivo: 25 dan 404 o redirigen sin la ficha.

Este modulo decide las tres cosas con la regla mas conservadora que se pudo
medir, y no escribe nada:

``nuevas``      se agregan solo si NADA indica que ya estan: ni hash, ni URL, ni
                el mismo `source_listing_id`, ni un numero de la URL que la
                preingestion ya tenga para esa agencia, ni el mismo titulo con
                el mismo precio, superficie y dormitorios. Ante la duda, no se
                agrega: servir dos veces la misma casa es peor que no servirla.
``alias``       el aviso con URL nueva refresca a la fila vieja por su hash, con
                la regla de `fusionar` de siempre (la identidad no cambia).
``retirables``  solo de agencias con cierre COMPLETO vigente (BEST_AVAILABLE no
                afirma inventario entero), y solo si la fila no aparece por
                ninguna de las vias anteriores.

Solo cuenta el cierre VIGENTE de cada agencia segun el ledger
(`vigentes_por_agencia`, NEXT-001): un paquete certificado viejo de una agencia
que hoy es NEEDS_FIX no aporta nada.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from connectors.base import calcular_hash_dedup  # noqa: E402
from connectors.texto import plegar  # noqa: E402
from scripts.ledger_de_certificacion import vigentes_por_agencia  # noqa: E402
from scripts.preingestion_rebuild import (EXTERNAL_PORTAL_HOSTS,  # noqa: E402
                                          derive_contract, host,
                                          normalizar_url, sanitize_count,
                                          sanitize_description)
from scripts.write_eligibility import motivo_rechazo  # noqa: E402

CERTIFICADOS = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE")
COMPLETO = "CERTIFIED_COMPLETE"
VERSION = "snapshot_certificadas_v1"


def numeros_de_url(url: Any) -> set[str]:
    """Los numeros de cuatro cifras o mas de la ruta y la consulta.

    Casi todas las plataformas ponen ahi el id del aviso (`/p/7779042-...`,
    `/propiedad/213750_...`, `?id=1769`). Tambien puede caer una altura de
    calle: eso solo hace mas conservadora la comparacion, nunca menos.
    """
    partes = urllib.parse.urlparse(str(url or ""))
    return set(re.findall(r"\d{4,}", partes.path + "?" + partes.query))


def firma(fila: dict[str, Any]) -> tuple | None:
    titulo = fila.get("titulo")
    titulo = plegar(titulo if isinstance(titulo, str) else None, conservar_espacios=False)
    if not titulo:
        return None
    return (titulo, fila.get("precio"), fila.get("superficie_total"), fila.get("dormitorios"))


@dataclass
class Conocidas:
    """Lo que la preingestion ya tiene, en cualquier estado."""

    hashes: dict[str, str] = field(default_factory=dict)            # hash -> status
    urls: set[str] = field(default_factory=set)
    avisos: dict[tuple[str, str], list[tuple[str, str]]] = field(default_factory=dict)
    numeros: dict[str, set[str]] = field(default_factory=dict)
    firmas: set[tuple] = field(default_factory=set)
    # Lo servible (CANDIDATE) por agencia, para decidir retiros.
    candidatas: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def conocidas_de(conexion: sqlite3.Connection) -> Conocidas:
    c = Conocidas()
    for crudo, canonical, status, hash_dedup, url_normalizada in conexion.execute(
            "select row_json, canonical_id, status, hash_dedup, url_normalized from rows"):
        fila = json.loads(crudo)
        if hash_dedup:
            c.hashes[hash_dedup] = status
        if url_normalizada:
            c.urls.add(url_normalizada)
        aviso = str(fila.get("source_listing_id") or "").strip()
        if canonical and aviso:
            c.avisos.setdefault((canonical, aviso), []).append((hash_dedup, status))
        if canonical:
            c.numeros.setdefault(canonical, set()).update(numeros_de_url(fila.get("source_url")))
        if status == "CANDIDATE":
            f = firma(fila)
            if f is not None:
                c.firmas.add((canonical,) + f)
            c.candidatas.setdefault(canonical, []).append(
                {"hash_dedup": hash_dedup, "source_url": fila.get("source_url"),
                 "source_listing_id": aviso})
    return c


def paquetes_vigentes(paquetes: Path, ledger: Path
                      ) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """(certificacion, filas de run2) de cada agencia cuyo cierre VIGENTE es certificado."""
    vigentes, _ambiguas = vigentes_por_agencia(ledger)
    fuera = []
    for carpeta in sorted(paquetes.iterdir()):
        archivo = carpeta / "certification.json"
        filas_run2 = carpeta / "properties_run2.jsonl"
        if not archivo.is_file() or not filas_run2.is_file():
            continue
        cert = json.loads(archivo.read_text(encoding="utf-8"))
        vigente = vigentes.get(cert.get("canonical_agency_id"))
        if (not vigente or vigente.get("status") not in CERTIFICADOS
                or cert.get("status") != vigente.get("status")
                or cert.get("checked_at") != vigente.get("checked_at")):
            continue
        filas = [json.loads(linea) for linea in filas_run2.read_text(encoding="utf-8").splitlines()
                 if linea.strip()]
        fuera.append((cert, filas))
    return fuera


@dataclass
class Decision:
    nuevas: list[dict[str, Any]] = field(default_factory=list)
    alias: dict[str, dict[str, Any]] = field(default_factory=dict)   # hash viejo -> fila fresca
    retirables: set[str] = field(default_factory=set)
    motivos: Counter = field(default_factory=Counter)


def decidir(vigentes: list[tuple[dict[str, Any], list[dict[str, Any]]]],
            conocidas: Conocidas, ajenas: set[str] | frozenset[str] = frozenset()) -> Decision:
    d = Decision()
    propuestas: list[dict[str, Any]] = []
    for cert, filas in vigentes:
        agencia = cert["canonical_agency_id"]
        if agencia in ajenas:
            d.motivos["omitida_web_ajena"] += len(filas)
            continue
        propios_hash = {f.get("hash_dedup") for f in filas}
        propias_urls = {normalizar_url(str(f.get("source_url") or "")) for f in filas}
        propios_avisos = {str(f.get("source_listing_id") or "").strip() for f in filas} - {""}
        propios_numeros: set[str] = set()
        for f in filas:
            propios_numeros |= numeros_de_url(f.get("source_url"))
        for fila in filas:
            hash_dedup = fila.get("hash_dedup")
            aviso = str(fila.get("source_listing_id") or "").strip()
            if hash_dedup in conocidas.hashes:
                d.motivos["ya_en_preingestion"] += 1
                continue
            if normalizar_url(str(fila.get("source_url") or "")) in conocidas.urls:
                d.motivos["url_ya_en_preingestion"] += 1
                continue
            previas = conocidas.avisos.get((agencia, aviso)) if aviso else None
            if previas:
                servibles = [h for h, status in previas if status == "CANDIDATE"]
                if len(servibles) == 1:
                    d.alias.setdefault(servibles[0], fila)
                    d.motivos["mismo_aviso_url_nueva"] += 1
                else:
                    d.motivos["mismo_aviso_sin_fila_servible_unica"] += 1
                continue
            if numeros_de_url(fila.get("source_url")) & conocidas.numeros.get(agencia, set()):
                d.motivos["numero_de_url_ya_visto"] += 1
                continue
            f = firma(fila)
            if f is not None and (agencia,) + f in conocidas.firmas:
                d.motivos["misma_firma"] += 1
                continue
            # Sin FK de `main` (cohorte canonica, P6: certificar != promover): se
            # sirve en la snapshot LOCAL solo si su identidad es la canonica de
            # verdad -el hash sale del id canonico y la URL-. No se escribe a main.
            if (fila.get("inmobiliaria_id") is None
                    and hash_dedup != calcular_hash_dedup(agencia, fila.get("source_url"))):
                d.motivos["agencia_sin_id_eretz"] += 1
                continue
            if host(str(fila.get("source_url") or "")) in EXTERNAL_PORTAL_HOSTS:
                d.motivos["portal"] += 1
                continue
            rechazo = motivo_rechazo(fila)
            if rechazo:
                d.motivos["rechazo:" + str(rechazo)] += 1
                continue
            propuestas.append(dict(fila, _agencia_del_paquete=agencia,
                                   _certificado=cert.get("checked_at"),
                                   _cierre=cert.get("status")))
        if cert.get("status") == COMPLETO:
            for previa in conocidas.candidatas.get(agencia, []):
                if (previa["hash_dedup"] in propios_hash
                        or normalizar_url(str(previa["source_url"] or "")) in propias_urls
                        or (previa["source_listing_id"]
                            and previa["source_listing_id"] in propios_avisos)
                        or numeros_de_url(previa["source_url"]) & propios_numeros):
                    continue
                d.retirables.add(previa["hash_dedup"])

    # Una URL que reclaman dos agencias no es de ninguna (la misma regla de la
    # preingestion, MULTI_AGENCY_NORMALIZED_URL).
    duenos: dict[str, set[str]] = {}
    for fila in propuestas:
        duenos.setdefault(normalizar_url(str(fila["source_url"])), set()).add(
            fila["_agencia_del_paquete"])
    vistas: set[str] = set()
    for fila in propuestas:
        url = normalizar_url(str(fila["source_url"]))
        if len(duenos[url]) > 1:
            d.motivos["url_de_varias_agencias"] += 1
            continue
        if url in vistas or fila["hash_dedup"] in vistas:
            d.motivos["repetida_en_paquetes"] += 1
            continue
        vistas.update((url, fila["hash_dedup"]))
        d.nuevas.append(preparar(fila))
        d.motivos["nueva"] += 1
    return d


def preparar(fila: dict[str, Any]) -> dict[str, Any]:
    """La misma limpieza de campos que la preingestion le hace a cada fila."""
    fila = dict(fila)
    fila["descripcion"], _limpia = sanitize_description(fila.get("descripcion"))
    for campo in ("banos", "dormitorios", "ambientes"):
        fila[campo], _motivo = sanitize_count(fila, campo)
    fila["operacion"], fila["tipo_propiedad"], derivados = derive_contract(fila)
    fila["_snapshot_certificadas"] = {
        "version": VERSION,
        "agencia": fila.pop("_agencia_del_paquete"),
        "certificado_en": fila.pop("_certificado"),
        "cierre": fila.pop("_cierre"),
        "campos_derivados": derivados,
    }
    return fila

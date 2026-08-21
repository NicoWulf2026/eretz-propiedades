#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auditoria GRATUITA de las webs que ERETZ ya tiene cargadas.

Antes de pagar un buscador conviene saber cuantas inmobiliarias se resuelven con
lo que ya tenemos. Esta fase no emite una sola consulta paga: se limita a las
URLs guardadas en main y staging, las verifica, y produce el numero exacto de
entidades que siguen necesitando busqueda externa.

Dos decisiones de diseno que ahorran trabajo de verdad:

  - Se trabaja por ENTIDAD CANONICA, no por fila. Una inmobiliaria con tres
    alias es una sola investigacion.

  - Las descargas se cachean por DOMINIO. Varias entidades pueden apuntar al
    mismo sitio -sucursales, un grupo, o un error de carga-, y bajar la home
    cuatro veces no agrega informacion.

Tener una URL cargada no prueba que sea correcta, y NO tenerla tampoco prueba
que no exista. Por eso una entidad sin URL queda en NO_EXISTING_WEB_DATA y
nunca en NOT_FOUND: eso ultimo solo puede afirmarse despues de buscar.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")
wd = _load("agency_web_discovery")
sc = _load("identity_scoring")

AUDIT_VERSION = "free_web_audit_v1"
UA = "Mozilla/5.0 (compatible; ERETZ-AgencyWebCheck/1.0; +contacto@eretz)"

# Estados de esta fase.
VERIFIED = wd.VERIFIED
HIGH = wd.HIGH_CONFIDENCE
AMBIG = wd.AMBIGUOUS
INACTIVE = wd.INACTIVE
WRONG = "INVALID_OR_WRONG_ENTITY"
PORTAL = "PORTAL_NOT_OFFICIAL"
SIN_DATO = "NO_EXISTING_WEB_DATA"
OFICINA_RED = wd.NO_SITE


def url_normalizada(url: str) -> str:
    """Forma canonica para no verificar el mismo sitio tres veces.

    `http://ejemplo.com`, `https://ejemplo.com/` y `https://www.ejemplo.com`
    son el mismo destino; lo unico que importa para bajar es el dominio.
    """
    u = (url or "").strip()
    if not u:
        return ""
    if not re.match(r"^\w+://", u):
        u = "https://" + u
    dom = wd.dominio(u)
    return f"https://{dom}" if dom else ""


def bajar(url: str, timeout: int = 12) -> dict:
    """Una descarga cortes, siguiendo redirects. Sin reintentos."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            html = r.read(200_000).decode("utf-8", "ignore")
            final = r.geturl()
            m = re.search(r"<title[^>]*>(.{0,200}?)</title>", html, re.I | re.S)
            titulo = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html,
                           flags=re.I | re.S)
            texto = re.sub(r"<[^>]+>", " ", texto)
            texto = re.sub(r"\s+", " ", texto)[:12000]
            return {"url": final, "http": r.status, "titulo": titulo, "texto": texto,
                    "html": html[:60000], "redirigio": wd.dominio(final) != wd.dominio(url)}
    except urllib.error.HTTPError as e:
        return {"url": url, "http": e.code, "titulo": "", "texto": "", "html": "",
                "redirigio": False}
    except Exception as e:
        return {"url": url, "http": None, "titulo": "", "texto": "", "html": "",
                "redirigio": False, "error": type(e).__name__}


def eretz_filas(base: str) -> dict[str, dict]:
    """Filas de main y staging, indexadas por `tabla:id`."""
    out: dict[str, dict] = {}
    for tabla in ("main", "staging"):
        args = ["vercel.cmd", "curl", f"{base}/api/agency-bridge?op={tabla}", "-s"]
        p = subprocess.run(args, cwd=FRONTEND, capture_output=True, text=True,
                           encoding="utf-8", errors="ignore", timeout=1800)
        for linea in p.stdout.splitlines():
            linea = linea.strip()
            if not linea.startswith("{"):
                continue
            try:
                datos = json.loads(linea)
            except json.JSONDecodeError:
                continue
            for f in datos.get("filas", []):
                out[f"{tabla}:{f['id']}"] = {**f, "tabla": tabla}
            break
    return out


def clasificar(entidad: dict, sitio: dict | None, url_previa: str) -> tuple[str, dict]:
    """Decide el estado de la URL preexistente y explica por que."""
    if not url_previa:
        return SIN_DATO, {"motivo": "ERETZ no tiene web cargada para esta entidad"}

    if wd.es_portal(url_previa):
        return PORTAL, {"motivo": f"{wd.dominio(url_previa)} es un portal o red social"}

    marca = wd.franquicia_de_dominio(url_previa)
    if marca:
        if wd.es_pagina_de_oficina(url_previa):
            return OFICINA_RED, {"motivo": "pagina de oficina dentro del dominio de la red",
                                 "official_office_page": url_previa}
        return PORTAL, {"motivo": f"{wd.dominio(url_previa)} es el dominio de la red, "
                                  f"no identifica una oficina"}

    if sitio is None or sitio.get("http") is None:
        return INACTIVE, {"motivo": "el dominio no responde"}
    if sitio.get("http", 0) >= 400:
        return INACTIVE, {"motivo": f"responde {sitio['http']}"}

    p = sc.puntuar(entidad, sitio)
    ev = {"identity_score": p.total, "positive_evidence": [s.clave for s in p.positivas],
          "negative_evidence": [s.clave for s in p.negativas],
          "explicacion": p.explicacion}
    if p.rechazado_por_rubro:
        ev["motivo"] = f"el sitio es de {p.rubro_detectado}, no de esta inmobiliaria"
        return WRONG, ev
    veredicto = sc.clasificar(p)
    if veredicto == "VERIFIED":
        return VERIFIED, ev
    if veredicto == "HIGH_CONFIDENCE":
        return HIGH, ev
    # Responde y no es de otro rubro, pero nada lo ata a esta inmobiliaria.
    ev["motivo"] = "responde pero no hay evidencia de que sea esta entidad"
    return AMBIG, ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    entidades = [json.loads(l) for l in
                 (dd / "crosswalk_final.jsonl").open(encoding="utf-8") if l.strip()]
    if a.limite:
        entidades = entidades[:a.limite]
    print(f"### AUDITORIA GRATUITA DE WEBS EXISTENTES ###", flush=True)
    print(f"  entidades canonicas inmobiliarias: {len(entidades):,}", flush=True)

    filas = eretz_filas(a.base)
    print(f"  filas ERETZ leidas:                {len(filas):,}", flush=True)

    # --- URL preexistente y datos de contacto de cada entidad ---
    # El contacto lo aporta ERETZ, no Roomix: Roomix solo publica nombre y logo.
    # Sin esta mezcla el puntaje se queda en 49 -nombre, localidad y rubro- y
    # nunca alcanza el umbral de VERIFIED, no porque falte evidencia sino
    # porque no se la estaba mirando.
    por_entidad: dict[str, str] = {}
    for e in entidades:
        cand = e.get("crosswalk_candidato") or {}
        clave = f"{cand.get('tabla')}:{cand.get('id')}" if cand.get("id") else None
        fila = filas.get(clave or "") or {}
        por_entidad[e["stable_id"]] = url_normalizada(fila.get("web") or "")
        for origen, destino in (("telefono", "telefono"), ("email_principal", "email"),
                                ("direccion", "direccion"), ("ciudad", "ciudad"),
                                ("provincia", "provincia")):
            if not e.get(destino) and fila.get(origen):
                e[destino] = fila[origen]

    dominios = sorted({u for u in por_entidad.values() if u})
    print(f"  con URL preexistente:              "
          f"{sum(1 for u in por_entidad.values() if u):,}", flush=True)
    print(f"  dominios distintos a verificar:    {len(dominios):,}", flush=True)

    # --- una descarga por dominio, no por entidad ---
    sitios: dict[str, dict] = {}
    hecho = 0
    for i in range(0, len(dominios), 60):
        trozo = dominios[i:i + 60]
        with ThreadPoolExecutor(max_workers=a.hilos) as ex:
            for url, sitio in zip(trozo, ex.map(bajar, trozo)):
                sitios[url] = sitio
        hecho += len(trozo)
        print(f"    descargados {hecho}/{len(dominios)}", flush=True)
        time.sleep(0.2)

    # --- clasificacion por entidad ---
    salida, cola = [], []
    estados: Counter = Counter()
    scrape: Counter = Counter()
    compartidos: dict[str, list[str]] = defaultdict(list)

    for e in entidades:
        url = por_entidad[e["stable_id"]]
        sitio = sitios.get(url)
        estado, ev = clasificar(e, sitio, url)
        estados[estado] += 1
        if url:
            compartidos[wd.dominio(url)].append(e["stable_id"])

        sc_estado = None
        if estado in (VERIFIED, HIGH) and sitio:
            diag = sc.diagnosticar_scrapeabilidad(sitio)
            sc_estado = diag["scrapeability_status"]
            scrape[sc_estado] += 1
            ev["plataforma"] = diag.get("plataforma")

        fila = {
            "canonical_agency_id": e["stable_id"],
            "canonical_name": e["nombre_original"],
            "nombre_normalizado": e["nombre_normalizado"],
            "tipo": e["tipo"],
            "franchise": e.get("red_franquicia"),
            "city": e.get("ciudad") or (e.get("zonas_observadas") or [None])[0],
            "province": e.get("provincia"),
            "eretz_status": e.get("crosswalk"),
            "eretz_id": (e.get("crosswalk_candidato") or {}).get("id"),
            "previous_url": url or None,
            "previous_url_status": estado,
            "selected_domain": (sitio or {}).get("url") if estado in (VERIFIED, HIGH) else None,
            "selected_office_page": ev.get("official_office_page"),
            "status": estado,
            "identity_score": ev.get("identity_score"),
            "positive_evidence": ev.get("positive_evidence", []),
            "negative_evidence": ev.get("negative_evidence", []),
            "reason": ev.get("motivo") or ev.get("explicacion"),
            "redirect_chain": [url, (sitio or {}).get("url")] if (sitio or {}).get("redirigio") else [],
            "scrapeability_status": sc_estado,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "verifier_version": wd.VERIFIER_VERSION,
            "audit_version": AUDIT_VERSION,
            "search_provider": None, "search_queries": [], "search_queries_count": 0,
        }
        salida.append(fila)

        # Todo lo que no quedo resuelto necesita buscador externo.
        if estado not in (VERIFIED, HIGH, OFICINA_RED):
            cola.append({
                "canonical_id": e["stable_id"],
                "nombre": e["nombre_original"],
                "aliases": e.get("variantes_de_nombre", []),
                "localidad": e.get("ciudad") or (e.get("zonas_observadas") or [None])[0],
                "provincia": e.get("provincia"),
                "franquicia": e.get("red_franquicia"),
                "matricula": e.get("matricula", []),
                "telefono": e.get("telefono"), "email": e.get("email"),
                "motivo_unresolved": estado,
                "existing_url_status": estado,
                "existing_url": url or None,
                "avisos_observados": e.get("avisos_observados", 0),
            })

    # Prioridad: mas evidencia primero, y las oficinas de franquicia arriba
    # porque su perfil oficial suele resolverse con una sola consulta.
    cola.sort(key=lambda r: (0 if r["franquicia"] else 1, -(r["avisos_observados"] or 0)))
    for i, r in enumerate(cola, 1):
        r["prioridad"] = i

    (dd / "agency_web_directory.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in salida) + "\n", encoding="utf-8")
    (dd / "web_search_unresolved.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in cola) + "\n", encoding="utf-8")

    print(f"\n### RESULTADO ###", flush=True)
    for k, v in estados.most_common():
        print(f"  {k:28} {v:6,}", flush=True)
    print(f"\n  scrapeabilidad (sobre verificadas):", flush=True)
    for k, v in scrape.most_common():
        print(f"    {k:30} {v:6,}", flush=True)
    multi = {k: v for k, v in compartidos.items() if len(v) > 1}
    print(f"\n  dominios compartidos por >1 entidad: {len(multi):,}", flush=True)
    print(f"  COLA PARA SEARCH API: {len(cola):,}", flush=True)
    print(f"  artefactos -> agency_web_directory.jsonl / web_search_unresolved.jsonl", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

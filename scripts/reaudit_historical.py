#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-auditoria gratuita de inmobiliarias historicamente no scrapeables.

Muchas fueron descartadas hace tiempo por logica vieja o incompleta: se las
marco error, bloqueada, sin listados o "requiere js" y nunca se volvio a mirar.
Los sitios cambian; el veredicto viejo no.

Esta pasada NO busca webs nuevas: reusa unicamente URLs que ya estaban
guardadas (dominio elegido, url previa, web cargada en ERETZ, candidatas de la
busqueda anterior). Sin buscadores, sin APIs pagas, sin descargar propiedades.

Una precaucion que vale mas que el volumen: cuando la URL nunca fue confirmada
como de esa inmobiliaria -las AMBIGUOUS y las de segunda pasada-, que el sitio
este vivo no alcanza. Promoverla a READY sin verificar identidad seria
adjudicarle a una inmobiliaria la web de otra, que es peor que dejarla afuera.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


aud = _load("audit_existing_webs")
dp = _load("detect_platform")
ident = _load("identity_scoring")

DETECTOR_VERSION = "historical_reaudit_v1"

READY = "SCRAPE_SOURCE_READY"
REQUIRES_JS = "REQUIRES_JS"
BLOCKED = "BLOCKED"
NO_LISTINGS = "NO_LISTINGS"
INACTIVE = "INACTIVE"
ERROR = "ERROR"
UNSUPPORTED = "UNSUPPORTED_PLATFORM"

# Estados historicos que esta pasada vuelve a mirar.
NO_SCRAPEABLES = {
    "SCRAPE_SOURCE_NO_LISTINGS", "SCRAPE_SOURCE_BLOCKED", "SCRAPE_SOURCE_REQUIRES_JS",
    "SCRAPE_SOURCE_UNKNOWN", "SCRAPE_SOURCE_ERROR", "SCRAPE_SOURCE_INACTIVE",
}
ESTADOS_WEB_NO_RESUELTOS = {
    "OFFICIAL_WEB_AMBIGUOUS", "SEARCH_SECOND_PASS_REQUIRED", "OFFICIAL_WEB_INACTIVE",
    "PORTAL_NOT_OFFICIAL", "NO_INDEPENDENT_WEBSITE", "NO_EXISTING_WEB_DATA",
}

# Dominios que no son una fuente propia: aunque respondan, no se scrapean como
# web de la inmobiliaria.
NO_ES_FUENTE_PROPIA = re.compile(
    r"(zonaprop|argenprop|mercadolibre|properati|inmuebles24|inmobusqueda|"
    r"buscainmueble|clasificados|facebook\.com|instagram\.com|linkedin\.com|"
    r"twitter\.com|x\.com/|youtube\.com|wa\.me|whatsapp\.com|linktr\.ee|"
    r"blogspot\.|wordpress\.com/|sites\.google\.com|paginasamarillas|"
    r"guiaempresas|cylex|opendi|infoisinfo)", re.I)

# Dominios estacionados o en venta: responden 200 y no son nada.
ESTACIONADO = re.compile(
    r"(this domain (is|may be) for sale|dominio en venta|domain for sale|"
    r"parked (domain|free)|sedoparking|godaddy\.com/forsale|"
    r"under construction|en construccion|proximamente|coming soon|"
    r"default web site page|apache2? (ubuntu|debian) default)", re.I)


def urls_reutilizables(fila: dict) -> list[str]:
    """URLs que ya estaban guardadas, en orden de confianza.

    El dominio elegido primero, las candidatas de la busqueda anterior al final:
    esas son las menos confiables y solo se usan si no hay nada mejor.
    """
    out: list[str] = []
    for k in ("selected_domain", "current_eretz_web", "previous_url", "selected_office_page"):
        v = fila.get(k)
        if isinstance(v, str) and v.strip().startswith("http"):
            out.append(v.strip())
    for c in (fila.get("candidate_urls") or []):
        u = c.get("url") if isinstance(c, dict) else c
        if isinstance(u, str) and u.startswith("http"):
            out.append(u)
    vistos, limpio = set(), []
    for u in out:
        clave = u.rstrip("/").lower()
        if clave not in vistos:
            vistos.add(clave)
            limpio.append(u)
    return limpio[:4]


def clasificar_sitio(sitio: dict, url: str) -> tuple[str, str]:
    """(estado, motivo) mirando solo lo que ya se bajo."""
    http = sitio.get("http")
    if NO_ES_FUENTE_PROPIA.search(sitio.get("url") or url):
        return UNSUPPORTED, "portal, red social o directorio: no es fuente propia"
    if http in (403, 401, 429):
        return BLOCKED, f"http {http}"
    if http in (404, 410):
        return INACTIVE, f"http {http}"
    if http is None or (isinstance(http, int) and http >= 500):
        return ERROR, f"sin respuesta o http {http}"
    if http != 200:
        return ERROR, f"http {http}"

    blob = " ".join(str(sitio.get(k) or "") for k in ("titulo", "texto"))
    if ESTACIONADO.search(blob[:4000]):
        return INACTIVE, "dominio estacionado o sitio sin contenido"
    if len(str(sitio.get("html") or "")) < 500:
        return INACTIVE, "respuesta vacia"

    plataforma, _, _ = dp.detectar_plataforma(sitio)
    if dp.tiene_listados(sitio) or dp.detectar_api(sitio) or dp.tiene_json_embebido(sitio):
        return READY, f"inventario visible en el HTML servido (plataforma: {plataforma or 'propia'})"
    if dp.requiere_js(sitio, plataforma):
        return REQUIRES_JS, f"el HTML servido no trae inventario ({plataforma or 'SPA'})"
    return NO_LISTINGS, "responde y es un sitio real, pero sin inventario a la vista"


def necesita_identidad(fila: dict) -> bool:
    """Si la URL nunca fue confirmada como de esta inmobiliaria, hay que
    verificar identidad antes de darla por buena."""
    return not fila.get("selected_domain")


def procesar(fila: dict) -> dict:
    urls = urls_reutilizables(fila)
    old = fila.get("scrapeability_status") or fila.get("status") or "UNKNOWN"
    base = {
        "inmobiliaria_id": fila.get("canonical_agency_id"),
        "eretz_id": fila.get("eretz_id"),
        "nombre": fila.get("canonical_name"),
        "old_status": old,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "detector_version": DETECTOR_VERSION,
    }
    if not urls:
        return {**base, "url": None, "new_status": ERROR,
                "evidence": {"motivo": "no hay ninguna URL guardada para reintentar"}}

    exigir_identidad = necesita_identidad(fila)
    mejor = None
    for url in urls:
        sitio = aud.bajar(url)
        estado, motivo = clasificar_sitio(sitio, url)
        ev = {"motivo": motivo, "http": sitio.get("http"),
              "titulo": (sitio.get("titulo") or "")[:120],
              "final_url": sitio.get("url"), "urls_probadas": len(urls)}

        if estado == READY and exigir_identidad:
            # Vivo no es lo mismo que suyo.
            p = ident.puntuar(fila, sitio)
            veredicto = ident.clasificar(p)
            ev["identity_score"] = p.total
            ev["identity_verdict"] = veredicto
            if veredicto not in ("VERIFIED", "HIGH_CONFIDENCE"):
                estado = UNSUPPORTED
                ev["motivo"] = (f"el sitio publica inventario pero no se pudo confirmar "
                                f"que sea de esta inmobiliaria ({veredicto})")

        cand = {**base, "url": url, "new_status": estado, "evidence": ev}
        if estado == READY:
            return cand
        # Se queda con el diagnostico menos terminal visto hasta ahora.
        orden = {READY: 0, REQUIRES_JS: 1, NO_LISTINGS: 2, BLOCKED: 3,
                 UNSUPPORTED: 4, INACTIVE: 5, ERROR: 6}
        if mejor is None or orden[estado] < orden[mejor["new_status"]]:
            mejor = cand
    return mejor


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    directorio = [json.loads(l) for l in
                  (dd / "agency_web_directory.jsonl").open(encoding="utf-8") if l.strip()]

    # El universo se arma de los artefactos, no de una lista fija: todo lo que
    # no quedo READY y conserva alguna URL para reintentar.
    universo = []
    for x in directorio:
        se = x.get("scrapeability_status")
        if se == "SCRAPE_SOURCE_READY":
            continue
        if se in NO_SCRAPEABLES or x.get("status") in ESTADOS_WEB_NO_RESUELTOS:
            universo.append(x)
    con_url = [x for x in universo if urls_reutilizables(x)]

    print("### RE-AUDITORIA HISTORICA GRATUITA ###", flush=True)
    print(f"  HISTORICAL_NON_SCRAPEABLE_TOTAL: {len(universo):,}", flush=True)
    print(f"  con URL reutilizable (re-auditables gratis): {len(con_url):,}", flush=True)
    print(f"  sin ninguna URL (requeriria buscador, se omiten): "
          f"{len(universo) - len(con_url):,}", flush=True)
    print(f"  estados historicos de origen:", flush=True)
    for k, v in Counter(x.get("scrapeability_status") or x.get("status")
                        for x in universo).most_common():
        print(f"    {k:32} {v:6,}", flush=True)

    salida = dd / "historical_scrapeability_reaudit.jsonl"
    hechas: set[str] = set()
    if salida.exists():
        for l in salida.open(encoding="utf-8"):
            if l.strip():
                try:
                    hechas.add(json.loads(l)["inmobiliaria_id"])
                except (ValueError, KeyError):
                    continue
    pendientes = [x for x in con_url if x["canonical_agency_id"] not in hechas]
    if a.limite:
        pendientes = pendientes[:a.limite]
    print(f"  ya re-auditadas: {len(hechas):,}   pendientes ahora: {len(pendientes):,}\n",
          flush=True)

    hecho = 0
    with salida.open("a", encoding="utf-8") as fh:
        for i in range(0, len(pendientes), 30):
            trozo = pendientes[i:i + 30]
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r in ex.map(procesar, trozo):
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            fh.flush()
            hecho += len(trozo)
            if hecho % 150 == 0 or hecho >= len(pendientes):
                print(f"    {min(hecho, len(pendientes))}/{len(pendientes)}", flush=True)
            time.sleep(0.2)

    filas = [json.loads(l) for l in salida.open(encoding="utf-8") if l.strip()]
    print(f"\n### RESULTADO ###", flush=True)
    print(f"  re-auditadas: {len(filas):,}", flush=True)
    print(f"\n  nuevo estado:", flush=True)
    for k, v in Counter(r["new_status"] for r in filas).most_common():
        print(f"    {k:24} {v:6,}  ({v/max(len(filas),1)*100:5.1f}%)", flush=True)

    rescatadas = [r for r in filas if r["new_status"] == READY]
    print(f"\n  RESCATADAS (no scrapeable -> READY): {len(rescatadas):,}", flush=True)
    print(f"  cambios old -> new mas frecuentes:", flush=True)
    for (o, n), v in Counter((r["old_status"], r["new_status"])
                             for r in filas).most_common(10):
        flecha = "  <-- rescate" if n == READY else ""
        print(f"    {o:30} -> {n:22} {v:5,}{flecha}", flush=True)
    print(f"\n  artefacto -> historical_scrapeability_reaudit.jsonl", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

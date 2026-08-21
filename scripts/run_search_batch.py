#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Lote de descubrimiento de webs con Tavily, dentro del nivel gratuito.

Una consulta por entidad y un tope duro de consumo. El tope no depende de que
alguien mire el contador: el proveedor se niega a emitir la consulta 1.451, y
ante un 402/429/432/433 se da por agotado y corta. No se habilita facturacion.

La prioridad importa porque los creditos alcanzan para una fraccion del padron.
Se atienden primero las oficinas de franquicia -su perfil oficial suele
resolverse con una sola consulta-, despues las que mas publican, y despues las
que traen telefono, email o matricula, porque son las que el verificador puede
confirmar de verdad en vez de dejar en alta confianza.

Ninguna entidad recibe una segunda consulta mientras quede otra sin ninguna.

Lo que no se resuelve NO queda en NOT_FOUND: queda en
SEARCH_SECOND_PASS_REQUIRED. Una sola busqueda basica no autoriza a afirmar que
una inmobiliaria no tiene web.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
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


d = _load("eretz_dedupe")
wd = _load("agency_web_discovery")
sc = _load("identity_scoring")
sp = _load("search_provider")
aud = _load("audit_existing_webs")

SEGUNDA_PASADA = "SEARCH_SECOND_PASS_REQUIRED"
RESUELTO = (wd.VERIFIED, wd.HIGH_CONFIDENCE, wd.NO_SITE)


def consulta_de(e: dict) -> str:
    """Una sola consulta, con los datos reales que tengamos.

    La localidad entra siempre que exista: es lo que separa a las homonimas, que
    son el error mas caro de esta fase.
    """
    nombre = (e.get("nombre") or "").strip()
    if not nombre:
        return ""
    partes = [f'"{nombre}"']
    if e.get("franquicia"):
        partes.append("inmobiliaria")
    else:
        partes.append("inmobiliaria")
    loc = (e.get("localidad") or "").replace("-", " ").strip()
    prov = (e.get("provincia") or "").strip()
    if loc:
        partes.append(loc)
    if prov and prov.lower() not in loc.lower():
        partes.append(prov)
    if not loc and not prov:
        partes.append("Argentina")
    return " ".join(partes)


def prioridad(e: dict) -> tuple:
    """Orden de atencion. Menor tupla = se atiende antes."""
    tiene_contacto = bool(e.get("telefono") or e.get("email") or e.get("matricula"))
    return (
        0 if e.get("franquicia") else 1,
        -(e.get("avisos_observados") or 0),
        0 if tiene_contacto else 1,
        0 if e.get("localidad") else 1,
    )


def volcar_directorio(dd: Path, directorio: dict, resultados: dict) -> None:
    """Escribe el directorio con lo resuelto hasta ahora. Determinista."""
    for cid, r in resultados.items():
        if cid in directorio:
            directorio[cid].update(r)
    orden = sorted(directorio.values(), key=lambda x: x["canonical_agency_id"])
    (dd / "agency_web_directory.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in orden) + "\n",
        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--proveedor", choices=("tavily", "serper"), default="tavily")
    ap.add_argument("--cola", default=None, help="jsonl de entrada; por defecto el de Tavily")
    ap.add_argument("--salida-cola", default=None)
    ap.add_argument("--tope", type=int, default=1450)
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--prueba", action="store_true", help="una sola consulta y salir")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    entrada = dd / (a.cola or "web_search_unresolved.jsonl")
    pendientes = [json.loads(l) for l in entrada.open(encoding="utf-8") if l.strip()]
    directorio = {x["canonical_agency_id"]: x for x in
                  (json.loads(l) for l in
                   (dd / "agency_web_directory.jsonl").open(encoding="utf-8") if l.strip())}
    ya = {k for k, v in directorio.items() if v["status"] in RESUELTO}
    cola = [e for e in pendientes if e["canonical_id"] not in ya]
    cola.sort(key=prioridad)

    motor = sp.Serper(tope=a.tope) if a.proveedor == "serper" else sp.Tavily(tope=a.tope)
    buscador = sp.ConCache(motor, dd / "search_cache.jsonl")
    if not buscador.disponible():
        print(f"{motor.ENV} ausente: no se ejecuta nada.", flush=True)
        return 3

    print(f"### LOTE {a.proveedor.upper()} (nivel gratuito) ###", flush=True)
    print(f"  pendientes al inicio:   {len(pendientes):,}", flush=True)
    print(f"  ya resueltas (se saltan): {len(ya):,}", flush=True)
    print(f"  elegibles esta corrida: {len(cola):,}", flush=True)
    print(f"  tope duro de consultas: {a.tope:,}", flush=True)

    estados: Counter = Counter()
    procesadas = 0
    rechazadas = 0
    racha_rechazos = 0
    resultados: dict[str, dict] = {}

    for e in cola:
        interno = buscador.interno
        if getattr(interno, "agotado", False):
            print(f"\n  TOPE ALCANZADO tras {interno.emitidas} consultas.", flush=True)
            break

        q = consulta_de(e)
        if not q:
            continue
        try:
            res = buscador.buscar(q, pais="AR", idioma="es", cantidad=8)
        except sp.ConsultaInvalida as exc:
            # Una consulta rechazada es un dato sobre ESA entidad, no sobre el
            # lote. Se anota y se sigue: confundir las dos cosas hizo que un
            # unico HTTP 400 cerrara una corrida con 5.500 entidades por delante.
            rechazadas += 1
            resultados[e["canonical_id"]] = {
                "status": SEGUNDA_PASADA, "selected_domain": None,
                "selected_office_page": None, "search_provider": a.proveedor,
                "search_queries": [q], "search_queries_count": 1,
                "candidate_urls": [], "scrapeability_status": None,
                "identity_score": None, "positive_evidence": [],
                "negative_evidence": [],
                "reason": f"el proveedor rechazo la consulta: {sp.redactar(str(exc))}",
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            estados[SEGUNDA_PASADA] += 1
            procesadas += 1
            racha_rechazos += 1
            # Una consulta rechazada es un accidente; una racha es una cuenta
            # sin saldo. Serper devuelve 400 -no 402- cuando se agota el free
            # tier, y sin esto el lote muele miles de entidades sin emitir una
            # sola consulta util.
            if racha_rechazos >= sp.RACHA_MAXIMA_RECHAZOS:
                print(f"\n  {racha_rechazos} rechazos seguidos: el proveedor "
                      f"dejo de atender. Se cierra el lote.", flush=True)
                break
            continue
        except RuntimeError as exc:
            msg = sp.redactar(str(exc))
            print(f"\n  proveedor detenido: {msg}", flush=True)
            break

        # Los portales no se visitan: no pueden ser la web oficial y bajarlos
        # solo gasta tiempo. Quedan igual como evidencia de la consulta.
        candidatas = []
        urls_vistas = set()
        for r in res:
            if not r.url or wd.es_portal(r.url):
                continue
            dom = wd.dominio(r.url)
            if dom in urls_vistas:
                continue
            urls_vistas.add(dom)
            candidatas.append(r)
            if len(candidatas) >= 4:
                break

        sitios = {}
        if candidatas:
            with ThreadPoolExecutor(max_workers=a.hilos) as ex:
                for r, sitio in zip(candidatas, ex.map(
                        lambda x: aud.bajar(x.url), candidatas)):
                    sitios[r.url] = sitio

        entidad = {
            "nombre_original": e["nombre"], "ciudad": e.get("localidad"),
            "provincia": e.get("provincia"), "telefono": e.get("telefono"),
            "email": e.get("email"), "matricula": e.get("matricula") or [],
            "red_franquicia": e.get("franquicia"), "zonas_observadas": [],
        }

        mejor, mejor_p, oficina = None, None, None
        for r in candidatas:
            sitio = sitios.get(r.url) or {}
            marca = wd.franquicia_de_dominio(r.url)
            if marca:
                if wd.es_pagina_de_oficina(r.url) and (
                        not e.get("franquicia") or marca == e["franquicia"]):
                    oficina = oficina or r.url
                continue
            if sitio.get("http") is None or sitio.get("http", 0) >= 400:
                continue
            p = sc.puntuar(entidad, sitio)
            if p.rechazado_por_rubro:
                continue
            if mejor_p is None or p.total > mejor_p.total:
                mejor, mejor_p = (r, sitio), p

        if mejor_p is None:
            estado = wd.NO_SITE if oficina else SEGUNDA_PASADA
            fila_extra = {"identity_score": None, "positive_evidence": [],
                          "negative_evidence": [],
                          "reason": ("perfil oficial dentro del dominio de la red" if oficina
                                     else "ninguna candidata resistio la verificacion")}
            elegido = None
        else:
            veredicto = sc.clasificar(mejor_p)
            estado = {"VERIFIED": wd.VERIFIED, "HIGH_CONFIDENCE": wd.HIGH_CONFIDENCE}.get(
                veredicto, wd.AMBIGUOUS)
            elegido = mejor[1].get("url") or mejor[0].url
            fila_extra = {"identity_score": mejor_p.total,
                          "positive_evidence": [s.clave for s in mejor_p.positivas],
                          "negative_evidence": [s.clave for s in mejor_p.negativas],
                          "reason": mejor_p.explicacion}

        sc_estado = None
        if estado in (wd.VERIFIED, wd.HIGH_CONFIDENCE) and mejor:
            diag = sc.diagnosticar_scrapeabilidad(mejor[1])
            sc_estado = diag["scrapeability_status"]

        resultados[e["canonical_id"]] = {
            "status": estado,
            "selected_domain": elegido if estado in (wd.VERIFIED, wd.HIGH_CONFIDENCE) else None,
            "selected_office_page": oficina,
            "search_provider": a.proveedor,
            "search_queries": [q],
            "search_queries_count": 1,
            "candidate_urls": [r.url for r in candidatas],
            "scrapeability_status": sc_estado,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **fila_extra,
        }
        estados[estado] += 1
        procesadas += 1
        racha_rechazos = 0

        if a.prueba:
            print(f"\n  PRUEBA -> {e['nombre'][:50]}", flush=True)
            print(f"    query: {q}", flush=True)
            print(f"    resultados: {len(res)} | candidatas: {len(candidatas)}", flush=True)
            print(f"    estado: {estado} | score: {fila_extra['identity_score']}", flush=True)
            print(f"    dominio: {elegido}", flush=True)
            return 0

        if procesadas % 25 == 0:
            # Checkpoint: si el proceso muere o hay que cortarlo, lo hecho
            # sobrevive. Escribir recien al final costo perder una corrida
            # entera de 2.400 entidades.
            volcar_directorio(dd, directorio, resultados)
            print(f"    {procesadas}/{len(cola)} | consultas={interno.emitidas} "
                  f"cache={buscador.hits} | {dict(estados)}", flush=True)

    # ---- artefactos deterministas ----
    for cid, r in resultados.items():
        if cid in directorio:
            directorio[cid].update(r)
    orden = sorted(directorio.values(), key=lambda x: x["canonical_agency_id"])
    (dd / "agency_web_directory.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in orden) + "\n", encoding="utf-8")

    resueltas = {k for k, v in directorio.items() if v["status"] in RESUELTO}
    restantes = [e for e in pendientes if e["canonical_id"] not in resueltas]
    salida_cola = dd / (a.salida_cola or "web_search_unresolved_after_tavily.jsonl")
    salida_cola.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in restantes) + "\n", encoding="utf-8")

    interno = buscador.interno
    print("\n### RESULTADO ###", flush=True)
    print(f"  entidades buscadas:      {procesadas:,}", flush=True)
    print(f"  consultas {a.proveedor}:{' '*(14-len(a.proveedor))}{interno.emitidas:,}", flush=True)
    print(f"  cache hits:              {buscador.hits:,}", flush=True)
    print(f"  consultas rechazadas:    {rechazadas:,}", flush=True)
    for k, v in estados.most_common():
        print(f"    {k:32} {v:6,}", flush=True)
    print(f"  pendientes restantes:    {len(restantes):,}", flush=True)
    cons = getattr(interno, "creditos_consumidos", None)
    if cons:
        print(f"  creditos consumidos (informados): {cons:,}", flush=True)
    print(f"  cola siguiente -> {salida_cola.name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

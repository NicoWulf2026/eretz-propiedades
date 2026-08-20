#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Busca y verifica la web oficial de cada inmobiliaria canonica.

Roomix no publica la web del anunciante -verificado en la ficha: solo hay nombre
y logo-, asi que el dominio hay que encontrarlo afuera y despues demostrar que
pertenece a esa inmobiliaria y no a otra.

Tres fases, en orden de costo creciente. La idea es no gastar una consulta paga
en algo que se resuelve gratis:

  A  La web que ERETZ ya tiene cargada. No se asume correcta: se valida. Si
     queda verificada, la entidad se cierra sin gastar nada.
  B  Dominios derivados del nombre. Baratos y sin costo por consulta.
  C  Buscador programatico. Solo para lo que sigue sin resolverse, con consultas
     progresivas y corte apenas hay evidencia suficiente.

Sin API key la fase C no corre y esas entidades quedan en SEARCH_API_PENDING.
NO en NOT_FOUND: eso significaria "se busco y no tiene web", que es una
afirmacion sobre la inmobiliaria y no sobre nuestras herramientas.

Reanudable: cada entidad resuelta se escribe y no se vuelve a investigar.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
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
sp = _load("search_provider")

UA = "Mozilla/5.0 (compatible; ERETZ-AgencyWebCheck/1.0; +contacto@eretz)"
TLDS = (".com.ar", ".com", ".ar")
RESUELTO = None  # se completa abajo, tras cargar wd


def candidatos_de_nombre(nombre: str) -> list[str]:
    """Dominios plausibles a partir del nombre.

    Las formas que una inmobiliaria suele registrar: el nombre completo sin
    espacios, el nucleo sin las palabras del rubro, y el nucleo con
    `propiedades`. Cada variante extra multiplica peticiones sin mejorar la
    probabilidad.
    """
    base = d.norm_name(nombre)
    if not base:
        return []
    toks = base.split()
    nucleo = [t for t in toks if t not in wd.RUIDO]
    formas = set()
    if toks:
        formas.add("".join(toks))
    if nucleo:
        formas.add("".join(nucleo))
        formas.add("".join(nucleo) + "propiedades")
        if len(nucleo) > 1:
            formas.add("".join(nucleo[:2]))
    out = []
    for f in sorted(formas):
        if 3 <= len(f) <= 40:
            for tld in TLDS:
                out.append(f"https://{f}{tld}")
    return out[:12]


def bajar(url: str, timeout: int = 12) -> "wd.Candidata":
    """Una peticion, sin reintentos. Un fallo es informacion, no un problema."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            cuerpo = r.read(180_000).decode("utf-8", "ignore")
            final = r.geturl()
            titulo = ""
            m = re.search(r"<title[^>]*>(.{0,200}?)</title>", cuerpo, re.I | re.S)
            if m:
                titulo = re.sub(r"\s+", " ", m.group(1)).strip()
            texto = re.sub(r"<script.*?</script>|<style.*?</style>", " ", cuerpo,
                           flags=re.I | re.S)
            texto = re.sub(r"<[^>]+>", " ", texto)
            texto = re.sub(r"\s+", " ", texto)[:8000]
            return wd.Candidata(url=final, origen="fetch", titulo=titulo, texto=texto,
                                http=r.status, redirects=[url] if final != url else [])
    except urllib.error.HTTPError as e:
        return wd.Candidata(url=url, origen="fetch", http=e.code)
    except Exception:
        # DNS inexistente, TLS roto o timeout: la candidata simplemente no esta.
        return wd.Candidata(url=url, origen="fetch", http=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--pausa", type=float, default=0.4)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    resuelto = (wd.VERIFIED, wd.HIGH_CONFIDENCE, wd.NO_SITE)

    padron = [json.loads(l) for l in
              (dd / "roomix_agency_directory.jsonl").open(encoding="utf-8") if l.strip()]
    cwin = _load("coverage_windows")
    objetivo = [e for e in padron if e.get("tipo") in cwin.CUENTA_COMO_AGENCIA]
    # Prioridad: primero las que ya tienen web en ERETZ -se cierran validando y
    # sin gastar consulta- y despues por volumen de avisos.
    objetivo.sort(key=lambda e: (0 if (e.get("current_eretz_web") or "").strip() else 1,
                                 -(e.get("avisos_observados") or 0)))

    salida = dd / "agency_web_directory.jsonl"
    hechas = wd.cargar_hechas(salida)
    pendientes = [e for e in objetivo if e["stable_id"] not in hechas]
    if a.limite:
        pendientes = pendientes[:a.limite]

    buscador = sp.ConCache(sp.Brave(), dd / "search_cache.jsonl")
    hay_api = buscador.disponible()

    print("### BUSQUEDA DE WEBS OFICIALES ###", flush=True)
    print(f"  entidades inmobiliarias: {len(objetivo):,}", flush=True)
    print(f"  ya resueltas:            {len(hechas):,}", flush=True)
    print(f"  a investigar ahora:      {len(pendientes):,}", flush=True)
    print(f"  buscador programatico:   {'BRAVE' if hay_api else 'AUSENTE (sin API key)'}",
          flush=True)

    estados: Counter = Counter()
    auditoria: Counter = Counter()
    consultas_totales = 0
    sin_api = 0
    con_una = 0

    with salida.open("a", encoding="utf-8") as fh:
        for i, e in enumerate(pendientes, 1):
            cands: list = []
            consultas: list[str] = []

            # ---- FASE A: la web que ERETZ ya tenia.
            actual = (e.get("current_eretz_web") or "").strip()
            if actual and not wd.es_portal(actual):
                c = bajar(actual)
                cands.append(c)
                aud = wd.auditar_web_eretz(e, c if c.http is not None else None)
            elif actual:
                aud = wd.auditar_web_eretz(e, None)
            else:
                aud = {"estado": wd.FALTANTE, "detalle": "ERETZ no tiene web cargada"}
            auditoria[aud["estado"]] += 1

            v = wd.verificar(e, cands) if cands else None

            # ---- FASE B: dominios derivados.
            if not v or v.estado not in resuelto:
                for url in candidatos_de_nombre(e["nombre_original"]):
                    c = bajar(url)
                    if c.http is not None:
                        cands.append(c)
                    time.sleep(a.pausa)
                    if len(cands) >= 4:
                        break
                v = wd.verificar(e, cands)

            # ---- FASE C: buscador, solo si hace falta.
            if v.estado in resuelto:
                sin_api += 1
            elif not hay_api:
                v = wd.Veredicto(wd.PENDING, None, v.official_office_page, v.senales,
                                 v.contras, 0.0,
                                 "requiere busqueda programatica; falta API key")
            else:
                for q in sp.consultas_para(e):
                    try:
                        res = buscador.buscar(q, pais="AR", idioma="es", cantidad=10)
                    except Exception as exc:
                        v = wd.Veredicto(wd.SEARCH_ERROR, None, v.official_office_page,
                                         v.senales, v.contras, 0.0, sp.redactar(str(exc)))
                        break
                    consultas.append(q)
                    consultas_totales += 1
                    for r in res:
                        # Un portal no puede ser la web oficial: no se visita.
                        if wd.es_portal(r.url):
                            continue
                        c = bajar(r.url)
                        if c.http is not None:
                            cands.append(c)
                        time.sleep(a.pausa)
                        if len(cands) >= 8:
                            break
                    v = wd.verificar(e, cands)
                    # Con evidencia suficiente se corta: las consultas cuestan.
                    if v.estado in resuelto:
                        break
                if len(consultas) == 1 and v.estado in resuelto:
                    con_una += 1

            fila = wd.fila_de_salida(e, v, cands)
            fila.update({
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "search_provider": buscador.nombre if consultas else None,
                "search_queries": consultas,
                "search_queries_count": len(consultas),
                "candidate_urls": [c.url for c in cands][:10],
                "eretz_web_audit": aud,
            })
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            fh.flush()
            estados[v.estado] += 1
            if i % 25 == 0:
                print(f"    {i}/{len(pendientes)}  {dict(estados)}  "
                      f"consultas={consultas_totales} cache={buscador.hits}", flush=True)

    print("\n### RESULTADO ###", flush=True)
    print(f"  estados:               {dict(estados)}", flush=True)
    print(f"  auditoria web ERETZ:   {dict(auditoria)}", flush=True)
    print(f"  resueltas sin API:     {sin_api:,}", flush=True)
    print(f"  resueltas con 1 query: {con_una:,}", flush=True)
    print(f"  consultas emitidas:    {consultas_totales:,}", flush=True)
    print(f"  cache hits / misses:   {buscador.hits} / {buscador.misses}", flush=True)
    print(f"  artefacto -> {salida}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

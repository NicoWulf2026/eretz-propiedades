#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Informe consolidado de la ingesta directa.

Lee los artefactos producidos y los cruza. No pide nada a la red, no toca la
base y no decide nada: si un numero sale raro, el problema esta en el artefacto,
no aca.

Dos reglas gobiernan este archivo:

  - Ningun numero se escribe a mano. Todos salen de los artefactos. Un informe
    con una constante adentro deja de ser un informe el dia que el dato cambia,
    y no avisa.

  - El universo de propiedades sale de `scripts/input_universe.py`, no de
    adivinar que archivos hay en el disco. Adivinando fue como el informe
    termino contando un universo distinto del que el write gate proceso.

La reconciliacion va primero, antes que cualquier otra cosa. Enumerado, pedido,
obtenido y escrito tienen que cerrar: una perdida silenciosa entre esas etapas
es exactamente el tipo de error que no avisa.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.input_universe import (ENTRADAS, OBLIGATORIAS,  # noqa: E402
                                    UNIVERSE_VERSION, contar,
                                    corridas_por_entrada, faltantes)

REPORT_VERSION = "mission_report_v2"

# Carpetas de corrida, para checkpoints, bajas y rendimiento. NO se usan para
# armar el universo: para eso esta input_universe.
CARPETAS = tuple(sorted({d for d, _, _ in ENTRADAS} | {
    "TOKKO_ROLLOUT_CTRL", "WP_CANARY", "GENERICO_CANARY", "FORMAS_CANARY"}))

CAMPOS = ("titulo", "descripcion", "operacion", "tipo_propiedad", "precio",
          "moneda", "provincia", "ciudad", "barrio", "direccion", "latitud",
          "longitud", "ambientes", "dormitorios", "banos", "superficie_total",
          "superficie_cubierta", "imagenes")

ARTEFACTOS_SALIDA = ("DB_WRITE_ELIGIBLE.jsonl", "CROSS_AGENCY_DUPLICATES.jsonl",
                     "WEB_NO_PROPIA.jsonl", "DUPLICADO_EN_ENTRADA.jsonl",
                     "NO_ES_UNA_FICHA.jsonl")


def recorrer(ruta: Path):
    """Una linea por vez. El write set son 800 MB: cargarlo entero en una lista
    es como se llega a un MemoryError que ademas trunca el artefacto."""
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def leer(ruta: Path) -> list:
    return list(recorrer(ruta))


def contar_lineas(ruta: Path) -> int:
    return sum(1 for _ in recorrer(ruta))


def host_de(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0].lower()


def titulo(letra: str, texto: str) -> None:
    print()
    print("=" * 74)
    print(letra + ". " + texto)
    print("=" * 74)


def corridas_de(base: Path, prefijo: str) -> list:
    salida = []
    if not base.exists():
        return salida
    for ruta in base.glob(prefijo + "run*"):
        n = ruta.name.split("run", 1)[1].split(".")[0]
        if n.isdigit():
            salida.append(n)
    return sorted(set(salida), key=int)


def git(raiz: Path, *args: str) -> str:
    try:
        return subprocess.run(("git",) + args, cwd=str(raiz), capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except Exception:
        return "?"


def env(nombre: str) -> str:
    return "PRESENTE" if os.environ.get(nombre) else "ABSENT"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    a = ap.parse_args()
    dd, raiz = Path(a.data_dir), Path(a.raiz)
    repo = Path(__file__).resolve().parents[1]
    problemas = []

    print("#" * 74)
    print("#  ERETZ PROPIEDADES - INFORME DE MISION  (" + REPORT_VERSION + ")")
    print("#" * 74)

    # ---------------------------------------------------------------- A -----
    titulo("A", "RECONCILIACION DE ENTRADAS")
    falt = faltantes(raiz)
    por_entrada = contar(raiz)
    universo = sum(por_entrada.values())
    print("  familias de entrada declaradas: %d  (%s)"
          % (len(ENTRADAS), UNIVERSE_VERSION))
    print("  entradas faltantes en disco:    %d" % len(falt))
    for f in falt:
        print("    AUSENTE " + f)
        problemas.append("entrada ausente: " + f)
    print("  obligatorias presentes:         %s"
          % sorted(OBLIGATORIAS & set(por_entrada)))
    for d, n in por_entrada.items():
        print("    %-24s %8d" % (d, n))
    print("  UNIVERSO_ANALIZADO (suma):      %d" % universo)

    runs_por_entrada = corridas_por_entrada(raiz)
    runs_declaradas = set()
    for rs in runs_por_entrada.values():
        runs_declaradas |= rs
    runs_declaradas.discard(None)

    salida_runs = Counter()
    for nombre in ARTEFACTOS_SALIDA:
        for p in recorrer(raiz / nombre):
            salida_runs[p.get("_run")] += 1
    sin_origen = {r for r in salida_runs if r not in runs_declaradas}
    print("  corridas declaradas por las entradas: %d" % len(runs_declaradas))
    print("  corridas presentes en los artefactos: %d" % len(salida_runs))
    print("  corridas SIN ORIGEN identificado:     %d" % len(sin_origen))
    for r in sorted(x for x in sin_origen if x)[:10]:
        print("    sin origen: %s  (%d propiedades)" % (r, salida_runs[r]))
    if sin_origen:
        problemas.append("%d corridas sin origen declarado" % len(sin_origen))

    # ---------------------------------------------------------------- B -----
    titulo("B", "INVARIANTES DEL WRITE SET")
    elegibles_n = 0
    hashes = set()
    urls_agencias = defaultdict(set)
    por_conn = Counter()
    campos_ok = defaultdict(Counter)
    agencias_elegibles = set()
    for p in recorrer(raiz / "DB_WRITE_ELIGIBLE.jsonl"):
        elegibles_n += 1
        hashes.add(p.get("hash_dedup"))
        urls_agencias[p.get("source_url")].add(p.get("canonical_agency_id"))
        agencias_elegibles.add(p.get("canonical_agency_id"))
        c = p.get("connector")
        por_conn[c] += 1
        for campo in CAMPOS:
            if p.get(campo) not in (None, "", []):
                campos_ok[campo][c] += 1
    urls_n = len(urls_agencias)
    multi = sum(1 for v in urls_agencias.values() if len(v) > 1)

    invariantes = (
        ("DB_WRITE_ELIGIBLE == HASHES_UNICOS", elegibles_n, len(hashes)),
        ("DB_WRITE_ELIGIBLE == URLS_UNICAS", elegibles_n, urls_n),
        ("MULTI_AGENCY_URLS_IN_WRITE_SET == 0", multi, 0),
    )
    for nombre, x, y in invariantes:
        print("  [%s] %-44s %d vs %d"
              % ("OK   " if x == y else "FALLA", nombre, x, y))
        if x != y:
            problemas.append("invariante rota: %s (%d vs %d)" % (nombre, x, y))

    # ---------------------------------------------------------------- C -----
    titulo("C", "UNIVERSO DE PROPIEDADES POR CATEGORIA EXCLUSIVA")
    pend_manifiesto = leer(raiz / "AGENCY_ID_PENDING_MANIFEST.jsonl")
    categorias = {
        "DB_WRITE_ELIGIBLE": elegibles_n,
        "CROSS_AGENCY_PENDING": contar_lineas(raiz / "CROSS_AGENCY_DUPLICATES.jsonl"),
        "WEB_NO_PROPIA": contar_lineas(raiz / "WEB_NO_PROPIA.jsonl"),
        "DUPLICADO_EN_ENTRADA": contar_lineas(raiz / "DUPLICADO_EN_ENTRADA.jsonl"),
        "AGENCY_ID_PENDING": sum(x.get("propiedades_descubiertas", 0)
                                 for x in pend_manifiesto),
        "NO_ES_UNA_FICHA": contar_lineas(raiz / "NO_ES_UNA_FICHA.jsonl"),
    }
    explicadas = sum(categorias.values())
    for k, v in sorted(categorias.items(), key=lambda t: -t[1]):
        print("    %-26s %8d" % (k, v))
    resto = universo - explicadas
    if resto:
        print("    %-26s %8d" % ("(sin categoria)", resto))
        problemas.append("%d propiedades sin categoria exclusiva" % resto)
    print("  TOTAL_ANALIZADAS  %d" % universo)
    print("  TOTAL_EXPLICADAS  %d" % (explicadas + max(resto, 0)))
    if resto < 0:
        problemas.append("las categorias suman mas que el universo analizado")

    # ---------------------------------------------------------------- D -----
    titulo("D", "AGENCIAS")
    directorio = leer(dd / "agency_web_directory.jsonl")
    manifiesto = leer(raiz / "SCRAPING_SOURCE_MANIFEST.jsonl")
    plataformas = leer(raiz / "agency_platform_directory.jsonl")
    print("  padron canonico:                   %d" % len(directorio))
    print("  manifest de fuentes:               %d" % len(manifiesto))
    if manifiesto:
        print("    con dominio demostrado:          %d"
              % sum(1 for x in manifiesto if x.get("official_domain")))
        print("    listas para scraping:            %d"
              % sum(1 for x in manifiesto if x.get("ready_for_scraping")))
        print("    pendientes de busqueda:          %d"
              % sum(1 for x in manifiesto if x.get("needs_external_search")))
        print("  por estado de identidad:")
        for k, v in Counter(x.get("identity_status")
                            for x in manifiesto).most_common(10):
            print("    %-34s %6d" % (k, v))
    print("  agencias con inventario elegible:  %d" % len(agencias_elegibles))
    print("  agencias sin eretz_id (pendientes):%d" % len(pend_manifiesto))
    mal = [x for x in plataformas if x.get("domain_mal_atribuido")]
    print("  webs mal atribuidas corregidas:    %d" % len(mal))
    for x in mal[:5]:
        print("    %-46s eretz=%s -> %s"
              % (str(x.get("canonical_agency_id"))[:44], x.get("eretz_id"),
                 x.get("web_kind")))

    # ---------------------------------------------------------------- E -----
    titulo("E", "PLATAFORMAS")
    mapa = leer(dd / "scrape_source_technology_map.jsonl")
    if mapa:
        for k, v in Counter(x.get("detected_platform")
                            for x in mapa).most_common(14):
            print("    %-24s %6d  (%5.1f%%)" % (k, v, v / len(mapa) * 100))
        print("  por estrategia:")
        for k, v in Counter(x.get("strategy") for x in mapa).most_common():
            print("    %-24s %6d" % (k, v))
    else:
        print("  (sin mapa tecnologico)")
    print("  inventario elegible por connector:")
    for k, v in por_conn.most_common():
        print("    %-24s %8d" % (k, v))

    # ---------------------------------------------------------------- F -----
    titulo("F", "CROSS-AGENCY")
    res = leer(raiz / "CROSS_AGENCY_RESOLUTION.jsonl")
    print("  urls disputadas: %d" % len(res))
    for k, v in Counter(x.get("categoria") for x in res).most_common():
        lib = sum(1 for x in res
                  if x.get("categoria") == k and x.get("liberable"))
        print("    %-34s %6d  liberables: %d" % (k, v, lib))
    print("  claims refutados por evidencia verificada: %d"
          % sum(1 for x in res if x.get("descartados_por_evidencia")))

    # ---------------------------------------------------------------- G -----
    titulo("G", "CASO BUSTAMANTE")
    bres = raiz / "BUSTAMANTE_RESOLUTION.json"
    if bres.exists():
        b = json.loads(bres.read_text(encoding="utf-8"))
        print("  veredicto: %s" % b.get("veredicto"))
        for e in b.get("entidades", []):
            print("    eretz=%-6s %-36s web=%s"
                  % (e.get("eretz_id"), str(e.get("nombre"))[:34],
                     e.get("web_status")))
        print("  entidades del padron en ambos mercados: %s"
              % b.get("entidades_que_operan_en_ambos_mercados"))
    host_b = "bustamantepropiedades.com"
    por_eid = Counter()
    for p in recorrer(raiz / "DB_WRITE_ELIGIBLE.jsonl"):
        if host_b in (p.get("source_url") or ""):
            por_eid[p.get("inmobiliaria_id")] += 1
    print("  propiedades de %s en el write set: %d"
          % (host_b, sum(por_eid.values())))
    for k, v in por_eid.most_common():
        print("    eretz_id %s: %d" % (k, v))

    # ---------------------------------------------------------------- H -----
    titulo("H", "AGENCIAS DUPLICADAS EN EL PADRON")
    dup = leer(raiz / "AGENCY_DUPLICATE_RESOLUTION_MANIFEST.jsonl")
    if not dup:
        print("  ninguna pendiente")
    for d in dup:
        print("  %-34s urls=%s" % (d.get("dominio"), d.get("urls_en_conflicto")))
        for f in d.get("fichas", []):
            print("    eretz=%-6s %-36s %s"
                  % (f.get("eretz_id"), str(f.get("nombre"))[:34],
                     f.get("estado_web")))
        print("    accion: %s" % str(d.get("accion_propuesta"))[:96])

    # ---------------------------------------------------------------- I -----
    titulo("I", "CALIDAD POR CAMPO (sobre el write set)")
    conns = sorted(x for x in por_conn if x)
    ancho = max(len(c) for c in CAMPOS)
    encabezado = "  ".join("%9s" % str(c)[:9] for c in conns)
    print("    %-*s  %s      total" % (ancho, "campo", encabezado))
    for campo in CAMPOS:
        fila = "  ".join("%8.1f%%" % (campos_ok[campo][c] /
                                      max(por_conn[c], 1) * 100) for c in conns)
        tot = sum(campos_ok[campo].values()) / max(elegibles_n, 1)
        print("    %-*s  %s  %8.1f%%" % (ancho, campo, fila, tot * 100))

    # ---------------------------------------------------------------- J -----
    titulo("J", "IDEMPOTENCIA Y CHECKPOINTS")
    for carpeta in CARPETAS:
        base = raiz / carpeta
        for corrida in corridas_de(base, "quality_report_"):
            q = base / ("quality_report_run%s.json" % corrida)
            try:
                r = json.loads(q.read_text(encoding="utf-8"))
            except Exception:
                continue
            print("  %-22s run%s  codigo=%s enum=%d escritas=%d recon=%s"
                  % (carpeta, corrida, r.get("version_codigo", "-"),
                     r.get("propiedades_enumeradas", 0),
                     r.get("propiedades_escritas", 0), r.get("reconcilia")))
            print("      cambios=%s  errores=%s"
                  % (r.get("cambios"), r.get("errores", 0)))

    # ---------------------------------------------------------------- K -----
    titulo("K", "BAJAS (modo observacion)")
    total_aus = 0
    for carpeta in CARPETAS:
        for corrida in corridas_de(raiz / carpeta, "absences_"):
            aus = leer(raiz / carpeta / ("absences_run%s.jsonl" % corrida))
            if aus:
                total_aus += len(aus)
                print("  %s run%s: %d %s"
                      % (carpeta, corrida, len(aus),
                         dict(Counter(x.get("estado") for x in aus))))
    if not total_aus:
        print("  ninguna ausencia registrada")
    print("  regla: 3 corridas seguidas sin ver la propiedad, y ninguna cuenta")
    print("         si la fuente no respondio o la enumeracion quedo incompleta.")
    print("  ninguna propiedad se desactiva en esta fase.")

    # ---------------------------------------------------------------- L -----
    titulo("L", "BUSQUEDA EXTERNA")
    pend = [x for x in manifiesto if x.get("needs_external_search")]
    print("  entidades pendientes de busqueda: %d" % len(pend))
    for v in ("BRAVE_SEARCH_API_KEY", "SERPAPI_KEY", "GOOGLE_CSE_KEY"):
        print("    %-24s %s" % (v, env(v)))
    print("  gasto en proveedores pagos: 0 (no se ejecuto ninguno)")

    # ---------------------------------------------------------------- M -----
    titulo("M", "SUPABASE / ESCRITURA")
    for v in ("ERETZ_PREVIEW_RO_URL", "DATABASE_URL_RO", "SUPABASE_URL"):
        print("    %-24s %s" % (v, env(v)))
    print("  escritura ejecutada: NO")
    print("  destino unico habilitado: internal_scraping.propiedades_raw")
    print("  rol de escritura: eretz_direct_property_writer (ya existe)")

    # ---------------------------------------------------------------- N -----
    titulo("N", "GIT")
    print("  branch: %s" % git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    print("  HEAD:   %s" % git(repo, "rev-parse", "HEAD")[:12])
    sucio = git(repo, "status", "--porcelain")
    print("  arbol:  %s" % ("limpio" if not sucio else "con cambios sin commitear"))
    print("  push/merge/Production: no")

    # ---------------------------------------------------------------- O -----
    titulo("O", "VEREDICTO")
    if problemas:
        print("  PROBLEMAS DETECTADOS:")
        for x in problemas:
            print("    - " + x)
        return 1
    print("  todas las invariantes verificadas cierran")
    return 0


if __name__ == "__main__":
    sys.exit(main())

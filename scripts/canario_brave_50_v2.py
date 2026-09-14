#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las MISMAS 50 del canario V1, con el verificador V2. Comparación A/B.

No escribe en la base. `database_writes: 0`. No guarda payload de Brave: sólo
la conclusión propia, verificada contra el sitio real.

Los 50 ids salen del artefacto del canario V1, no de una selección nueva. Si
se re-eligiera la muestra, una mejora de precisión y una muestra más fácil
serían indistinguibles — y las difíciles son justamente las que importan.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))


def cargar_env() -> None:
    for ruta in (Path(r"D:\INMO CAPITAL\Inmo-Capital-main\.env"), RAIZ / ".env"):
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, valor = linea.split("=", 1)
            if nombre.strip() and nombre.strip() not in os.environ:
                os.environ[nombre.strip()] = valor.strip().strip('"').strip("'")


cargar_env()

import search_provider as sp  # noqa: E402
import verificador_identidad_v2 as v2  # noqa: E402
from run_web_discovery import candidatos_de_nombre  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PADRON = DATOS / "roomix_agency_directory.jsonl"
V1 = DATOS / "BRAVE_CANARIO_50.jsonl"
SALIDA = DATOS / "BRAVE_CANARIO_50_V2.jsonl"

USD_POR_MIL = 5.0
CONSULTAS_MAXIMAS = 3
UA = {"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)", "Accept-Encoding": "gzip"}


def bajar(url: str, timeout: float = 20) -> v2.Sitio:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            crudo = r.read(400_000)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    crudo = gzip.decompress(crudo)
                except OSError:
                    pass
            cuerpo = crudo.decode("utf-8", "replace")
            final = r.url
        titulo = ""
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", cuerpo)
        if m:
            titulo = re.sub(r"\s+", " ", m.group(1)).strip()
        texto = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", cuerpo)
        texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", texto))[:8000]
        return v2.Sitio(url=final, titulo=titulo, texto=texto, http=200)
    except urllib.error.HTTPError as e:
        return v2.Sitio(url=url, http=e.code)
    except Exception:
        return v2.Sitio(url=url, http=None)


def padron_por_id() -> dict[str, dict]:
    fuera = {}
    for linea in PADRON.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("stable_id"):
            fuera[fila["stable_id"]] = fila
    return fuera


def consulta_siguiente(fila: dict, fallo: str | None) -> str | None:
    nombre = (fila.get("nombre_original") or "").strip()
    zonas = [z for z in (fila.get("zonas_observadas") or []) if z]
    red = fila.get("red_franquicia")
    if not nombre:
        return None
    if fallo is None:
        zona = zonas[0] if zonas else ""
        return f'"{nombre}" "{zona}" inmobiliaria' if zona else f'"{nombre}" inmobiliaria'
    if fallo == "sin_resultado":
        return f"{nombre} inmobiliaria argentina"
    if fallo == "nada_propio":
        if red:
            return f'"{nombre}" {red} oficina argentina'
        zona = zonas[1] if len(zonas) > 1 else (zonas[0] if zonas else "")
        return f'"{nombre}" {zona} sitio oficial'.strip()
    return None


def resolver(fila: dict, buscador, pausa: float) -> dict:
    entidad = {"nombre_original": fila.get("nombre_original") or "",
               "zonas_observadas": fila.get("zonas_observadas") or [],
               "matricula": fila.get("matricula") or []}
    candidatas: list[v2.Sitio] = []

    # --- GRATIS
    for url in candidatos_de_nombre(entidad["nombre_original"])[:4]:
        s = bajar(url)
        if s.http is not None:
            candidatas.append(s)
        time.sleep(pausa)
    veredicto = v2.verificar(entidad, candidatas) if candidatas else None
    if veredicto and veredicto.clase in (v2.OFFICIAL_WEB, v2.OFFICIAL_OFFICE_PAGE):
        return {"v": veredicto, "via": "RESOLVED_FREE", "consultas": 0}

    # --- PAGO
    usadas, fallo = 0, None
    for _ in range(CONSULTAS_MAXIMAS):
        consulta = consulta_siguiente(fila, fallo)
        if not consulta:
            break
        try:
            resultados = buscador.buscar(consulta, pais="AR", idioma="es")
        except sp.ConsultaInvalida:
            fallo = "sin_resultado"
            continue
        usadas += 1
        urls = [r.url for r in resultados if r.url]
        if not urls:
            fallo = "sin_resultado"
            continue
        nuevas = 0
        for u in urls[:5]:
            if any(c.url == u for c in candidatas):
                continue
            s = bajar(u)
            if s.http is not None:
                candidatas.append(s)
                nuevas += 1
            time.sleep(pausa)
            if nuevas >= 3:
                break
        veredicto = v2.verificar(entidad, candidatas)
        if veredicto.clase in (v2.OFFICIAL_WEB, v2.OFFICIAL_OFFICE_PAGE):
            break
        fallo = "nada_propio"

    veredicto = veredicto or (v2.verificar(entidad, candidatas) if candidatas
                              else v2.VeredictoV2(clase=v2.NO_OFFICIAL_WEB_FOUND))
    return {"v": veredicto, "via": "BRAVE" if usadas else "RESOLVED_FREE",
            "consultas": usadas}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()

    buscador = sp.Brave()
    if not buscador.disponible():
        print("BRAVE_AUTH_FAILED")
        return 1
    if not V1.exists():
        raise SystemExit("falta el artefacto del canario V1")

    v1 = {}
    for linea in V1.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            v1[fila["agency_id"]] = fila
    padron = padron_por_id()
    muestra = [padron[i] for i in v1 if i in padron]

    print("### CANARIO V2 — LAS MISMAS 50 ###")
    print(f"  ids del canario V1:  {len(v1)}")
    print(f"  encontradas:         {len(muestra)}")
    print(f"  verificador:         V2 (tipo de sitio + identidad)\n")

    clases: Counter = Counter()
    vias: Counter = Counter()
    consultas = 0
    cambios = []
    empezo = time.time()
    filas = []

    for i, fila in enumerate(muestra, 1):
        try:
            r = resolver(fila, buscador, args.pausa)
        except RuntimeError as e:
            print(f"  proveedor: {e}")
            break
        v = r["v"]
        clases[v.clase] += 1
        vias[r["via"]] += 1
        consultas += r["consultas"]
        antes = v1[fila["stable_id"]]["source_class"]
        if antes != v.clase:
            cambios.append((fila.get("nombre_original"), antes, v.clase, v.url))
        filas.append({
            "agency_id": fila["stable_id"],
            "nombre": fila.get("nombre_original"),
            "source_class": v.clase,
            "confidence": v.confianza,
            "site_type": v.tipo_de_sitio,
            "official_url": v.url,
            "evidence_summary": "; ".join(v.evidencias)[:300] or v.razon[:300],
            "contras": "; ".join(v.contras)[:200],
            "discovery_method": r["via"],
            "queries_used": r["consultas"],
            "clase_v1": antes,
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        if i % 5 == 0:
            print(f"  {i}/{len(muestra)}  consultas {consultas}", flush=True)

    with SALIDA.open("w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    n = len(filas)
    of = clases[v2.OFFICIAL_WEB]
    op = clases[v2.OFFICIAL_OFFICE_PAGE]
    print("\n=== METRICAS V2 ===")
    print(f"TOTAL_SAMPLE                 {n}")
    print(f"RESOLVED_FREE                {vias['RESOLVED_FREE']}")
    print(f"BRAVE_QUERIES                {consultas}")
    for c in (v2.OFFICIAL_WEB, v2.OFFICIAL_OFFICE_PAGE, v2.EXTERNAL_PORTAL_PROFILE,
              v2.NO_OFFICIAL_WEB_FOUND, v2.IDENTITY_AMBIGUOUS, v2.INACTIVE_SOURCE,
              v2.REVIEW_REQUIRED, v2.BLOCKED):
        print(f"{c:28} {clases[c]}")
    print(f"TOTAL_RESOLVED               {of + op}")
    if n:
        print(f"RESOLUTION_RATE              {(of + op) / n:.1%}")
        print(f"QUERIES_PER_AGENCY           {consultas / n:.2f}")
    if of + op:
        print(f"QUERIES_PER_RESOLVED_AGENCY  {consultas / (of + op):.2f}")
    print(f"ESTIMATED_COST               USD {consultas / 1000 * USD_POR_MIL:.3f}")
    print(f"DURACION                     {(time.time() - empezo) / 60:.1f} min")

    print(f"\n=== CAMBIOS RESPECTO DE V1: {len(cambios)} ===")
    for nombre, antes, ahora, url in cambios:
        print(f"  {str(nombre)[:30]:32} {antes[:22]:24} -> {ahora[:22]:24}")
        if url:
            print(f"       {url[:74]}")
    print(f"\nartefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

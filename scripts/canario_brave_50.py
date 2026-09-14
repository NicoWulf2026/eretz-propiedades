#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Canario de 50: ¿Brave acelera el cierre del universo antes del 12/10?

No escribe en la base. `database_writes: 0`. No guarda payload de Brave: sólo
la conclusión propia, verificada contra el sitio real.

### Lo que la muestra puede y no puede estratificar

El §1 pide estratos por teléfono, email y dirección. **No existen.** El padrón
trae las claves `telefono` y `email` vacías en las 9.622 filas, y no hay
direcciones. Simular esos estratos sería inventar una representatividad que la
muestra no tiene, así que se estratifica por lo que sí hay, al 100 %:

    nombre distintivo vs generico   cuanto ayuda el nombre a buscar
    CABA/GBA vs interior            un nombre repetido en el interior es peor
    volumen de avisos               tamanyo de la inmobiliaria
    franquicia vs independiente     decide OFFICIAL_WEB vs OFFICE_PAGE
    con o sin matricula             la unica evidencia dura que existe

### El orden: gratis antes que pago

Primero dominios derivados del nombre. Si `vanzini.com.ar` responde y se
verifica, la agencia cierra en `RESOLVED_FREE` sin gastar una consulta. Medir
cuanto se cierra gratis es parte del canario: si es mucho, Brave importa menos.

### Brave genera candidatas, no verdades

Una URL que Brave devuelve primera no es una web oficial. Cada candidata se
abre y se verifica contra el sitio real, y ante duda se prefiere AMBIGUOUS: un
falso negativo cuesta tiempo, un falso positivo contamina cientos de
propiedades con la identidad equivocada.

Uso:
    python scripts/canario_brave_50.py --dry-run
    python scripts/canario_brave_50.py
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))


def cargar_env() -> None:
    """La key vive en un .env ignorado por git. Se carga, nunca se imprime."""
    for ruta in (Path(r"D:\INMO CAPITAL\Inmo-Capital-main\.env"),
                 RAIZ / ".env"):
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, valor = linea.split("=", 1)
            nombre = nombre.strip()
            if nombre and nombre not in os.environ:
                os.environ[nombre] = valor.strip().strip('"').strip("'")


cargar_env()

import agency_web_discovery as wd  # noqa: E402
import search_provider as sp  # noqa: E402
from run_web_discovery import candidatos_de_nombre  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
PADRON = DATOS / "roomix_agency_directory.jsonl"
UNIVERSO = CERT / "ERETZ_UNIVERSO.jsonl"
SALIDA = DATOS / "BRAVE_CANARIO_50.jsonl"

USD_POR_MIL = 5.0
CONSULTAS_MAXIMAS = 3
TAMANYO = 50

UA = {"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)",
      "Accept-Encoding": "gzip"}

# Ciudades donde un apellido se repite mucho: el nombre solo no alcanza.
GRANDES = {"capital federal", "caba", "palermo", "belgrano", "recoleta",
           "caballito", "flores", "almagro", "villa urquiza", "nunyez",
           "la plata", "rosario", "cordoba", "mendoza", "mar del plata",
           "san miguel de tucuman", "salta", "neuquen", "bahia blanca"}
GBA = {"vicente lopez", "san isidro", "tigre", "pilar", "quilmes", "lomas de zamora",
       "lanus", "moron", "san martin", "avellaneda", "berazategui", "escobar",
       "malvinas argentinas", "tres de febrero", "hurlingham", "ituzaingo"}


def bajar(url: str, timeout: float = 20) -> wd.Candidata:
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
        return wd.Candidata(url=final, origen="verificacion", titulo=titulo,
                            texto=texto, http=200,
                            redirects=[url] if final != url else [])
    except urllib.error.HTTPError as e:
        return wd.Candidata(url=url, origen="verificacion", http=e.code)
    except Exception:
        return wd.Candidata(url=url, origen="verificacion", http=None)


# --------------------------------------------------------------------------
# Seleccion de la muestra
# --------------------------------------------------------------------------

def pendientes_de_web() -> list[dict]:
    """Las que no tienen web oficial ni pagina de oficina verificada."""
    resueltas = set()
    for nombre in ("AGENCY_OFFICIAL_WEB_VERIFIED.jsonl",):
        ruta = DATOS / nombre
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except ValueError:
                continue
            if fila.get("official_url") and fila.get("canonical_agency_id"):
                resueltas.add(fila["canonical_agency_id"])

    fuera = []
    for linea in PADRON.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("tipo") not in ("INMOBILIARIA", "OFICINA_FRANQUICIA"):
            continue
        if fila.get("stable_id") in resueltas:
            continue
        if (fila.get("official_web") or "").strip():
            continue
        if (fila.get("official_office_page") or "").strip():
            continue
        fuera.append(fila)
    return fuera


def es_generico(nombre: str) -> bool:
    """Un nombre sin tokens propios es el caso dificil: 'Inmobiliaria Centro'."""
    return len(wd.tokens_distintivos(nombre)) <= 1


def zona_de(fila: dict) -> str:
    zonas = [z.lower() for z in (fila.get("zonas_observadas") or [])]
    if any(z in GRANDES for z in zonas):
        return "gran ciudad"
    if any(z in GBA for z in zonas):
        return "GBA"
    return "interior"


def seleccionar(candidatas: list[dict], semilla: int = 12) -> list[dict]:
    """Cuotas por estrato, sin elegir las 50 mas faciles.

    Se ordena por volumen DENTRO de cada estrato y se toma alternando desde
    arriba y desde abajo, para que entren grandes y chicas de cada grupo.
    """
    random.seed(semilla)
    estratos: dict[tuple, list[dict]] = {}
    for fila in candidatas:
        clave = (zona_de(fila),
                 "generico" if es_generico(fila.get("nombre_original") or "") else "distintivo",
                 "franquicia" if fila.get("red_franquicia") else "independiente")
        estratos.setdefault(clave, []).append(fila)

    for filas in estratos.values():
        filas.sort(key=lambda f: -(f.get("avisos_observados") or 0))

    elegidas: list[dict] = []
    claves = sorted(estratos, key=lambda k: -len(estratos[k]))
    vuelta = 0
    while len(elegidas) < TAMANYO and any(estratos[k] for k in claves):
        for clave in claves:
            filas = estratos[clave]
            if not filas or len(elegidas) >= TAMANYO:
                continue
            # Alternar extremos: una grande, una chica, una grande...
            elegidas.append(filas.pop(0 if vuelta % 2 == 0 else -1))
        vuelta += 1
    return elegidas[:TAMANYO]


# --------------------------------------------------------------------------
# Resolucion
# --------------------------------------------------------------------------

def consultas_para(fila: dict, fallo_anterior: str | None) -> str | None:
    """La siguiente consulta depende de lo que fallo en la anterior."""
    nombre = (fila.get("nombre_original") or "").strip()
    zonas = [z for z in (fila.get("zonas_observadas") or []) if z]
    red = fila.get("red_franquicia")
    if not nombre:
        return None
    if fallo_anterior is None:
        zona = zonas[0] if zonas else ""
        return f'"{nombre}" "{zona}" inmobiliaria' if zona else f'"{nombre}" inmobiliaria'
    if fallo_anterior == "sin_resultado":
        # El entrecomillado fue demasiado estricto: aflojarlo.
        return f'{nombre} inmobiliaria argentina'
    if fallo_anterior == "solo_portales":
        # Hay presencia pero toda en portales: pedir el sitio propio.
        if red:
            return f'"{nombre}" {red} oficina'
        zona = zonas[1] if len(zonas) > 1 else (zonas[0] if zonas else "")
        return f'"{nombre}" {zona} sitio oficial propiedades'.strip()
    return None


def clasificar(veredicto, candidatas) -> str:
    if veredicto is None:
        return "NO_OFFICIAL_WEB_FOUND"
    if veredicto.estado == wd.VERIFIED:
        return "OFFICIAL_WEB"
    if veredicto.estado == wd.HIGH_CONFIDENCE:
        return "OFFICIAL_WEB"
    if veredicto.official_office_page:
        return "OFFICIAL_OFFICE_PAGE"
    if veredicto.estado == wd.AMBIGUOUS:
        return "IDENTITY_AMBIGUOUS"
    if veredicto.estado == wd.NO_SITE:
        return "NO_OFFICIAL_WEB_FOUND"
    if veredicto.estado == "OFFICIAL_WEB_INACTIVE":
        return "INACTIVE_SOURCE"
    return "REVIEW_REQUIRED"


def resolver(fila: dict, buscador, pausa: float) -> dict:
    nombre = fila.get("nombre_original") or ""
    entidad = {"stable_id": fila.get("stable_id"),
               "nombre_original": nombre,
               "red_franquicia": fila.get("red_franquicia"),
               "zonas_observadas": fila.get("zonas_observadas") or [],
               "matricula": fila.get("matricula") or []}

    # --- GRATIS: dominios derivados del nombre.
    candidatas: list[wd.Candidata] = []
    for url in candidatos_de_nombre(nombre)[:4]:
        c = bajar(url)
        if c.http is not None:
            candidatas.append(c)
        time.sleep(pausa)
    veredicto = wd.verificar(entidad, candidatas) if candidatas else None
    if veredicto and veredicto.estado in (wd.VERIFIED, wd.HIGH_CONFIDENCE):
        return {"clase": clasificar(veredicto, candidatas), "via": "RESOLVED_FREE",
                "consultas": 0, "veredicto": veredicto, "candidatas": candidatas}

    # --- PAGO: Brave, adaptativo, con techo.
    usadas, fallo = 0, None
    for _ in range(CONSULTAS_MAXIMAS):
        consulta = consultas_para(fila, fallo)
        if not consulta:
            break
        try:
            resultados = buscador.buscar(consulta, pais="AR", idioma="es")
        except sp.ConsultaInvalida:
            fallo = "sin_resultado"
            continue
        usadas += 1
        urls = [r.url for r in resultados if r.url]
        propias = [u for u in urls if not wd.es_portal(u)]
        if not urls:
            fallo = "sin_resultado"
            continue
        if not propias:
            fallo = "solo_portales"
            continue
        for u in propias[:3]:
            c = bajar(u)
            if c.http is not None:
                candidatas.append(c)
            time.sleep(pausa)
        veredicto = wd.verificar(entidad, candidatas)
        # Corte temprano: con evidencia suficiente no se gasta la siguiente.
        if veredicto.estado in (wd.VERIFIED, wd.HIGH_CONFIDENCE):
            break
        fallo = "solo_portales"

    veredicto = veredicto or (wd.verificar(entidad, candidatas) if candidatas else None)
    return {"clase": clasificar(veredicto, candidatas),
            "via": "BRAVE" if usadas else "RESOLVED_FREE",
            "consultas": usadas, "veredicto": veredicto, "candidatas": candidatas}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tamanyo", type=int, default=TAMANYO)
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()

    buscador = sp.Brave()
    if not buscador.disponible():
        print("BRAVE_AUTH_FAILED: la variable no esta en el entorno")
        return 1

    pendientes = pendientes_de_web()
    muestra = seleccionar(pendientes)[:args.tamanyo]

    print("### CANARIO BRAVE — 50 SIN WEB ###")
    print(f"  universo pendiente de web:  {len(pendientes):,}")
    print(f"  muestra:                    {len(muestra)}")
    print(f"  techo de consultas:         {len(muestra) * CONSULTAS_MAXIMAS}")
    print(f"  costo techo:                "
          f"USD {len(muestra) * CONSULTAS_MAXIMAS / 1000 * USD_POR_MIL:.2f}\n")

    estratos = Counter((zona_de(f),
                        "generico" if es_generico(f.get("nombre_original") or "") else "distintivo",
                        "franquicia" if f.get("red_franquicia") else "independiente")
                       for f in muestra)
    print("  estratos de la muestra:")
    for clave, n in estratos.most_common():
        print(f"     {' / '.join(clave):48} {n:3}")
    avisos = sorted(f.get("avisos_observados") or 0 for f in muestra)
    print(f"  avisos por agencia: min {avisos[0]}, mediana "
          f"{avisos[len(avisos)//2]}, max {avisos[-1]}")

    if args.dry_run:
        print("\n  DRY-RUN: no se gasta nada.")
        for f in muestra[:12]:
            print(f"     {(f.get('nombre_original') or '')[:36]:38} "
                  f"{zona_de(f):12} {f.get('avisos_observados')}")
        print("database_writes: 0")
        return 0

    clases: Counter = Counter()
    vias: Counter = Counter()
    consultas_totales = 0
    empezo = time.time()
    filas_salida = []

    for i, fila in enumerate(muestra, 1):
        try:
            r = resolver(fila, buscador, args.pausa)
        except sp.ProveedorAgotado:
            print("  PROVEEDOR AGOTADO: se corta el canario")
            break
        except RuntimeError as e:
            # `redactar` ya quito la key del mensaje del proveedor.
            print(f"  error del proveedor: {e}")
            break
        clases[r["clase"]] += 1
        vias[r["via"]] += 1
        consultas_totales += r["consultas"]
        v = r["veredicto"]
        filas_salida.append({
            "agency_id": fila.get("stable_id"),
            "nombre": fila.get("nombre_original"),
            "zona": zona_de(fila),
            "estrato_nombre": "generico" if es_generico(fila.get("nombre_original") or "") else "distintivo",
            "red_franquicia": fila.get("red_franquicia"),
            "avisos_observados": fila.get("avisos_observados"),
            "source_class": r["clase"],
            "official_url": (v.official_web if v else None),
            "official_office_page": (v.official_office_page if v else None),
            "verification_status": (v.estado if v else "SIN_CANDIDATA"),
            "evidence_summary": (v.razon if v else "ninguna candidata respondio")[:400],
            "confidence": (v.confianza if v else 0.0),
            "discovery_method": r["via"],
            "queries_used": r["consultas"],
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        if i % 5 == 0:
            print(f"  {i}/{len(muestra)}  consultas {consultas_totales}",
                  flush=True)

    with SALIDA.open("w", encoding="utf-8") as fh:
        for f in filas_salida:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    n = len(filas_salida)
    oficiales = clases["OFFICIAL_WEB"]
    oficinas = clases["OFFICIAL_OFFICE_PAGE"]
    resueltas = oficiales + oficinas
    print("\n=== METRICAS DEL CANARIO ===")
    print(f"TOTAL_SAMPLE                 {n}")
    print(f"RESOLVED_FREE                {vias['RESOLVED_FREE']}")
    print(f"BRAVE_QUERIES                {consultas_totales}")
    for clase in ("OFFICIAL_WEB", "OFFICIAL_OFFICE_PAGE", "EXTERNAL_PORTAL_PROFILE",
                  "NO_OFFICIAL_WEB_FOUND", "IDENTITY_AMBIGUOUS", "INACTIVE_SOURCE",
                  "BLOCKED", "REVIEW_REQUIRED"):
        print(f"{clase:28} {clases[clase]}")
    print(f"TOTAL_RESOLVED               {resueltas}")
    if n:
        print(f"RESOLUTION_RATE              {resueltas / n:.1%}")
        print(f"QUERIES_PER_AGENCY           {consultas_totales / n:.2f}")
    if resueltas:
        print(f"QUERIES_PER_RESOLVED_AGENCY  {consultas_totales / resueltas:.2f}")
    print(f"ESTIMATED_COST               "
          f"USD {consultas_totales / 1000 * USD_POR_MIL:.3f}")
    print(f"DURACION                     {(time.time() - empezo) / 60:.1f} min")
    print(f"\nartefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

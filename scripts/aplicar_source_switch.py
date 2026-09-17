#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mover la fuente de una agencia a su propio dominio. §8, §11, §86.

**Dry-run por defecto.** Sin `--aplicar` no escribe nada. No toca la base, no
toca producción, no cambia ningún extractor y no cambia ninguna huella global:
sólo el registro local de fuentes. `database_writes: 0`.

Por qué esto no es editar un campo
-----------------------------------
La tentación es cambiar `official_url` y listo. Sería un error, y se ve mirando
el registro real de `iglesias real estate`:

    official_url        https://alquenia.com/inmobiliarias/.../iglesias-real-estate
    detected_platform   TOKKO
    platform_confidence 0.9
    strategy            TOKKO_CONNECTOR

Ese `TOKKO` con 0,9 de confianza **no es de Iglesias**: es el stack de Alquenia,
el portal. Todo el registro describe el sitio que estamos abandonando. Cambiar
sólo la URL apuntaría el scraper al sitio propio de la agencia mientras le dice
al selector de conector que se trata del Tokko de un portal, y el resultado
sería peor que no haber tocado nada.

Así que el cambio es: bajar el sitio propio, **volver a detectar** contra él con
`detect_platform.clasificar()` —el detector que ya existe, en su versión v2— y
reescribir el registro entero con la detección nueva. La URL vieja se conserva
como evidencia, nunca se borra.

Qué exige antes de tocar nada
-----------------------------
Que la agencia esté marcada `APTO` en `ERETZ_SOURCE_SWITCH_CANARIO.jsonl`, que
es donde quedó la verificación de propiedad del §8: el dominio responde, la
marca coincide, no es portal, hay catálogo visible, y **se abrieron fichas para
comprobar que son suyas y que ninguna nombra a otra inmobiliaria**. Una agencia
que no pasó por ahí no entra acá.

Uso:
    python scripts/aplicar_source_switch.py                 # dry-run
    python scripts/aplicar_source_switch.py --aplicar
    python scripts/aplicar_source_switch.py --solo "emir elhelou"
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import detect_platform  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
REGISTRO = DATOS / "scrape_source_technology_map.jsonl"
CANARIO = CERT / "ERETZ_SOURCE_SWITCH_CANARIO.jsonl"
AUDITORIA = CERT / "ERETZ_SOURCE_SWITCH_APLICADO.jsonl"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

SITEMAPS = ("/wp-sitemap.xml", "/sitemap_index.xml", "/sitemap.xml")


def bajar(url: str, limite: int = 900_000) -> tuple[int, str, str]:
    respuesta = urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=25)
    crudo = respuesta.read(limite)
    if respuesta.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return respuesta.status, respuesta.url, crudo.decode("utf-8", "replace")


def tiene_sitemap_de_propiedades(base: str) -> bool:
    raiz = re.match(r"(https?://[^/]+)", base)
    if not raiz:
        return False
    for ruta in SITEMAPS:
        try:
            _, _, cuerpo = bajar(raiz.group(1) + ruta, 300_000)
        except Exception:
            time.sleep(0.8)
            continue
        if re.search(r"(?i)<loc>[^<]*(propiedad|inmueble|propert)", cuerpo):
            return True
        time.sleep(0.8)
    return False


def detectar(url: str) -> dict[str, Any] | None:
    """Vuelve a detectar la plataforma contra el sitio NUEVO."""
    try:
        http, final, html = bajar(url)
    except Exception as e:
        return {"error": f"{type(e).__name__} {getattr(e, 'code', '')}".strip()}
    titulo = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if m:
        titulo = re.sub(r"\s+", " ", m.group(1)).strip()
    texto = re.sub(r"\s+", " ", re.sub(
        r"(?s)<(script|style)[^>]*>.*?</\1>", " ", html))
    sitio = {"html": html, "texto": texto, "titulo": titulo, "url": final}
    señal = detect_platform.clasificar(
        sitio, sitemap_propiedades=tiene_sitemap_de_propiedades(final))
    señal["_http"] = http
    señal["_final_url"] = final
    señal["_titulo"] = titulo
    return señal


def aptas(solo: str | None) -> list[dict]:
    filas = []
    for linea in CANARIO.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        fila = json.loads(linea)
        if fila.get("veredicto") != "APTO":
            continue
        if solo and solo.lower() not in (fila.get("agency_name") or "").lower():
            continue
        filas.append(fila)
    return filas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="escribir de verdad; sin esto es dry-run")
    ap.add_argument("--solo", help="filtrar por nombre de agencia")
    ap.add_argument("--tope", type=int, default=3,
                    help="§86: primero 2-3, nunca 10 juntas")
    args = ap.parse_args()

    candidatas = aptas(args.solo)[:args.tope]
    if not candidatas:
        print("no hay candidatas APTO en el canario")
        return 1

    registro = {}
    orden = []
    for linea in REGISTRO.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            orden.append(("crudo", linea))
            continue
        clave = fila.get("canonical_agency_id")
        orden.append(("fila", clave))
        if clave:
            registro[clave] = fila

    print(f"registro de fuentes: {len(registro)} agencias")
    print(f"candidatas del canario: {len(candidatas)}")
    print(f"modo: {'APLICAR' if args.aplicar else 'DRY-RUN (no escribe nada)'}\n")

    cambios = []
    for fila in candidatas:
        clave = fila["agency_id"]
        viejo = registro.get(clave)
        if not viejo:
            print(f"   {fila['agency_name'][:30]:32} SIN REGISTRO, se saltea")
            continue
        propio = fila["dominio_propio"]
        print(f"=== {fila['agency_name']}")
        print(f"    de : {viejo.get('official_url', '')[:78]}")
        print(f"    a  : {propio}")
        señal = detectar(propio)
        if not señal or señal.get("error"):
            print(f"    NO SE APLICA: el sitio propio no respondio "
                  f"({(señal or {}).get('error')})\n")
            continue
        print(f"    deteccion vieja (era del PORTAL): "
              f"{viejo.get('detected_platform')} conf "
              f"{viejo.get('platform_confidence')} -> {viejo.get('strategy')}")
        print(f"    deteccion nueva (del sitio SUYO): "
              f"{señal['detected_platform']} conf "
              f"{señal['platform_confidence']} -> {señal['strategy']}")
        print(f"    titulo: {señal['_titulo'][:70]}")

        nuevo = dict(viejo)
        nuevo["official_url"] = señal["_final_url"]
        # La URL vieja NO se borra: el §11 pide conservarla como evidencia.
        nuevo["previous_source_url"] = viejo.get("official_url")
        nuevo["previous_source_kind"] = "EXTERNAL_PORTAL_PROFILE"
        nuevo["evidence"] = {"titulo": señal["_titulo"],
                             "final_url": señal["_final_url"]}
        nuevo["http"] = señal["_http"]
        nuevo["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        for campo in ("detected_platform", "platform_confidence",
                      "detected_framework", "detected_api", "sitemap",
                      "requires_js", "has_listings", "json_embedded",
                      "strategy", "detector_version"):
            nuevo[campo] = señal[campo]
        # §7: queda escrito POR QUE gano, no solo que gano.
        nuevo["source_selection_reason"] = "OWN_DOMAIN_VERIFIED_OWNERSHIP"
        nuevo["source_selection_confidence"] = "ALTA"
        nuevo["source_selection_evidence"] = fila.get("porque")
        cambios.append((clave, viejo, nuevo, fila))
        print()

    if not cambios:
        print("nada que cambiar")
        return 0

    if not args.aplicar:
        print(f"{'=' * 74}")
        print(f"  DRY-RUN: {len(cambios)} cambios preparados y NO escritos.")
        print("  Para aplicar: --aplicar")
        print("\n  Al aplicar, esas agencias se recertifican contra un sitio")
        print("  nuevo. Hay que mirar inventario, identidad, RUN1/RUN2,")
        print("  inventario ajeno y procedencia antes de ampliar al resto.")
        print("\ndatabase_writes: 0")
        return 0

    respaldo = REGISTRO.with_suffix(
        f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(REGISTRO, respaldo)
    print(f"respaldo: {respaldo.name}")

    for clave, _, nuevo, _ in cambios:
        registro[clave] = nuevo

    # Se reescribe respetando el orden original, para que el diff sea legible.
    lineas = []
    for tipo, valor in orden:
        if tipo == "crudo":
            lineas.append(valor)
        elif valor in registro:
            lineas.append(json.dumps(registro[valor], ensure_ascii=False))
    temporal = REGISTRO.with_suffix(".jsonl.tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    temporal.replace(REGISTRO)

    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for clave, viejo, nuevo, fila in cambios:
            fh.write(json.dumps({
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "canonical_agency_id": clave,
                "agency_name": fila["agency_name"],
                "de": viejo.get("official_url"),
                "a": nuevo["official_url"],
                "deteccion_vieja": {"platform": viejo.get("detected_platform"),
                                    "strategy": viejo.get("strategy")},
                "deteccion_nueva": {"platform": nuevo["detected_platform"],
                                    "strategy": nuevo["strategy"]},
                "evidencia_del_canario": fila.get("porque"),
                "respaldo": respaldo.name,
                "database_writes": 0,
            }, ensure_ascii=False) + "\n")

    print(f"aplicados: {len(cambios)}   auditoria: {AUDITORIA.name}")
    print("\n  Estas agencias se van a recertificar contra un sitio nuevo en la")
    print("  proxima pasada de la cola. Revisar despues: inventario, identidad,")
    print("  RUN1/RUN2, inventario ajeno y procedencia.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

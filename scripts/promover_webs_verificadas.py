#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que las webs verificadas lleguen a la cola, en vez de quedar en un archivo.

No escribe en la base. `database_writes: 0`.

El hueco que arregla: `verificar_candidatas_web.py` establece webs oficiales y
las deja en `AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl`. Pero `load_catalog` —lo
que decide qué agencias tienen identidad `READY`— no lee ese archivo: lee
`AGENCY_OFFICIAL_WEB_VERIFIED.jsonl`, y sólo las filas con
`verificacion == "VERIFICADA_ARGENTINA"`.

O sea que 155 webs establecidas eran invisibles para la cola. Encontrar el dato
y no conectarlo es lo mismo que no encontrarlo.

**Por qué no alcanza con copiar.** El artefacto que la cola lee exige una cosa
más que mi verificación no comprueba: que el sitio sea argentino. Mi paso
establece *"este sitio es de esta inmobiliaria"*; el artefacto además pide
*"y está en Argentina"*. Copiar sin ese chequeo metería en la cola dominios
extranjeros, que es justo lo que la corrida anterior rechazó en 10 casos
(`RECHAZADA_TLD_EXTRANJERO` 8, `RECHAZADA_OTRO_PAIS` 2).

Por eso acá se comprueba antes de promover, y lo que no pasa queda anotado con
su razón en vez de descartarse en silencio.

Uso:
    python scripts/promover_webs_verificadas.py            # dry-run
    python scripts/promover_webs_verificadas.py --aplicar
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import shutil
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
ORIGEN = DATOS / "AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl"
DESTINO = DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"

ESTABLECIDAS = {"OFFICIAL_WEB_VERIFIED", "OFFICIAL_WEB_HIGH_CONFIDENCE"}
UA = {"User-Agent": "Mozilla/5.0 (compatible; ERETZ/1.0)",
      "Accept-Encoding": "gzip"}

# TLD que no son argentinos y no admiten prueba en contrario barata.
TLD_EXTRANJERO = re.compile(r"\.(uy|br|cl|py|bo|pe|es|mx|co|us|it|fr)$", re.I)
# Senyales de que la pagina habla de Argentina.
SENALES_AR = re.compile(
    r"argentin|buenos aires|c[oó]rdoba|rosario|mendoza|santa fe|tucum[aá]n|"
    r"salta|neuqu[eé]n|bariloche|mar del plata|la plata|CABA|\+54|0800|"
    r"\bAFIP\b|CUIT", re.I)


def traer(url: str, timeout: float = 15) -> str:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            crudo = r.read(200_000)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    crudo = gzip.decompress(crudo)
                except OSError:
                    pass
            return crudo.decode("utf-8", "replace")
    except Exception:
        return ""


def es_argentina(url: str) -> tuple[str, str]:
    """Devuelve (verificacion, razon). El .ar cierra solo; el resto se abre."""
    host = urlsplit(url).netloc.lower()
    if host.endswith(".ar"):
        return "VERIFICADA_ARGENTINA", "dominio .ar"
    if TLD_EXTRANJERO.search(host):
        return "RECHAZADA_TLD_EXTRANJERO", f"tld de otro pais en {host}"
    html = traer(url)
    if not html:
        return "NO_RESPONDE", "no se pudo abrir para comprobar el pais"
    texto = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", texto))[:20000]
    if len(texto.strip()) < 200:
        return "PAGINA_SIN_TEXTO", "la pagina no sirve texto suficiente"
    m = SENALES_AR.search(texto)
    if m:
        return "VERIFICADA_ARGENTINA", f"la pagina menciona '{m.group(0)}'"
    return "SIN_EVIDENCIA_DE_PAIS", "ninguna senyal de Argentina en el texto"


def ya_en_destino() -> set[str]:
    fuera = set()
    if not DESTINO.exists():
        return fuera
    for linea in DESTINO.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fuera.add(json.loads(linea)["canonical_agency_id"])
        except (ValueError, KeyError):
            continue
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto no toca el artefacto que la cola lee")
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()

    if not ORIGEN.exists():
        raise SystemExit(f"no existe {ORIGEN}")
    presentes = ya_en_destino()
    candidatas = []
    for linea in ORIGEN.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        if fila.get("estado") not in ESTABLECIDAS:
            continue
        if not fila.get("official_web"):
            continue
        if fila["canonical_agency_id"] in presentes:
            continue
        candidatas.append(fila)

    print("### PROMOVER WEBS VERIFICADAS A LA COLA ###")
    print(f"  webs establecidas sin promover: {len(candidatas):,}")
    print(f"  ya presentes en el destino:     {len(presentes):,}")
    if not args.aplicar:
        print("\n  DRY-RUN: no se toca nada. Agregar --aplicar para promover.")

    estados: Counter = Counter()
    nuevas = []
    for i, fila in enumerate(candidatas, 1):
        verificacion, razon = es_argentina(fila["official_web"])
        estados[verificacion] += 1
        if verificacion == "VERIFICADA_ARGENTINA":
            nuevas.append({
                "canonical_agency_id": fila["canonical_agency_id"],
                "nombre": fila.get("canonical_name") or "",
                "estado": "AFIRMABLE",
                "razon": fila.get("razon") or "",
                "official_url": fila["official_web"],
                "origen_descubierto": fila["official_web"],
                "url_descubierta": fila["official_web"],
                "era_ruta_profunda": False,
                "entidades_que_reclaman_el_host": 1,
                "identity_score": fila.get("confianza") or 0,
                "verificacion": verificacion,
                "verificacion_razon": razon,
                "origen_del_dato": "verificar_candidatas_web",
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "database_writes": 0,
            })
        if i % 25 == 0:
            print(f"  {i}/{len(candidatas)}", flush=True)
        time.sleep(args.pausa)

    print("\nRESULTADO DE LA COMPROBACION DE PAIS")
    for estado, n in estados.most_common():
        print(f"   {estado[:34]:36} {n:5}")

    if args.aplicar and nuevas:
        respaldo = DESTINO.with_suffix(
            f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(DESTINO, respaldo)
        with DESTINO.open("a", encoding="utf-8") as fh:
            for fila in nuevas:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"\n   promovidas: {len(nuevas):,}")
        print(f"   respaldo:   {respaldo.name}")
        print("   la cola las va a ver en su proximo arranque")
    elif nuevas:
        print(f"\n   promoveria {len(nuevas):,} (dry-run)")

    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

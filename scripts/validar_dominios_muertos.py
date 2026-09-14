#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los 139 `DOMAIN_DEAD`: ¿están muertos, o estaban caídos ese día?

No escribe en la base. `database_writes: 0`.

El §6 lo pide explícitamente: no confundir una caída temporal con un cierre. Y
en este bloque ya confundí cinco veces "no pude leer" con un hallazgo, así que
acá la prueba se diseña al revés — **para que sea difícil declarar muerto**, no
fácil.

### Qué se considera muerte, y qué no

    MUERTO           el DNS no resuelve, o el dominio está parkeado/en venta
    VIVO             responde y sirve contenido
    CAIDO_HOY        el DNS resuelve pero no contesta: puede ser de hoy nomás
    ILEGIBLE         contesta vacío o con desafío anti-bot

Sólo `MUERTO` es terminal. `CAIDO_HOY` vuelve a la cola: un servidor apagado
una tarde no es una inmobiliaria cerrada.

La diferencia entre `MUERTO` y `CAIDO_HOY` es el DNS. Un dominio abandonado de
verdad pierde los registros o los apunta a un parking; uno con el servidor
caído sigue resolviendo a su IP.

Uso:
    python scripts/validar_dominios_muertos.py
"""
from __future__ import annotations

import argparse
import gzip
import json
import re
import socket
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

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_DOMINIOS_MUERTOS_VALIDADOS.jsonl"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}

MUERTO, VIVO, CAIDO_HOY, ILEGIBLE = "MUERTO", "VIVO", "CAIDO_HOY", "ILEGIBLE"


def resuelve(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except OSError:
        return False


def pedir(url: str, timeout: float = 15) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            crudo = r.read(300_000)
            if r.headers.get("Content-Encoding") == "gzip":
                try:
                    crudo = gzip.decompress(crudo)
                except OSError:
                    pass
            return r.status, crudo.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def diagnosticar(url: str, pausa: float) -> tuple[str, str]:
    """Dos intentos separados en el tiempo. Uno solo no distingue nada."""
    host = urlsplit(url if "://" in url else "https://" + url).netloc
    if not host:
        return MUERTO, "no hay host en la url registrada"
    if not resuelve(host):
        # Sin DNS no hay servidor que pueda estar caido: el dominio se solto.
        return MUERTO, f"el DNS no resuelve {host}"

    base = url if "://" in url else "https://" + url
    estado1, cuerpo1 = pedir(base)
    if estado1 is None:
        time.sleep(max(pausa, 3.0))
        estado2, cuerpo2 = pedir(base)
        if estado2 is None:
            # El DNS resuelve pero nadie contesta, dos veces. Puede ser de hoy.
            return CAIDO_HOY, "el DNS resuelve y el servidor no contesta (2 intentos)"
        estado1, cuerpo1 = estado2, cuerpo2

    if estado1 and estado1 >= 400:
        return CAIDO_HOY, f"HTTP {estado1}"
    if not cuerpo1.strip():
        return ILEGIBLE, f"HTTP {estado1} con cuerpo vacio: desafio o app"

    sitio = v2.Sitio(url=base, titulo="", texto=re.sub(
        r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", re.sub(
            r"(?s)<(script|style)[^>]*>.*?</\1>", " ", cuerpo1)))[:8000],
        http=estado1, html_bytes=len(cuerpo1))
    tipo = v2.clasificar_sitio(sitio)
    if tipo == v2.PARKED_DOMAIN:
        return MUERTO, "el dominio esta parkeado o en venta"
    return VIVO, f"responde y sirve contenido ({tipo})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pausa", type=float, default=0.8)
    args = ap.parse_args()

    web = {}
    for linea in (DATOS / "agency_web_directory.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            f = json.loads(linea)
            if f.get("canonical_agency_id"):
                web[f["canonical_agency_id"]] = f
    filas = [json.loads(l) for l in (CERT / "ERETZ_STAGING_BREAKDOWN.jsonl").read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]
    objetivo = [f for f in filas if f["block_reason"] == "DOMAIN_DEAD"]

    print("### VALIDAR DOMINIOS MUERTOS ###")
    print(f"  a validar: {len(objetivo)}")
    print("  solo MUERTO es terminal; CAIDO_HOY vuelve a la cola\n")

    estados: Counter = Counter()
    salida = []
    for i, f in enumerate(objetivo, 1):
        w = web.get(f["agency_id"]) or {}
        # La url de estas filas vive en las candidatas probadas, no en
        # `selected_domain`: justamente porque ninguna quedo seleccionada.
        # Se descartan las de portales: que buscainmueble responda no dice nada
        # sobre si la inmobiliaria tiene dominio.
        candidatas = [u for u in (w.get("candidate_urls") or [])
                      if u and not v2.es_portal_url(u)]
        url = (w.get("selected_domain") or w.get("previous_url")
               or (candidatas[0] if candidatas else "")
               or f.get("official_url") or "")
        if not url:
            estados["SIN_URL"] += 1
            salida.append({"agency_id": f["agency_id"], "nombre": f.get("nombre"),
                           "estado": "SIN_URL", "razon": "no hay dominio registrado",
                           "url": ""})
            continue
        estado, razon = diagnosticar(url, args.pausa)
        estados[estado] += 1
        salida.append({"agency_id": f["agency_id"], "nombre": f.get("nombre"),
                       "url": url, "estado": estado, "razon": razon,
                       "avisos_observados": f.get("avisos_observados") or 0,
                       "cuando": time.strftime("%Y-%m-%dT%H:%M:%S")})
        time.sleep(args.pausa)
        if i % 25 == 0:
            print(f"  {i}/{len(objetivo)}", flush=True)

    with SALIDA.open("w", encoding="utf-8") as fh:
        for s in salida:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")

    print("\n=== RESULTADO ===")
    for estado, n in estados.most_common():
        marca = "  TERMINAL" if estado == MUERTO else ""
        print(f"   {estado:14} {n:5}{marca}")
    print(f"\n  terminalizables como fuente inactiva: {estados[MUERTO]}")
    print(f"  vuelven a la cola:                    "
          f"{estados[VIVO] + estados[CAIDO_HOY] + estados[ILEGIBLE]}")
    print(f"\n  artefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

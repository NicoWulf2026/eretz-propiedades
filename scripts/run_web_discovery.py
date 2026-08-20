#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Busca y verifica la web oficial de cada inmobiliaria canonica.

Roomix no publica la web del anunciante, asi que hay que encontrarla afuera. Sin
acceso a un buscador programatico, la via disponible es generar dominios
candidatos a partir del nombre y despues COMPROBAR que el sitio corresponde a
esa inmobiliaria. La generacion es barata y equivocarse no cuesta nada; lo que
decide es la verificacion, que es la parte cara y la que evita el falso
positivo.

Eso tiene una consecuencia honesta que conviene decir de entrada: este metodo
encuentra las webs cuyo dominio se parece al nombre, y no encuentra las que
eligieron un dominio sin relacion. El NOT_FOUND de este script significa "no lo
encontro este metodo", no "no tiene web".

Reanudable: cada entidad resuelta se escribe y no se vuelve a investigar.
Cortes: un dominio por vez, con pausa, y sin reintentos agresivos.
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

UA = "Mozilla/5.0 (compatible; ERETZ-AgencyWebCheck/1.0; +contacto@eretz)"
TLDS = (".com.ar", ".com", ".ar")


def candidatos_de_nombre(nombre: str) -> list[str]:
    """Dominios plausibles a partir del nombre.

    Se prueban las formas que una inmobiliaria suele registrar: el nombre
    completo sin espacios, el nucleo sin las palabras del rubro, y el nucleo con
    `propiedades`. No se inventa nada mas: cada candidata extra multiplica las
    peticiones sin mejorar la probabilidad.
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


def bajar(url: str, timeout: int = 12) -> wd.Candidata:
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
            return wd.Candidata(url=final, origen="dominio_derivado", titulo=titulo,
                                texto=texto, http=r.status,
                                redirects=[url] if final != url else [])
    except urllib.error.HTTPError as e:
        return wd.Candidata(url=url, origen="dominio_derivado", http=e.code)
    except Exception:
        # DNS inexistente, TLS roto, timeout: la candidata simplemente no existe.
        return wd.Candidata(url=url, origen="dominio_derivado", http=None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--pausa", type=float, default=0.4)
    ap.add_argument("--limite", type=int, default=0)
    a = ap.parse_args()
    dd = Path(a.data_dir)

    padron = [json.loads(l) for l in
              (dd / "roomix_agency_directory.jsonl").open(encoding="utf-8") if l.strip()]
    cwin = _load("coverage_windows")
    objetivo = [e for e in padron if e.get("tipo") in cwin.CUENTA_COMO_AGENCIA]
    # Las que mas publican primero: son las que mas importa resolver.
    objetivo.sort(key=lambda e: -(e.get("avisos_observados") or 0))

    salida = dd / "agency_web_directory.jsonl"
    hechas = wd.cargar_hechas(salida)
    pendientes = [e for e in objetivo if e["stable_id"] not in hechas]
    if a.limite:
        pendientes = pendientes[:a.limite]

    print(f"### BUSQUEDA DE WEBS OFICIALES ###", flush=True)
    print(f"  entidades inmobiliarias: {len(objetivo):,}", flush=True)
    print(f"  ya resueltas:            {len(hechas):,}", flush=True)
    print(f"  a investigar ahora:      {len(pendientes):,}", flush=True)

    estados: Counter = Counter()
    with salida.open("a", encoding="utf-8") as fh:
        for i, e in enumerate(pendientes, 1):
            cands = []
            for url in candidatos_de_nombre(e["nombre_original"]):
                c = bajar(url)
                # Solo se conservan las que respondieron algo: una candidata
                # inexistente no aporta ni como evidencia.
                if c.http is not None:
                    cands.append(c)
                time.sleep(a.pausa)
                if len(cands) >= 3:
                    break
            v = wd.verificar(e, cands)
            fila = wd.fila_de_salida(e, v, cands)
            fila["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            fh.flush()
            estados[v.estado] += 1
            if i % 25 == 0:
                print(f"    {i}/{len(pendientes)}  {dict(estados)}", flush=True)

    print(f"\n  resultado: {dict(estados)}", flush=True)
    print(f"  artefacto -> {salida}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Construye ROOMIX_AGENCY_DIRECTORY: el padron unico de publicadores.

Las fichas de Roomix no son el objetivo: son el unico lugar donde aparece el
bloque "Publicado por". De cada ficha solo se conserva lo que hace falta para
identificar y verificar al publicador. Este script no lee ni un dato de la
propiedad: precio, descripcion, fotos y caracteristicas no entran, ni siquiera
de paso.

Si 300 avisos son de la misma inmobiliaria, el resultado es UNA inmobiliaria con
300 evidencias acumuladas.

Lo que Roomix expone del publicador, verificado en la pagina: nombre y logo. NO
expone telefono, web ni email, asi que esas columnas quedan vacias a proposito y
no por falta de esfuerzo. La zona se infiere del slug de las URLs que ya
guardamos como provenance, no de leer el aviso.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")
cw = _load("agency_crosswalk")

DIRECTORY_VERSION = "roomix_agency_directory_v1"
LOGO = "https://cdn.roomix.ai/agents/{agent_id}"

# Tokens del slug que describen la propiedad, no la zona. Se descartan para que
# la zona inferida no quede contaminada con "3-ambientes" o "departamento".
RUIDO_SLUG = re.compile(
    r"^(departamento|depto|casa|ph|local|oficina|cochera|terreno|lote|galpon|"
    r"quinta|campo|edificio|duplex|loft|monoambiente|piso|"
    r"\d+|\d+-?ambientes?|ambientes?|dormitorios?|banos?|amb)$")


def zona_de_url(url: str) -> str:
    """Zona aproximada a partir del slug. Senal debil, se usa solo para ayudar
    a identificar, nunca para decidir identidad por si sola."""
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"-[0-9a-f]{6,}$", "", slug)          # hash final
    toks = [t for t in slug.split("-") if t and not RUIDO_SLUG.match(t)]
    return " ".join(toks[-3:]) if toks else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--eretz-keys", help="JSON con claves de main y staging para el cruce")
    a = ap.parse_args()
    dd = Path(a.data_dir)

    obs = [json.loads(l) for l in (dd / "observations.jsonl").open(encoding="utf-8") if l.strip()]
    pubs = {p["agent_id"]: p for p in
            (json.loads(l) for l in (dd / "publishers.jsonl").open(encoding="utf-8") if l.strip())}

    fr = {}
    fp = dd / "franchises.json"
    if fp.exists():
        fr = json.loads(fp.read_text(encoding="utf-8"))

    def red_de(nombre: str) -> str | None:
        n = d.norm_name(nombre).replace(" ", "")
        for marca in fr:
            m = d.norm_name(marca).replace(" ", "")
            if m and m in n:
                return marca
        return None

    # --- acumulacion de evidencia por publicador ---
    ev_urls: dict[str, list[str]] = defaultdict(list)
    ev_zonas: dict[str, Counter] = defaultdict(Counter)
    ev_nombres: dict[str, Counter] = defaultdict(Counter)
    primera: dict[str, int] = {}
    ultima: dict[str, int] = {}
    for o in obs:
        aid = o.get("agent_id")
        if not aid:
            continue
        ev_urls[aid].append(o["url"])
        z = zona_de_url(o["url"])
        if z:
            ev_zonas[aid][z] += 1
        if o.get("agent_name"):
            ev_nombres[aid][o["agent_name"]] += 1
        ts = o.get("ts") or 0
        primera[aid] = min(primera.get(aid, ts), ts)
        ultima[aid] = max(ultima.get(aid, ts), ts)

    # --- cruce contra ERETZ, si hay claves disponibles ---
    eretz_main: set[str] = set()
    eretz_staging: set[str] = set()
    if a.eretz_keys and Path(a.eretz_keys).exists():
        k = json.loads(Path(a.eretz_keys).read_text(encoding="utf-8"))
        eretz_main = {x.lower() for x in k.get("main", [])}
        eretz_staging = {x.lower() for x in k.get("staging", [])}

    filas = []
    for aid, p in pubs.items():
        nombre = p.get("raw_name") or ""
        norm = d.norm_name(nombre)
        tipo = p.get("type") or cw.classify(nombre)
        red = red_de(nombre)
        zonas = [z for z, _ in ev_zonas[aid].most_common(5)]

        if not eretz_main and not eretz_staging:
            clasif, razon = "SIN_CRUZAR", "no se aportaron claves de ERETZ"
        elif norm in eretz_main:
            clasif, razon = "EXACT_MATCH", "presente en inmobiliarias_main"
        elif norm in eretz_staging:
            clasif, razon = "HIGH_CONFIDENCE_EXISTING", "presente en inmobiliarias_staging"
        elif tipo != "INMOBILIARIA":
            clasif, razon = "REJECTED_NOT_AGENCY", f"tipo {tipo}"
        elif len(norm) < 4:
            clasif, razon = "INSUFFICIENT_DATA", "nombre demasiado corto"
        else:
            clasif, razon = "HIGH_CONFIDENCE_NEW", "sin coincidencia en main ni staging"

        filas.append({
            "stable_id": aid,
            "nombre_original": nombre,
            "nombre_normalizado": norm,
            "nucleo": d.norm_core(nombre),
            "variantes_de_nombre": [n for n, _ in ev_nombres[aid].most_common(3)],
            "tipo": tipo,
            "red_franquicia": red,
            "roomix_agent_id": aid,
            "roomix_logo": LOGO.format(agent_id=aid),
            "avisos_observados": len(ev_urls[aid]),
            "evidencia_urls": ev_urls[aid][:10],
            "evidencia_total": len(ev_urls[aid]),
            "zonas_observadas": zonas,
            # Roomix no publica estos datos del anunciante. Verificado en la
            # ficha: solo hay nombre y logo.
            "telefono": None, "web": None, "email": None,
            "clasificacion_eretz": clasif,
            "razon": razon,
            "matricula": sorted(d.matriculas(nombre)),
            "primera_vista_ts": primera.get(aid),
            "ultima_vista_ts": ultima.get(aid),
            "matcher_version": d.MATCHER_VERSION,
            "directory_version": DIRECTORY_VERSION,
            "provenance": "roomix_public_property_page",
        })

    filas.sort(key=lambda r: -r["avisos_observados"])
    out = dd / "roomix_agency_directory.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in filas) + "\n",
                   encoding="utf-8")

    print("### ROOMIX_AGENCY_DIRECTORY ###", flush=True)
    print(f"  avisos usados como evidencia: {len(obs):,}", flush=True)
    print(f"  publicadores unicos:          {len(filas):,}", flush=True)
    print(f"  compresion evidencia->entidad: {len(obs)/max(len(filas),1):.1f} avisos por entidad",
          flush=True)
    print(f"\n  por tipo:            {dict(Counter(r['tipo'] for r in filas).most_common())}",
          flush=True)
    print(f"  por clasificacion:   {dict(Counter(r['clasificacion_eretz'] for r in filas).most_common())}",
          flush=True)
    redes = Counter(r["red_franquicia"] for r in filas if r["red_franquicia"])
    print(f"  oficinas por red:    {dict(redes.most_common())}", flush=True)
    print(f"  con matricula:       {sum(1 for r in filas if r['matricula']):,}", flush=True)
    print(f"\n  padron -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

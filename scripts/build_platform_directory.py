#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mapa de plataformas: una fila por agencia con web conocida.

Cruza todo lo que ya se midio -mapa tecnologico, censo de no soportadas y el
resultado real de cada rollout- en un solo directorio. La diferencia con el mapa
tecnologico original es que ese decia "que parece usar este sitio" y este dice
"que se logro leer, con que connector y cuanto salio".

La clasificacion no se re-adivina: se toma la evidencia mas fuerte disponible,
en este orden, porque cada nivel corrige al anterior con datos reales.

  1. el rollout: si un connector enumero inventario, la plataforma es esa
  2. el censo de no soportadas: reviso las que fallaron y las reclasifico
  3. el mapa tecnologico: la deteccion inicial por marcadores del HTML

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "platform_directory_v1"

ROLLOUTS = [
    ("TOKKO_ROLLOUT_FULL", "tokko"),
    ("WP_ROLLOUT_FULL", "wordpress"),
    ("C21_CANARY", "century21"),
    ("GENERICO_CANARY", "generico"),
    ("RESCATE_generico", "generico"),
    ("RESCATE_tokko", "tokko"),
    ("RESCATE_wordpress", "wordpress"),
]


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def host(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", u or "").split("/")[0].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    a = ap.parse_args()
    dd, raiz = Path(a.data_dir), Path(a.raiz)

    directorio = {d["canonical_agency_id"]: d
                  for d in leer(dd / "agency_web_directory.jsonl")}
    mapa = {m["canonical_agency_id"]: m
            for m in leer(dd / "scrape_source_technology_map.jsonl")}
    censo = {c["canonical_agency_id"]: c
             for c in leer(raiz / "UNSUPPORTED_CENSUS.jsonl")}

    # Resultado real por fuente, con el connector que lo consiguio.
    resultado: dict[str, dict] = {}
    props_por_agencia: Counter = Counter()
    for carpeta, connector in ROLLOUTS:
        base = raiz / carpeta
        # Se leen TODAS las corridas, no la ultima. Preferir la mas reciente
        # esconde lo que una corrida a medias todavia no proceso: con la segunda
        # corrida en curso, 511 fuentes Tokko ya terminadas figuraban como no
        # intentadas.
        inv = []
        for corrida in ("1", "2"):
            inv += leer(base / f"source_inventory_run{corrida}.jsonl")
        for r in inv:
            cid = r.get("canonical_agency_id")
            previo = resultado.get(cid)
            # Gana el que efectivamente trajo inventario.
            if previo and previo.get("enumeradas", 0) >= (r.get("enumeradas") or 0):
                continue
            resultado[cid] = {**r, "connector": r.get("connector") or connector}
        # Para el conteo de propiedades se usa UNA sola corrida -la mas
        # completa-: sumar las dos contaria cada propiedad dos veces.
        mejor, n = None, -1
        for corrida in ("1", "2"):
            props = base / f"properties_run{corrida}.jsonl"
            if props.exists():
                filas_p = leer(props)
                if len(filas_p) > n:
                    mejor, n = filas_p, len(filas_p)
        for p in (mejor or []):
            props_por_agencia[p.get("canonical_agency_id")] += 1

    filas = []
    for cid, d in directorio.items():
        m = mapa.get(cid) or {}
        c = censo.get(cid) or {}
        r = resultado.get(cid) or {}
        dominio = (r.get("official_url") or m.get("official_url")
                   or d.get("selected_domain") or d.get("current_eretz_web"))
        if not dominio:
            continue

        enumeradas = r.get("enumeradas") or 0
        declarado = r.get("total_declarado") or c.get("declared_inventory")

        # --- plataforma, por evidencia mas fuerte primero -------------------
        if enumeradas and r.get("connector"):
            plataforma = {"tokko": "TOKKO", "wordpress": "WORDPRESS",
                          "century21": "CENTURY21", "generico": "SITIO_PROPIO"
                          }.get(r["connector"], r["connector"].upper())
            variante = r.get("variante") or c.get("clasificacion_nueva")
            confianza, evidencia = "alta", "el connector enumero inventario"
        elif c:
            plataforma = (c.get("plataforma_detectada") or "").upper() or "DESCONOCIDA"
            variante = c.get("clasificacion_nueva")
            confianza, evidencia = "media", "censo de fuentes no soportadas"
        elif m:
            plataforma = m.get("detected_platform") or "DESCONOCIDA"
            variante = m.get("strategy")
            confianza, evidencia = "baja", "marcadores del HTML"
        else:
            plataforma, variante = "SIN_CLASIFICAR", None
            confianza, evidencia = "ninguna", "no se intento"

        # --- estado del connector -------------------------------------------
        estado = r.get("estado")
        if estado == "OK" and enumeradas:
            cs = "SUPPORTED_STANDARD" if variante in (
                "TFW_ESTANDAR", "WORDPRESS_REST", "C21_JSON") else "SUPPORTED_CUSTOM"
        elif estado == "ENUMERACION_INCOMPLETA":
            cs = "ENUMERACION_INCOMPLETA"
        elif estado in ("BLOQUEADA",):
            cs = "NETWORK_BLOCKED"
        elif c.get("status") == "PLATAFORMA_CONOCIDA_SIN_INVENTARIO":
            cs = "NO_INVENTORY"
        elif estado in ("VARIANTE_NO_SOPORTADA", "ERROR_DISCOVERY", "EXCEPCION"):
            cs = "UNSUPPORTED_PLATFORM"
        elif not r and not c:
            cs = "NO_INTENTADA"
        else:
            cs = "UNKNOWN"

        eid = d.get("eretz_id")
        filas.append({
            "canonical_agency_id": cid,
            "eretz_id": int(eid) if str(eid).isdigit() else None,
            "agency_name": d.get("canonical_name"),
            "domain": dominio,
            "host": host(dominio),
            "province": d.get("province"),
            "platform": plataforma,
            "variant": variante,
            "confidence": confianza,
            "evidence": evidencia,
            "declared_inventory": declarado,
            "enumerated_inventory": enumeradas or None,
            "coverage_ratio": (round(enumeradas / declarado, 4)
                               if declarado and enumeradas else None),
            "properties_normalized": props_por_agencia.get(cid) or None,
            "connector": r.get("connector"),
            "connector_status": cs,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "classifier_version": VERSION,
        })

    Path(a.salida).write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in filas), encoding="utf-8")

    print("### DIRECTORIO DE PLATAFORMAS ###")
    print(f"  agencias con web: {len(filas):,}\n")
    print("  por plataforma:")
    for k, v in Counter(f["platform"] for f in filas).most_common(14):
        props = sum(f["properties_normalized"] or 0
                    for f in filas if f["platform"] == k)
        con = sum(1 for f in filas if f["platform"] == k
                  and f["connector_status"].startswith("SUPPORTED"))
        print(f"    {k:18} {v:5,} agencias  {con:5,} con connector  "
              f"{props:7,} propiedades")
    print("\n  por estado del connector:")
    for k, v in Counter(f["connector_status"] for f in filas).most_common():
        print(f"    {k:26} {v:5,}")
    print(f"\n  artefacto -> {a.salida}")

    # --- ranking del proximo connector por ROI ------------------------------
    sin_conector = [f for f in filas
                    if not f["connector_status"].startswith("SUPPORTED")]
    por_plat = defaultdict(list)
    for f in sin_conector:
        por_plat[f["platform"]].append(f)
    print("\n  proximas plataformas por cobertura pendiente:")
    for k, g in sorted(por_plat.items(), key=lambda t: -len(t[1]))[:8]:
        decl = sum(x["declared_inventory"] or 0 for x in g)
        print(f"    {k:18} {len(g):5,} agencias  inventario declarado {decl:7,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

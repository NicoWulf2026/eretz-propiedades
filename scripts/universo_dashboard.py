#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dónde está cada una de las 6.597, y si llegamos al 12 de octubre.

No escribe nada. `database_writes: 0`.

Existe porque "vamos por 360 de 764" era una respuesta honesta a la pregunta
equivocada. 764 no es el universo: es el subconjunto que YA tiene identidad
resuelta. El universo son 6.597, y el 75 % de ellas está detenido antes de
llegar a la cola de certificación.

El cuello de botella medido el 2026-09-14 no es descubrir webs ni certificar:

    4.953 inmobiliarias EXISTEN en la base, en el namespace `staging`, con
    nombre coincidente de alta confianza, y NINGUNA fue promovida a `main`.
    La evidencia lo dice literal: "0/4920 candidates linked by
    main.staging_id_origen".

`eretz_id` tiene que ser una FK de `main` porque se escribe como
`inmobiliaria_id` de cada propiedad. Sin promoción no hay FK, sin FK no hay
READY, y sin READY no se certifica. Encontrarles la web no las desbloquea:
1.698 de ellas YA tienen dominio conocido y siguen paradas igual.

Uso:
    python scripts/universo_dashboard.py
    python scripts/universo_dashboard.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import load_catalog, resolve_identity  # noqa: E402

V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
DIRECTORIO = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
            r"\AGENCY_CERTIFICATION_RESULTS.jsonl")
RESOLUCION = V2 / "AGENCY_ID_RESOLUTION_FINAL.jsonl"

DEADLINE = date(2026, 10, 12)
# Estados en los que una agencia ya no vuelve a la cola.
TERMINALES = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "BLOCKED_EXTERNAL",
              "NO_INVENTORY_CONFIRMED", "IDENTITY_PENDING"}


def resoluciones() -> dict[str, dict]:
    fuera = {}
    for linea in RESOLUCION.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("canonical_agency_id"):
            fuera[fila["canonical_agency_id"]] = fila
    return fuera


def certificaciones() -> tuple[dict[str, str], dict[str, str]]:
    """Último estado por agencia, y cuándo se vio por primera vez."""
    estado, primera = {}, {}
    if not CERT.exists():
        return estado, primera
    for linea in CERT.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        agencia = fila.get("canonical_agency_id")
        if not agencia:
            continue
        estado[agencia] = fila.get("status") or ""
        primera.setdefault(agencia, fila.get("checked_at") or "")
    return estado, primera


def medir() -> dict:
    catalogo = load_catalog(V2, DATOS, DIRECTORIO)
    resol = resoluciones()
    estado_cert, primera_vez = certificaciones()

    bloqueo = Counter()
    identidad = Counter()
    cert = Counter()
    con_dominio_bloqueado = 0
    sin_web_con_fk = 0

    for canonical_id, registro in catalogo.items():
        ident = resolve_identity(registro, canonical_id)
        identidad[ident["identity_status"]] += 1
        razones = " | ".join(ident.get("identity_reasons") or [])
        r = resol.get(canonical_id) or {}
        evidencia = r.get("evidence") or {}

        if ident["identity_status"] == "READY":
            bloqueo["0_listas_para_certificar"] += 1
            cert[estado_cert.get(canonical_id) or "sin_intentar"] += 1
            continue

        if r.get("resolution_method") == "STAGING_NAMESPACE_NOT_A_MAIN_FK":
            bloqueo["1_staging_sin_promover_a_main"] += 1
            if r.get("official_domain"):
                con_dominio_bloqueado += 1
        elif r.get("resolution_status") == "NOT_FOUND_IN_ERETZ":
            bloqueo["2_sin_candidata_en_eretz"] += 1
        elif r.get("resolution_status") == "AMBIGUOUS":
            bloqueo["3_candidata_ambigua"] += 1
        elif "official website unavailable" in razones:
            bloqueo["4_resuelta_pero_sin_web"] += 1
            sin_web_con_fk += 1
        elif ident["identity_status"] == "BLOCKED_EXTERNAL":
            bloqueo["5_web_ajena_o_portal"] += 1
        else:
            bloqueo["6_otro"] += 1

    return {"universo": len(catalogo), "bloqueo": dict(bloqueo),
            "identidad": dict(identidad), "certificacion": dict(cert),
            "bloqueadas_con_dominio_conocido": con_dominio_bloqueado,
            "sin_web_con_fk": sin_web_con_fk,
            "primera_vez": primera_vez, "estado_cert": estado_cert}


def ritmo(primera_vez: dict[str, str], horas: int = 24) -> int:
    """Agencias vistas por primera vez en las últimas N horas."""
    ahora = time.time()
    n = 0
    for cuando in primera_vez.values():
        if not cuando:
            continue
        try:
            t = datetime.strptime(cuando[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
        except ValueError:
            continue
        if ahora - t <= horas * 3600:
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    m = medir()
    hoy = date.today()
    dias = (DEADLINE - hoy).days
    terminales = sum(n for e, n in m["certificacion"].items() if e in TERMINALES)
    no_terminales = m["universo"] - terminales
    real = ritmo(m["primera_vez"], 24)
    requerido = no_terminales / dias if dias > 0 else float("inf")
    proyeccion = (hoy.toordinal() + no_terminales / real) if real else None

    if args.json:
        print(json.dumps({**{k: v for k, v in m.items()
                             if k not in ("primera_vez", "estado_cert")},
                          "dias_restantes": dias, "terminales": terminales,
                          "ritmo_real_24h": real,
                          "ritmo_requerido": round(requerido, 1)},
                         ensure_ascii=False, indent=1))
        return 0

    print(f"UNIVERSO ERETZ — {hoy}   deadline {DEADLINE}   faltan {dias} dias\n")
    print(f"universo canonico: {m['universo']:,}\n")
    print("DONDE ESTA CADA UNA")
    etiquetas = {
        "0_listas_para_certificar": "listas para certificar (la pasada actual)",
        "1_staging_sin_promover_a_main": "EN STAGING, SIN PROMOVER A MAIN",
        "2_sin_candidata_en_eretz": "sin candidata en ERETZ (altas nuevas)",
        "3_candidata_ambigua": "candidata ambigua",
        "4_resuelta_pero_sin_web": "resuelta, le falta la web",
        "5_web_ajena_o_portal": "web ajena o perfil de portal",
        "6_otro": "otro",
    }
    for clave in sorted(m["bloqueo"]):
        n = m["bloqueo"][clave]
        print(f"   {etiquetas.get(clave, clave):44} {n:6,}  "
              f"{n / m['universo'] * 100:5.1f} %")

    print(f"\n   de las bloqueadas en staging, YA tienen dominio conocido: "
          f"{m['bloqueadas_con_dominio_conocido']:,}")
    print(f"   lo que Brave desbloquearia por si solo:                   "
          f"{m['sin_web_con_fk']:,}")

    print("\nCERTIFICACION DE LAS LISTAS")
    for estado, n in sorted(m["certificacion"].items(), key=lambda x: -x[1]):
        print(f"   {estado[:40]:44} {n:6,}")

    print("\nRITMO")
    print(f"   terminales hoy:                {terminales:6,}")
    print(f"   no terminales:                 {no_terminales:6,}")
    print(f"   ritmo real (nuevas / 24 h):    {real:6}")
    print(f"   ritmo requerido para el 12/10: {requerido:6.1f} por dia")
    if proyeccion:
        print(f"   fecha proyectada:              "
              f"{date.fromordinal(int(proyeccion))}")
    else:
        print("   fecha proyectada:              nunca al ritmo actual")

    estado = "RED" if not real or requerido > real * 1.1 else "GREEN"
    print(f"\nDEADLINE_STATUS: {estado}")
    if estado == "RED":
        print("   el cuello de botella no es certificar ni descubrir webs:")
        print("   es la promocion de staging a main, que es un write productivo")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

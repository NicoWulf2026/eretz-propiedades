#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una fila por inmobiliaria canónica, con su estado y qué la destraba.

No escribe en la base. `database_writes: 0`.

Es el control de universo del §17: hasta ahora el estado de cada inmobiliaria
vivía repartido en cinco artefactos que no se miraban juntos —resolución de
identidad, directorio de plataformas, directorio web, verificación de
candidatas y resultados de certificación—, y por eso se podía contestar "vamos
por 360 de 764" sin notar que 764 era el 11,6 % del universo.

El campo que importa es `blocker`: qué hay que destrabar, no en qué estado
está. Un estado describe; un blocker se puede accionar.

Salida: ERETZ_UNIVERSO.jsonl + ERETZ_UNIVERSO.csv

Uso:
    python scripts/universo_tabla.py
    python scripts/universo_tabla.py --blocker PROMOCION_STAGING
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import load_catalog, resolve_identity  # noqa: E402

V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
DIRECTORIO = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT_DIR = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT_DIR / "ERETZ_UNIVERSO"

TERMINALES = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "BLOCKED_EXTERNAL",
              "NO_INVENTORY_CONFIRMED"}

# Qué hay que destrabar. En orden: el primero que aplica es el que manda,
# porque destrabar el segundo sin el primero no cambia nada. Encontrarle la web
# a una agencia que está en staging no la vuelve certificable.
PROMOCION = "PROMOCION_STAGING"
ALTA_NUEVA = "ALTA_NUEVA_EN_ERETZ"
AMBIGUA = "IDENTIDAD_AMBIGUA"
WEB = "FALTA_WEB"
WEB_AJENA = "WEB_AJENA"
VALIDACION = "FALTA_VALIDACION_LIVE"
CERTIFICAR = "CERTIFICAR"
NINGUNO = "NINGUNO"

SIGUIENTE = {
    PROMOCION: "promover su fila de staging a main (autorizacion pendiente)",
    ALTA_NUEVA: "decidir si se da de alta en ERETZ",
    AMBIGUA: "desambiguar a mano: dos candidatas",
    WEB: "buscar web (candidatas ya pagas, o Brave si no hay ninguna)",
    WEB_AJENA: "cerrar como perfil de portal o pagina de oficina",
    VALIDACION: "validar identidad contra la fuente viva",
    CERTIFICAR: "esta en la cola",
    NINGUNO: "cerrada",
}


def leer_jsonl(ruta: Path, clave: str = "canonical_agency_id") -> dict[str, dict]:
    fuera: dict[str, dict] = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get(clave):
            fuera[fila[clave]] = fila
    return fuera


def ultimos_resultados() -> dict[str, dict]:
    """El ultimo resultado de cada agencia, no el primero."""
    fuera: dict[str, dict] = {}
    ruta = CERT_DIR / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("canonical_agency_id"):
            fuera[fila["canonical_agency_id"]] = fila
    return fuera


def fila_de(canonical_id: str, registro: dict, resol: dict, web: dict,
            verif: dict, cert: dict) -> dict:
    ident = resolve_identity(registro, canonical_id)
    razones = " | ".join(ident.get("identity_reasons") or [])
    metodo = resol.get("resolution_method")
    estado_res = resol.get("resolution_status")

    if ident["identity_status"] == "READY":
        estado_cert = cert.get("status") or "EN_COLA"
        blocker = NINGUNO if estado_cert in TERMINALES else CERTIFICAR
    elif metodo == "STAGING_NAMESPACE_NOT_A_MAIN_FK":
        estado_cert = ""
        blocker = PROMOCION
    elif estado_res == "NOT_FOUND_IN_ERETZ":
        estado_cert = ""
        blocker = ALTA_NUEVA
    elif estado_res == "AMBIGUOUS":
        estado_cert = ""
        blocker = AMBIGUA
    elif ident["identity_status"] == "BLOCKED_EXTERNAL":
        estado_cert = ""
        blocker = WEB_AJENA
    elif "official website unavailable" in razones:
        estado_cert = ""
        blocker = WEB
    else:
        estado_cert = ""
        blocker = VALIDACION

    # La web que mas evidencia tiene, en ese orden.
    url = (verif.get("official_web") or ident.get("official_url")
           or web.get("selected_domain") or web.get("selected_office_page"))
    clase = ("OFFICIAL_OFFICE_PAGE" if (not verif.get("official_web")
                                        and web.get("selected_office_page"))
             else (registro.get("platform", {}).get("web_kind") or
                   ("OFFICIAL_WEB" if url else "")))
    metodo_web = ("verificacion_de_candidatas" if verif.get("official_web")
                  else (web.get("search_provider") or
                        ("eretz" if ident.get("official_url") else "")))

    auditoria = cert.get("enumeration_audit") or {}
    return {
        "agency_id": canonical_id,
        "nombre": ident.get("agency_name") or "",
        "ciudad": (registro.get("directory") or {}).get("city") or web.get("city") or "",
        "provincia": (registro.get("directory") or {}).get("province")
                     or web.get("province") or "",
        "eretz_id": ident.get("eretz_id") or "",
        "identity_status": ident["identity_status"],
        "web_status": web.get("status") or "",
        "official_url": url or "",
        "source_class": clase,
        "discovery_method": metodo_web,
        "evidence_strength": verif.get("confianza") or web.get("identity_score") or "",
        "certification_status": estado_cert,
        "terminal_status": ("TERMINAL" if estado_cert in TERMINALES else "ABIERTA"),
        "properties_count": auditoria.get("enumerated") or "",
        "last_attempt": cert.get("checked_at") or "",
        "blocker": blocker,
        "next_action": SIGUIENTE[blocker],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocker", help="listar solo las de este blocker")
    ap.add_argument("--salida", default=str(SALIDA))
    args = ap.parse_args()

    catalogo = load_catalog(V2, DATOS, DIRECTORIO)
    resol = leer_jsonl(V2 / "AGENCY_ID_RESOLUTION_FINAL.jsonl")
    web = leer_jsonl(DATOS / "agency_web_directory.jsonl")
    verif = leer_jsonl(DATOS / "AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl")
    cert = ultimos_resultados()

    filas = [fila_de(k, v, resol.get(k) or {}, web.get(k) or {},
                     verif.get(k) or {}, cert.get(k) or {})
             for k, v in sorted(catalogo.items())]

    if args.blocker:
        elegidas = [f for f in filas if f["blocker"] == args.blocker]
        for f in elegidas[:40]:
            print(f"   {f['nombre'][:38]:40} {f['ciudad'][:18]:20} "
                  f"{f['official_url'][:44]}")
        print(f"\n{len(elegidas)} con blocker {args.blocker}")
        return 0

    base = Path(args.salida)
    with open(f"{base}.jsonl", "w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    with open(f"{base}.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)

    print(f"UNIVERSO: {len(filas):,} inmobiliarias\n")
    cuenta = Counter(f["blocker"] for f in filas)
    print(f"{'blocker':26} {'agencias':>9}  siguiente accion")
    for blocker, n in cuenta.most_common():
        print(f"{blocker:26} {n:9,}  {SIGUIENTE[blocker]}")

    terminales = sum(1 for f in filas if f["terminal_status"] == "TERMINAL")
    con_web = sum(1 for f in filas if f["official_url"])
    print(f"\n   terminales:        {terminales:6,}")
    print(f"   con web conocida:  {con_web:6,}")
    print(f"\n   {base}.jsonl")
    print(f"   {base}.csv")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

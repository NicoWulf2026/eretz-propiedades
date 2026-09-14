#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las 4.953 de staging, una por una, con por qué está bloqueada.

No escribe en la base. `database_writes: 0`.

Hasta ahora las 4.953 eran una sola etiqueta —`STAGING`— y eso oculta la
pregunta que importa: **cuántas se pueden cerrar por regla y cuántas hay que
investigar**. Una etiqueta describe; un `BLOCK_REASON` se puede accionar.

La distinción que ordena la tabla es si la agencia necesita que alguien la
mire. Casi nunca: la mayoría se cierra con lo que ya está escrito en los
artefactos, y eso es lo que decide si el 12/10 es alcanzable.

Uso:
    python scripts/staging_breakdown.py
    python scripts/staging_breakdown.py --razon NO_WEB --listar
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.agency_certifier import load_catalog, resolve_identity  # noqa: E402

V2DIR = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
DIRECTORIO = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_STAGING_BREAKDOWN"

# Cada razon dice quien la puede resolver. Las tres columnas del §18 salen de
# aca y no de una estimacion.
#   automatable: se cierra con lo ya escrito, sin red ni humano
#   brave:       necesita una busqueda nueva
#   certificar:  ya tiene web; falta correr el certificador
#   manual:      hace falta que alguien mire
RAZONES = {
    "OFFICIAL_WEB_LISTA": ("tiene web verificada y espera promocion", True, False, True, False),
    "WEB_SIN_VERIFICAR": ("tiene candidata encontrada y sin abrir", True, False, True, False),
    "EXTERNAL_PORTAL_ONLY": ("su web declarada es un perfil de portal ajeno", True, False, False, False),
    "OFFICIAL_OFFICE_PAGE": ("es una oficina dentro de una red", True, False, False, False),
    "NO_WEB": ("no tiene web ni candidata: hace falta buscar", False, True, False, False),
    "DOMAIN_DEAD": ("su dominio no responde o esta parkeado", True, False, False, False),
    "IDENTITY_AMBIGUOUS": ("dos o mas candidatas y ninguna decide", False, False, False, True),
    "NO_INVENTORY": ("no publica catalogo", True, False, False, False),
    "SOURCE_BLOCKED": ("la fuente rechaza el acceso automatizado", True, False, False, False),
    "NETWORK_MEMBER": ("pertenece a una red y no tiene sitio propio", True, False, False, False),
    "INSUFFICIENT_EVIDENCE": ("sin nombre util ni zona: no hay por donde empezar", False, False, False, True),
    "OTHER": ("sin clasificar", False, False, False, True),
}


def leer(ruta: Path, clave: str = "canonical_agency_id") -> dict[str, dict]:
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


def razon_de(canonical_id: str, web: dict, verif: dict, verificadas: dict,
             padron: dict) -> str:
    """La primera que aplica manda, y el orden no es arbitrario.

    Se pregunta de lo mas resuelto a lo menos: si ya hay web verificada, da
    igual lo que diga el directorio; si el dominio esta muerto, no tiene
    sentido preguntar si es ambigua.
    """
    if canonical_id in verificadas:
        return "OFFICIAL_WEB_LISTA"

    clase = (verif.get("estado") or "")
    if clase in ("OFFICIAL_WEB_VERIFIED", "OFFICIAL_WEB_HIGH_CONFIDENCE"):
        return "OFFICIAL_WEB_LISTA"
    if clase == "OFFICIAL_WEB_INACTIVE":
        return "DOMAIN_DEAD"
    if clase == "OFFICIAL_WEB_AMBIGUOUS":
        return "IDENTITY_AMBIGUOUS"

    estado = (web.get("status") or "")
    if web.get("selected_office_page"):
        return "OFFICIAL_OFFICE_PAGE"
    if estado == "OFFICIAL_WEB_VERIFIED":
        return "OFFICIAL_WEB_LISTA"
    if estado == "OFFICIAL_WEB_INACTIVE":
        return "DOMAIN_DEAD"
    if estado == "PORTAL_NOT_OFFICIAL":
        return "EXTERNAL_PORTAL_ONLY"
    if estado == "NO_INDEPENDENT_WEBSITE":
        return "NETWORK_MEMBER" if (padron.get("red_franquicia")) else "NO_INVENTORY"
    if estado == "OFFICIAL_WEB_HIGH_CONFIDENCE" or web.get("selected_domain"):
        return "WEB_SIN_VERIFICAR"
    if estado == "OFFICIAL_WEB_AMBIGUOUS":
        return ("WEB_SIN_VERIFICAR" if (web.get("candidate_urls") or [])
                else "NO_WEB")
    if estado in ("SEARCH_SECOND_PASS_REQUIRED", "NO_EXISTING_WEB_DATA"):
        if web.get("candidate_urls"):
            return "WEB_SIN_VERIFICAR"
        if not (padron.get("nombre_original") or "").strip():
            return "INSUFFICIENT_EVIDENCE"
        return "NO_WEB"
    return "OTHER"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--razon")
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args()

    catalogo = load_catalog(V2DIR, DATOS, DIRECTORIO)
    resol = leer(V2DIR / "AGENCY_ID_RESOLUTION_FINAL.jsonl")
    web = leer(DATOS / "agency_web_directory.jsonl")
    verif = leer(DATOS / "AGENCY_WEB_CANDIDATAS_VERIFICADAS.jsonl")
    verificadas = {k: v for k, v in
                   leer(DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl").items()
                   if v.get("official_url")}
    padron = leer(DATOS / "roomix_agency_directory.jsonl", "stable_id")

    filas = []
    for canonical_id, registro in catalogo.items():
        r = resol.get(canonical_id) or {}
        if r.get("resolution_method") != "STAGING_NAMESPACE_NOT_A_MAIN_FK":
            continue
        ident = resolve_identity(registro, canonical_id)
        razon = razon_de(canonical_id, web.get(canonical_id) or {},
                         verif.get(canonical_id) or {}, verificadas,
                         padron.get(canonical_id) or {})
        filas.append({
            "agency_id": canonical_id,
            "nombre": ident.get("agency_name") or "",
            "block_reason": razon,
            "avisos_observados": (padron.get(canonical_id) or {}).get("avisos_observados") or 0,
            "red_franquicia": (padron.get(canonical_id) or {}).get("red_franquicia"),
            "official_url": (verificadas.get(canonical_id) or {}).get("official_url")
                            or (web.get(canonical_id) or {}).get("selected_domain") or "",
        })

    if args.razon:
        elegidas = [f for f in filas if f["block_reason"] == args.razon]
        if args.listar:
            for f in elegidas[:40]:
                print(f"   {f['nombre'][:40]:42} {f['avisos_observados']:6} "
                      f"{f['official_url'][:40]}")
        print(f"\n{len(elegidas)} con razon {args.razon}")
        return 0

    with open(f"{SALIDA}.jsonl", "w", encoding="utf-8") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")

    cuenta = Counter(f["block_reason"] for f in filas)
    avisos = Counter()
    for f in filas:
        avisos[f["block_reason"]] += f["avisos_observados"]

    total = len(filas)
    print(f"STAGING BLOQUEADAS: {total:,}\n")
    print(f"{'BLOCK_REASON':24} {'AGENCIAS':>8} {'%':>6} {'AVISOS':>9}  "
          f"{'AUTO':>5} {'BRAVE':>6} {'CERT':>5} {'MANUAL':>7}")
    automatables = brave = certificar = manual = 0
    for razon, n in cuenta.most_common():
        desc, auto, br, cert, man = RAZONES.get(razon, ("", False, False, False, True))
        automatables += n if auto else 0
        brave += n if br else 0
        certificar += n if cert else 0
        manual += n if man else 0
        print(f"{razon:24} {n:8,} {n/total*100:5.1f} {avisos[razon]:9,}  "
              f"{'si' if auto else '-':>5} {'si' if br else '-':>6} "
              f"{'si' if cert else '-':>5} {'si' if man else '-':>7}")

    print(f"\n  cerrables por regla, sin red ni humano: {automatables:,} "
          f"({automatables/total:.0%})")
    print(f"  necesitan una busqueda nueva:           {brave:,} "
          f"({brave/total:.0%})")
    print(f"  ya tienen web y esperan certificar:     {certificar:,}")
    print(f"  requieren que alguien mire:             {manual:,} "
          f"({manual/total:.0%})")
    print(f"\n  artefacto: {SALIDA}.jsonl")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

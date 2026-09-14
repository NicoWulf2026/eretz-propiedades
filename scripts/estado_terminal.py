#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Qué significa que una inmobiliaria esté terminada. Una sola definición.

No escribe nada. `database_writes: 0`.

### Por qué hace falta fijarlo

En el bloque anterior dije que 2.488 de staging eran "cerrables por regla".
**Eso mezcló dos cosas distintas** y el §4 lo advierte con razón: cerrable por
regla no es lo mismo que terminal. De esas 2.488, la mayoría —las que ya tienen
web verificada o candidata— no están terminadas: están *listas para
certificar*, que es un estado de trabajo pendiente, no de trabajo hecho.

Contarlas como terminales habría inflado el numerador justo en el reporte que
decide si hace falta comprar máquinas.

### La definición

Una agencia tiene DOS ejes independientes, y sólo está terminada cuando los dos
lo están:

    TERMINAL_IDENTITY    sabemos quién es y dónde publica, o demostramos que
                         no se puede saber
    TERMINAL_INVENTORY   tenemos su catálogo, o demostramos que no hay catálogo
                         que tener

`AGENCY_TERMINAL = TERMINAL_IDENTITY and TERMINAL_INVENTORY`

La asimetría importa: una agencia puede tener identidad resuelta y catálogo
pendiente (es lo normal), pero **no al revés**. Sin identidad no hay a quién
atribuirle el catálogo.

### Lo que NO es terminal

    OFFICIAL_WEB_LISTA    tiene web, falta certificar  -> READY
    WEB_SIN_VERIFICAR     hay candidata sin abrir      -> trabajo
    NO_WEB                falta buscar                 -> trabajo
    IDENTITY_AMBIGUOUS    sin política agotada         -> trabajo

Una agencia sólo cierra por "no se pudo" cuando la política de búsqueda se
agotó y quedó escrito que se agotó. `NOT_SEARCHED` no es un final.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")

# --- eje identidad ---------------------------------------------------------
# Terminal: sabemos quién es y dónde publica, o está demostrado que no.
IDENTIDAD_TERMINAL = {
    "OFFICIAL_WEB_VERIFICADA",       # web propia abierta y corroborada
    "OFFICIAL_OFFICE_PAGE_VERIFICADA",
    "EXTERNAL_PORTAL_ONLY",          # sólo existe dentro de un portal ajeno
    "SOURCE_INACTIVE",               # dominio muerto, demostrado
    "NO_OFFICIAL_WEB_AFTER_POLICY",  # se buscó lo acordado y no hay
    "IDENTITY_AMBIGUOUS_AFTER_POLICY",
    "BLOCKED_EXTERNAL",
}
# --- eje inventario --------------------------------------------------------
INVENTARIO_TERMINAL = {
    "CERTIFIED_COMPLETE",
    "CERTIFIED_BEST_AVAILABLE",
    "NO_INVENTORY_CONFIRMED",
    "BLOCKED_EXTERNAL",
    # Si la identidad cerró sin fuente propia, no hay inventario que buscar:
    # el eje queda terminal por imposibilidad, no por logro.
    "NO_SOURCE_TO_CERTIFY",
}


def identidad_de(fila: dict) -> str:
    """El estado de identidad a partir del block_reason del breakdown."""
    razon = fila.get("block_reason") or ""
    if razon == "OFFICIAL_OFFICE_PAGE":
        # Sólo si fue validada contra la fuente. El breakdown solo dice que hay
        # una url candidata.
        return ("OFFICIAL_OFFICE_PAGE_VERIFICADA" if fila.get("office_validada")
                else "PENDIENTE_VALIDAR_OFICINA")
    if razon == "DOMAIN_DEAD":
        return "SOURCE_INACTIVE" if fila.get("muerte_confirmada") else "PENDIENTE_CONFIRMAR_MUERTE"
    if razon == "EXTERNAL_PORTAL_ONLY":
        return "EXTERNAL_PORTAL_ONLY"
    if razon == "OFFICIAL_WEB_LISTA":
        return "OFFICIAL_WEB_VERIFICADA"
    if razon == "WEB_SIN_VERIFICAR":
        return "PENDIENTE_VERIFICAR_CANDIDATA"
    if razon == "NO_WEB":
        return "PENDIENTE_BUSCAR"
    if razon == "IDENTITY_AMBIGUOUS":
        return "PENDIENTE_DESAMBIGUAR"
    return "PENDIENTE"


def inventario_de(fila: dict, estado_cert: str | None) -> str:
    if estado_cert in INVENTARIO_TERMINAL:
        return estado_cert
    identidad = identidad_de(fila)
    if identidad in ("EXTERNAL_PORTAL_ONLY", "SOURCE_INACTIVE",
                     "NO_OFFICIAL_WEB_AFTER_POLICY", "BLOCKED_EXTERNAL"):
        # Identidad cerrada sin fuente propia: no hay catálogo que certificar.
        return "NO_SOURCE_TO_CERTIFY"
    if identidad in ("OFFICIAL_WEB_VERIFICADA", "OFFICIAL_OFFICE_PAGE_VERIFICADA"):
        return "READY_FOR_CERTIFICATION"
    return "PENDIENTE"


def es_terminal(identidad: str, inventario: str) -> bool:
    return identidad in IDENTIDAD_TERMINAL and inventario in INVENTARIO_TERMINAL


def main() -> int:
    breakdown = CERT / "ERETZ_STAGING_BREAKDOWN.jsonl"
    validadas = {}
    ruta_val = CERT / "ERETZ_OFFICE_PAGES_VALIDADAS.jsonl"
    if ruta_val.exists():
        for linea in ruta_val.read_text(encoding="utf-8", errors="replace").splitlines():
            if linea.strip():
                f = json.loads(linea)
                validadas[f["agency_id"]] = f["clase"] == "OFFICIAL_OFFICE_PAGE"

    filas = [json.loads(l) for l in
             breakdown.read_text(encoding="utf-8", errors="replace").splitlines()
             if l.strip()]
    ident = Counter()
    inv = Counter()
    terminales = 0
    for f in filas:
        f["office_validada"] = validadas.get(f["agency_id"], False)
        i = identidad_de(f)
        v = inventario_de(f, None)
        ident[i] += 1
        inv[v] += 1
        if es_terminal(i, v):
            terminales += 1

    total = len(filas)
    print(f"STAGING: {total:,}\n")
    print("EJE IDENTIDAD")
    for k, n in ident.most_common():
        marca = "  TERMINAL" if k in IDENTIDAD_TERMINAL else ""
        print(f"   {k:36} {n:6,}{marca}")
    print("\nEJE INVENTARIO")
    for k, n in inv.most_common():
        marca = "  TERMINAL" if k in INVENTARIO_TERMINAL else ""
        print(f"   {k:36} {n:6,}{marca}")
    print(f"\nAGENCY_TERMINAL (los dos ejes): {terminales:,}")
    listas = inv.get("READY_FOR_CERTIFICATION", 0)
    print(f"READY_FOR_CERTIFICATION:        {listas:,}")
    print(f"pendientes de trabajo:          {total - terminales - listas:,}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

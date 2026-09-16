#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sacar los perfiles de portal de la lista de webs propias. §6, §78.2.

No escribe en la base. `database_writes: 0`. Toca UN archivo local de
identidad, con backup y en seco por defecto.

Qué corrige y qué no:

  - NO borra la agencia;
  - NO la marca inactiva;
  - NO toca el extractor, ni una huella, ni producción;
  - **conserva la url** en `url_como_evidencia`, porque un perfil en un portal
    sigue siendo prueba de que la inmobiliaria existe y opera. Lo único que
    deja de ser es fuente de inventario.

Lo único que cambia es `verificacion`, que es el campo por el que el
certificador decide si esa url es la web de la agencia:

    VERIFICADA_ARGENTINA  ->  EXTERNAL_PORTAL_PROFILE

Por qué vale la pena: en 48 h, SIETE agencias pararon la cola por esto, y entre
todas enumeramos **4.007 propiedades ajenas** —4.000 de una sola—. Diagnosticar
la octava a mano cuando ya se conoce el patrón es tiempo tirado.

Uso:
    python scripts/corregir_fuentes_de_portal.py            # en seco
    python scripts/corregir_fuentes_de_portal.py --aplicar
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
VERIFICADAS = DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
REGISTRO = CERT / "ERETZ_SOURCE_REGISTRY.jsonl"
AUDITORIA = CERT / "ERETZ_SOURCE_REGISTRY_CORRECCIONES.jsonl"

# Sólo estas dos clases se corrigen. `OFFICIAL_OFFICE_PAGE` NO entra: la página
# de una oficina dentro de su red no es un portal ajeno, y apagarla sería el
# error inverso —el que casi cometo con las cuatro de `tuinmobiliaria`—.
A_CORREGIR = ("EXTERNAL_PORTAL_PROFILE", "EXTERNAL_PORTAL_LISTING")


def leer(p: Path) -> list[dict]:
    fuera = []
    for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if l.strip():
            try:
                fuera.append(json.loads(l))
            except ValueError:
                continue
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo informa; no toca el archivo")
    args = ap.parse_args()

    if not REGISTRO.exists():
        print("falta el registro: corré antes auditar_source_registry.py")
        return 1
    registro = {r["agency_id"]: r for r in leer(REGISTRO)}
    objetivo = {a: r for a, r in registro.items()
                if r.get("source_type") in A_CORREGIR}

    filas = leer(VERIFICADAS)
    cambios = []
    for f in filas:
        a = f.get("canonical_agency_id")
        r = objetivo.get(a)
        if not r:
            continue
        if f.get("verificacion") != "VERIFICADA_ARGENTINA":
            continue
        cambios.append({
            "agency_id": a,
            "agency_name": f.get("nombre"),
            "antes_verificacion": f.get("verificacion"),
            "despues_verificacion": r["source_type"],
            "url_como_evidencia": f.get("official_url"),
            "evidencia_de_la_clasificacion": r.get("evidence"),
            "confianza": r.get("confidence"),
            "enumeradas_desde_esa_fuente": r.get("enumeradas"),
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    print(f"clasificadas como portal en el registro: {len(objetivo)}")
    print(f"de esas, con entrada en VERIFICADAS:     {len(cambios)}\n")
    if not cambios:
        print("no hay nada que corregir")
        return 0

    print(f"{'agencia':30} {'enum':>5}  {'antes':22} -> despues")
    ajeno = 0
    for c in cambios:
        ajeno += c["enumeradas_desde_esa_fuente"] or 0
        print(f"{(c['agency_name'] or '')[:28]:30} "
              f"{str(c['enumeradas_desde_esa_fuente'] or 0):>5}  "
              f"{c['antes_verificacion']:22} -> {c['despues_verificacion']}")
        print(f"     {c['evidencia_de_la_clasificacion'][:96]}")
    print(f"\n  propiedades AJENAS que dejarian de enumerarse: {ajeno:,}")
    print("  la url queda guardada como evidencia; la agencia NO se borra "
          "ni se marca inactiva")

    if not args.aplicar:
        print("\n(en seco) usá --aplicar para escribir el archivo")
        print("\ndatabase_writes: 0")
        return 0

    respaldo = VERIFICADAS.with_suffix(
        f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(VERIFICADAS, respaldo)

    por_id = {c["agency_id"]: c for c in cambios}
    nuevas = []
    for f in filas:
        c = por_id.get(f.get("canonical_agency_id"))
        if c and f.get("verificacion") == "VERIFICADA_ARGENTINA":
            f = dict(f)
            f["verificacion"] = c["despues_verificacion"]
            f["verificacion_razon"] = c["evidencia_de_la_clasificacion"]
            f["url_como_evidencia"] = f.get("official_url")
            f["inventory_allowed"] = False
            f["corregido_en"] = c["cuando"]
        nuevas.append(f)
    VERIFICADAS.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in nuevas),
        encoding="utf-8")

    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for c in cambios:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\ncorregidas {len(cambios)}")
    print(f"respaldo:  {respaldo.name}")
    print(f"auditoria: {AUDITORIA.name}")
    print("\n  La cola se recalcula sola en el proximo arranque de los workers:")
    print("  el certificador lee este archivo al armar la pasada.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una agencia cuyos datos son de Tokko puede no tener el frontend de Tokko.

Dry-run por defecto. No toca produccion, no cambia extractores, no cambia
huellas. `database_writes: 0`.

El caso
-------
`fios consultoria` figura con `connector: tokko` en el directorio de
plataformas y enumera CERO. La plataforma esta bien clasificada -las imagenes
salen de `static.tokkobroker.com` y los ids coinciden con las fichas- pero el
**frontend** es PHP a medida: `listado.php?...&pagina=N` y fichas con slug.
El conector de Tokko espera el frontend del producto y encuentra otro.

`strategy_for()` corta antes de mirar nada mas:

    if connector != "generico":
        return connector

asi que la estrategia es `tokko` y el descubrimiento generico **nunca corre**.
Se comprobo ejecutando `GenericoConnector.discover()` a mano contra las dos
fuentes: devuelve `LISTADO_HTML` soportada, con 17 fichas reales en
`coldwell banker andes` -`ficha.php?id=6711786` y siguientes-.

El precedente ya esta en el codigo, con su comentario. `choose_connector()`
devuelve `generico` para las fuentes recuperadas porque *"la evidencia de
tecnologia de un portal rechazado no describe el sitio oficial recuperado"*.
Es el mismo razonamiento: la evidencia de plataforma no describe el frontend.

Por que se toca `connector` y no `publication_mechanism`
--------------------------------------------------------
Porque `publication_mechanism` **no se declara**: es salida de la
certificacion. `agency_certifier.py` lo toma de `run2["variante"]`, y los 2.596
registros del directorio lo tienen vacio. Alcanza con poner `generico` y dejar
que el descubrimiento clasifique la forma; imponerle una variante a mano seria
adivinar lo que la fuente puede decir sola.

La guarda
---------
Solo se tocan agencias que hoy enumeran **cero**. No hay nada que empeorar: si
el reenrutado falla, siguen en cero. Una agencia que enumera algo NO entra aca
aunque su conector parezca equivocado, porque cambiarlo podria perder
inventario real y eso si seria un retroceso.

Uso:
    python scripts/corregir_enrutado_de_conector.py
    python scripts/corregir_enrutado_de_conector.py --aplicar
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

# Las rutas REALES que usa la cola, escritas y no descubiertas con un glob:
# asi se colo el error que dejo cinco correcciones inertes.
V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
AUDITORIA = CERT / "ERETZ_ENRUTADO_CORREGIDO.jsonl"


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def ultimos_resultados() -> dict[str, dict[str, Any]]:
    ultimo: dict[str, dict[str, Any]] = {}
    for fila in _jsonl(CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"):
        clave = fila.get("canonical_agency_id")
        if clave:
            ultimo[clave] = fila
    return ultimo


def enumeradas(resultado: dict[str, Any]) -> int:
    return int((resultado.get("enumeration_audit") or {}).get("enumerated") or 0)


def candidatas(conector: str = "tokko") -> list[tuple[str, dict[str, Any]]]:
    """Agencias con ese conector declarado que hoy enumeran cero.

    Se excluye `BLOCKED_EXTERNAL` a proposito: ahi el cero no lo explica el
    enrutado sino que la fuente nos bloquea, y reenrutar no lo arreglaria.
    Tambien se excluye `IDENTITY_PENDING`, que esta frenada antes del scraping.
    """
    declarado = {}
    for fila in _jsonl(PLATAFORMAS):
        clave = fila.get("canonical_agency_id")
        if clave:
            declarado[clave] = fila
    resultados = ultimos_resultados()
    salida = []
    for clave, fila in declarado.items():
        if (fila.get("connector") or "").lower() != conector:
            continue
        resultado = resultados.get(clave)
        if not resultado:
            continue
        if resultado.get("status") not in ("NEEDS_FIX",):
            continue
        if enumeradas(resultado):
            continue
        salida.append((clave, fila))
    return sorted(salida)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    ap.add_argument("--conector", default="tokko",
                    help="conector declarado que se sospecha mal enrutado")
    ap.add_argument("--solo", action="append", default=[],
                    help="limitar a estas agencias (subcadena)")
    args = ap.parse_args()

    elegidas = candidatas(args.conector)
    if args.solo:
        elegidas = [(c, f) for c, f in elegidas
                    if any(s.lower() in c.lower() for s in args.solo)]
    if not elegidas:
        print(f"no hay agencias con connector={args.conector} en NEEDS_FIX y "
              f"cero enumeradas")
        return 1

    from scripts.agency_certifier import load_catalog, choose_connector
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)

    print(f"agencias con connector={args.conector}, NEEDS_FIX y CERO "
          f"enumeradas: {len(elegidas)}\n")
    print(f"  {'AGENCIA':40} {'RESUELVE HOY':12} {'DOMINIO':40}")
    print(f"  {'-' * 40} {'-' * 12} {'-' * 40}")
    for clave, fila in elegidas:
        registro = catalogo.get(clave)
        hoy = choose_connector(registro) if registro else "SIN ENTRADA"
        print(f"  {clave.split(':')[-1][:40]:40} {hoy:12} "
              f"{str(fila.get('domain'))[:40]}")

    if not args.aplicar:
        print(f"\n  DRY-RUN: {len(elegidas)} cambios preparados y NO escritos.")
        print("  Para aplicar: --aplicar")
        print("\ndatabase_writes: 0")
        return 0

    respaldo = PLATAFORMAS.with_suffix(
        f".jsonl.bak_{time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(PLATAFORMAS, respaldo)
    claves = {c for c, _ in elegidas}
    lineas, escritas = [], 0
    for fila in _jsonl(PLATAFORMAS):
        if fila.get("canonical_agency_id") in claves:
            fila = dict(fila)
            # El conector viejo se conserva: el §11 pide evidencia, no borrado.
            fila["previous_connector"] = fila.get("connector")
            fila["connector"] = "generico"
            fila["connector_corrected_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            fila["connector_corrected_reason"] = (
                "plataforma correcta, frontend ajeno: el descubrimiento "
                "generico reconoce la forma y el conector de la plataforma no")
            escritas += 1
        lineas.append(json.dumps(fila, ensure_ascii=False))
    temporal = PLATAFORMAS.with_suffix(".jsonl.tmp")
    temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    temporal.replace(PLATAFORMAS)

    with AUDITORIA.open("a", encoding="utf-8") as fh:
        for clave, fila in elegidas:
            fh.write(json.dumps({
                "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "canonical_agency_id": clave,
                "capa": "agency_platform_directory.jsonl :: connector",
                "de": fila.get("connector"), "a": "generico",
                "porque": "frontend ajeno a la plataforma declarada",
                "respaldo": respaldo.name, "database_writes": 0},
                ensure_ascii=False) + "\n")

    # LA VERIFICACION QUE IMPORTA: no que el archivo quedo escrito, sino que la
    # cola elige distinto. Se recarga el catalogo desde cero.
    print(f"\naplicadas: {escritas}   respaldo: {respaldo.name}")
    print("\nverificacion con las rutas REALES de la cola:")
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    fallaron = 0
    for clave, _ in elegidas:
        ahora = choose_connector(catalogo.get(clave, {}))
        ok = ahora == "generico"
        fallaron += not ok
        print(f"   {'OK ' if ok else 'NO '}{clave.split(':')[-1][:40]:40} "
              f"-> {ahora}")
    if fallaron:
        print(f"\n  {fallaron} NO resuelven a `generico`: hay otra capa "
              f"ganando. NO dar por aplicado.")
        return 1
    print("\n  Falta lo unico que prueba que sirvio: recertificar y ver si "
          "enumeran.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

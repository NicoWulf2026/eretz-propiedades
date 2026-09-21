# -*- coding: utf-8 -*-
"""Que ficha cambio entre las dos corridas, y en que campo.

La cola informa «1 MODIFICADA de 200» y con eso no se puede diagnosticar nada:
no se sabe cual ficha ni que campo, asi que no se puede ir a la fuente y
preguntar si esa propiedad cambio de verdad. El 2026-09-21 eso bloqueo cuatro
diagnosticos seguidos -`alagna`, `carina gonzalez`, `carlos castano` y
`castro y compania`- y yo lo habia anotado como el item 8 de la tanda
congelada, con la idea de que habia que cambiar `compare_runs`.

**Estaba mal planteado.** El dato no se pierde: `agency_certifier.py` ya
escribe `properties_run1.jsonl` y `properties_run2.jsonl` en el paquete de
cada agencia. Lo unico que faltaba era leerlos. Por eso esto es un script
nuevo y no un cambio en el certificador: `compare_runs` esta dentro de
`shared/certifier` y tocarlo invalidaria las certificaciones vigentes; leer un
archivo que ya existe no invalida nada.

    python scripts/que_cambio_entre_corridas.py "castro y compania"

Campos que se ignoran a proposito, porque cambian en toda corrida y no son
contenido de la propiedad:

  `_run`, `_cambio`   marcas que pone el runner
  `provenance.*`      lleva adentro la marca de tiempo de la corrida

`database_writes: 0`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

PAQUETES = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")

# No son contenido de la propiedad: cambian en cada corrida por construccion.
CAMPOS_DE_CORRIDA = frozenset({"_run", "_cambio", "_orden", "scraped_at",
                               "fetched_at", "updated_at", "checked_at",
                               "provenance"})


def leer_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def por_url(props) -> dict[str, dict[str, Any]]:
    salida = {}
    for p in props:
        clave = p.get("source_url") or p.get("hash_dedup")
        if clave:
            salida[clave] = p
    return salida


def campos_distintos(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """Los campos con contenido distinto, sin las marcas de corrida."""
    return sorted(c for c in set(a) | set(b)
                  if c not in CAMPOS_DE_CORRIDA and a.get(c) != b.get(c))


def comparar(paquete: Path) -> dict[str, Any]:
    a = por_url(leer_jsonl(paquete / "properties_run1.jsonl"))
    b = por_url(leer_jsonl(paquete / "properties_run2.jsonl"))
    cambiadas = []
    for clave in sorted(set(a) & set(b)):
        campos = campos_distintos(a[clave], b[clave])
        if campos:
            cambiadas.append({"url": clave, "campos": campos,
                              "run1": {c: a[clave].get(c) for c in campos},
                              "run2": {c: b[clave].get(c) for c in campos}})
    return {"run1": len(a), "run2": len(b),
            "solo_en_run1": sorted(set(a) - set(b)),
            "solo_en_run2": sorted(set(b) - set(a)),
            "cambiadas": cambiadas}


def buscar_paquete(nombre: str, raiz: Path = PAQUETES) -> Path | None:
    """El paquete cuyo `canonical_agency_id` contiene `nombre`."""
    aguja = nombre.lower()
    for run1 in sorted(raiz.glob("*/run1.json")):
        try:
            datos = json.loads(run1.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if aguja in str(datos.get("canonical_agency_id", "")).lower():
            return run1.parent
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agencia", help="parte del canonical_agency_id")
    ap.add_argument("--paquetes", default=str(PAQUETES))
    ap.add_argument("--valores", action="store_true",
                    help="imprimir los valores de cada campo distinto")
    args = ap.parse_args(argv)

    paquete = buscar_paquete(args.agencia, Path(args.paquetes))
    if paquete is None:
        print(json.dumps({"error": "no encontre el paquete",
                          "buscado": args.agencia}, ensure_ascii=False))
        return 1
    r = comparar(paquete)
    print(f"paquete: {paquete.name}")
    print(f"run1={r['run1']}  run2={r['run2']}  "
          f"solo_en_run1={len(r['solo_en_run1'])}  "
          f"solo_en_run2={len(r['solo_en_run2'])}")
    for u in r["solo_en_run1"][:20]:
        print(f"  la 2a corrida NO vio: {u}")
    for u in r["solo_en_run2"][:20]:
        print(f"  la 2a corrida vio de mas: {u}")
    print(f"fichas con contenido distinto: {len(r['cambiadas'])}")
    for c in r["cambiadas"]:
        print(f"\n  {c['url']}")
        print(f"  campos: {c['campos']}")
        if args.valores:
            for campo in c["campos"]:
                print(f"     {campo}:")
                print(f"        run1 = {str(c['run1'][campo])[:300]}")
                print(f"        run2 = {str(c['run2'][campo])[:300]}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

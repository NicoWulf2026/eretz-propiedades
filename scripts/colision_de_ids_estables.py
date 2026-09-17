#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""`identity_collisions: 0` mientras 178 urls colapsan en 35 ids. §29, §31, §39.

Sólo lectura sobre artefactos locales. `database_writes: 0`. No arregla el
extractor —eso cambia huellas y va a la ventana semántica—: hace **visible** una
colisión que hoy el propio campo que debería denunciarla declara inexistente.

Cómo apareció
-------------
Buscando qué formato darle al artefacto por propiedad, el índice único sobre
`(agency_id, source_listing_id)` falló al construirse. No era un problema del
formato: el par no es único.

`baron inmobiliaria` tiene el id `300` en **36 propiedades distintas**, con 36
urls distintas, en la misma corrida:

    /propiedades/casa-en-venta-3-ambientes-oslo-al-300-7ebd1c
    /propiedades/casa-en-venta-4-ambientes-larrea-al-300-7ebb54
    /propiedades/departamento-en-venta-3-ambientes-mitre-al-300-3-7eb865

El extractor tomó `300` de *"Oslo al 300"*: el número de calle. Lo único que
distingue esas urls es el sufijo hexadecimal del final.

`conti propiedades` falla al revés. Sus urls son `/propiedad/494/chalet-b-...`
y el extractor se quedó con el slug en vez del `494`, así que veinte
propiedades comparten `chalet-b-villa-eden-la-falda`.

Por qué no es P0 hoy, y por qué igual importa
---------------------------------------------
Se midió antes de asustarse. `enumerated` cuenta **urls**, no ids —`baron` dice
178, no 35— y la comparación RUN1/RUN2 usa `run1_urls`/`run2_urls`. Así que el
inventario no se pierde y no hay COMPLETE falso por esto.

Lo que sí está roto es la señal. En el mismo registro conviven
`ids_unicos: 35`, `enumeradas: 178` y `identity_collisions: 0`. El campo que
existe para denunciar esto declara que no pasa nada, teniendo la prueba al
lado. Es el §39 exacto: una señal que afirma más de lo que verifica.

Y el riesgo está aguas abajo. Dedupe (§62), lifecycle (§63) y cualquier cosa
que use el id estable como clave colapsarían 108 propiedades en 51. Diez de las
agencias afectadas están **CERTIFIED_COMPLETE**.

Uso:
    python scripts/colision_de_ids_estables.py
    python scripts/colision_de_ids_estables.py --detalle "baron"
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
RESULTADOS = CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl"
PROPIEDADES = CERT / "ERETZ_PROPIEDADES_CERTIFICADAS.jsonl"
SALIDA = CERT / "ERETZ_COLISION_DE_IDS.json"

# Debajo de esto una agencia no dice nada: con 3 urls, que dos compartan id
# puede ser una repetición real de la fuente.
MINIMO_PARA_OPINAR = 5


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


def desde_los_resultados() -> list[dict[str, Any]]:
    """La señal barata: `ids_unicos` contra `enumeradas`, en cada resultado."""
    ultimo: dict[str, dict] = {}
    for fila in _jsonl(RESULTADOS):
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila

    filas = []
    for agencia, resultado in ultimo.items():
        corrida = resultado.get("run1") or {}
        ids = corrida.get("ids_unicos")
        urls = corrida.get("enumeradas")
        if not ids or not urls or urls < MINIMO_PARA_OPINAR or ids >= urls:
            continue
        comparacion = resultado.get("comparison") or {}
        filas.append({
            "canonical_agency_id": agencia,
            "agency_name": resultado.get("agency_name"),
            "status": resultado.get("status"),
            "ids_unicos": ids,
            "urls_enumeradas": urls,
            "urls_por_id": round(urls / ids, 2),
            "ratio": round(ids / urls, 3),
            # Lo que el sistema DICE sobre esto mismo, al lado del número que
            # lo desmiente. Es el corazón del hallazgo.
            "identity_collisions_declarado": comparacion.get("identity_collisions"),
            "connector_strategy": resultado.get("connector_strategy"),
            "official_url": resultado.get("official_url"),
        })
    filas.sort(key=lambda f: f["ratio"])
    return filas


def desde_las_propiedades() -> dict[str, list[dict[str, Any]]]:
    """La prueba cara: los ids repetidos de verdad, con sus urls."""
    por_agencia: dict[str, Counter] = defaultdict(Counter)
    urls: dict[tuple, list[str]] = defaultdict(list)
    for fila in _jsonl(PROPIEDADES):
        agencia = fila.get("agency_id")
        listing = fila.get("source_listing_id")
        if not agencia or listing is None:
            continue
        por_agencia[agencia][listing] += 1
        if len(urls[(agencia, listing)]) < 4:
            urls[(agencia, listing)].append(fila.get("source_url") or "")
    detalle: dict[str, list[dict[str, Any]]] = {}
    for agencia, cuenta in por_agencia.items():
        repetidos = [{"source_listing_id": k, "veces": v,
                      "urls_de_ejemplo": urls[(agencia, k)]}
                     for k, v in cuenta.most_common() if v > 1]
        if repetidos:
            detalle[agencia] = repetidos
    return detalle


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detalle", help="mostrar las urls de una agencia")
    args = ap.parse_args()

    filas = desde_los_resultados()
    detalle = desde_las_propiedades()

    if args.detalle:
        clave = next((a for a in detalle if args.detalle.lower() in a.lower()), None)
        if not clave:
            print(f"sin colisiones registradas para {args.detalle!r}")
            return 1
        print(f"{clave}\n")
        for caso in detalle[clave][:6]:
            print(f"  id {caso['source_listing_id']!r} x{caso['veces']}")
            for u in caso["urls_de_ejemplo"]:
                print(f"     {u[:100]}")
            print()
        print("database_writes: 0")
        return 0

    completas = [f for f in filas if f["status"] == "CERTIFIED_COMPLETE"]
    ciegas = [f for f in filas if f["identity_collisions_declarado"] == 0]

    reporte = {
        "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agencias_con_ids_colapsados": len(filas),
        "de_esas_certified_complete": len(completas),
        "de_esas_con_identity_collisions_cero": len(ciegas),
        "que_NO_esta_roto": ("el inventario. `enumerated` cuenta urls y la "
                             "comparacion RUN1/RUN2 usa run1_urls y run2_urls, "
                             "asi que no hay perdida ni COMPLETE falso por esto"),
        "que_SI_esta_roto": ("la señal. `identity_collisions` declara 0 "
                             "teniendo `ids_unicos` y `enumeradas` al lado en "
                             "el mismo registro"),
        "riesgo": ("aguas abajo: dedupe, lifecycle y cualquier cosa que use el "
                   "id estable como clave colapsarian propiedades distintas"),
        "agencias": filas,
        "database_writes": 0,
    }
    SALIDA.write_text(json.dumps(reporte, ensure_ascii=False, indent=1),
                      encoding="utf-8")

    print(f"agencias donde el id estable colapsa: {len(filas)}")
    print(f"  de esas, CERTIFIED_COMPLETE:        {len(completas)}")
    print(f"  de esas, con identity_collisions=0: {len(ciegas)}\n")
    print(f"  {'AGENCIA':34} {'ESTADO':22} {'IDS':>5} {'URLS':>5} {'x/ID':>5}  DICE")
    print(f"  {'-' * 34} {'-' * 22} {'-' * 5} {'-' * 5} {'-' * 5}  ----")
    for f in filas[:15]:
        print(f"  {(f['agency_name'] or '')[:34]:34} {f['status'][:22]:22} "
              f"{f['ids_unicos']:5} {f['urls_enumeradas']:5} "
              f"{f['urls_por_id']:5}  collisions={f['identity_collisions_declarado']}")
    if len(filas) > 15:
        print(f"  ... y {len(filas) - 15} mas en el artefacto")

    print(f"\n  Lo que NO esta roto: el inventario. `enumerated` cuenta urls")
    print(f"  -baron dice 178, no 35- y RUN1/RUN2 compara por url.")
    print(f"\n  Lo que SI esta roto: la señal. Las {len(ciegas)} declaran")
    print(f"  identity_collisions=0 teniendo la prueba en el campo de al lado.")
    print(f"\n  El arreglo del extractor es DATA PLANE y va a la ventana.")
    print(f"  Esto solo lo hace visible.")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

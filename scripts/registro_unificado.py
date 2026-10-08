#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Registro unificado de inmobiliarias: MAIN (produccion) ∪ CANONICO (scraping), una fila por entidad.

Solo lectura sobre todos los artefactos; escribe unicamente su propia salida. `database_writes: 0`.

Por que existe (mision 08-10, `docs/agent/MISION_PADRON_COMPLETO.md`): el padron de produccion
(`inmobiliarias_main`, 7.004) y el padron que scrapea la cola (roomix, 6.597) solo comparten 1.118
agencias. Contar "procesadas de 7.004" sin unirlos mezcla universos. Este registro:

- da a cada agencia conocida EXACTAMENTE una fila y un estado excluyente con su proxima accion;
- vincula MAIN y CANONICO por FK resuelta y, como evidencia (no como afirmacion), por el host de los
  avisos que MAIN tiene en produccion;
- comprueba la invariante de "ninguna olvidada": todo id de MAIN y toda identidad canonica aparecen.

Lo que todavia no se sabe se dice: los ids de MAIN sin nombre ni web local quedan
`MAIN_SIN_DATOS_LOCALES` hasta que se lea `inmobiliarias_main` (nombre, web, telefono, ciudad).

    python scripts/registro_unificado.py [--salida DIR]
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from scripts.agency_certifier import choose_connector, load_catalog, resolve_identity  # noqa: E402
from scripts.ledger_de_certificacion import vigentes_por_agencia  # noqa: E402
from scripts.plan_de_escritura import agencias_con_web_ajena  # noqa: E402
from scripts.preingestion_manifest import base_canonica  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402

VERSION = "registro_unificado_v1"
CERTIFICADOS = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE")

# Estado excluyente -> proxima accion. El primero que aplica manda.
ACCION = {
    "IDENTIDAD_CONFLICTIVA": "desambiguar (dos candidatas o web de atribucion ambigua)",
    "SIN_WEB_PROPIA": "buscar web propia; si no existe, cerrar con evidencia (solo portal / oficina de red)",
    "SIN_WEB": "descubrir web (fuentes propias primero, busqueda paga al final)",
    "WEB_SIN_VERIFICAR": "verificar la web automaticamente (nombre, telefono, dominio)",
    "LISTA_PARA_SCRAPEAR": "certificar (cola)",
    "NEEDS_FIX": "resolver la familia de defecto y recertificar",
    "BLOCKED_EXTERNAL": "reintentar con evidencia nueva (bloqueo del sitio o fuente externa)",
    "SIN_INVENTARIO_CONFIRMADO": "reverificar periodicamente",
    "CERTIFICADA": "mantener fresca (recrawl por frescura)",
    "MAIN_SIN_DATOS_LOCALES": "leer nombre/web/telefono de inmobiliarias_main y resolver contra el canonico",
    "MAIN_CON_HOST_SIN_IDENTIDAD": "crear identidad canonica desde el host de sus avisos y verificar",
}


def _host(url: Any) -> str:
    h = urllib.parse.urlparse(str(url or "")).netloc.lower()
    return h.removeprefix("www.")


def _ro(ruta: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(ruta).as_posix()}?mode=ro", uri=True)


def estado_canonico(ident: dict[str, Any], registro: dict[str, Any], ledger: dict[str, Any] | None,
                    ajenas: set[str], dup_ids: set[str], cid: str) -> str:
    resolucion = (registro.get("resolution") or {}).get("resolution_status")
    web_kind = (registro.get("platform") or {}).get("web_kind")
    if resolucion == "AMBIGUOUS" or web_kind == "AMBIGUOUS_WEB_ATTRIBUTION" or cid in dup_ids:
        return "IDENTIDAD_CONFLICTIVA"
    if ident["identity_status"] == "BLOCKED_EXTERNAL" or cid in ajenas:
        return "SIN_WEB_PROPIA"
    if not ident["official_url"]:
        return "SIN_WEB"
    if ident["identity_status"] == "IDENTITY_PENDING":
        return "WEB_SIN_VERIFICAR"
    status = (ledger or {}).get("status")
    if not status:
        return "LISTA_PARA_SCRAPEAR"
    if status in CERTIFICADOS:
        return "CERTIFICADA"
    if status == "NO_INVENTORY_CONFIRMED":
        return "SIN_INVENTARIO_CONFIRMADO"
    if status == "BLOCKED_EXTERNAL":
        return "BLOCKED_EXTERNAL"
    return "NEEDS_FIX"


def construir() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    v2 = dato("ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    directorio = dato("agency_platform_directory.jsonl")
    cat = load_catalog(v2, dato("ERETZ_AGENCY_DATA"), directorio)
    ajenas = agencias_con_web_ajena(directorio)
    dup_ids: set[str] = set()
    ruta_dup = v2 / "DUPLICATE_OR_CONFLICT.jsonl"
    if ruta_dup.exists():
        for linea in ruta_dup.read_text(encoding="utf-8", errors="replace").splitlines():
            if linea.strip():
                try:
                    dup_ids.add(json.loads(linea).get("canonical_agency_id"))
                except ValueError:
                    pass
    vig, _ambiguas = vigentes_por_agencia(dato("ERETZ_AGENCY_CERTIFICATION_20260827",
                                               "AGENCY_CERTIFICATION_RESULTS.jsonl"))
    servidas = collections.Counter(a for (a,) in _ro(dato("ERETZ_API_CONTRACT", "ERETZ_API_SNAPSHOT.sqlite3"))
                                   .execute("select agency_id from propiedades"))
    pre = collections.Counter(c for (c,) in _ro(base_canonica()).execute(
        "select canonical_id from rows where status = 'CANDIDATE'"))

    rec = _ro(v2 / "SUPABASE_RECONCILIATION.sqlite3")
    main_ids = {int(i) for (i,) in rec.execute("select id from agencies")}
    hosts_main: dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
    avisos_main: collections.Counter = collections.Counter()
    for i, url in rec.execute("select inmobiliaria_id, source_url from dbrows where inmobiliaria_id is not null"):
        avisos_main[int(i)] += 1
        if url:
            hosts_main[int(i)][_host(url)] += 1

    filas: list[dict[str, Any]] = []
    main_vinculados: dict[int, str] = {}
    por_host: dict[str, list[str]] = collections.defaultdict(list)
    for cid in sorted(cat):
        ident = resolve_identity(cat[cid], cid)
        led = vig.get(cid)
        estado = estado_canonico(ident, cat[cid], led, ajenas, dup_ids, cid)
        eretz = int(ident["eretz_id"]) if ident.get("eretz_id") else None
        if eretz in main_ids:
            main_vinculados[eretz] = cid
        host = _host(ident.get("official_url"))
        if host:
            por_host[host].append(cid)
        filas.append({
            "entidad": cid, "origen": "CANONICO", "canonical_agency_id": cid, "eretz_id": eretz,
            "nombre": ident.get("agency_name"), "web": ident.get("official_url"), "host": host or None,
            "identidad": ident["identity_status"], "estado": estado, "proxima_accion": ACCION[estado],
            "conector_previsto": choose_connector(cat[cid]) if ident.get("official_url") else None,
            "cierre_ledger": (led or {}).get("status"), "cierre_en": (led or {}).get("checked_at"),
            "filas_servidas": servidas.get(cid, 0), "filas_preingestion_candidatas": pre.get(cid, 0),
        })

    for mid in sorted(main_ids - set(main_vinculados)):
        hosts = hosts_main.get(mid)
        host = hosts.most_common(1)[0][0] if hosts else None
        candidatas = por_host.get(host, []) if host else []
        estado = "MAIN_CON_HOST_SIN_IDENTIDAD" if host else "MAIN_SIN_DATOS_LOCALES"
        filas.append({
            "entidad": f"main:{mid}", "origen": "MAIN", "canonical_agency_id": None, "eretz_id": mid,
            "nombre": None, "web": None, "host": host,
            "identidad": None, "estado": estado, "proxima_accion": ACCION[estado],
            "avisos_en_produccion": avisos_main.get(mid, 0),
            # Evidencia, no afirmacion: un host compartido (redes, portales) puede tener varias agencias.
            "posible_identidad_canonica_por_host": candidatas[:5] or None,
        })

    # Invariante: ninguna olvidada.
    vistos_canonicos = {f["canonical_agency_id"] for f in filas if f["canonical_agency_id"]}
    vistos_main = {f["eretz_id"] for f in filas if f["eretz_id"] in main_ids}
    invariante = {
        "canonicos_en_registro": len(vistos_canonicos), "canonicos_esperados": len(cat),
        "main_en_registro": len(vistos_main), "main_esperados": len(main_ids),
        "ok": vistos_canonicos == set(cat) and vistos_main == main_ids,
    }
    resumen = {
        "version": VERSION, "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"), "entidades": len(filas),
        "por_estado": dict(collections.Counter(f["estado"] for f in filas).most_common()),
        "main_vinculados_por_fk": len(main_vinculados),
        "main_sin_identidad_con_host": sum(1 for f in filas if f["estado"] == "MAIN_CON_HOST_SIN_IDENTIDAD"),
        "main_sin_identidad_con_host_y_candidata_por_host": sum(
            1 for f in filas if f["estado"] == "MAIN_CON_HOST_SIN_IDENTIDAD" and f["posible_identidad_canonica_por_host"]),
        "con_filas_servidas": sum(1 for f in filas if f.get("filas_servidas")),
        "invariante_ninguna_olvidada": invariante, "database_writes": 0,
    }
    return filas, resumen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", type=Path, default=dato("ERETZ_REGISTRO"))
    args = ap.parse_args()
    filas, resumen = construir()
    args.salida.mkdir(parents=True, exist_ok=True)
    tmp = args.salida / "REGISTRO_INMOBILIARIAS.jsonl.tmp"
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for f in filas:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    tmp.replace(args.salida / "REGISTRO_INMOBILIARIAS.jsonl")
    (args.salida / "REGISTRO_RESUMEN.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    return 0 if resumen["invariante_ninguna_olvidada"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

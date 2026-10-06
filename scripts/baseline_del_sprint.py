#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Baseline del sprint de beta (12/10) y barrido de senales de falso COMPLETE. Solo lectura.

Pedido del usuario (06-10): un baseline REAL, separando MEDIDO de ESTIMADO, y una
busqueda de certificaciones COMPLETE sospechosas: declarado >> enumerado, exactamente
20, una sola pagina con techo redondo, portal multi-agencia o host compartido.
Lee el ledger (resultado vigente por agencia), la snapshot servida y la cola.
`database_writes: 0`.

    python scripts/baseline_del_sprint.py [--json salida.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from scripts.agency_web_discovery import es_portal  # noqa: E402
from scripts.ledger_de_certificacion import vigentes_por_agencia  # noqa: E402
from scripts.rutas_de_datos import dato  # noqa: E402

CERT = dato("ERETZ_AGENCY_CERTIFICATION_20260827")
SERVIDA = dato("ERETZ_API_CONTRACT", "ERETZ_API_SNAPSHOT.sqlite3")
COMPLETAS = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE")


def _corrida(fila: dict[str, Any]) -> dict[str, Any]:
    return fila.get("run2") or fila.get("run1") or {}


def _host(fila: dict[str, Any]) -> str:
    h = (_corrida(fila).get("host") or "").lower()
    return h.removeprefix("www.")


def senales(fila: dict[str, Any], hosts: collections.Counter) -> list[str]:
    """Por que una COMPLETE podria ser falsa. Vacio = sin senal."""
    r = _corrida(fila)
    enum = int(r.get("enumeradas") or 0)
    decl = r.get("total_declarado")
    fuera = []
    if isinstance(decl, (int, float)) and decl and enum < 0.8 * decl:
        fuera.append(f"declarado {int(decl)} > enumerado {enum}")
    if enum in (10, 12, 20, 24, 30) and int(r.get("paginas") or 0) <= 1 and not decl:
        fuera.append(f"techo redondo {enum} en 1 pagina sin total declarado")
    if r.get("paginacion_interrumpida"):
        fuera.append("paginacion interrumpida")
    if r.get("enumeracion_completa") is False:
        fuera.append("enumeracion no completa")
    if fila.get("official_url") and es_portal(fila["official_url"]):
        fuera.append("web oficial es portal")
    if hosts[_host(fila)] > 1:
        fuera.append(f"host compartido por {hosts[_host(fila)]} agencias")
    if fila.get("codigo_cambio_en_vuelo"):
        fuera.append("codigo cambio en vuelo")
    return fuera


def medir() -> dict[str, Any]:
    vig, ambiguas = vigentes_por_agencia(CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl")
    estados = collections.Counter(f.get("status") for f in vig.values())
    hosts = collections.Counter(_host(f) for f in vig.values() if _host(f))
    enumeradas = sum(int(_corrida(f).get("enumeradas") or 0)
                     for f in vig.values() if f.get("status") in COMPLETAS)
    sospechosas = {}
    for aid, f in vig.items():
        if f.get("status") == "CERTIFIED_COMPLETE":
            s = senales(f, hosts)
            if s:
                sospechosas[aid] = {"host": _host(f), "connector": f.get("connector"),
                                    "enumeradas": _corrida(f).get("enumeradas"),
                                    "declarado": _corrida(f).get("total_declarado"),
                                    "checked_at": f.get("checked_at"), "senales": s}
    servida = None
    if SERVIDA.exists():
        con = sqlite3.connect(f"file:{SERVIDA.as_posix()}?mode=ro", uri=True)
        servida = con.execute("select count(*) from propiedades").fetchone()[0]
        con.close()
    pendientes = {}
    for p in sorted(CERT.glob("AGENCY_CERTIFICATION_PROGRESS.w[0-9].json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pendientes[p.stem.rsplit(".", 1)[-1]] = {
            "pendientes": d.get("pending_count"), "cola": d.get("queue_size"),
            "ultimo_latido": d.get("last_heartbeat"), "modo": d.get("mode")}
    return {"MEDIDO": {
        "agencias_con_resultado": len(vig), "ambiguas": len(ambiguas),
        "estados": dict(estados.most_common()),
        "propiedades_enumeradas_en_certificadas": enumeradas,
        "snapshot_servida_propiedades": servida,
        "progreso_por_worker": pendientes,
        "complete_con_senal": len(sospechosas)},
        "complete_sospechosas": sospechosas}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    m = medir()
    texto = json.dumps(m, ensure_ascii=False, indent=1)
    if args.json:
        args.json.write_text(texto, encoding="utf-8")
    print(json.dumps(m["MEDIDO"], ensure_ascii=False, indent=1))
    por = collections.Counter(s.split(" ")[0] + " " + s.split(" ")[1]
                              for v in m["complete_sospechosas"].values() for s in v["senales"])
    print("senales en COMPLETE:", dict(por.most_common()))
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

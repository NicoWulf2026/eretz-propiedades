#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verificar la web del directorio de plataformas de las agencias fuera de `main` (P6, fase 2).

Politica P6 del usuario (29-09): certificar por identidad canonica cuando la
identidad quede demostrada. 1.028 agencias fuera de `main` tienen una web oficial
en el directorio de plataformas que nadie ABRIO para establecer que es de esa
agencia: `free_web_audit_v1` puntuo URLs sin visitarlas (597 de 598 salian de
confianza alta), asi que ese estado no prueba nada.

Para cada una, con la misma evidencia que el resto del circuito:
  1. se abre la web y se decide con `agency_web_discovery.verificar` (identidad);
  2. se comprueba que sea argentina (`promover_webs_verificadas.es_argentina`);
  3. se CUENTA cuantas agencias del universo reclaman el mismo host: un dominio
     compartido no identifica a nadie.
Solo lo que pasa las tres cosas se agrega a `AGENCY_OFFICIAL_WEB_VERIFIED.jsonl`
como AFIRMABLE, con el estado real del resolver y el conteo real del host. Todo
lo demas queda en el registro de esta corrida con su razon.

Reanudable. Sin consultas pagas. No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agency_web_discovery as wd  # noqa: E402
from promover_webs_verificadas import es_argentina  # noqa: E402
from verificar_candidatas_web import bajar  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
DESTINO = DATOS / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
REGISTRO = DATOS / "AGENCY_DIRECTORY_WEB_VERIFICATION.jsonl"
ESTABLECIDAS = (wd.VERIFIED, wd.HIGH_CONFIDENCE)
# Tokko sirve cientos de dominios desde un backend con limite compartido: entre
# agencias Tokko se espera mas, para no sumar un tercer pedido concurrente al del
# worker de certificacion (ver `run_agency_certification_queue.worker_de`).
PAUSA_TOKKO = 4.0


def host_de(url: str | None) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def reclamantes_por_host() -> dict[str, set[str]]:
    """Cuantas agencias del universo nombran cada host, en cualquier fuente."""
    por_host: dict[str, set[str]] = defaultdict(set)
    for fila in _jsonl(PLATAFORMAS):
        if fila.get("domain"):
            por_host[host_de(fila["domain"])].add(fila["canonical_agency_id"])
    for fila in _jsonl(DATOS / "agency_web_directory.jsonl"):
        if fila.get("official_url"):
            por_host[host_de(fila["official_url"])].add(fila["canonical_agency_id"])
    for fila in _jsonl(DESTINO):
        if fila.get("official_url"):
            por_host[host_de(fila["official_url"])].add(fila["canonical_agency_id"])
    return por_host


def cohorte(catalogo) -> list[tuple[str, dict]]:
    from scripts.agency_certifier import resolve_identity
    verificadas = {f["canonical_agency_id"] for f in _jsonl(DESTINO)}
    hechas = {f["canonical_agency_id"] for f in _jsonl(REGISTRO)}
    fuera = []
    for cid, rec in sorted(catalogo.items()):
        ide = resolve_identity(rec, cid)
        if (ide["identity_status"] == "IDENTITY_PENDING"
                and rec["resolution"].get("resolution_status") == "NOT_FOUND_IN_ERETZ"
                and rec["platform"].get("web_kind") == "OFFICIAL_WEB"
                and rec["platform"].get("domain")
                and cid not in verificadas and cid not in hechas):
            fuera.append((cid, rec))
    return fuera


def entidad(cid: str, rec: dict) -> dict:
    d, p = rec.get("directory") or {}, rec.get("platform") or {}
    zonas = [z for z in (d.get("city") or p.get("city"), d.get("province") or p.get("province")) if z]
    return {"stable_id": cid,
            "nombre_original": d.get("canonical_name") or p.get("agency_name") or cid.split(":", 1)[-1],
            "red_franquicia": d.get("franchise"), "zonas_observadas": zonas, "matricula": []}


def main() -> int:
    from scripts.agency_certifier import load_catalog
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo registra; con esto agrega las establecidas al artefacto de la cola")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--pausa", type=float, default=0.4)
    args = ap.parse_args()
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    pendientes = cohorte(catalogo)
    if args.limite:
        pendientes = pendientes[:args.limite]
    hosts = reclamantes_por_host()
    print(f"### VERIFICAR WEBS DEL DIRECTORIO (P6 fase 2) ### {len(pendientes)} agencias", flush=True)
    estados: Counter = Counter()
    with REGISTRO.open("a", encoding="utf-8") as reg, DESTINO.open("a", encoding="utf-8") as dest:
        for i, (cid, rec) in enumerate(pendientes, 1):
            url = rec["platform"]["domain"]
            veredicto_id, pais, razon_pais = None, None, None
            if wd.es_portal(url):
                estado = "PORTAL"
            else:
                candidata = bajar(url)
                es_tokko = str(rec["platform"].get("platform") or rec["platform"].get("connector") or "").lower() == "tokko"
                time.sleep(PAUSA_TOKKO if es_tokko else args.pausa)
                if candidata.http is None:
                    estado = "NO_RESPONDE"
                else:
                    veredicto_id = wd.verificar(entidad(cid, rec), [candidata])
                    estado = veredicto_id.estado
            n_host = len(hosts.get(host_de(url), set()) | {cid})
            afirmable = False
            if estado in ESTABLECIDAS:
                web = veredicto_id.official_web or url
                if host_de(web) != host_de(url):
                    estado = "OTRA_WEB"
                elif n_host != 1:
                    estado = "HOST_COMPARTIDO"
                else:
                    pais, razon_pais = es_argentina(web)
                    afirmable = pais == "VERIFICADA_ARGENTINA"
                    if not afirmable:
                        estado = f"PAIS:{pais}"
            estados["AFIRMABLE" if afirmable else estado] += 1
            fila = {"canonical_agency_id": cid, "url": url, "estado": estado,
                    "confianza": getattr(veredicto_id, "confianza", None),
                    "razon": getattr(veredicto_id, "razon", None),
                    "entidades_que_reclaman_el_host": n_host,
                    "verificacion": pais, "verificacion_razon": razon_pais,
                    "afirmable": afirmable, "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "database_writes": 0}
            reg.write(json.dumps(fila, ensure_ascii=False) + "\n")
            reg.flush()
            if afirmable and args.aplicar:
                dest.write(json.dumps({
                    "canonical_agency_id": cid, "nombre": entidad(cid, rec)["nombre_original"],
                    "estado": "AFIRMABLE", "razon": veredicto_id.razon,
                    "official_url": veredicto_id.official_web or url,
                    "origen_descubierto": url, "url_descubierta": url,
                    "era_ruta_profunda": False,
                    "entidades_que_reclaman_el_host": n_host,
                    "estado_del_resolver": estado,
                    "identity_score": veredicto_id.confianza,
                    "verificacion": pais, "verificacion_razon": razon_pais,
                    "origen_del_dato": "verificar_webs_del_directorio",
                    "cuando": fila["cuando"], "database_writes": 0}, ensure_ascii=False) + "\n")
                dest.flush()
            if i % 50 == 0:
                print(f"  {i}/{len(pendientes)} {dict(estados)}", flush=True)
    print(json.dumps(dict(estados), ensure_ascii=False))
    print("consultas pagas: 0\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

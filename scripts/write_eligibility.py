#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que propiedades pueden escribirse hoy en propiedades_raw, y cuales no.

La regla no admite matices: una propiedad solo entra a la base si su
inmobiliaria tiene `eretz_id` real. Un id sintetico, derivado o temporal
produciria filas que no pertenecen a ninguna inmobiliaria existente, y ese error
no se nota al insertar: aparece meses despues, cuando alguien une las tablas y
faltan agencias.

Las que no lo tienen quedan AGENCY_ID_PENDING. Se descubren, se normalizan, se
validan y viven en los artefactos; simplemente no se escriben todavia.

Solo lee artefactos. No toca la base ni la red.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import calcular_hash_dedup  # noqa: E402

ELEGIBLE = "DB_WRITE_ELIGIBLE"
PENDIENTE = "AGENCY_ID_PENDING"
NO_ES_FICHA = "NO_ES_UNA_FICHA"
CROSS_AGENCIA = "CROSS_AGENCY_DUPLICATE"

# Defensa en profundidad: aunque el connector ya filtre, lo que llega a la base
# se revisa otra vez. Las paginas que se cuelan son siempre las mismas y entran
# porque comparten la ruta con las fichas: el listado se llama "propiedades" y
# la busqueda "buscar-propiedades".
RECHAZOS = [
    ("query_string", re.compile(r"[?#]")),
    ("busqueda", re.compile(r"/(buscar|busqueda|search|filtrar|filtro|"
                            r"resultados?|results?)(/|$|-)", re.I)),
    ("paginacion", re.compile(r"/(page|pagina|pag)[/_-]?\d+/?$", re.I)),
    ("categoria_o_tag", re.compile(r"/(category|categoria|categorias|tag|tags|"
                                   r"etiqueta|etiquetas|rubro)(/|$)", re.I)),
    ("archivo_por_fecha", re.compile(r"/\d{4}/\d{2}(/\d{2})?/?$")),
    ("institucional", re.compile(r"/(nosotros|about|quienes[-_]somos|contacto|"
                                 r"contact|servicios|tasacion|blog|noticias|"
                                 r"novedades|privacidad|terminos|login|admin|"
                                 r"sucursales|equipo|staff|faq)(/|$)", re.I)),
    ("feed_o_recurso", re.compile(r"(/feed/?$|\.(xml|json|rss|pdf|jpe?g|png)$)", re.I)),
    ("solo_la_seccion", re.compile(r"/(propiedades|inmuebles|propert(y|ies)|"
                                   r"listings?|emprendimientos)/?$", re.I)),
    # Segunda capa para Wasi. El connector filtra por forma de ficha y no emite
    # ninguna de estas, pero con WordPress la primera capa tambien alcanzaba
    # "en teoria" y entraron 56 paginas de busqueda igual: donde hay una sola
    # barrera, tarde o temprano se pasa algo.
    ("listado_wasi", re.compile(r"://[^/]+/s/[a-z0-9-]+(/[a-z0-9-]+)?/?$", re.I)),
    ("institucional_wasi", re.compile(r"/main-[a-z0-9-]+\.html?$", re.I)),
]

# Un id que es en realidad una query string o un texto largo no identifica nada.
LARGO_MAXIMO_ID = 120


def motivo_rechazo(p: dict) -> str | None:
    url = p.get("source_url") or ""
    if not url.startswith("http"):
        return "url_invalida"
    lid = str(p.get("source_listing_id") or "")
    if not lid:
        return "sin_source_listing_id"
    if len(lid) > LARGO_MAXIMO_ID or "=" in lid or "&" in lid:
        return "id_derivado_de_query"
    for nombre, patron in RECHAZOS:
        if patron.search(url):
            return nombre
    return None


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    out = []
    for l in ruta.open(encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entradas", nargs="+", required=True)
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    ap.add_argument("--resolucion", default="",
                    help="CROSS_AGENCY_RESOLUTION.jsonl; sin el, ningun "
                         "conflicto cross-agency se libera")
    a = ap.parse_args()

    padron = {}
    for d in leer(Path(a.data_dir) / "agency_web_directory.jsonl"):
        eid = d.get("eretz_id")
        if str(eid).isdigit():
            padron[d["canonical_agency_id"]] = int(eid)

    props: list[dict] = []
    for e in a.entradas:
        props.extend(leer(Path(e)))
    if not props:
        print("sin propiedades")
        return 1

    elegibles, pendientes, descartadas = [], [], []
    vistos_hash = set()
    for p in props:
        motivo = motivo_rechazo(p)
        if motivo:
            descartadas.append({**p, "motivo_rechazo": motivo})
            continue
        real = padron.get(p.get("canonical_agency_id"))
        if real is None:
            pendientes.append(p)
            continue
        q = dict(p)
        q["inmobiliaria_id"] = real
        # El hash depende del id, asi que se recalcula con el real: el del
        # artefacto se produjo con el sustituto del canary y no coincidiria con
        # lo que produce produccion.
        q["hash_dedup"] = calcular_hash_dedup(real, p.get("source_url"))
        if q["hash_dedup"] in vistos_hash:
            # Dos urls que normalizan igual son la misma propiedad. Escribir las
            # dos no crearia un duplicado -el indice unico lo impide- pero haria
            # que la reconciliacion no cierre.
            continue
        vistos_hash.add(q["hash_dedup"])
        q["db_write_status"] = ELEGIBLE
        elegibles.append(q)

    # --- misma url reclamada por dos inmobiliarias ---------------------------
    # El hash lleva el id de agencia, asi que dos agencias con la MISMA url dan
    # hashes distintos y las dos entrarian a la base: dos copias del mismo
    # inmueble bajo duenos distintos, duplicados introducidos por nosotros
    # aunque el indice unico no los vea.
    #
    # No se fusiona nada. Se conserva la copia de la agencia que mas inventario
    # aporta en ese dominio -la que mejor evidencia tiene de ser la duena- y las
    # otras quedan documentadas para que alguien decida.
    por_url = defaultdict(list)
    for q in elegibles:
        por_url[q.get("source_url")].append(q)

    # La adjudicacion NO se decide aca por tamano de inventario: eso le daba el
    # aviso a la agencia mas grande sin mirar de quien era. La decide
    # resolve_cross_agency.py con la evidencia de cada ficha, y aca solo se
    # aplica. Sin ese archivo, ningun conflicto se libera.
    resolucion = {}
    ruta_res = Path(a.resolucion) if a.resolucion else         Path(a.salida).with_name("CROSS_AGENCY_RESOLUTION.jsonl")
    for r in leer(ruta_res):
        resolucion[r.get("source_url")] = r

    cruzadas, conservadas = [], []
    for url, grupo in por_url.items():
        if len({q.get("canonical_agency_id") for q in grupo}) <= 1:
            conservadas.extend(grupo)
            continue
        r = resolucion.get(url) or {}
        dueno = r.get("canonical_owner") if r.get("liberable") else None
        for q in grupo:
            if dueno and q.get("canonical_agency_id") == dueno:
                q["cross_agency"] = {"categoria": r.get("categoria"),
                                     "motivo": r.get("motivo"),
                                     "reclamantes": [c.get("canonical_agency_id")
                                                     for c in r.get("reclamantes") or []]}
                conservadas.append(q)
            else:
                cruzadas.append({**q,
                                 "db_write_status": CROSS_AGENCIA,
                                 "categoria_conflicto": r.get("categoria") or "SIN_RESOLVER",
                                 "motivo_conflicto": r.get("motivo") or
                                 "conflicto todavia sin clasificar",
                                 "adjudicada_a": dueno,
                                 "url_en_disputa": url})
    elegibles = conservadas
    if cruzadas:
        ruta_cross = Path(a.salida).with_name("CROSS_AGENCY_DUPLICATES.jsonl")
        ruta_cross.write_text(
            chr(10).join(json.dumps(q, ensure_ascii=False) for q in cruzadas),
            encoding="utf-8")
        print(f"  {CROSS_AGENCIA:26}  {len(cruzadas):,}  (misma url, dos inmobiliarias)")
        for k, v in Counter(q["categoria_conflicto"] for q in cruzadas).most_common():
            print(f"      {k:34} {v:6,}")
        print(f"      -> {ruta_cross}")

    Path(a.salida).write_text(
        "\n".join(json.dumps(q, ensure_ascii=False) for q in elegibles),
        encoding="utf-8")

    n = len(props)
    print("### ELEGIBILIDAD PARA ESCRITURA EN propiedades_raw ###")
    print(f"  propiedades analizadas:     {n:,}")
    print(f"  {ELEGIBLE:24}    {len(elegibles):,}  ({len(elegibles)/n*100:.1f}%)")
    print(f"  {PENDIENTE:24}    {len(pendientes):,}  ({len(pendientes)/n*100:.1f}%)")
    print(f"  {NO_ES_FICHA:24}    {len(descartadas):,}  ({len(descartadas)/n*100:.1f}%)")
    if descartadas:
        for k, v in Counter(x["motivo_rechazo"] for x in descartadas).most_common():
            print(f"      {k:26} {v:6,}")
    print(f"\n  agencias elegibles:         "
          f"{len({q['canonical_agency_id'] for q in elegibles}):,}")
    print(f"  agencias sin eretz_id:      "
          f"{len({p.get('canonical_agency_id') for p in pendientes}):,}")
    print(f"  hash unicos entre elegibles:"
          f"{len({q['hash_dedup'] for q in elegibles}):,}")
    print(f"\n  por connector (elegibles):  "
          f"{dict(Counter(q.get('connector') for q in elegibles))}")
    print(f"  por connector (pendientes): "
          f"{dict(Counter(p.get('connector') for p in pendientes))}")

    # --- manifiesto de agencias sin id real ---------------------------------
    # No se inventa ningun id. Se documenta que falta y por que, para que quien
    # pueda resolverlo tenga todo a mano.
    por_agencia = defaultdict(list)
    for x in pendientes:
        por_agencia[x.get("canonical_agency_id")].append(x)
    manifiesto = []
    for cid, g in sorted(por_agencia.items(), key=lambda t: -len(t[1])):
        prov = g[0].get("provenance") or {}
        manifiesto.append({
            "canonical_agency_id": cid,
            "agency_name": prov.get("agency_name"),
            "official_domain": prov.get("official_domain"),
            "connector": g[0].get("connector"),
            "propiedades_descubiertas": len(g),
            "estado": PENDIENTE,
            "motivo": ("la entidad no tiene eretz_id en el crosswalk canonico: "
                       "esta en el padron de Roomix pero no se pudo enlazar con "
                       "una inmobiliaria de ERETZ"),
            "evidencia_disponible": {
                "urls_de_ejemplo": [x.get("source_url") for x in g[:3]],
                "plataforma": prov.get("source_platform"),
            },
        })
    ruta_man = Path(a.salida).with_name("AGENCY_ID_PENDING_MANIFEST.jsonl")
    ruta_man.write_text(
        chr(10).join(json.dumps(m, ensure_ascii=False) for m in manifiesto),
        encoding="utf-8")

    print()
    print(f"  agencias en {PENDIENTE}: {len(manifiesto)}")
    for m in manifiesto[:10]:
        print(f"    {(m['agency_name'] or '?')[:36]:36} "
              f"{m['propiedades_descubiertas']:5,} props  {m['connector']}")
    print(f"  manifiesto -> {ruta_man}")
    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

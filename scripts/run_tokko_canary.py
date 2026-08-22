#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Canary Tokko: probar el conector antes de soltarlo sobre 920 fuentes.

Modo DRY RUN. No escribe una sola fila en Supabase: todo va a artefactos fuera
del repo. La pregunta que responde no es "anda" sino "los datos que produce son
correctos", que son cosas distintas y solo la segunda importa.

Dos costos distintos, tratados distinto:
  - enumerar el inventario es barato (una peticion por cada 20 avisos), asi que
    se enumera COMPLETO para poder verificar que la paginacion no pierde nada;
  - bajar fichas es caro, asi que se normaliza una muestra acotada por fuente.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import (AUSENCIAS_PARA_BAJA, Bloqueado, Checkpoint,  # noqa: E402
                             Descargador, ErrorPermanente, ErrorTransitorio,
                             Fuente, LimitadorDeRitmo)
from connectors.tokko import TokkoConnector  # noqa: E402


def id_sustituto(canonical_agency_id: str) -> int:
    """Id numerico estable para el canary, derivado del id canonico.

    En produccion este numero sale de la base. Aca hay que fabricarlo, y usar
    hash() de Python fue un error: esta aleatorizado por proceso, asi que cada
    corrida generaba un id distinto para la misma inmobiliaria. Como el id entra
    en hash_dedup y en el fingerprint, la segunda corrida veia las 322
    propiedades como modificadas y la prueba de idempotencia daba negativo por
    una razon que no tenia nada que ver con el connector.
    """
    # Acotado al rango de INTEGER de PostgreSQL: la columna inmobiliaria_id es
    # INTEGER, y sha256[:8] llega a 4.294.967.295, mas del doble del maximo.
    # Sin el tope el insert falla recien contra la base, con el lote a medias.
    return int(hashlib.sha256(canonical_agency_id.encode()).hexdigest()[:8], 16) % 2_000_000_000


def num(valor, ancho: int = 4) -> str:
    """Formatea para el log sin romperse con None.

    `dict.get(k, "-")` no protege: si la clave existe con valor None devuelve
    None igual, y f"{None:>4}" levanta TypeError. Eso volteo una corrida entera.
    """
    return f"{valor:>{ancho}}" if valor is not None else "-".rjust(ancho)


def host_de(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def elegir_muestra(tokko: list[dict], descubrimiento: list[dict], n: int) -> list[dict]:
    """Muestra representativa, no la comoda.

    Se mezclan a proposito fuentes grandes y chicas, dominios propios y
    compartidos, provincias distintas y al menos una variante no estandar: si el
    canary solo prueba casos faciles no prueba nada.
    """
    por_id = {d["canonical_agency_id"]: d for d in descubrimiento}
    enriquecidas = []
    for x in tokko:
        d = por_id.get(x["canonical_agency_id"], {})
        enriquecidas.append({**x, "_total": d.get("total_declarado"),
                             "_variante": d.get("variante"),
                             "_host": host_de(x["official_url"])})

    con_total = [x for x in enriquecidas if x["_total"]]
    con_total.sort(key=lambda x: -x["_total"])
    elegidas: list[dict] = []
    vistos_host: set[str] = set()

    def sumar(cands, cuantos):
        for c in cands:
            if len(elegidas) >= n or cuantos <= 0:
                break
            if c["canonical_agency_id"] in {e["canonical_agency_id"] for e in elegidas}:
                continue
            if c["_host"] in vistos_host:
                continue
            vistos_host.add(c["_host"])
            elegidas.append(c)
            cuantos -= 1

    tercio = max(1, len(con_total) // 3)
    sumar(con_total[:tercio], max(1, n // 3))                      # grandes
    sumar(con_total[tercio:2 * tercio], max(1, n // 3))            # medianas
    sumar(list(reversed(con_total[2 * tercio:])), max(1, n // 3))  # chicas
    # Al menos una variante no soportada, para comprobar que se reporta y no
    # se traga el error.
    sumar([x for x in enriquecidas if x["_variante"] == "TOKKO_FRONTEND_PROPIO"], 2)
    sumar([x for x in enriquecidas if x["_host"] in
           {h for h, c in Counter(y["_host"] for y in enriquecidas).items() if c > 1}], 2)
    resto = [x for x in enriquecidas if x not in elegidas]
    random.Random(20260822).shuffle(resto)
    sumar(resto, n - len(elegidas))
    return elegidas[:n]


def procesar_fuente(con: TokkoConnector, f: Fuente, max_fichas: int) -> dict:
    t0 = time.time()
    r: dict = {"canonical_agency_id": f.canonical_agency_id, "agency_name": f.agency_name,
               "official_url": f.official_url, "host": host_de(f.official_url)}
    try:
        plan = con.discover(f)
    except (ErrorTransitorio, Bloqueado, ErrorPermanente) as e:
        con.anotar_error(f, "discover", e)
        return {**r, "estado": "ERROR_DISCOVERY", "clase_error": type(e).__name__,
                "segundos": round(time.time() - t0, 1)}

    r.update({"variante": plan["variante"], "soportada": plan["soportada"],
              "total_declarado": plan["total_declarado"],
              "tokko_client_id": plan["tokko_client_id"],
              "ruta_listado": plan["ruta_listado"]})
    if not plan["soportada"]:
        return {**r, "estado": "VARIANTE_NO_SOPORTADA",
                "segundos": round(time.time() - t0, 1)}

    try:
        avisos = list(con.fetch_listing(f, plan))
    except (ErrorTransitorio, Bloqueado) as e:
        con.anotar_error(f, "listado", e)
        return {**r, "estado": "ERROR_LISTADO", "clase_error": type(e).__name__,
                "segundos": round(time.time() - t0, 1)}

    ids = [a["source_listing_id"] for a in avisos]
    r["enumeradas"] = len(ids)
    r["ids_unicos"] = len(set(ids))
    r["duplicados_en_listado"] = len(ids) - len(set(ids))
    r["paginas_recorridas"] = max((a["pagina"] for a in avisos), default=0)
    if plan["total_declarado"]:
        r["cobertura_vs_declarado"] = round(len(set(ids)) / plan["total_declarado"], 3)

    muestra = avisos[:max_fichas]
    props, problemas = [], Counter()
    for a in muestra:
        try:
            p = con.normalize(a, f)
        except (ErrorTransitorio, Bloqueado) as e:
            con.anotar_error(f, "detalle", e)
            continue
        if p is None:
            continue
        estado = con.registrar(f, p)
        d = p.a_dict()
        d["_cambio"] = estado
        props.append(d)
        for q in d["problemas"]:
            problemas[q] += 1

    r["normalizadas"] = len(props)
    r["problemas"] = dict(problemas)
    if props:
        def lleno(campo):
            return sum(1 for p in props if p.get(campo) not in (None, "", []))
        r["completitud"] = {c: round(lleno(c) / len(props), 3) for c in (
            "titulo", "precio", "moneda", "operacion", "tipo_propiedad", "direccion",
            "barrio", "dormitorios", "banos", "ambientes", "superficie_cubierta",
            "latitud", "imagenes")}
        r["hash_unicos"] = len({p["hash_dedup"] for p in props})
        r["fotos_ajenas"] = sum(
            1 for p in props for u in p["imagenes"]
            if f"/{p['source_listing_id']}_" not in u)
        r["monedas"] = dict(Counter(p["moneda"] for p in props))
        r["operaciones"] = dict(Counter(p["operacion"] for p in props))
    r["estado"] = "OK"
    r["segundos"] = round(time.time() - t0, 1)
    return {**r, "_props": props}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\TOKKO_CANARY")
    ap.add_argument("--fuentes", type=int, default=16)
    ap.add_argument("--max-fichas", type=int, default=25)
    ap.add_argument("--intervalo", type=float, default=1.5)
    ap.add_argument("--corrida", default="1")
    a = ap.parse_args()
    dd, out = Path(a.data_dir), Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)

    mapa = [json.loads(l) for l in
            (dd / "scrape_source_technology_map.jsonl").open(encoding="utf-8") if l.strip()]
    tokko = [x for x in mapa if x["detected_platform"] == "TOKKO"]
    desc = []
    if (dd / "tokko_discovery.jsonl").exists():
        desc = [json.loads(l) for l in
                (dd / "tokko_discovery.jsonl").open(encoding="utf-8") if l.strip()]

    muestra = elegir_muestra(tokko, desc, a.fuentes)
    print(f"### CANARY TOKKO — corrida {a.corrida} (DRY RUN, sin escribir en Supabase) ###")
    print(f"  universo Tokko: {len(tokko):,}   canary: {len(muestra)}")
    print(f"  ritmo: 1 peticion cada {a.intervalo}s por host   "
          f"tope de fichas por fuente: {a.max_fichas}\n", flush=True)

    con = TokkoConnector(
        descargador=Descargador(LimitadorDeRitmo(a.intervalo)),
        checkpoint=Checkpoint(out / "checkpoint.json"))

    sufijo = f"_run{a.corrida}"
    ruta_inv = out / f"source_inventory{sufijo}.jsonl"
    ruta_norm = out / f"normalized_sample{sufijo}.jsonl"
    for r_ in (ruta_inv, ruta_norm):
        r_.write_text("", encoding="utf-8")

    t0 = time.time()
    resultados, todas = [], []
    for i, x in enumerate(muestra, 1):
        f = Fuente(canonical_agency_id=x["canonical_agency_id"],
                   agency_name=x.get("agency_name") or "",
                   official_url=x["official_url"],
                   inmobiliaria_id=id_sustituto(x["canonical_agency_id"]),
                   detected_platform="TOKKO")
        r = procesar_fuente(con, f, a.max_fichas)
        props = r.pop("_props", [])
        todas.extend(props)
        resultados.append(r)
        # Se escribe apenas termina cada fuente. Guardar solo al final ya costo
        # una corrida entera: un error en la ultima fuente borraba el trabajo
        # de las quince anteriores.
        with ruta_inv.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        with ruta_norm.open("a", encoding="utf-8") as fh:
            for pr in props:
                fh.write(json.dumps(pr, ensure_ascii=False) + "\n")
        con.checkpoint.de(f.canonical_agency_id)["corridas"] = \
            con.checkpoint.de(f.canonical_agency_id).get("corridas", 0) + 1
        con.checkpoint.guardar()
        print(f"  [{i:2}/{len(muestra)}] {r['estado']:22} "
              f"{(r.get('agency_name') or '')[:26]:26} "
              f"enum={num(r.get('enumeradas'))} norm={num(r.get('normalizadas'), 3)} "
              f"decl={num(r.get('total_declarado'))} {r['segundos']:>5}s", flush=True)

    sufijo = f"_run{a.corrida}"
    (out / f"source_inventory{sufijo}.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in resultados), encoding="utf-8")
    (out / f"normalized_sample{sufijo}.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in todas), encoding="utf-8")
    (out / f"errors{sufijo}.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in con.errores), encoding="utf-8")

    # ---- duplicados: hay que separar los dos tipos, no mezclarlos ----
    por_hash = defaultdict(list)
    for p in todas:
        por_hash[p["hash_dedup"]].append(p)
    dup_fuente = {h: v for h, v in por_hash.items() if len(v) > 1}

    # Mismo inmueble ofrecido por dos inmobiliarias: no es un error de la
    # ingesta, es un hecho del mercado. Se marca, no se fusiona.
    por_pista = defaultdict(set)
    for p in todas:
        if p.get("latitud") and p.get("precio"):
            clave = (round(p["latitud"], 5), round(p["longitud"] or 0, 5),
                     p["precio"], p["moneda"])
            por_pista[clave].add(p["canonical_agency_id"])
    cross = {str(k): sorted(v) for k, v in por_pista.items() if len(v) > 1}
    (out / f"duplicate_candidates{sufijo}.json").write_text(json.dumps(
        {"source_duplicates": {h: [p["source_url"] for p in v]
                               for h, v in dup_fuente.items()},
         "cross_agency_duplicates": cross}, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = [r for r in resultados if r["estado"] == "OK"]
    resumen = {
        "corrida": a.corrida,
        "fuentes_canary": len(muestra),
        "fuentes_ok": len(ok),
        "fuentes_por_estado": dict(Counter(r["estado"] for r in resultados)),
        "propiedades_enumeradas": sum(r.get("enumeradas", 0) for r in ok),
        "propiedades_normalizadas": len(todas),
        "inventario_declarado": sum(r.get("total_declarado") or 0 for r in ok),
        "duplicados_intra_fuente": len(dup_fuente),
        "duplicados_cross_agency": len(cross),
        "agencias_por_hash_max": max((len({p["canonical_agency_id"] for p in v})
                                      for v in por_hash.values()), default=0),
        "fotos_ajenas": sum(r.get("fotos_ajenas", 0) for r in ok),
        "peticiones": con.descargador.pedidos,
        "megabytes": round(con.descargador.bytes_bajados / 1e6, 1),
        "segundos": round(time.time() - t0, 1),
        "errores": len(con.errores),
        "cambios": dict(Counter(p["_cambio"] for p in todas)),
    }
    (out / f"quality_report{sufijo}.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n### RESUMEN corrida {a.corrida} ###")
    for k, v in resumen.items():
        print(f"  {k:26} {v}")
    if ok:
        campos = defaultdict(list)
        for r in ok:
            for c, v in (r.get("completitud") or {}).items():
                campos[c].append(v)
        print("\n  completitud media por campo:")
        for c, vs in sorted(campos.items(), key=lambda t: -sum(t[1]) / len(t[1])):
            print(f"    {c:22} {sum(vs)/len(vs)*100:5.1f}%")
    print(f"\n  artefactos -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

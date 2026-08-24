#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Mapa de plataformas: una fila por agencia con web conocida.

Cruza todo lo que ya se midio -mapa tecnologico, censo de no soportadas y el
resultado real de cada rollout- en un solo directorio. La diferencia con el mapa
tecnologico original es que ese decia "que parece usar este sitio" y este dice
"que se logro leer, con que connector y cuanto salio".

La clasificacion no se re-adivina: se toma la evidencia mas fuerte disponible,
en este orden, porque cada nivel corrige al anterior con datos reales.

  1. el rollout: si un connector enumero inventario, la plataforma es esa
  2. el censo de no soportadas: reviso las que fallaron y las reclasifico
  3. el mapa tecnologico: la deteccion inicial por marcadores del HTML

Solo lee artefactos.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

VERSION = "platform_directory_v2"

# La clasificacion de la url -web propia, oficina de una red, perfil en un
# portal ajeno- se recalcula aca. No se hereda del archivo anterior: este script
# reconstruye cada fila desde cero, asi que sin recalcularla la regeneracion
# siguiente borraba en silencio las 337 reclasificaciones y "agencias con web
# propia" volvia de 2.259 a 2.596, contando paginas de terceros como cobertura.
from scripts.reclassify_portal_profiles import clasificar as clasificar_web  # noqa: E402

ROLLOUTS = [
    ("TOKKO_ROLLOUT_FULL", "tokko"),
    ("WP_ROLLOUT_FULL", "wordpress"),
    ("C21_CANARY", "century21"),
    ("GENERICO_CANARY", "generico"),
    ("RESCATE_generico", "generico"),
    ("RESCATE_tokko", "tokko"),
    ("RESCATE_wordpress", "wordpress"),
    ("RESCATE_nextjs", "generico"),
    ("WASI_ROLLOUT_FULL", "wasi"),
    # Segunda tanda de rescates, sobre el censo del residual: solo fuentes con
    # fichas a la vista. Las que solo tenian marcadores de plataforma no entran
    # -las 81 de Tokko sin evidencia devolvieron cero-.
    ("RESCATE2_wordpress", "wordpress"),
    ("RESCATE2_tokko", "generico"),
    ("RESCATE2_generico", "generico"),
]


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


def host(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", u or "").split("/")[0].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    a = ap.parse_args()
    dd, raiz = Path(a.data_dir), Path(a.raiz)

    directorio = {d["canonical_agency_id"]: d
                  for d in leer(dd / "agency_web_directory.jsonl")}
    mapa = {m["canonical_agency_id"]: m
            for m in leer(dd / "scrape_source_technology_map.jsonl")}
    censo = {c["canonical_agency_id"]: c
             for c in leer(raiz / "UNSUPPORTED_CENSUS.jsonl")}
    wasi = {w["canonical_agency_id"]: w
            for w in leer(raiz / "WASI_DISCOVERY.jsonl") if w.get("es_wasi")}

    # Resultado real por fuente, con el connector que lo consiguio.
    resultado: dict[str, dict] = {}
    props_por_agencia: Counter = Counter()
    for carpeta, connector in ROLLOUTS:
        base = raiz / carpeta
        # Se leen TODAS las corridas, no la ultima. Preferir la mas reciente
        # esconde lo que una corrida a medias todavia no proceso: con la segunda
        # corrida en curso, 511 fuentes Tokko ya terminadas figuraban como no
        # intentadas.
        # Las corridas se descubren, no se listan: estaba fijo en ("1","2") y
        # apenas aparecio una corrida 3 el directorio dejo de verla en silencio,
        # que es el mismo error que el comentario de arriba dice evitar.
        corridas = sorted(p.name.rsplit("run", 1)[1].split(".")[0]
                          for p in base.glob("source_inventory_run*.jsonl"))
        inv = []
        for corrida in corridas:
            inv += leer(base / f"source_inventory_run{corrida}.jsonl")
        for r in inv:
            cid = r.get("canonical_agency_id")
            previo = resultado.get(cid)
            # Gana el que efectivamente trajo inventario.
            if previo and previo.get("enumeradas", 0) >= (r.get("enumeradas") or 0):
                continue
            resultado[cid] = {**r, "connector": r.get("connector") or connector}
        # Para el conteo de propiedades se usa UNA sola corrida -la mas
        # completa-: sumar las dos contaria cada propiedad dos veces.
        mejor, n = None, -1
        for corrida in corridas:
            props = base / f"properties_run{corrida}.jsonl"
            if props.exists():
                filas_p = leer(props)
                if len(filas_p) > n:
                    mejor, n = filas_p, len(filas_p)
        for p in (mejor or []):
            props_por_agencia[p.get("canonical_agency_id")] += 1

    filas = []
    for cid, d in directorio.items():
        m = mapa.get(cid) or {}
        c = censo.get(cid) or {}
        r = resultado.get(cid) or {}
        dominio = (r.get("official_url") or m.get("official_url")
                   or d.get("selected_domain") or d.get("current_eretz_web"))
        if not dominio:
            continue

        enumeradas = r.get("enumeradas") or 0
        declarado = r.get("total_declarado") or c.get("declared_inventory")

        # --- plataforma, por evidencia mas fuerte primero -------------------
        w = wasi.get(cid) or {}
        if w.get("es_wasi"):
            # El fingerprint de Wasi pide el HTML servido y combina senales:
            # es evidencia mas fuerte que los marcadores del mapa, que a estos
            # sitios los etiquetaba LARAVEL -el framework de abajo- o UNKNOWN.
            plataforma = "WASI"
            variante = w.get("familia")
            confianza = "alta" if w.get("confianza") == "alta" else "media"
            evidencia = w.get("motivo") or "fingerprint de Wasi"
            declarado = declarado or w.get("declared_inventory")
            enumeradas = enumeradas or w.get("enumerated_unique") or 0
        elif enumeradas and r.get("connector"):
            plataforma = {"tokko": "TOKKO", "wordpress": "WORDPRESS",
                          "century21": "CENTURY21", "generico": "SITIO_PROPIO"
                          }.get(r["connector"], r["connector"].upper())
            variante = r.get("variante") or c.get("clasificacion_nueva")
            confianza, evidencia = "alta", "el connector enumero inventario"
        elif c:
            plataforma = (c.get("plataforma_detectada") or "").upper() or "DESCONOCIDA"
            variante = c.get("clasificacion_nueva")
            confianza, evidencia = "media", "censo de fuentes no soportadas"
        elif m:
            plataforma = m.get("detected_platform") or "DESCONOCIDA"
            variante = m.get("strategy")
            confianza, evidencia = "baja", "marcadores del HTML"
        else:
            plataforma, variante = "SIN_CLASIFICAR", None
            confianza, evidencia = "ninguna", "no se intento"

        # --- estado del connector -------------------------------------------
        estado = r.get("estado")
        if w.get("es_wasi") and not (estado == "OK" and enumeradas):
            # Detectada y con via de extraccion medida, pero sin corrida que lo
            # confirme. Cuando el rollout SI enumero, manda el rollout: si no,
            # una fuente con 3.598 propiedades extraidas seguiria figurando
            # como "detectada pero sin connector".
            cs = ("DETECTED_NOT_BUILT" if w.get("connector")
                  else "NO_INVENTORY" if w.get("familia") == "WASI_SIN_INVENTARIO"
                  else "UNKNOWN")
        elif estado == "OK" and enumeradas:
            cs = "SUPPORTED_STANDARD" if variante in (
                "TFW_ESTANDAR", "WORDPRESS_REST", "C21_JSON") else "SUPPORTED_CUSTOM"
        elif estado == "ENUMERACION_INCOMPLETA":
            cs = "ENUMERACION_INCOMPLETA"
        elif estado in ("BLOQUEADA",):
            cs = "NETWORK_BLOCKED"
        elif c.get("status") == "PLATAFORMA_CONOCIDA_SIN_INVENTARIO":
            cs = "NO_INVENTORY"
        elif estado in ("VARIANTE_NO_SOPORTADA", "ERROR_DISCOVERY", "EXCEPCION"):
            cs = "UNSUPPORTED_PLATFORM"
        elif not r and not c:
            cs = "NO_INTENTADA"
        else:
            cs = "UNKNOWN"

        eid = d.get("eretz_id")
        tipo_web, motivo_web = clasificar_web(dominio)
        filas.append({
            "canonical_agency_id": cid,
            "eretz_id": int(eid) if str(eid).isdigit() else None,
            "agency_name": d.get("canonical_name"),
            "domain": dominio,
            "host": host(dominio),
            "province": d.get("province"),
            # Que ES esa url. Es una pregunta distinta de que tecnologia usa: un
            # dominio propio corriendo sobre Wasi sigue siendo web oficial.
            "web_kind": tipo_web,
            "web_kind_reason": motivo_web or None,
            "platform": plataforma,
            "variant": variante,
            "confidence": confianza,
            "evidence": evidencia,
            "declared_inventory": declarado,
            "enumerated_inventory": enumeradas or None,
            "coverage_ratio": (round(enumeradas / declarado, 4)
                               if declarado and enumeradas else None),
            "properties_normalized": props_por_agencia.get(cid) or None,
            "connector": r.get("connector"),
            "connector_status": cs,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "classifier_version": VERSION,
        })

    Path(a.salida).write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in filas), encoding="utf-8")

    print("### DIRECTORIO DE PLATAFORMAS ###")
    # --- reconciliacion, antes de cualquier resumen -------------------------
    # Un resumen truncado no es un detalle de presentacion: las categorias
    # dejaban de sumar el universo y parecia que faltaban 114 agencias cuando
    # lo que faltaba eran 21 categorias chicas que el top no imprimia.
    total = len(filas)
    ids = {f["canonical_agency_id"] for f in filas}
    cuenta_plat = Counter(f["platform"] for f in filas)
    cuenta_estado = Counter(f["connector_status"] for f in filas)
    problemas = []
    if len(ids) != total:
        problemas.append(f"{total - len(ids)} filas duplicadas por agencia")
    if sum(cuenta_plat.values()) != total:
        problemas.append("la clasificacion por plataforma no suma el universo")
    if sum(cuenta_estado.values()) != total:
        problemas.append("los estados de connector no suman el universo")
    if any(not f.get("platform") or not f.get("connector_status") for f in filas):
        problemas.append("hay filas sin plataforma o sin estado")
    print("  RECONCILIACION")
    print(f"    agencias con web:      {total:,}")
    print(f"    ids unicos:            {len(ids):,}")
    print(f"    suma por plataforma:   {sum(cuenta_plat.values()):,} "
          f"en {len(cuenta_plat)} categorias")
    print(f"    suma por estado:       {sum(cuenta_estado.values()):,} "
          f"en {len(cuenta_estado)} categorias")
    print(f"    RECONCILIA:            {'si' if not problemas else 'NO'}")
    for x in problemas:
        print(f"      !! {x}")
    # --- que ES cada url: web propia, oficina de una red, perfil ajeno ------
    # La cobertura se mide sobre las webs PROPIAS. Contar los perfiles en
    # portales ajenos infla el numero con paginas de terceros.
    cuenta_kind = Counter(f["web_kind"] for f in filas)
    print("\n  CLASIFICACION DE LA URL")
    for k, v in cuenta_kind.most_common():
        print(f"    {k:26} {v:5,}  ({v/total*100:5.1f}%)")
    propias = [f for f in filas if f["web_kind"] == "OFFICIAL_WEB"]
    print(f"    {'AGENCIAS CON WEB PROPIA':26} {len(propias):5,}")

    # --- cuadro de cobertura, solo sobre las webs propias -------------------
    print("\n  COBERTURA POR TECNOLOGIA (solo web propia)")
    print(f"    {'plataforma':18} {'detect':>6} {'proces':>6} {'procesa':>7} "
          f"{'c/props':>7} {'error':>6} {'pend':>6} {'propiedades':>12}")
    orden = Counter(f["platform"] for f in propias)
    for k, det in orden.most_common():
        g = [f for f in propias if f["platform"] == k]
        # procesable: hay un connector que la puede leer, escrito o por escribir
        proc = sum(1 for f in g if f["connector_status"] in
                   ("SUPPORTED_STANDARD", "SUPPORTED_CUSTOM", "DETECTED_NOT_BUILT"))
        hecho = sum(1 for f in g if f["connector_status"].startswith("SUPPORTED"))
        conp = sum(1 for f in g if f["properties_normalized"])
        err = sum(1 for f in g if f["connector_status"] in
                  ("NETWORK_BLOCKED", "UNSUPPORTED_PLATFORM",
                   "ENUMERACION_INCOMPLETA"))
        pend = sum(1 for f in g if f["connector_status"] in
                   ("NO_INTENTADA", "NO_INVENTORY", "UNKNOWN", "DETECTED_NOT_BUILT"))
        props = sum(f["properties_normalized"] or 0 for f in g)
        print(f"    {k[:18]:18} {det:6,} {proc:6,} {hecho:7,} {conp:7,} "
              f"{err:6,} {pend:6,} {props:12,}")

    # --- residual: que queda afuera, con nombre y apellido -------------------
    # "Muchos" o "pocos" no sirve para decidir el proximo connector. Se emite la
    # lista con dominio e id para que el siguiente frente se elija sobre datos.
    residual = [
        {"canonical_agency_id": f["canonical_agency_id"],
         "eretz_id": f["eretz_id"], "agency_name": f["agency_name"],
         "domain": f["domain"], "host": f["host"], "province": f["province"],
         "platform": f["platform"], "confidence": f["confidence"],
         "evidence": f["evidence"], "connector_status": f["connector_status"],
         "declared_inventory": f["declared_inventory"]}
        for f in propias
        if not f["connector_status"].startswith("SUPPORTED")]
    ruta_res = Path(a.salida).with_name("RESIDUAL_UNCOVERED.jsonl")
    ruta_res.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in residual),
        encoding="utf-8")
    print(f"\n  SIN COBERTURA (web propia): {len(residual):,}"
          f"  -> {ruta_res.name}")
    for k, v in Counter(r["platform"] for r in residual).most_common(8):
        decl = sum(x["declared_inventory"] or 0 for x in residual
                   if x["platform"] == k)
        print(f"    {k[:22]:22} {v:5,}  inventario declarado conocido {decl:7,}")

    print()
    print(f"  agencias con web: {len(filas):,}\n")
    print("  por plataforma:")
    for k, v in Counter(f["platform"] for f in filas).most_common(14):
        props = sum(f["properties_normalized"] or 0
                    for f in filas if f["platform"] == k)
        con = sum(1 for f in filas if f["platform"] == k
                  and f["connector_status"].startswith("SUPPORTED"))
        print(f"    {k:18} {v:5,} agencias  {con:5,} con connector  "
              f"{props:7,} propiedades")
    resto = cuenta_plat.most_common()[14:]
    if resto:
        claves = {k for k, _ in resto}
        con = sum(1 for f in filas if f["platform"] in claves
                  and f["connector_status"].startswith("SUPPORTED"))
        props = sum(f["properties_normalized"] or 0 for f in filas
                    if f["platform"] in claves)
        print(f"    {'otras ' + str(len(resto)) + ' plataformas':18} "
              f"{sum(v for _, v in resto):5,} agencias  {con:5,} con connector  "
              f"{props:7,} propiedades")
    print("\n  por estado del connector:")
    for k, v in Counter(f["connector_status"] for f in filas).most_common():
        print(f"    {k:26} {v:5,}")
    print(f"\n  artefacto -> {a.salida}")

    # --- ranking del proximo connector por ROI ------------------------------
    sin_conector = [f for f in filas
                    if not f["connector_status"].startswith("SUPPORTED")]
    por_plat = defaultdict(list)
    for f in sin_conector:
        por_plat[f["platform"]].append(f)
    print("\n  proximas plataformas por cobertura pendiente:")
    for k, g in sorted(por_plat.items(), key=lambda t: -len(t[1]))[:8]:
        decl = sum(x["declared_inventory"] or 0 for x in g)
        print(f"    {k:18} {len(g):5,} agencias  inventario declarado {decl:7,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

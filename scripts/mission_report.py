#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Informe consolidado de la ingesta directa.

Lee todos los artefactos producidos y los cruza. No pide nada a la red, no toca
la base y no decide nada: si un numero sale raro, el problema esta en el
artefacto, no aca.

La reconciliacion es lo que mas importa: enumerado, pedido, obtenido y escrito
tienen que cerrar. Una perdida silenciosa entre esas etapas es exactamente el
tipo de error que no avisa.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CORRIDAS = {
    "TOKKO (rollout completo)": ("TOKKO_ROLLOUT_FULL", "tokko"),
    "TOKKO (rollout controlado)": ("TOKKO_ROLLOUT_CTRL", "tokko"),
    "WORDPRESS (rollout completo)": ("WP_ROLLOUT_FULL", "wordpress"),
    "WORDPRESS (canary)": ("WP_CANARY", "wordpress"),
    "CENTURY 21 (canary)": ("C21_CANARY", "century21"),
    "GENERICO (canary)": ("GENERICO_CANARY", "generico"),
    "WASI (rollout completo)": ("WASI_ROLLOUT_FULL", "wasi"),
    "RESCATE 2 (generico)": ("RESCATE2_generico", "generico"),
    "RESCATE 2 (tokko)": ("RESCATE2_tokko", "generico"),
    "RESCATE 2 (wordpress)": ("RESCATE2_wordpress", "wordpress"),
    "RESCATE 3 (formas descubiertas)": ("RESCATE3_shapes", "generico"),
    "FORMAS VERIFICADAS (por fuente)": ("FORMAS_ROLLOUT", "generico"),
    "RESIDUAL (generico)": ("RESIDUAL_ROLLOUT", "generico"),
}


def corridas_de(base: Path, prefijo: str) -> list[str]:
    """Las corridas que existen, no las que alguien supuso que iban a existir.

    Estaba fijo en ("1", "2"): el informe mostraba la corrida 2 de Tokko -la
    anterior al arreglo del checkpoint, con todo marcado NUEVA- y escondia la 3,
    que es la que cerro con 99,83% sin cambios. El numero que el informe
    mostraba decia lo contrario de lo que habia pasado.
    """
    salida = []
    for ruta in base.glob(f"{prefijo}run*"):
        n = ruta.name.split("run", 1)[1].split(".")[0]
        if n.isdigit():
            salida.append(n)
    return sorted(set(salida), key=int)


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


def host_de(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0].lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    a = ap.parse_args()
    dd, raiz = Path(a.data_dir), Path(a.raiz)

    print("=" * 70)
    print("A. FUENTES DE INMOBILIARIAS")
    print("=" * 70)
    directorio = leer(dd / "agency_web_directory.jsonl")
    mapa = leer(dd / "scrape_source_technology_map.jsonl")
    cola = leer(dd / "web_search_queue_current.jsonl")
    print(f"  padron canonico:              {len(directorio):,}")
    print(f"  universo tecnologico mapeado: {len(mapa):,}")
    print(f"  cola pendiente de busqueda:   {len(cola):,}")
    if cola:
        print(f"    con candidatas guardadas:   "
              f"{sum(1 for c in cola if c.get('tiene_candidatas')):,}")
        print(f"    requieren Search API:       "
              f"{sum(1 for c in cola if not c.get('tiene_candidatas')):,}")
    for k, v in Counter(x.get("status") for x in directorio).most_common(8):
        print(f"    {str(k):32} {v:6,}")

    print()
    print("=" * 70)
    print("B. MAPA DE PLATAFORMAS")
    print("=" * 70)
    for k, v in Counter(x["detected_platform"] for x in mapa).most_common(12):
        print(f"    {k:22} {v:6,}  ({v/max(len(mapa),1)*100:5.1f}%)")
    print("\n  por estrategia:")
    for k, v in Counter(x["strategy"] for x in mapa).most_common():
        print(f"    {k:22} {v:6,}")

    print()
    print("=" * 70)
    print("C. CORRIDAS DE INGESTA")
    print("=" * 70)
    todas_props: list[dict] = []
    for etiqueta, (carpeta, _) in CORRIDAS.items():
        base = raiz / carpeta
        if not base.exists():
            continue
        print(f"\n  {etiqueta}  [{carpeta}]")
        for corrida in corridas_de(base, "quality_report_"):
            q = base / f"quality_report_run{corrida}.json"
            if not q.exists():
                continue
            r = json.loads(q.read_text(encoding="utf-8"))
            cambios = r.get("cambios") or {}
            print(f"    run{corrida}  codigo={r.get('version_codigo','-')} "
                  f"fuentes={r.get('fuentes_intentadas',0):,} "
                  f"enum={r.get('propiedades_enumeradas',0):,} "
                  f"escritas={r.get('propiedades_escritas',0):,} "
                  f"recon={r.get('reconcilia')}")
            print(f"          estados={r.get('fuentes_por_estado')}")
            print(f"          cambios={cambios}  errores={r.get('errores',0)}  "
                  f"potential_inactive={r.get('potential_inactive',0)}")
        # Las propiedades de la corrida mas reciente, que no es la mas grande:
        # la primera corrida de WordPress tenia 19.019 filas y la sexta 18.505,
        # y la autoritativa es la sexta -la primera incluye propiedades que ya
        # no existen y fotos que eran iconos de la pagina-.
        for corrida in reversed(corridas_de(base, "properties_")):
            p = base / f"properties_run{corrida}.jsonl"
            corregida = p.with_name(p.name.replace(".jsonl", ".coherente.jsonl"))
            elegida = corregida if corregida.exists() else p
            if elegida.exists():
                todas_props.extend(leer(elegida))
                break

    if not todas_props:
        print("\n  (sin propiedades todavia)")
        return 0

    n = len(todas_props)
    print()
    print("=" * 70)
    print("D. INGESTA CONSOLIDADA")
    print("=" * 70)
    print(f"  propiedades descubiertas: {n:,}")
    for k, v in Counter(p.get("connector") for p in todas_props).most_common():
        print(f"    {k:18} {v:7,}")
    print(f"  inmobiliarias con inventario: "
          f"{len({p.get('canonical_agency_id') for p in todas_props}):,}")

    print()
    print("=" * 70)
    print("E. DUPLICADOS  (objetivo: introducidos = 0)")
    print("=" * 70)
    hashes = Counter(p.get("hash_dedup") for p in todas_props)
    por_hash = defaultdict(set)
    for p in todas_props:
        por_hash[p.get("hash_dedup")].add(p.get("canonical_agency_id"))
    print(f"  hash repetido:                 {sum(1 for c in hashes.values() if c > 1):,}")
    print(f"  hash compartido entre agencias:{sum(1 for v in por_hash.values() if len(v) > 1):,}")
    urls = Counter(p.get("source_url") for p in todas_props)
    print(f"  url repetida:                  {sum(1 for c in urls.values() if c > 1):,}")
    pistas = defaultdict(set)
    for p in todas_props:
        if p.get("latitud") and p.get("precio") and p.get("moneda"):
            pistas[(round(p["latitud"], 5), round(p.get("longitud") or 0, 5),
                    p["precio"], p["moneda"])].add(p.get("canonical_agency_id"))
    print(f"  candidatos cross-agency:       "
          f"{sum(1 for v in pistas.values() if len(v) > 1):,}  (se marcan, no se fusionan)")

    print()
    print("=" * 70)
    print("F. CALIDAD POR CAMPO")
    print("=" * 70)
    campos = ("titulo", "descripcion", "operacion", "tipo_propiedad", "precio",
              "moneda", "provincia", "ciudad", "barrio", "direccion", "latitud",
              "dormitorios", "banos", "ambientes", "superficie_total",
              "superficie_cubierta", "imagenes")
    por_conn = defaultdict(list)
    for p in todas_props:
        por_conn[p.get("connector")].append(p)
    ancho = max(len(c) for c in campos)
    conns = sorted(por_conn)
    print(f"    {'campo':{ancho}}  " + "  ".join(f"{c[:9]:>9}" for c in conns) + "     total")
    for c in campos:
        fila = []
        for k in conns:
            g = por_conn[k]
            fila.append(sum(1 for p in g if p.get(c) not in (None, "", [])) / max(len(g), 1))
        tot = sum(1 for p in todas_props if p.get(c) not in (None, "", [])) / n
        print(f"    {c:{ancho}}  " + "  ".join(f"{v*100:8.1f}%" for v in fila) +
              f"  {tot*100:8.1f}%")

    print()
    print("=" * 70)
    print("G. BAJAS (modo observacion)")
    print("=" * 70)
    total_aus = 0
    for etiqueta, (carpeta, _) in CORRIDAS.items():
        for corrida in corridas_de(raiz / carpeta, "absences_"):
            aus = leer(raiz / carpeta / f"absences_run{corrida}.jsonl")
            if aus:
                total_aus += len(aus)
                print(f"  {etiqueta} run{corrida}: {len(aus):,} "
                      f"{dict(Counter(x.get('estado') for x in aus))}")
    if not total_aus:
        print("  ninguna ausencia registrada todavia")
    print("  regla: 3 corridas seguidas sin ver la propiedad, y ninguna cuenta")
    print("         si la fuente no respondio o la enumeracion quedo incompleta.")
    print("  ninguna propiedad se desactiva en esta fase.")

    print()
    print("=" * 70)
    print("H. RENDIMIENTO")
    print("=" * 70)
    for etiqueta, (carpeta, _) in CORRIDAS.items():
        q = raiz / carpeta / "quality_report_run1.json"
        if not q.exists():
            continue
        r = json.loads(q.read_text(encoding="utf-8"))
        seg = r.get("segundos") or 1
        esc = r.get("propiedades_escritas", 0)
        print(f"  {etiqueta:30} {esc:7,} props  {seg/60:6.1f} min  "
              f"{esc/seg*3600:9,.0f} props/h")
    return 0


if __name__ == "__main__":
    sys.exit(main())

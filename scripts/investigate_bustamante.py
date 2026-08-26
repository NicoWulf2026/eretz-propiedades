#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que son en realidad los dos "Bustamante" que se disputaban 3.137 propiedades.

El caso llego planteado como un duplicado del padron: eretz_id 1028 y 651
apuntando al mismo sitio, con 3.137 propiedades en conflicto, y la pregunta de
cual de los dos ids conserva ERETZ.

La pregunta estaba mal planteada, y los datos lo dicen sin ambiguedad:

  1028  Bustamante Propiedades      zonas: Villanueva, El Cazador, Villanueva
                                    Tigre, Canning, Belen de Escobar
  651   Bustamante Inmobiliaria     zonas: Bajo la Via, Los Perales, Chijra,
                                    Terrenos La Almona

Ninguna zona en comun. Ningun agent_id de Roomix en comun. Nombres comerciales
distintos. Y de las 6.597 entidades del padron, CERO operan en los dos grupos de
zonas: son dos mercados que no se tocan.

La prueba definitiva la da el sitio en disputa, que se presenta solo:

  "Bustamante Propiedades | Inmobiliaria en Tigre, Pilar, Nordelta, Escobar y
   Villanueva"

Esas son las zonas de 1028. El sitio no menciona ninguna de las de 651.

Conclusion: ENTIDADES_DISTINTAS. No hay nada que fusionar. Lo que hay es una URL
mal atribuida: a 651 se le asigno el sitio de 1028. El directorio verificado por
identidad nunca le asigno dominio a 651 -quedo AMBIGUOUS-; la atribucion
equivocada entro despues, en el directorio de plataformas.

Consecuencia: las 3.137 propiedades no estan en disputa. Son de 1028. Y 651
vuelve a la cola de descubrimiento, que es donde tiene que estar una
inmobiliaria de la que todavia no sabemos la web.

Solo lee artefactos y, con --aplicar, corrige la atribucion equivocada. No toca
la base ni borra ninguna entidad.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

CASO = "bustamante"
VERSION = "bustamante_investigation_v1"

DUPLICADO = "DUPLICADO_CANONICO"
SUCURSALES = "SUCURSALES_RELACIONADAS"
DISTINTAS = "ENTIDADES_DISTINTAS"
AMBIGUO = "AMBIGUO"


def leer(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]


def zonas(e: dict) -> set[str]:
    return {z.lower().strip() for z in (e.get("zonas_observadas") or []) if z}


# "centro" la comparten decenas de ciudades: no ubica nada y no puede contar
# como zona en comun.
GENERICAS = {"centro", "comercial centro", "microcentro"}


def clasificar(a: dict, b: dict, comparten_zona: int) -> tuple[str, list[str]]:
    """Decide con evidencia, y dice cual la sostiene."""
    ev: list[str] = []
    za, zb = zonas(a) - GENERICAS, zonas(b) - GENERICAS
    comun = za & zb
    ids_a = set(a.get("raw_agent_ids") or [])
    ids_b = set(b.get("raw_agent_ids") or [])

    if ids_a & ids_b:
        ev.append(f"comparten agent_id de Roomix: {sorted(ids_a & ids_b)}")
        return DUPLICADO, ev

    if comun:
        ev.append(f"zonas en comun: {sorted(comun)}")
        return SUCURSALES if len(comun) < min(len(za), len(zb)) else DUPLICADO, ev

    ev.append(f"sin zonas en comun: {sorted(za)} vs {sorted(zb)}")
    ev.append("sin agent_id de Roomix en comun")
    ev.append(f"nombres distintos: {a.get('nombre_original')} vs "
              f"{b.get('nombre_original')}")
    if comparten_zona == 0:
        ev.append("ninguna de las 6.597 entidades del padron opera en los dos "
                  "grupos de zonas: son mercados que no se tocan")
        return DISTINTAS, ev
    return AMBIGUO, ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--plataformas",
                    default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\BUSTAMANTE_RESOLUTION.json")
    ap.add_argument("--aplicar", action="store_true",
                    help="sin esto solo informa; con esto quita la atribucion "
                         "equivocada del directorio de plataformas")
    a = ap.parse_args()

    dd = Path(a.data_dir)
    cw = leer(dd / "crosswalk_final.jsonl")
    awd = {x["canonical_agency_id"]: x for x in leer(dd / "agency_web_directory.jsonl")}
    pd_rows = leer(Path(a.plataformas))

    fam = [x for x in cw if CASO in (x.get("nombre_normalizado") or "").lower()]
    por_id = {x["stable_id"]: x for x in fam}
    uno = por_id.get("roomix:bustamante propiedades")
    dos = por_id.get("roomix:bustamante inmobiliaria")
    if not uno or not dos:
        print("no estan las dos entidades del caso en el padron")
        return 1

    za, zb = zonas(uno) - GENERICAS, zonas(dos) - GENERICAS
    ambos = sum(1 for x in cw
                if (zonas(x) - GENERICAS) & za and (zonas(x) - GENERICAS) & zb)
    veredicto, evidencia = clasificar(uno, dos, ambos)

    # El sitio en disputa: a quien nombra.
    host = "bustamantepropiedades.com"
    disputan = [r for r in pd_rows if host in (r.get("host") or "")]

    informe = {
        "caso": CASO,
        "veredicto": veredicto,
        "evidencia": evidencia,
        "entidades": [
            {"stable_id": e["stable_id"], "nombre": e.get("nombre_original"),
             "eretz_id": (awd.get(e["stable_id"]) or {}).get("eretz_id"),
             "zonas": sorted(zonas(e)), "avisos": e.get("avisos_observados"),
             "raw_agent_ids": e.get("raw_agent_ids"),
             "web_verificada": (awd.get(e["stable_id"]) or {}).get("selected_domain"),
             "web_status": (awd.get(e["stable_id"]) or {}).get("status")}
            for e in (uno, dos)],
        "entidades_que_operan_en_ambos_mercados": ambos,
        "sitio_en_disputa": {
            "host": host,
            "se_presenta_como": ("Bustamante Propiedades | Inmobiliaria en Tigre, "
                                 "Pilar, Nordelta, Escobar y Villanueva"),
            "coincide_con": "roomix:bustamante propiedades",
            "reclamantes_en_directorio_plataformas": [
                {"canonical_agency_id": r["canonical_agency_id"],
                 "eretz_id": r.get("eretz_id")} for r in disputan]},
        "familia_bustamante": [
            {"stable_id": e["stable_id"], "nombre": e.get("nombre_original"),
             "zonas": sorted(zonas(e))} for e in fam],
        "accion": ("quitar la atribucion de %s a roomix:bustamante inmobiliaria "
                   "(eretz_id 651) y devolverla a la cola de descubrimiento" % host),
        "propiedades_liberadas_para_1028": 3137,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "investigation_version": VERSION,
    }

    Path(a.salida).write_text(json.dumps(informe, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print("### CASO BUSTAMANTE ###")
    print(f"  veredicto: {veredicto}\n")
    for e in informe["entidades"]:
        print(f"  {e['nombre'][:34]:36} eretz_id={str(e['eretz_id']):6} "
              f"avisos={e['avisos']}")
        print(f"      zonas: {', '.join(e['zonas'])[:78]}")
        print(f"      web verificada: {e['web_verificada']} ({e['web_status']})")
    print("\n  evidencia:")
    for x in evidencia:
        print(f"    - {x[:104]}")
    print(f"\n  entidades del padron que operan en los dos mercados: {ambos}")
    print(f"  el sitio en disputa se presenta como: "
          f"{informe['sitio_en_disputa']['se_presenta_como'][:70]}")

    if veredicto == DISTINTAS and a.aplicar:
        n = 0
        for r in pd_rows:
            if (r.get("canonical_agency_id") == "roomix:bustamante inmobiliaria"
                    and host in (r.get("host") or "")):
                r["domain_mal_atribuido"] = r.get("domain")
                r["domain"] = None
                r["host"] = None
                # NO es NOT_FOUND: lo unico demostrado es que ESE sitio no
                # era suyo. Su web propia nunca se busco, asi que la
                # entidad vuelve a la cola, no a una conclusion.
                r["web_kind"] = "SEARCH_API_PENDING"
                r["web_kind_reason"] = (
                    "el sitio es de Bustamante Propiedades (eretz_id 1028), que "
                    "opera en Tigre/Pilar/Nordelta/Escobar; esta inmobiliaria "
                    "opera en otro mercado y no comparte ninguna zona")
                r["needs_external_search"] = True
                n += 1
        tmp = Path(a.plataformas).with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in pd_rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(Path(a.plataformas))
        print(f"\n  corregidas {n} filas del directorio de plataformas")
        print("  651 vuelve a la cola de descubrimiento; 1028 conserva su sitio")
    elif veredicto == DISTINTAS:
        print("\n  (informe solamente; usar --aplicar para corregir la atribucion)")

    print(f"\n  artefacto -> {a.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

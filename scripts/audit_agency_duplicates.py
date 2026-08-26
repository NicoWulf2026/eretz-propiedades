#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que otras entidades del padron podrian ser la misma inmobiliaria.

Genera candidatos. No fusiona ninguno, y no deberia: fusionar mal es la clase de
error que no se nota al hacerlo y aparece meses despues, cuando el inventario de
dos empresas quedo bajo un solo id y ya nadie recuerda de donde salio cual.

Tres casos ya resueltos ensenaron que el parecido del nombre es la peor
evidencia posible. Bustamante, Salerno y Zarate compartian apellido y dominio y
eran seis inmobiliarias distintas en seis mercados que no se tocan. Por eso las
senales estan ordenadas por lo que realmente prueban:

  agent_id de Roomix compartido  no se comparte por casualidad
  matricula compartida           la otorga un colegio, identifica a la empresa
  telefono o mail compartidos    fuertes, pero una franquicia central los
                                 comparte entre oficinas
  dominio compartido             debil solo: es lo que confundio los tres casos
  nombre parecido                por si mismo no prueba nada

Un candidato con una sola senal debil no es un candidato: es un homonimo. Por
eso se exige o una senal fuerte, o dos debiles que apunten al mismo lado.

Solo lee artefactos. No pide nada a la red y no escribe en ningun padron.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

AUDIT_VERSION = "agency_duplicate_audit_v1"

FUERTE = "FUERTE"
DEBIL = "DEBIL"

# Que peso tiene cada senal, y por que.
SENALES = {
    "agent_id_compartido": (FUERTE, "un id de Roomix no se comparte por casualidad"),
    "matricula_compartida": (FUERTE, "la matricula la otorga un colegio a una empresa"),
    "telefono_compartido": (DEBIL, "una franquicia comparte el telefono central"),
    "email_compartido": (DEBIL, "una franquicia comparte la casilla central"),
    "dominio_compartido": (DEBIL, "dos homonimas pueden aparecer en el mismo sitio"),
    "nucleo_de_nombre_igual": (DEBIL, "el apellido es lo que confunde, no lo que prueba"),
    "zonas_compartidas": (DEBIL, "operar en la misma zona no las hace la misma"),
}

# Casillas y telefonos que no identifican a nadie.
GENERICOS_MAIL = {"info@", "contacto@", "ventas@", "administracion@", "hola@"}

GENERICAS_ZONA = {"centro", "comercial centro", "microcentro"}

# Senales que acompanan pero no identifican, y que por lo tanto no pueden ser
# una de las dos que hacen falta para levantar un candidato.
#
# El apellido es lo que confundio Bustamante, Salerno y Zarate. Y compartir zona
# es lo normal: en Palermo trabajan cientos de inmobiliarias, asi que "las dos
# operan en Palermo" no acerca en nada a que sean la misma. Contandolas, la
# auditoria devolvia 948 pares que solo tenian en comun un portal y una ciudad.
NO_IDENTIFICAN = {"nucleo_de_nombre_igual", "zonas_compartidas"}

# Cuantas agencias distintas tienen que colgar de un host para que compartirlo
# deje de decir algo. Un portal aloja a decenas: que dos figuren ahi no las
# vincula mas de lo que las vincula figurar en la misma guia telefonica.
AGENCIAS_PARA_SER_PORTAL = 3


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def tel(t: str) -> str:
    """Solo los digitos, y los ultimos ocho: los prefijos varian por como los
    escribio cada quien, el numero no."""
    d = re.sub(r"[^0-9]", "", str(t or ""))
    return d[-8:] if len(d) >= 8 else ""


def host(u: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", u or "").split("/")[0].lower()


def leer(ruta: Path):
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except ValueError:
                continue


def claves_de(e: dict, dominio: str | None) -> dict:
    """Las senales de esta entidad, ya normalizadas."""
    mails = set()
    for m in ([e.get("email")] if isinstance(e.get("email"), str)
              else (e.get("email") or [])):
        m = norm(m)
        if m and "@" in m and not any(m.startswith(g) for g in GENERICOS_MAIL):
            mails.add(m)
    mats = {norm(x) for x in (e.get("matricula") or []) if norm(x)}
    telefonos = {tel(e.get("telefono"))} - {""}
    zonas = {norm(z) for z in (e.get("zonas_observadas") or [])} - GENERICAS_ZONA
    return {
        "agent_id_compartido": set(e.get("raw_agent_ids") or []),
        "matricula_compartida": mats,
        "telefono_compartido": telefonos,
        "email_compartido": mails,
        "dominio_compartido": {host(dominio)} - {""} if dominio else set(),
        "nucleo_de_nombre_igual": {norm(e.get("nucleo"))} - {""},
        "zonas_compartidas": zonas,
    }


def evaluar(a: dict, b: dict) -> tuple:
    """(senales_en_comun, fuerza). No decide nada mas."""
    comunes = {}
    for senal, valores_a in a.items():
        compartido = valores_a & b[senal]
        if compartido:
            comunes[senal] = sorted(compartido)[:4]
    fuertes = [s for s in comunes if SENALES[s][0] == FUERTE]
    debiles = [s for s in comunes if SENALES[s][0] == DEBIL]
    if fuertes:
        return comunes, FUERTE
    # El nombre solo no cuenta: es exactamente lo que confundio los tres casos
    # ya resueltos.
    utiles = [s for s in debiles if s not in NO_IDENTIFICAN]
    if len(utiles) >= 2:
        return comunes, DEBIL
    return comunes, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--raiz", default=r"D:\INMO CAPITAL")
    ap.add_argument("--salida",
                    default=r"D:\INMO CAPITAL\AGENCY_DUPLICATE_CANDIDATES.jsonl")
    a = ap.parse_args()
    dd, raiz = Path(a.data_dir), Path(a.raiz)

    awd = {x["canonical_agency_id"]: x for x in leer(dd / "agency_web_directory.jsonl")}
    plat = {x.get("canonical_agency_id"): x
            for x in leer(raiz / "agency_platform_directory.jsonl")}

    ents, claves = {}, {}
    for e in leer(dd / "crosswalk_final.jsonl"):
        sid = e.get("stable_id")
        if not sid:
            continue
        d = (awd.get(sid) or {}).get("selected_domain") or (
            plat.get(sid) or {}).get("domain")
        ents[sid] = e
        claves[sid] = claves_de(e, d)

    # Un host del que cuelgan tres o mas agencias es un portal: compartirlo no
    # las vincula. Se descuenta antes de indexar, no despues, para que tampoco
    # cuente como una de las dos senales debiles.
    cuantas_por_host = Counter()
    for cs in claves.values():
        for h in cs["dominio_compartido"]:
            cuantas_por_host[h] += 1
    portales = {h for h, n in cuantas_por_host.items()
                if n >= AGENCIAS_PARA_SER_PORTAL}
    for cs in claves.values():
        cs["dominio_compartido"] -= portales

    # Indice invertido por cada valor de cada senal: comparar 6.597 entidades
    # de a pares son 21 millones de comparaciones y casi todas dan cero.
    indice = defaultdict(set)
    for sid, cs in claves.items():
        for senal, valores in cs.items():
            for v in valores:
                indice[(senal, v)].add(sid)

    pares = set()
    for (senal, _), sids in indice.items():
        if len(sids) < 2 or len(sids) > 40:
            # Un valor que comparten cuarenta entidades no identifica a nadie:
            # es una franquicia, un portal o un telefono de central.
            continue
        orden = sorted(sids)
        for i, x in enumerate(orden):
            for y in orden[i + 1:]:
                pares.add((x, y))

    candidatos = []
    for x, y in sorted(pares):
        comunes, fuerza = evaluar(claves[x], claves[y])
        if not fuerza:
            continue
        candidatos.append({
            "entidades": [
                {"canonical_agency_id": s,
                 "nombre": ents[s].get("nombre_original"),
                 "eretz_id": (awd.get(s) or {}).get("eretz_id"),
                 "avisos": ents[s].get("avisos_observados"),
                 "zonas": sorted({norm(z) for z in
                                  (ents[s].get("zonas_observadas") or [])})[:6]}
                for s in (x, y)],
            "fuerza": fuerza,
            "senales": comunes,
            "por_que_cada_senal": {s: SENALES[s][1] for s in comunes},
            "accion": "candidato para revision humana; no se fusiona nada",
            "audit_version": AUDIT_VERSION,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    salida = Path(a.salida)
    tmp = salida.with_suffix(salida.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for c in candidatos:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    tmp.replace(salida)

    print("### CANDIDATOS A DUPLICADO EN EL PADRON ###")
    print("  entidades analizadas: %d" % len(ents))
    print("  pares con alguna senal en comun: %d" % len(pares))
    print("  candidatos que superan el umbral: %d" % len(candidatos))
    print()
    for f in (FUERTE, DEBIL):
        g = [c for c in candidatos if c["fuerza"] == f]
        print("  %s: %d" % (f, len(g)))
        for c in g[:6]:
            e1, e2 = c["entidades"]
            print("    %-30s + %-30s  %s"
                  % (str(e1["nombre"])[:28], str(e2["nombre"])[:28],
                     ", ".join(c["senales"])))
    print()
    print("  senales mas frecuentes:")
    for k, v in Counter(s for c in candidatos for s in c["senales"]).most_common():
        print("    %-26s %5d" % (k, v))
    print()
    print("  NINGUNA entidad se fusiono. Esto es una lista para mirar.")
    print("  artefacto -> %s" % salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Las 733 promociones y los 54 vinculos, contra el padron de hoy. No escribe.

Una promocion calculada hace una semana puede haber quedado sin sentido: la
inmobiliaria pudo haberse creado entretanto, o pudo aparecer otra con el mismo
nombre. Crear un alta que ya existe no rompe nada visible el primer dia -deja
dos filas para la misma inmobiliaria- y despues cuesta muchisimo desarmarlo.

Cinco clases, y solo la primera se podria escribir:

  STILL_SAFE   ni el dominio ni el nombre aparecen en el padron. Es un alta.
  NOW_EXISTS   el dominio YA esta en `inmobiliarias_main.web`. No es un alta:
               es un vinculo, y el dry-run de vinculos ya sabe hacer eso.
  AMBIGUOUS    el nombre normalizado coincide con MAS de una fila del padron.
               No se puede elegir por nosotros.
  CONFLICT     el nombre coincide con una fila que declara OTRO dominio. O es
               una homonima real o una de las dos webs esta mal atribuida;
               en cualquier caso hay que mirarlo.
  REVIEW       coincide con exactamente una fila y esa fila no declara web.
               Probablemente sea la misma y le falte el dato, pero
               "probablemente" no alcanza para crear ni para vincular.

El padron se baja una sola vez -id, nombre, host, activa- y el cruce se hace
aca. La normalizacion es la misma de los dos lados: sin acentos, minusculas,
sin puntuacion, espacios colapsados.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

D = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY")

# Palabras que casi todas comparten: dejarlas dentro hace que "X Propiedades" y
# "Y Propiedades" se parezcan mas de lo que son. Se usan solo para decidir si
# un nombre quedo VACIO despues de limpiarlo, no para comparar.
GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes",
             "raices", "negocios", "inmobiliarios", "servicios", "srl", "sa",
             "s", "a", "sas", "estudio", "grupo", "real", "estate", "y", "de",
             "del", "la", "el", "los", "las"}


def sin_acentos(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s: str) -> str:
    s = sin_acentos(s).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def host(u: str) -> str:
    u = (u or "").lower()
    u = re.sub(r"^https?://", "", u).split("/")[0]
    return re.sub(r"^www\.", "", u).split(":")[0]


def padron(ruta: Path) -> list[dict]:
    """El volcado viene como una sola celda con tabuladores y saltos."""
    crudo = ruta.read_text(encoding="utf-8", errors="replace")
    # El volcado viene escapado DOS veces -`\\t` y `\\n` literales en el
    # archivo-, asi que se deshacen los dos niveles y en ese orden: al reves,
    # el primer paso dejaria un tabulador de verdad seguido de una barra
    # suelta y la fila quedaria partida.
    cuerpo = crudo
    for doble, simple in ((r"\\t", "\t"), (r"\\n", "\n")):
        cuerpo = cuerpo.replace(doble, simple)
    cuerpo = cuerpo.replace(r"\t", "\t").replace(r"\n", "\n")
    filas = []
    for linea in cuerpo.splitlines():
        partes = linea.split("\t")
        if len(partes) < 4 or not partes[0].strip().isdigit():
            continue
        filas.append({"id": int(partes[0].strip()), "nombre": partes[1],
                      "host": partes[2].strip(), "activa": partes[3].strip()})
    return filas


def main() -> int:
    filas = padron(Path(sys.argv[1]))
    print(f"padron: {len(filas)} inmobiliarias")
    if len(filas) < 6000:
        raise SystemExit("el padron vino corto; no clasifico con datos parciales")

    por_host = defaultdict(list)
    por_nombre = defaultdict(list)
    for f in filas:
        if f["host"]:
            por_host[f["host"]].append(f)
        n = norm(f["nombre"])
        if n:
            por_nombre[n].append(f)

    ult = {}
    for linea in (D / "AGENCY_PROMOTION_GATE.jsonl").read_text(
            encoding="utf-8").splitlines():
        if linea.strip():
            g = json.loads(linea)
            if g.get("canonical_agency_id"):
                ult[g["canonical_agency_id"]] = g
    seguras = [g for g in ult.values()
               if g.get("promotion_state") == "SAFE_TO_PROMOTE"]

    clases = Counter()
    SALIDA.mkdir(parents=True, exist_ok=True)
    with open(SALIDA / "revalidacion_promociones.jsonl", "w",
              encoding="utf-8") as g:
        for p in seguras:
            cid = p["canonical_agency_id"]
            h = host(p.get("domain"))
            n = norm(p.get("agency_name"))
            homonimas = por_nombre.get(n, []) if n else []
            mismo_host = por_host.get(h, []) if h else []

            if mismo_host:
                clase = "NOW_EXISTS"
                ev = (f"el dominio ya figura en main: "
                      f"{[x['id'] for x in mismo_host][:3]}")
            elif len(homonimas) > 1:
                clase = "AMBIGUOUS"
                ev = (f"{len(homonimas)} filas del padron con el mismo nombre: "
                      f"{[x['id'] for x in homonimas][:3]}")
            elif len(homonimas) == 1:
                otra = homonimas[0]
                if otra["host"] and h and otra["host"] != h:
                    clase = "CONFLICT"
                    ev = (f"main {otra['id']} tiene el mismo nombre y declara "
                          f"otro dominio")
                else:
                    clase = "REVIEW"
                    ev = (f"main {otra['id']} tiene el mismo nombre y no "
                          f"declara web")
            else:
                clase = "STILL_SAFE"
                ev = "ni el dominio ni el nombre estan en el padron"
            clases[clase] += 1
            g.write(json.dumps({"canonical_agency_id": cid, "clase": clase,
                                "dominio": h, "evidencia": ev,
                                "writes": False},
                               ensure_ascii=False) + "\n")

    print(f"\npromociones revalidadas: {len(seguras)}")
    for c, k in clases.most_common():
        print(f"  {c:12} {k:5}  ({100*k/len(seguras):5.1f} %)")

    # --- los 54 vinculos ---
    por_id = {f["id"]: f for f in filas}
    enlaces = [json.loads(l) for l in
               (D / "AGENCY_MAIN_LINK_DRYRUN.jsonl").read_text(
                   encoding="utf-8").splitlines() if l.strip()]
    enlaces = [e for e in enlaces if e.get("action") == "LINK_TO_EXISTING"]
    clases_l = Counter()
    with open(SALIDA / "revalidacion_vinculos.jsonl", "w",
              encoding="utf-8") as g:
        for e in enlaces:
            destinos = [int(x) for x in (e.get("main_candidates") or [])
                        if str(x).isdigit()]
            n = norm(e.get("agency_name"))
            faltan = [d for d in destinos if d not in por_id]
            homonimas = por_nombre.get(n, []) if n else []
            if faltan:
                clase, ev = "CONFLICT", f"el destino ya no existe: {faltan}"
            elif len(destinos) != 1:
                clase, ev = "AMBIGUOUS", f"{len(destinos)} destinos declarados"
            elif len(homonimas) > 1:
                clase = "AMBIGUOUS"
                ev = (f"el nombre coincide ahora con {len(homonimas)} filas: "
                      f"{[x['id'] for x in homonimas][:3]}")
            elif homonimas and homonimas[0]["id"] != destinos[0]:
                clase = "CONFLICT"
                ev = (f"el nombre resuelve a main {homonimas[0]['id']} y el "
                      f"dry-run apunta a {destinos[0]}")
            else:
                clase, ev = "STILL_SAFE", f"main {destinos[0]} sigue siendo el unico"
            clases_l[clase] += 1
            g.write(json.dumps({"canonical_agency_id": e["canonical_agency_id"],
                                "clase": clase, "destino": destinos,
                                "evidencia": ev, "writes": False},
                               ensure_ascii=False) + "\n")

    print(f"\nvinculos revalidados: {len(enlaces)}")
    for c, k in clases_l.most_common():
        print(f"  {c:12} {k:5}")
    print(f"\nartefactos en {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

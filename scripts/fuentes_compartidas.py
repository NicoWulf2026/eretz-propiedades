#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Dos agencias con la MISMA url de fuente van a enumerar el mismo catalogo.

Solo lectura. No escribe en produccion, no cambia extractores, no cambia
huellas. `database_writes: 0`. Propone, no aplica.

Que encontro
------------
De las 3.113 agencias con fuente resoluble, **25 urls estan compartidas por 61
agencias**. No es lo mismo que compartir HOST: `buscainmueble.com` aparece en
70 agencias y cada una tiene su propia url dentro del host, que es como
funciona un SaaS y esta bien. El problema es la url IDENTICA.

Las peores:

    10 agencias  https://cir.org.ar/socios
     4 agencias  https://www.remax-urbana.com.ar
     3 agencias  https://indice-inmobiliario.com/buscar
     2 agencias  https://www.cpmclz.com.ar/colegiados
     ... y 21 mas

`cir.org.ar/socios` es la lista de socios de un colegio inmobiliario. No es la
web de ninguna de esas diez agencias, y certificarlas contra ella les
atribuiria a las diez el mismo inventario -o el mismo cero-.

El dano hasta hoy es casi nulo y conviene decirlo con el numero: **24 de las 25
no tienen ninguna certificada ni una sola propiedad**, porque la cola todavia
no llego. La unica con inventario es `cosapropiedades.com`, con 478
propiedades y dos agencias de nombre casi identico -`cosa propiedades` y
`cas as propiedades`-, que probablemente sean la misma cargada dos veces.

O sea: esto no es un incendio, es una mina. Y desactivarla antes de pisarla
cuesta muchisimo menos que separar inventario mezclado despues.

Por que no lo ve el detector que ya existe
------------------------------------------
`identity_collisions` del certificador mide colisiones DENTRO de una corrida
-cuantas urls colapsan en un mismo `hash_dedup`-. Es otra pregunta. Nadie
estaba mirando si dos agencias distintas apuntan al mismo lugar.

Uso:
    python scripts/fuentes_compartidas.py
    python scripts/fuentes_compartidas.py --solo DIRECTORIO_INSTITUCIONAL
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

V2 = Path(r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
PLATAFORMAS = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
SALIDA = CERT / "ERETZ_FUENTES_COMPARTIDAS.json"

# Rutas de una entidad que AGRUPA inmobiliarias: colegios, camaras, portales
# con padron. Ninguna es la web de ninguno de sus miembros.
RE_DIRECTORIO = re.compile(
    r"/(socios?|socias?|colegiados?|miembros?|padron|matriculados?|"
    r"asociados?|infractores?|comercializadores?|inmobiliarias?|"
    r"agencias?|directorio)\b", re.I)

# Buscadores: la pagina de resultados de un portal, que sirve el inventario de
# todos sus anunciantes.
RE_BUSCADOR = re.compile(r"/(buscar|busqueda|search|resultados|listado)\b",
                         re.I)

# Prefijos de red/franquicia. Dos oficinas de la misma red compartiendo el
# sitio de la red no es un error de identidad del mismo tipo: es una decision
# comercial de ellos, y nosotros igual no podemos atribuirle a una oficina el
# inventario de otra.
REDES = ("re max", "remax", "century 21", "century21", "coldwell banker",
         "keller williams", "century")


def _jsonl(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            yield json.loads(linea)
        except ValueError:
            continue


def nombre_de(clave: str) -> str:
    return clave.split(":", 1)[-1].strip().lower()


def normalizar(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()


def clasificar(url: str, agencias: list[str]) -> str:
    """Que clase de coincidencia es. El orden de las reglas importa.

    Primero lo que NO es fuente de nadie -un directorio institucional, un
    buscador de portal-, porque eso vale para todas las agencias del grupo.
    Recien despues se mira la relacion entre ellas.
    """
    ruta = urllib.parse.urlparse(url).path
    if RE_DIRECTORIO.search(ruta):
        return "DIRECTORIO_INSTITUCIONAL"
    if RE_BUSCADOR.search(ruta):
        return "BUSCADOR_DE_PORTAL"
    nombres = [nombre_de(a) for a in agencias]
    if all(any(n.startswith(red) or red in n for red in REDES) for n in nombres):
        return "OFICINAS_DE_RED"
    if len(nombres) == 2 and difflib.SequenceMatcher(
            None, nombres[0], nombres[1]).ratio() >= 0.75:
        return "POSIBLE_DUPLICADO"
    return "SIN_CLASIFICAR"


def recomendacion(clase: str) -> str:
    return {
        "DIRECTORIO_INSTITUCIONAL":
            "no es la web de ninguna: sacarla como fuente de las dos o mas",
        "BUSCADOR_DE_PORTAL":
            "es el buscador de un portal: sirve inventario ajeno, sacarla",
        "OFICINAS_DE_RED":
            "una sola oficina puede quedarse el sitio; las demas necesitan "
            "su propia url o quedan sin fuente declarada",
        "POSIBLE_DUPLICADO":
            "revisar si son la misma agencia cargada dos veces antes de tocar "
            "la fuente: el arreglo puede ser de identidad y no de fuente",
        "SIN_CLASIFICAR":
            "mirar a mano: no hay patron reconocible",
    }[clase]


def colisiones() -> list[dict[str, Any]]:
    from scripts.agency_certifier import load_catalog, resolve_identity
    from ledger_de_certificacion import vigentes_por_agencia
    catalogo = load_catalog(V2, DATOS, PLATAFORMAS)
    vigentes, _ = vigentes_por_agencia(
        CERT / "AGENCY_CERTIFICATION_RESULTS.jsonl")
    por_url: dict[str, list[str]] = collections.defaultdict(list)
    for clave, registro in catalogo.items():
        url = (resolve_identity(registro, clave) or {}).get("official_url")
        if url:
            por_url[normalizar(url)].append(clave)
    salida = []
    for url, agencias in por_url.items():
        if len(agencias) < 2:
            continue
        agencias = sorted(agencias)
        certificadas, propiedades = 0, 0
        for agencia in agencias:
            resultado = vigentes.get(agencia) or {}
            if str(resultado.get("status") or "").startswith("CERTIFIED"):
                certificadas += 1
            propiedades += int((resultado.get("enumeration_audit") or {}
                                ).get("enumerated") or 0)
        clase = clasificar(url, agencias)
        salida.append({"url": url, "agencias": agencias,
                       "cuantas": len(agencias), "clase": clase,
                       "certificadas": certificadas,
                       "propiedades": propiedades,
                       "recomendacion": recomendacion(clase)})
    return sorted(salida, key=lambda x: (-x["propiedades"], -x["cuantas"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", default="")
    args = ap.parse_args()

    grupos = colisiones()
    if args.solo:
        grupos = [g for g in grupos if g["clase"] == args.solo]
    if not grupos:
        print("no hay dos agencias compartiendo la misma url de fuente")
        return 0

    print(f"urls compartidas por 2 o mas agencias: {len(grupos)}")
    print(f"agencias involucradas: {sum(g['cuantas'] for g in grupos)}\n")
    print(f"  {'CLASE':26} {'AG':>3} {'CERT':>4} {'PROPS':>6}  URL")
    print(f"  {'-' * 26} {'-' * 3} {'-' * 4} {'-' * 6}  {'-' * 44}")
    for g in grupos:
        print(f"  {g['clase'][:26]:26} {g['cuantas']:>3} "
              f"{g['certificadas']:>4} {g['propiedades']:>6}  {g['url'][:44]}")

    print()
    for clase, cuantos in collections.Counter(
            g["clase"] for g in grupos).most_common():
        print(f"  {clase:26} {cuantos:>3} grupos  -> {recomendacion(clase)}")

    con_dano = [g for g in grupos if g["propiedades"] or g["certificadas"]]
    print(f"\n  grupos con inventario o certificacion YA atribuidos: "
          f"{len(con_dano)} de {len(grupos)}")
    for g in con_dano:
        print(f"     {g['url'][:52]:52} {g['propiedades']} propiedades")
    if not con_dano:
        print("     ninguno: la cola todavia no llego. Es una mina, no un "
              "incendio.")

    SALIDA.write_text(json.dumps(
        {"cuando": time.strftime("%Y-%m-%dT%H:%M:%S"), "grupos": grupos,
         "database_writes": 0}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nartefacto: {SALIDA}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

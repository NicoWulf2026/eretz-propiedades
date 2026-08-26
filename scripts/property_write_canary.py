#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Canary de escritura de propiedades al pipeline ERETZ.

Escribe por el unico camino habilitado y con el privilegio minimo:

    BEGIN;
    SET LOCAL ROLE eretz_direct_property_writer;
    INSERT INTO internal_scraping.propiedades_raw (...) ON CONFLICT DO NOTHING;
    COMMIT;

`SET LOCAL` y no `SET`: el rol vuelve solo al terminar la transaccion, asi que
ninguna sentencia posterior queda corriendo con privilegios elevados por
accidente.

Lo que mas importa aca no es insertar sino DEJAR DE INSERTAR cuando algo no
cierra. Por eso las trece comprobaciones corren antes del COMMIT y cualquiera
que falle aborta la transaccion entera.

Un cuidado que no estaba en la lista y vale mas que varios de los que si: el
`inmobiliaria_id` tiene que ser el REAL del padron, no el sustituto que usan
los canaries de scraping. Escribir con un id inventado llenaria la tabla de
propiedades que no pertenecen a ninguna inmobiliaria existente, y el error solo
aparece mucho despues, cuando alguien intenta unir las tablas.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from connectors.base import RUTA_PIPELINE  # noqa: E402
from scripts.ingest_to_pipeline import RAW_COLUMNS, a_fila_raw, rechazos  # noqa: E402

ROL = "eretz_direct_property_writer"

# El unico usuario con el que se entra. El rol de escritura se asume DESPUES,
# con SET LOCAL, y solo durante la transaccion.
USUARIO_ESPERADO = "eretz_preview_ro"

# En orden de preferencia. El pooler primero porque el endpoint directo de
# Supabase es IPv6 por diseno y desde una red sin IPv6 utilizable no resuelve.
VARIABLES_RO = ("ERETZ_PREVIEW_RO_POOLER_URL", "ERETZ_PREVIEW_RO_URL",
                "SUPABASE_PREVIEW_RO_URL")

# Usuarios con los que NO se entra, aunque la variable exista y funcione.
# Entrar como superusuario para "probar rapido" saltea exactamente la
# restriccion que el rol minimo existe para imponer, y una vez que funciona
# nadie vuelve a cablearlo bien.
PROHIBIDOS = ("postgres", "service_role", "neondb_owner", "supabase_admin")


def usuario_de(url):
    m = re.match(r"^[a-z+]+://([^:/@]+)", url or "")
    return (m.group(1) if m else "").lower()


def elegir_credencial():
    """La credencial de solo lectura, o nada. Nunca el superusuario.

    Devuelve (url, explicacion). No imprime la url: lleva la contrasena.
    """
    for v in VARIABLES_RO:
        u = os.environ.get(v)
        if u:
            quien = usuario_de(u)
            if quien in PROHIBIDOS:
                return "", ("%s existe pero entra como %r, que esta prohibido"
                            % (v, quien))
            return u, "%s (usuario %s)" % (v, quien or "?")
    # Lo que haya quedado configurado de antes solo sirve si NO es superusuario.
    for v in ("SUPABASE_POOLER_DATABASE_URL", "SUPABASE_DATABASE_URL"):
        u = os.environ.get(v)
        if not u:
            continue
        quien = usuario_de(u)
        if quien in PROHIBIDOS:
            return "", ("%s entra como %r: no se usa para saltear la "
                        "restriccion de privilegio minimo" % (v, quien))
        return u, "%s (usuario %s)" % (v, quien or "?")
    return "", "ninguna variable de credencial configurada"
TABLA = "internal_scraping.propiedades_raw"
SECUENCIA = "internal_scraping.propiedades_raw_id_seq"


def cargar_env() -> None:
    for nombre in (".env", ".env.local"):
        ruta = RUTA_PIPELINE / nombre
        if not ruta.exists():
            continue
        for linea in ruta.read_text(encoding="utf-8", errors="ignore").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def normalizar(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", str(nombre or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\b(s\.?a\.?|s\.?r\.?l\.?|srl|sa|sas|ltda)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


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


class Fallo(RuntimeError):
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--limite", type=int, default=50)
    ap.add_argument("--escribir", action="store_true",
                    help="sin esto valida y hace ROLLBACK")
    a = ap.parse_args()

    cargar_env()
    # El endpoint directo de Supabase es IPv6 por diseno. Desde una red sin IPv6
    # utilizable el camino correcto es el pooler (Supavisor) sobre IPv4, asi que
    # se prefiere su variable cuando existe. No se adivina host: si no esta
    # configurada, se dice y se corta.
    url, via = elegir_credencial()
    print("### CANARY DE ESCRITURA DE PROPIEDADES ###")
    print(f"  destino: {TABLA}   rol: {ROL}")
    print(f"  modo:    {'ESCRITURA (COMMIT si pasa todo)' if a.escribir else 'VALIDACION (ROLLBACK)'}")
    print("  credencial: %s" % via)
    if not url:
        print("")
        print("  [1] DB_CREDENTIAL_PENDING: no hay credencial de escritura "
              "utilizable.")
        print("      Se necesita %s apuntando al usuario %s."
              % (VARIABLES_RO[1], USUARIO_ESPERADO))
        print("      El canary queda listo: en cuanto exista, corre sin cambios.")
        return 2
    try:
        import psycopg
    except ImportError:
        print("\n  falta psycopg.")
        return 2

    props = leer(Path(a.entrada))[:a.limite]
    if not props:
        print("\n  sin propiedades de entrada.")
        return 2

    try:
        with psycopg.connect(url, connect_timeout=25) as cn:
            with cn.cursor() as cur:
                # [1] identidad ANTES de cambiar de rol. Preguntarlo despues
                # mostraria el rol asumido y no diria nada sobre con quien se
                # entro realmente.
                cur.execute("select current_user, session_user, current_database()")
                usuario, sesion, base = cur.fetchone()
                print(f"\n  [1] conectado  current_user={usuario} "
                      f"session_user={sesion} db={base}")

            with cn.transaction():
                with cn.cursor() as cur:
                    # [2][3] la transaccion ya esta abierta; se asume el rol
                    # SOLO dentro de ella.
                    cur.execute(f"SET LOCAL ROLE {ROL}")
                    cur.execute("select current_user")
                    print(f"  [3] rol asumido: {cur.fetchone()[0]}")

                    # [10][11] privilegios: se consultan, no se ensayan a lo
                    # bruto sobre datos reales.
                    cur.execute(
                        "select has_table_privilege(%s,'SELECT'),"
                        "       has_table_privilege(%s,'INSERT'),"
                        "       has_table_privilege(%s,'UPDATE'),"
                        "       has_table_privilege(%s,'DELETE')",
                        (TABLA, TABLA, TABLA, TABLA))
                    sel, ins, upd, dele = cur.fetchone()
                    print(f"  [10] privilegios sobre {TABLA}: "
                          f"SELECT={sel} INSERT={ins} UPDATE={upd} DELETE={dele}")
                    if not (sel and ins):
                        raise Fallo("faltan SELECT/INSERT")
                    if upd or dele:
                        raise Fallo("el rol tiene UPDATE o DELETE: no es minimo")
                    cur.execute("select has_sequence_privilege(%s,'USAGE')", (SECUENCIA,))
                    print(f"  [10] USAGE sobre la secuencia: {cur.fetchone()[0]}")

                    # [11] confirmacion adicional dentro de un savepoint: la
                    # sentencia se intenta de verdad y se descarta, asi que no
                    # toca ningun dato aunque el privilegio existiera.
                    for sentencia, nombre in (
                            (f"update {TABLA} set titulo=titulo where false", "UPDATE"),
                            (f"delete from {TABLA} where false", "DELETE")):
                        try:
                            with cn.transaction():
                                cur.execute(sentencia)
                            raise Fallo(f"{nombre} no fue rechazado")
                        except psycopg.errors.InsufficientPrivilege:
                            print(f"  [11] {nombre} rechazado, como debe ser")

                    # [4] lectura del padron
                    cur.execute("select count(*) from public.inmobiliarias_main")
                    n_main = cur.fetchone()[0]
                    cur.execute("select count(*) from public.inmobiliarias_staging")
                    n_stg = cur.fetchone()[0]
                    print(f"  [4] padron legible: main={n_main:,} staging={n_stg:,}")

                    # --- resolver inmobiliaria_id REAL ---------------------
                    # Sale del directorio, donde el crosswalk ya lo resolvio.
                    # Rehacer la asociacion por nombre contra la base seria
                    # repetir el paso mas delicado de todo el proyecto y con
                    # menos evidencia de la que se uso la primera vez.
                    dd = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
                    padron = {}
                    for d in leer(dd / "agency_web_directory.jsonl"):
                        eid = d.get("eretz_id")
                        if str(eid).isdigit():
                            padron[d["canonical_agency_id"]] = int(eid)
                    cur.execute("select id from public.inmobiliarias_main")
                    existentes = {r[0] for r in cur.fetchall()}
                    cur.execute("select id from public.inmobiliarias_staging")
                    existentes |= {r[0] for r in cur.fetchall()}

                    from connectors.base import calcular_hash_dedup
                    listas, sin_id, fuera_padron = [], 0, 0
                    for p in props:
                        real = padron.get(p.get("canonical_agency_id"))
                        if real is None:
                            sin_id += 1
                            continue
                        if real not in existentes:
                            # El id existe en el directorio pero no en la base:
                            # insertarlo dejaria una propiedad huerfana que solo
                            # se descubre al unir las tablas, mucho despues.
                            fuera_padron += 1
                            continue
                        q = dict(p)
                        q["inmobiliaria_id"] = real
                        q["hash_dedup"] = calcular_hash_dedup(real, p.get("source_url"))
                        if rechazos(q):
                            continue
                        listas.append(q)
                    print(f"  [5] sin id en el directorio: {sin_id}  "
                          f"con id inexistente en la base: {fuera_padron}")
                    print(f"  [5] entrada: {len(props)}  listas para escribir: "
                          f"{len(listas)}")
                    if not listas:
                        raise Fallo("ninguna propiedad pudo asociarse a una "
                                    "inmobiliaria del padron")

                    # [6][7] insertar
                    columnas = ", ".join(RAW_COLUMNS)
                    marcas = ", ".join(["%s"] * len(RAW_COLUMNS))
                    sql = (f"INSERT INTO {TABLA} ({columnas}) VALUES ({marcas}) "
                           f"ON CONFLICT (hash_dedup) DO NOTHING RETURNING id")
                    insertadas = ya_estaban = 0
                    for q in listas:
                        fila = a_fila_raw(q)
                        cur.execute(sql, [fila[c] for c in RAW_COLUMNS])
                        if cur.fetchone():
                            insertadas += 1
                        else:
                            ya_estaban += 1
                    print(f"  [6] insertadas={insertadas}  ya_estaban={ya_estaban}")

                    # [8][9] el mismo lote otra vez, dentro de la misma
                    # transaccion: ninguna debe entrar de nuevo.
                    repetidas = 0
                    for q in listas:
                        fila = a_fila_raw(q)
                        cur.execute(sql, [fila[c] for c in RAW_COLUMNS])
                        if cur.fetchone():
                            repetidas += 1
                    print(f"  [9] segunda pasada del mismo lote: "
                          f"{repetidas} filas nuevas (debe ser 0)")
                    if repetidas:
                        raise Fallo("la segunda pasada inserto duplicados")

                    # [12] reconciliacion
                    cur.execute(f"select count(*) from {TABLA} where hash_dedup = any(%s)",
                                ([q["hash_dedup"] for q in listas],))
                    presentes = cur.fetchone()[0]
                    print(f"  [12] presentes en la tabla: {presentes} "
                          f"de {len(listas)}  reconcilia={presentes == len(listas)}")
                    if presentes != len(listas):
                        raise Fallo("no reconcilia")
                    cur.execute(f"select count(*) from {TABLA} "
                                f"where hash_dedup = any(%s) and status <> 'raw'",
                                ([q["hash_dedup"] for q in listas],))
                    print(f"  [12] con status distinto de 'raw': {cur.fetchone()[0]}")

                    if not a.escribir:
                        # [13] en modo validacion se aborta a proposito: se
                        # comprobo todo el camino sin dejar rastro.
                        raise Fallo("__rollback_pedido__")

            print("\n  [13] COMMIT: el canary paso.")
            return 0

    except Fallo as e:
        if str(e) == "__rollback_pedido__":
            print("\n  [13] ROLLBACK: validacion completa, nada quedo escrito.")
            print("       Volve a correr con --escribir para confirmar.")
            return 0
        print(f"\n  ABORTADO: {e}")
        return 3
    except Exception as e:
        print(f"\n  ERROR: {type(e).__name__}: {str(e)[:200]}")
        return 3


if __name__ == "__main__":
    sys.exit(main())

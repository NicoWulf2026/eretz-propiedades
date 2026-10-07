"""Ensayo de backup/restore contra el backup Neon (PostgreSQL 17) en SOLO LECTURA, restore LOCAL desechable.

remoto (read-only, via pg_ro2.py) --pg_dump 17 -Fc--> archivo --sha256/TOC--> cluster local PG17 desechable
--pg_restore--> base 'restaurada' --> comparar con el remoto: conteos y md5 por tabla, esquema (pg_dump -s),
funciones (md5 de la definicion) y matriz de permisos --> dano deliberado --> recovery desde el mismo archivo.
Nunca escribe en el remoto: toda consulta remota pasa por pg_solo_lectura.py (default_transaction_read_only=on).

Corrida limpia 07-10 (Neon, tras el corte de luz): dump 65,9 MB en 214,8 s, restore 54,1 s sin errores, 9/9 tablas
identicas (conteo + md5 con la sesion fijada en UTC), esquema/funciones/permisos identicos, dano deliberado
(propiedades_raw 80.054 -> 64.927) y recovery identico al origen. writes remotos: 0.

    python scripts/ensayo_backup_remoto.py                                   # contra el backup Neon
    ERETZ_ENSAYO_ORIGEN=SUPABASE_DATABASE_URL python scripts/ensayo_backup_remoto.py   # produccion, con credencial valida
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1])]
from scripts.rutas_de_datos import dato  # noqa: E402

PY = sys.executable
WRAP = str(Path(__file__).with_name("pg_solo_lectura.py"))
# Origen remoto: el backup Neon (ensayo). Con credencial productiva valida: SUPABASE_DATABASE_URL.
VAR = os.environ.get("ERETZ_ENSAYO_ORIGEN", "NEON_DB_URL_BACKUP")
BIN = Path(str(dato("_herramientas", "pgsql17", "bin")))
BASE = Path(str(dato("_b_scratch", "ensayo_backup_remoto", "pg_local")))
PORT = "55433"
LOCAL = dict(os.environ, PGHOST="localhost", PGPORT=PORT, PGUSER="eretz_local")
INF = {"origen": "Neon backup (PostgreSQL 17, solo lectura)", "writes_remotos": 0, "pasos": []}


def paso(nombre, **d):
    INF["pasos"].append({"paso": nombre, **d})
    print(nombre, json.dumps(d, ensure_ascii=False, default=str)[:400], flush=True)


def remoto(herr, *args, directo=False):
    extra = ["--directo"] if directo else []
    r = subprocess.run([PY, WRAP, VAR, "pgsql17", herr, *extra, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"remoto {herr}: {r.stderr[-600:]}")
    return r.stdout


def local(herr, *args, ok=True):
    r = subprocess.run([str(BIN / herr), *args], env=LOCAL, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    if ok and r.returncode != 0:
        raise RuntimeError(f"local {herr}: {r.stderr[-800:]}")
    return r.stdout


def q_remoto(sql, directo):
    return remoto("psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql, directo=directo).strip()


def q_local(db, sql):
    return local("psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", db, "-c", sql).strip()


TABLAS = ("select quote_ident(n.nspname)||'.'||quote_ident(c.relname) from pg_class c join pg_namespace n on n.oid=c.relnamespace "
          "where c.relkind in ('r','p') and n.nspname not in ('pg_catalog','information_schema') and n.nspname !~ '^pg_' "
          "order by 1")
FUNCIONES = ("select n.nspname||'.'||p.proname||'('||pg_get_function_identity_arguments(p.oid)||')|'||md5(pg_get_functiondef(p.oid)) "
             "from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname not in ('pg_catalog','information_schema') "
             "and n.nspname !~ '^pg_' and p.prokind in ('f','p') order by 1")
PERMISOS = ("select grantee||'|'||table_schema||'.'||table_name||'|'||string_agg(privilege_type, ',' order by privilege_type) "
            "from information_schema.role_table_grants where table_schema not in ('pg_catalog','information_schema') "
            "group by grantee, table_schema, table_name order by 1")


# `x::text` depende de la sesion: timestamptz sale en la zona horaria del servidor (Neon UTC, el cluster
# local America/Buenos_Aires) y los float con extra_float_digits. Sin fijarlo, la misma fila da otro md5.
SESION = ("SET TimeZone TO 'UTC'; SET DateStyle TO 'ISO, YMD'; SET IntervalStyle TO 'postgres'; "
          "SET extra_float_digits TO 3; SET bytea_output TO 'hex'; ")


def huella_tablas(q):
    tablas = [t for t in q(TABLAS).splitlines() if t]
    fuera = {}
    for t in tablas:
        n = q(f"select count(*) from {t}")
        h = q(SESION + f"select md5(coalesce(string_agg(md5(x::text), '' order by md5(x::text)), '')) from {t} x")
        fuera[t] = (int(n), h)
    return fuera


def diferencias(a, b):
    por_conteo = sorted(t for t in a if a[t][0] != (b.get(t) or (None,))[0])
    por_contenido = sorted(t for t in a if t not in por_conteo and a[t] != b.get(t))
    return por_conteo, por_contenido


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def esquema_normalizado(texto):
    return "\n".join(l for l in texto.splitlines()
                     if l and not l.startswith("--") and not l.startswith("\\restrict") and not l.startswith("\\unrestrict")
                     and "SET " not in l[:4])


# ---------------------------------------------------------------- remoto: conexion y dump
directo = False
try:
    q_remoto("select 1", False)
    remoto("pg_dump", "--schema-only", "-f", os.devnull)
except RuntimeError as e:
    paso("pooler no sirve para pg_dump, se usa host directo", motivo=str(e)[-200:])
    directo = True
ro = q_remoto("select current_setting('transaction_read_only')||'|'||split_part(version(),' ',2)", directo)
paso("conexion remota de solo lectura", transaction_read_only=ro.split("|")[0], version=ro.split("|")[1], directo=directo)
if ro.split("|")[0] != "on":
    sys.exit("la sesion remota NO es de solo lectura: se aborta")

if BASE.exists():
    subprocess.run([str(BIN / "pg_ctl"), "-D", str(BASE / "data"), "stop", "-m", "fast"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)
dump = BASE / "neon_backup.dump"
t0 = time.time()
remoto("pg_dump", "-Fc", "-Z", "6", "-f", str(dump), directo=directo)
paso("BACKUP pg_dump -Fc (solo lectura)", bytes=dump.stat().st_size, segundos=round(time.time() - t0, 1), sha256=sha(dump))
remoto_tablas = huella_tablas(lambda s: q_remoto(s, directo))
remoto_funciones = q_remoto(FUNCIONES, directo)
remoto_permisos = q_remoto(PERMISOS, directo)
remoto_esquema = esquema_normalizado(remoto("pg_dump", "--schema-only", directo=directo))
roles = [r for r in q_remoto("select rolname from pg_roles where rolname !~ '^pg_' order by 1", directo).splitlines() if r]
paso("huella del origen remoto", tablas=len(remoto_tablas), filas=sum(n for n, _ in remoto_tablas.values()),
     funciones=len(remoto_funciones.splitlines()), permisos=len(remoto_permisos.splitlines()), roles=len(roles))

# ---------------------------------------------------------------- local: cluster desechable y restore
local("initdb", "-D", str(BASE / "data"), "-U", "eretz_local", "--auth=trust", "-E", "UTF8", "--locale=C")
r = subprocess.run([str(BIN / "pg_ctl"), "-D", str(BASE / "data"), "-l", str(BASE / "server.log"), "-w", "start",
                    "-o", f"-p {PORT} -c listen_addresses=localhost"], env=LOCAL,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if r.returncode != 0:
    sys.exit("pg_ctl start fallo")
try:
    toc = local("pg_restore", "-l", str(dump))
    paso("integridad del archivo (pg_restore -l)", entradas_toc=sum(1 for l in toc.splitlines() if l and not l.startswith(";")))
    for rol in roles:  # los roles no viajan en pg_dump: se crean para que permisos y dueños se puedan restaurar
        local("psql", "-X", "-q", "-d", "postgres", "-c", f'DO $$BEGIN CREATE ROLE "{rol}" NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END$$;')

    def restaurar():
        local("createdb", "-O", roles[0] if "neondb_owner" not in roles else "neondb_owner", "restaurada")
        t = time.time()
        r = subprocess.run([str(BIN / "pg_restore"), "-d", "restaurada", str(dump)], env=LOCAL,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        errores = [l for l in r.stderr.splitlines() if "error" in l.lower()]
        return round(time.time() - t, 1), errores

    segundos, errores = restaurar()
    loc = huella_tablas(lambda s: q_local("restaurada", s))
    por_conteo, por_contenido = diferencias(remoto_tablas, loc)
    distintas = por_conteo + por_contenido
    paso("RESTORE local", segundos=segundos, errores_de_restore=len(errores), ejemplos_error=errores[:3],
         filas_restauradas=sum(n for n, _ in loc.values()),
         tablas_identicas=len(remoto_tablas) - len(distintas), distintas_por_conteo=por_conteo,
         distintas_por_contenido=por_contenido)
    esquema_ok = esquema_normalizado(local("pg_dump", "--schema-only", "-d", "restaurada")) == remoto_esquema
    funciones_ok = q_local("restaurada", FUNCIONES) == remoto_funciones
    permisos_ok = q_local("restaurada", PERMISOS) == remoto_permisos
    paso("VALIDACION esquema / funciones (RPC) / permisos", esquema_identico=esquema_ok, funciones_identicas=funciones_ok,
         permisos_identicos=permisos_ok)

    mayor = max(remoto_tablas, key=lambda t: remoto_tablas[t][0])
    q_local("restaurada", f"delete from {mayor} where ctid in (select ctid from {mayor} tablesample system (20))")
    danada = huella_tablas(lambda s: q_local("restaurada", s))
    paso("dano deliberado", tabla=mayor, filas_antes=remoto_tablas[mayor][0], filas_despues=danada[mayor][0])
    local("dropdb", "restaurada")
    segundos2, errores2 = restaurar()
    rec = huella_tablas(lambda s: q_local("restaurada", s))
    paso("RECOVERY desde el backup", segundos=segundos2, identico_al_origen=rec == remoto_tablas,
         filas=sum(n for n, _ in rec.values()), diferencias=diferencias(remoto_tablas, rec),
         esquema_identico=esquema_normalizado(local("pg_dump", "--schema-only", "-d", "restaurada")) == remoto_esquema)
    INF["resultado"] = "OK" if (not distintas and rec == remoto_tablas and esquema_ok and funciones_ok and permisos_ok) else "REVISAR"
finally:
    subprocess.run([str(BIN / "pg_ctl"), "-D", str(BASE / "data"), "stop", "-m", "fast"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    paso("cluster local detenido")
    (BASE.parent / "ensayo_neon.json").write_text(json.dumps(INF, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("RESULTADO", INF.get("resultado"))

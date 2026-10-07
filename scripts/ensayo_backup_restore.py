"""Ensayo LOCAL y DESECHABLE de backup -> checksum -> conteos -> restore -> validacion -> recovery.

PostgreSQL 16.15 (binarios oficiales en _herramientas/pgsql16), cluster temporal en _b_scratch, puerto propio,
solo localhost, sin servicio. Esquema real (public.propiedades + migrations/property_safe_merge_audit.sql) cargado
con las filas de la snapshot servida (avisos publicos). NO toca produccion: no hay credencial en juego.

Primera corrida OK (07-10, sprint_rc2): 76.486 propiedades, pg_dump -Fc 30,8 MB en 12,9 s, restore 22 s identico
(conteo + md5 por tabla), RPC y permisos intactos; dano deliberado (10.926 filas borradas, precios alterados,
auditoria vaciada) y recovery desde el backup identico al origen.

    python scripts/ensayo_backup_restore.py   # informe en _b_scratch/ensayo_backup_restore/ensayo_backup_restore.json
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO), str(REPO / "scripts")]
from scripts.rutas_de_datos import dato  # noqa: E402

BIN = Path(str(dato("_herramientas", "pgsql16", "bin")))
BASE = Path(str(dato("_b_scratch", "ensayo_backup_restore", "pg_local")))
SNAP = Path(str(dato("ERETZ_API_CONTRACT", "ERETZ_API_SNAPSHOT.sqlite3")))
PORT = "55432"
ENV = dict(os.environ, PGHOST="localhost", PGPORT=PORT, PGUSER="eretz_local")
INFORME = {"motor": "PostgreSQL 16.15 local desechable", "production_connections": 0, "pasos": []}


def paso(nombre, **datos):
    INFORME["pasos"].append({"paso": nombre, **datos})
    print(nombre, json.dumps(datos, ensure_ascii=False, default=str)[:300], flush=True)


def corre(*args, entrada=None, ok=True):
    r = subprocess.run([str(BIN / args[0]), *args[1:]], env=ENV, capture_output=True, text=True,
                       input=entrada, encoding="utf-8", errors="replace")
    if ok and r.returncode != 0:
        raise SystemExit(f"{args[0]} fallo: {r.stderr[-800:]}")
    return r


def sql(db, consulta):
    return corre("psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-d", db, "-c", consulta).stdout.strip()


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def huellas(db):
    """Conteo y huella de contenido por tabla (md5 de las filas ordenadas)."""
    fuera = {}
    for t in ("public.inmobiliarias_main", "public.propiedades", "public.property_merge_audit"):
        n = int(sql(db, f"select count(*) from {t}"))
        h = sql(db, f"select md5(coalesce(string_agg(x::text, '|' order by x::text), '')) from {t} x")
        fuera[t] = {"filas": n, "md5": h}
    return fuera


if BASE.exists():
    corre("pg_ctl", "-D", str(BASE / "data"), "stop", "-m", "fast", ok=False)
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)
corre("initdb", "-D", str(BASE / "data"), "-U", "eretz_local", "--auth=trust", "-E", "UTF8", "--locale=C")
# En Windows el servidor hereda los pipes de stdout/stderr si se capturan y `run` no vuelve
# nunca: pg_ctl start va sin capturar (el servidor escribe en server.log).
r = subprocess.run([str(BIN / "pg_ctl"), "-D", str(BASE / "data"), "-l", str(BASE / "server.log"), "-w", "start",
                    "-o", f"-p {PORT} -c listen_addresses=localhost"], env=ENV,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if r.returncode != 0:
    raise SystemExit(f"pg_ctl start fallo ({r.returncode}); ver {BASE / 'server.log'}")
paso("cluster desechable arriba", puerto=PORT, datos=str(BASE / "data"))
try:
    corre("createdb", "origen")
    sql("origen", """
      CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;
      CREATE SCHEMA internal_scraping;
      CREATE TABLE public.inmobiliarias_main (id bigint PRIMARY KEY, nombre text);
      CREATE TABLE public.propiedades (
        id bigserial PRIMARY KEY, inmobiliaria_id integer REFERENCES public.inmobiliarias_main(id), url text,
        url_normalizada text, hash_dedup text NOT NULL UNIQUE, id_externo text, titulo text, descripcion text,
        precio numeric, moneda text, tipo_propiedad text, operacion text,
        ambientes integer, dormitorios integer, banos integer, superficie_total numeric, superficie_cubierta numeric,
        direccion text, barrio text, ciudad text, provincia text, pais text, latitud double precision,
        longitud double precision, imagenes text[], fuente_extraccion text,
        estado text, updated_at timestamptz DEFAULT now());""")
    corre("psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", "origen", "-f",
          str(REPO / "migrations" / "property_safe_merge_audit.sql"))
    # Datos: la snapshot servida (sprint_rc2), una agencia -> un id numerico local.
    con = sqlite3.connect(f"file:{SNAP.as_posix()}?mode=ro", uri=True)
    filas = con.execute("select id, agency_id, source_url, titulo, descripcion, operacion, tipo_propiedad, precio, "
                        "moneda, ambientes, dormitorios, banos, superficie_total, superficie_cubierta, latitud, "
                        "longitud, localidad, provincia, barrio from propiedades").fetchall()
    agencias = {a: i + 1 for i, a in enumerate(sorted({f[1] for f in filas}))}
    csv_ag = BASE / "agencias.tsv"; csv_p = BASE / "propiedades.tsv"

    def esc(v):
        if v is None:
            return r"\N"
        return str(v).replace("\\", "\\\\").replace("\t", " ").replace("\n", " ").replace("\r", " ")
    csv_ag.write_text("".join(f"{i}\t{esc(a)}\n" for a, i in agencias.items()), encoding="utf-8")
    with open(csv_p, "w", encoding="utf-8") as fh:
        for f in filas:
            fh.write("\t".join(esc(v) for v in (agencias[f[1]], f[2], f[0], f[3], f[4], f[7], f[8], f[6], f[5], f[9],
                                                 f[10], f[11], f[12], f[13], f[18], f[16], f[17], f[14], f[15],
                                                 "snapshot", "activa")) + "\n")
    corre("psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", "origen", "-c",
          f"\\copy public.inmobiliarias_main (id, nombre) from '{csv_ag.as_posix()}'")
    corre("psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", "origen", "-c",
          f"\\copy public.propiedades (inmobiliaria_id, url, hash_dedup, titulo, descripcion, precio, moneda, "
          f"tipo_propiedad, operacion, ambientes, dormitorios, banos, superficie_total, superficie_cubierta, barrio, "
          f"ciudad, provincia, latitud, longitud, fuente_extraccion, estado) from '{csv_p.as_posix()}'")
    # Un evento auditado real por el RPC, para que la auditoria tambien viaje en el backup.
    pid = sql("origen", "select id from public.propiedades order by id limit 1")
    fila = sql("origen", f"select row_to_json(p)::text from public.propiedades p where id={pid}")
    d = json.loads(fila)
    lit = lambda s: "'" + str(s).replace("'", "''") + "'"  # noqa: E731
    auditoria = json.dumps([{"field": "titulo", "old_value": d["titulo"], "new_value": "ensayo backup",
                             "decision": "ACCEPTED_SOURCE_CHANGE", "confidence": 1, "reason": "ensayo-backup-1"}])
    sql("origen", "select public.apply_property_safe_merge("
        f"{pid}, {d['inmobiliaria_id']}, {lit(d['url'])}, {lit(d['hash_dedup'])}, {lit('snapshot')}, "
        f"{lit(json.dumps({'titulo': 'ensayo backup'}))}::jsonb, {lit(d['inmobiliaria_id'])}, {lit('ensayo')}, "
        f"{lit(auditoria)}::jsonb)")
    antes = huellas("origen")
    paso("origen cargado", **{t: v["filas"] for t, v in antes.items()})

    dump = BASE / "eretz_backup.dump"
    t0 = time.time()
    corre("pg_dump", "-d", "origen", "-Fc", "-Z", "6", "-f", str(dump))
    paso("BACKUP pg_dump -Fc", bytes=dump.stat().st_size, segundos=round(time.time() - t0, 1), sha256=sha(dump))
    lista = corre("pg_restore", "-l", str(dump)).stdout
    paso("integridad del archivo (pg_restore -l)", entradas_toc=sum(1 for l in lista.splitlines() if l and not l.startswith(";")))

    corre("createdb", "restaurada")
    t0 = time.time()
    corre("pg_restore", "-d", "restaurada", "--exit-on-error", str(dump))
    despues = huellas("restaurada")
    paso("RESTORE en base nueva", segundos=round(time.time() - t0, 1),
         identica=despues == antes, **{t: v["filas"] for t, v in despues.items()})
    if despues != antes:
        raise SystemExit("VALIDACION FALLIDA: la restaurada no coincide con el origen")
    rpc = sql("restaurada", "select has_function_privilege('service_role', "
                            "'public.apply_property_safe_merge(bigint,bigint,text,text,text,jsonb,text,text,jsonb)','EXECUTE')")
    paso("VALIDACION funciones y permisos", rpc_execute_service_role=rpc)

    # Recovery: dano deliberado en la restaurada y vuelta atras desde el mismo backup.
    sql("restaurada", "delete from public.property_merge_audit; delete from public.propiedades where id % 7 = 0; "
                      "update public.propiedades set precio = 1 where id % 11 = 0")
    danada = huellas("restaurada")
    paso("dano deliberado", **{t: v["filas"] for t, v in danada.items()})
    corre("dropdb", "restaurada")
    corre("createdb", "restaurada")
    corre("pg_restore", "-d", "restaurada", "--exit-on-error", str(dump))
    recuperada = huellas("restaurada")
    paso("RECOVERY desde el backup", identica_al_origen=recuperada == antes,
         **{t: v["filas"] for t, v in recuperada.items()})
    INFORME["resultado"] = "OK" if recuperada == antes else "FALLA"
finally:
    corre("pg_ctl", "-D", str(BASE / "data"), "stop", "-m", "fast", ok=False)
    paso("cluster detenido")
    (BASE.parent / "ensayo_backup_restore.json").write_text(json.dumps(INFORME, ensure_ascii=False, indent=1, default=str),
                                                           encoding="utf-8")
print("RESULTADO", INFORME.get("resultado"))

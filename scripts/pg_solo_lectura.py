"""Herramienta de PostgreSQL contra una base REMOTA en SOLO LECTURA, sin exponer la credencial.

Uso: python scripts/pg_solo_lectura.py <VARIABLE_DEL_ENV> <pgsql16|pgsql17> <psql|pg_dump> [--directo] [args...]
Cuando exista una credencial productiva valida (READY #1): SUPABASE_DATABASE_URL + pgsql17 (produccion es PG17).
- La credencial existente se lee del .env legado y va SOLO al entorno del hijo (PGPASSWORD); nunca se imprime.
- Sesion forzada a solo lectura (default_transaction_read_only=on) y SSL obligatorio.
- --directo: para Neon, usa el host sin '-pooler' (pg_dump necesita sesion, no pgbouncer en modo transaccion).
- La salida se filtra: cualquier aparicion de la contrasena se reemplaza por ***.
"""
import os
import re
import subprocess
import sys
from urllib.parse import parse_qs, unquote, urlsplit

sys.path[:0] = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
from scripts.rutas_de_datos import dato  # noqa: E402

ENV = str(dato("eretz-propiedades", ".env"))
HERR = str(dato("_herramientas"))
PERMITIDAS = {"psql", "pg_dump"}
PERMITIDAS_VAR = {"NEON_DB_URL_BACKUP", "SUPABASE_DATABASE_URL"}

var, version, herramienta, *args = sys.argv[1:]
if var not in PERMITIDAS_VAR or herramienta not in PERMITIDAS or version not in ("pgsql16", "pgsql17"):
    sys.exit("uso no permitido")
directo = "--directo" in args
args = [a for a in args if a != "--directo"]
url = None
for linea in open(ENV, encoding="utf-8", errors="replace"):
    m = re.match(rf"\s*{var}\s*=\s*(.*)", linea)
    if m:
        url = m.group(1).strip().strip('"').strip("'")
if not url:
    sys.exit(f"BLOCKED_CREDENTIAL: no hay {var}")
u = urlsplit(url)
secreto = unquote(u.password or "")
host = u.hostname or ""
if directo:
    host = host.replace("-pooler", "")
q = parse_qs(u.query)
env = dict(os.environ, PGPASSWORD=secreto, PGHOST=host, PGPORT=str(u.port or 5432),
           PGUSER=unquote(u.username or ""), PGDATABASE=(u.path or "/postgres").lstrip("/") or "postgres",
           PGSSLMODE=(q.get("sslmode") or ["require"])[0], PGCONNECT_TIMEOUT="20",
           PGAPPNAME="eretz_backup_readonly", PGOPTIONS="-c default_transaction_read_only=on")
r = subprocess.run([os.path.join(HERR, version, "bin", herramienta + ".exe"), *args], env=env,
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
limpio = (lambda t: t.replace(secreto, "***")) if secreto else (lambda t: t)
sys.stdout.write(limpio(r.stdout))
sys.stderr.write(limpio(r.stderr))
sys.exit(r.returncode)

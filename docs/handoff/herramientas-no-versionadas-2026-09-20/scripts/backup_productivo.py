"""Backup productivo verificable, de solo lectura.

No hay `pg_dump` en esta maquina, asi que el respaldo se toma con `COPY ... TO
STDOUT`, que es exactamente lo mismo que hace `pg_dump --data-only` por dentro:
lee la tabla entera y la escribe tal cual, sin tocar nada.

Tres cosas lo hacen seguro:

  - la sesion se abre `default_transaction_read_only`, asi que aunque el script
    tuviera un error no podria escribir;
  - corre dentro de una transaccion REPEATABLE READ, asi que las dos tablas
    salen del MISMO instante y no de dos momentos distintos;
  - al terminar cuenta las lineas del archivo y las compara con el `count(*)`
    que declaro la base. Un dump que no se verifico no es un backup.

Se guarda comprimido y con el encabezado, para que se pueda restaurar con
`COPY ... FROM` sin adivinar el orden de las columnas.
"""
from __future__ import annotations

import gzip
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg

TABLAS = ("public.propiedades", "public.inmobiliarias_main")


def url_de_produccion() -> str:
    """La cadena de conexion, del entorno o del .env. Nunca se imprime."""
    if os.environ.get("SUPABASE_DATABASE_URL"):
        return os.environ["SUPABASE_DATABASE_URL"]
    env = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\.env")
    for linea in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.startswith("SUPABASE_DATABASE_URL="):
            return linea.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no encuentro SUPABASE_DATABASE_URL")


def main() -> int:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    destino.mkdir(parents=True, exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")

    with psycopg.connect(url_de_produccion(), autocommit=False) as cx:
        with cx.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")

        resumen = []
        for tabla in TABLAS:
            corto = tabla.split(".")[-1]
            archivo = destino / f"eretz_prod_{corto}_{sello}.csv.gz"

            with cx.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {tabla}")
                declaradas = cur.fetchone()[0]

            escritas = 0
            with gzip.open(archivo, "wb") as salida, cx.cursor() as cur:
                with cur.copy(
                    f"COPY (SELECT * FROM {tabla}) TO STDOUT "
                    "WITH (FORMAT csv, HEADER true)"
                ) as copia:
                    for bloque in copia:
                        salida.write(bloque)
                        escritas += bytes(bloque).count(b"\n")

            resumen.append((tabla, archivo, declaradas, escritas))
            print(f"{tabla}: {declaradas} filas declaradas -> {archivo.name}",
                  flush=True)

        cx.rollback()  # ni siquiera un commit vacio

    # Verificacion: se cuentan las lineas REALES del archivo, no las que
    # creimos escribir. El encabezado es una linea de mas, y los campos con
    # saltos de linea adentro rompen el conteo ingenuo, asi que se cuenta con
    # el lector de CSV.
    import csv
    print("\n--- verificacion ---")
    todo_bien = True
    for tabla, archivo, declaradas, _ in resumen:
        with gzip.open(archivo, "rt", encoding="utf-8", newline="") as f:
            filas = sum(1 for _ in csv.reader(f)) - 1  # menos el encabezado
        ok = filas == declaradas
        todo_bien &= ok
        print(f"{tabla}: base {declaradas} / archivo {filas} "
              f"-> {'COINCIDE' if ok else 'NO COINCIDE'}")
        print(f"   {archivo}  ({archivo.stat().st_size / 1e6:.1f} MB)")

    print("\nBACKUP VERIFICADO" if todo_bien else "\nBACKUP NO VERIFICADO")
    return 0 if todo_bien else 1


if __name__ == "__main__":
    raise SystemExit(main())

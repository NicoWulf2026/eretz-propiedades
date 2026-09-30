#!/usr/bin/env python
"""P18, SOLO LECTURA: ¿puede `eretz_preview_ro` asumir el rol escritor hoy?

Imprime UNA palabra: YES, NO o UNABLE_TO_VERIFY (con un motivo sin datos
sensibles). Nunca imprime la url, el usuario de conexion, contrasenas ni tokens.

- Lee la url de una variable de entorno (por defecto ERETZ_PREVIEW_RO_URL); nunca
  por argumento, para que no quede en el historial de la consola.
- La sesion se abre en modo READ ONLY y la unica sentencia es un SELECT sobre
  catalogos (pg_roles, pg_has_role). No escribe ni cambia roles.

    python scripts/cloud_bridge/p18_chequeo_lectura.py
    python scripts/cloud_bridge/p18_chequeo_lectura.py --variable OTRA_VARIABLE_RO
"""
from __future__ import annotations

import argparse
import os
import sys

CONSULTA = """
select
  exists(select 1 from pg_roles where rolname = 'eretz_preview_ro') as hay_ro,
  exists(select 1 from pg_roles where rolname = 'eretz_direct_property_writer') as hay_escritor,
  case when exists(select 1 from pg_roles where rolname = 'eretz_preview_ro')
        and exists(select 1 from pg_roles where rolname = 'eretz_direct_property_writer')
       then pg_has_role('eretz_preview_ro', 'eretz_direct_property_writer', 'MEMBER')
  end as puede_asumir
"""


def veredicto(fila: tuple | None) -> tuple[str, str]:
    """(YES|NO|UNABLE_TO_VERIFY, motivo) a partir de la fila de CONSULTA."""
    if not fila:
        return "UNABLE_TO_VERIFY", "sin respuesta"
    hay_ro, hay_escritor, puede = fila
    if not hay_ro:
        return "UNABLE_TO_VERIFY", "el rol eretz_preview_ro no existe en esta base"
    if not hay_escritor:
        return "NO", "el rol eretz_direct_property_writer no existe"
    return ("YES", "eretz_preview_ro es miembro del escritor") if puede else \
        ("NO", "eretz_preview_ro no es miembro del escritor")


def main(argv: list[str] | None = None, conectar=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variable", default="ERETZ_PREVIEW_RO_URL")
    args = ap.parse_args(argv)
    url = (os.environ.get(args.variable) or "").strip()
    if not url:
        print(f"UNABLE_TO_VERIFY: la variable {args.variable} no esta definida")
        return 2
    try:
        if conectar is None:
            import psycopg
            conectar = lambda u: psycopg.connect(u, connect_timeout=20)  # noqa: E731
        with conectar(url) as cn:
            cn.read_only = True
            with cn.cursor() as cur:
                cur.execute(CONSULTA)
                fila = cur.fetchone()
            cn.rollback()
    except Exception as exc:  # el tipo, nunca el mensaje: puede traer la url
        print(f"UNABLE_TO_VERIFY: {type(exc).__name__}")
        return 2
    resultado, motivo = veredicto(fila)
    print(f"{resultado}: {motivo}")
    return 0 if resultado != "UNABLE_TO_VERIFY" else 2


if __name__ == "__main__":
    sys.exit(main())

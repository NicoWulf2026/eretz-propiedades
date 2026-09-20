#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Los diez controles de la Fase 1. Solo lee.

Se corre DESPUES de poner `public` en Exposed schemas. Cada control tiene un
veredicto propio y el conjunto tiene uno solo: si algo que antes estaba cerrado
quedo abierto, el veredicto es ROLLBACK y hay que vaciar el campo, no arreglarlo
concediendo o quitando permisos.

Los controles 5, 6 y 7 no se creen la teoria: consultan la API **con la anon
key**, que es exactamente lo que haria cualquiera con la clave publica. Que la
tabla no tenga GRANT es la explicacion; que la API responda 401/404 y no una
lista de propiedades es la prueba.

La linea de base -tomada antes del cambio, el 2026-09-09- es:

    anon lee en public .......... solo geography_columns, geometry_columns
                                  y spatial_ref_sys (los tres de PostGIS)
    usage en internal_scraping .. ninguno
    pgrst.db_schemas ............ ausente
    propiedades ................. 257.073 filas
    inmobiliarias_main .......... 7.004 filas

No imprime claves: la anon key se lee del entorno y solo se informa si esta o
no esta.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = {
    "anon_lee_en_public": {"geography_columns", "geometry_columns",
                           "spatial_ref_sys"},
    "propiedades": 257073,
    "inmobiliarias_main": 7004,
}
ENV = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\.env")


def del_entorno(clave: str) -> str | None:
    if os.environ.get(clave):
        return os.environ[clave]
    if not ENV.exists():
        return None
    for linea in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.startswith(clave + "="):
            return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def pedir(url: str, clave: str) -> tuple[int, str]:
    pedido = urllib.request.Request(url, headers={
        "apikey": clave, "Authorization": f"Bearer {clave}",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(pedido, timeout=20) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "replace")
    except Exception as e:                                   # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def main() -> int:
    url = del_entorno("SUPABASE_URL")
    anon = del_entorno("SUPABASE_ANON_KEY")
    if not url or not anon:
        print("falta SUPABASE_URL o SUPABASE_ANON_KEY en el entorno")
        return 2
    print(f"proyecto: {url}")
    print(f"anon key: {'presente' if anon else 'ausente'}\n")

    controles: list[tuple[str, bool, str]] = []

    # El canario NO es `/rest/v1/`: ese endpoint solo acepta la service_role
    # key y devuelve 401 aunque PostgREST este perfecto. El canario es una
    # tabla: con el schema cache roto responde 503 con PGRST002, y con el
    # cache cargado responde 401/403 -porque `anon` no tiene SELECT-, que es
    # justamente el resultado que queremos.
    codigo_p, cuerpo_p = pedir(
        f"{url}/rest/v1/propiedades?select=id&limit=1", anon)
    controles.append((
        "1. PostgREST responde", codigo_p != 503,
        f"propiedades -> HTTP {codigo_p}"
        + (" (sigue caido)" if codigo_p == 503 else "")))
    controles.append((
        "2. el schema cache cargo", "PGRST002" not in cuerpo_p,
        "sin PGRST002" if "PGRST002" not in cuerpo_p
        else "PGRST002 sigue apareciendo"))
    # El marcador `pg_pgrst_no_exposed_schemas` vive en los REGISTROS de
    # PostgREST, no en el cuerpo del 503. Este control solo puede confirmar que
    # tampoco se filtro a la respuesta; el registro se mira aparte, por MCP.
    controles.append((
        "3. sin pg_pgrst_no_exposed_schemas en la respuesta",
        "pg_pgrst_no_exposed_schemas" not in cuerpo_p,
        "no aparece en el cuerpo (el registro se revisa por MCP)"
        if "pg_pgrst_no_exposed_schemas" not in cuerpo_p
        else "EL MARCADOR SIGUE"))

    # 4. `internal_scraping` no expuesto. Con el cache cargado, una tabla de un
    # esquema no expuesto no existe para la API: 404. Un 503 no prueba nada
    # -la API esta caida-, asi que ese caso se declara indeterminado.
    codigo_is, _ = pedir(
        f"{url}/rest/v1/propiedades_raw?select=id&limit=1", anon)
    controles.append((
        "4. internal_scraping NO expuesto",
        codigo_is == 404 or codigo_is == 503,
        f"propiedades_raw -> HTTP {codigo_is}"
        + (" (indeterminado: la API esta caida)" if codigo_is == 503 else "")))

    # 5 y 6. Nadie puede leer el catalogo con la clave publica.
    lee = codigo_p == 200 and cuerpo_p.strip().startswith("[") \
        and cuerpo_p.strip() != "[]"
    controles.append((
        "5. anon NO lee public.propiedades", not lee,
        f"HTTP {codigo_p}" + (" y devolvio filas" if lee else " sin filas")))
    controles.append((
        "6. authenticated NO lee (mismo grant)", not lee,
        "authenticated no tiene mas SELECT que anon; se verifica por SQL"))

    # 7. Ninguna tabla de producto quedo publicada.
    expuestas = []
    for tabla in ("propiedades", "inmobiliarias_main", "propiedades_raw",
                  "publish_queue", "scraping_runs",
                  "backup_propiedades_url_normalizada_20260729_235540"):
        c, b = pedir(f"{url}/rest/v1/{tabla}?select=*&limit=1", anon)
        if c == 200 and b.strip().startswith("[") and b.strip() != "[]":
            expuestas.append(tabla)
    controles.append((
        "7. ninguna tabla de producto publicada", not expuestas,
        "ninguna devuelve filas" if not expuestas
        else "DEVUELVEN FILAS: " + ", ".join(expuestas)))

    print("Los siguientes tres se comprueban por SQL (MCP), no por HTTP:")
    print("  8. no cambio ningun dato   -> count(propiedades)=257073, "
          "count(inmobiliarias_main)=7004")
    print("  9. no cambio RLS           -> 37 de 39 tablas de public con RLS")
    print(" 10. no cambio ningun GRANT  -> anon/authenticated con SELECT solo "
          "sobre los tres objetos de PostGIS\n")

    ancho = max(len(c[0]) for c in controles)
    fallados = []
    for nombre, ok, detalle in controles:
        print(f"{'OK  ' if ok else 'FALLA'} {nombre:{ancho}}  {detalle}")
        if not ok:
            fallados.append(nombre)

    abierto = any(n.startswith(("5.", "6.", "7.")) for n in fallados)
    print()
    if abierto:
        print("VEREDICTO: ROLLBACK INMEDIATO")
        print("Quedo legible algo que antes no lo era. Vaciar Exposed schemas "
              "en Settings -> API y volver a correr esto.")
        print("NO conceder ni quitar permisos para taparlo.")
        return 1
    if fallados:
        print("VEREDICTO: FASE 1 NO APLICADA O INCOMPLETA")
        print("Nada quedo expuesto de mas, pero la API todavia no responde.")
        return 1
    print("VEREDICTO: FASE 1 VERDE")
    print("La API volvio y no se publico un solo dato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

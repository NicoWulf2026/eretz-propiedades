#!/usr/bin/env python
"""Geocode propiedades_staging rows in Neon (Etapa 6.5).

This script ONLY uses INTERNAL_DB_URL (Neon). It never reads or writes Supabase.
It takes propiedades_staging rows with geocoding_status='pending', tries to
geocode them reusing the pure logic from scraper/geocoder.py, caches the result
in geocoding_results and updates propiedades_staging with latitud/longitud and
geocoding_status in ('done','failed','skipped').

Default mode is dry-run (no Nominatim calls, no writes). Pass --commit to persist.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# -----------------------------------------------------------------------------
# Importar SOLO logica pura desde scraper/geocoder.py (no se modifica ese archivo).
# Si algo falla, abortar con mensaje claro en vez de duplicar logica.
# -----------------------------------------------------------------------------
try:
    from scraper.geocoder import (  # type: ignore
        NominatimProvider,
        prepare_address_for_geocoding,
        build_query_variants,
        geocode_with_fallbacks,
        evaluate_city_bounds,
        is_coordinate_inside_argentina,
        classify_geocoding_quality,
    )
except Exception as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "No se pudo importar la logica de scraper/geocoder.py: "
        f"{type(exc).__name__}: {exc}. "
        "Verifica que el script se ejecute desde la raiz del repo y que "
        "scraper/geocoder.py + sus dependencias (requests, dotenv) esten disponibles."
    )


STAGING_SELECT_SQL = """
SELECT
  id,
  inmobiliaria_id,
  hash_dedup,
  titulo,
  direccion_normalizada,
  barrio,
  ciudad,
  provincia,
  pais,
  validation_score,
  geocoding_status,
  status
FROM public.propiedades_staging
WHERE geocoding_status = 'pending'
  AND status = 'staging'
ORDER BY validation_score DESC, id ASC
LIMIT %s
"""


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env() -> None:
    load_env_file(REPO_ROOT / ".env")
    load_env_file(REPO_ROOT / ".env.local")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def internal_db_config() -> str:
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not env_flag("USE_INTERNAL_DB", default=False):
        raise SystemExit("USE_INTERNAL_DB no esta en true; abortando para no usar una DB equivocada.")
    if not db_url:
        raise SystemExit("Falta INTERNAL_DB_URL; abortando.")
    return db_url


def connect_internal_db(db_url: str):
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Falta instalar psycopg/psycopg-binary para usar INTERNAL_DB_URL.") from exc
    return psycopg.connect(db_url, row_factory=dict_row)


def _jsonb(value: Any):
    from psycopg.types.json import Jsonb  # type: ignore

    return Jsonb(value)


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# -----------------------------------------------------------------------------
# Mapeo staging -> formato esperado por scraper/geocoder.py
# -----------------------------------------------------------------------------
def build_geocoder_row(staging: Dict[str, Any]) -> Dict[str, Any]:
    direccion = clean_text(staging.get("direccion_normalizada"))
    pais = clean_text(staging.get("pais")) or "Argentina"
    return {
        "propiedad_id": staging.get("id"),
        "direccion": direccion,
        "direccion_limpia": direccion,
        "direccion_geocoding_limpia": direccion,
        "titulo": clean_text(staging.get("titulo")),
        "barrio": clean_text(staging.get("barrio")),
        "ciudad_final": clean_text(staging.get("ciudad")),
        "ciudad": clean_text(staging.get("ciudad")),
        "provincia_final": clean_text(staging.get("provincia")),
        "provincia": clean_text(staging.get("provincia")),
        "pais": pais,
    }


def is_garbage_address(direccion: Optional[str]) -> bool:
    """True si la direccion claramente no vale la pena geocodificar."""
    text = clean_text(direccion)
    if not text:
        return True
    if len(text) < 5:
        return True
    if not any(ch.isdigit() for ch in text):
        return True
    return False


def fetch_staging_rows(cur, limit: int) -> List[Dict[str, Any]]:
    cur.execute(STAGING_SELECT_SQL, [limit])
    return [dict(row) for row in cur.fetchall()]


def geocoding_result_exists(cur, propiedad_id: Any, direccion_geocoding: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM public.geocoding_results
        WHERE propiedad_id = %s
          AND direccion_geocoding = %s
        LIMIT 1
        """,
        [propiedad_id, direccion_geocoding],
    )
    return cur.fetchone() is not None


def insert_geocoding_result(cur, payload: Dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO public.geocoding_results (
            propiedad_id,
            direccion_geocoding,
            latitud,
            longitud,
            precision_geocoding,
            proveedor,
            raw_response,
            status,
            error_message
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            payload.get("propiedad_id"),
            payload.get("direccion_geocoding"),
            payload.get("latitud"),
            payload.get("longitud"),
            payload.get("precision_geocoding"),
            payload.get("proveedor"),
            _jsonb(payload.get("raw_response")),
            payload.get("status"),
            payload.get("error_message"),
        ],
    )


def update_staging_geocoding(
    cur,
    staging_id: int,
    latitud: Optional[float],
    longitud: Optional[float],
    geocoding_status: str,
) -> None:
    cur.execute(
        """
        UPDATE public.propiedades_staging
        SET latitud = %s,
            longitud = %s,
            geocoding_status = %s
        WHERE id = %s
          AND geocoding_status = 'pending'
        """,
        [latitud, longitud, geocoding_status, staging_id],
    )


def coords_are_valid(
    lat: Any,
    lon: Any,
    ciudad: Any,
    provincia: Any,
    pais: Any,
) -> bool:
    lat_f = to_float(lat)
    lon_f = to_float(lon)
    if lat_f is None or lon_f is None:
        return False
    if not is_coordinate_inside_argentina(lat_f, lon_f):
        return False
    within_city, checked = evaluate_city_bounds(lat_f, lon_f, ciudad, provincia, pais)
    if checked and within_city is False:
        return False
    return True


def _augment_raw_response(raw_response: Any) -> Any:
    marker = {"inmocapital_source": "staging"}
    if isinstance(raw_response, dict):
        enriched = dict(raw_response)
        enriched["inmocapital_source"] = "staging"
        return enriched
    return {"inmocapital_source": "staging", "provider_response": raw_response, **marker}


def process_row_commit(
    cur,
    provider: "NominatimProvider",
    staging: Dict[str, Any],
) -> Tuple[str, int]:
    """Geocodifica una fila y persiste. Devuelve (resultado, requests_consumidos)."""
    staging_id = int(staging["id"])
    geo_row = build_geocoder_row(staging)
    ciudad = geo_row.get("ciudad")
    provincia = geo_row.get("provincia")
    pais = geo_row.get("pais")

    cur.execute("SAVEPOINT geocode_staging_row")
    try:
        # Anti-basura 1: direccion claramente inutil
        if is_garbage_address(geo_row.get("direccion")):
            update_staging_geocoding(cur, staging_id, None, None, "skipped")
            cur.execute("RELEASE SAVEPOINT geocode_staging_row")
            return "skipped", 0

        # Anti-basura 2: readiness de geocoder.py
        cleaning = prepare_address_for_geocoding(geo_row)
        if cleaning.readiness != "geocoding_ready_safe":
            update_staging_geocoding(cur, staging_id, None, None, "skipped")
            cur.execute("RELEASE SAVEPOINT geocode_staging_row")
            return "skipped", 0

        queries = build_query_variants(geo_row)
        if not queries:
            update_staging_geocoding(cur, staging_id, None, None, "skipped")
            cur.execute("RELEASE SAVEPOINT geocode_staging_row")
            return "skipped", 0

        result, attempted = geocode_with_fallbacks(provider, queries, geo_row)
        requests_used = len(attempted)
        direccion_geocoding = result.matched_query or queries[0]

        lat = result.latitud
        lon = result.longitud
        success = result.status == "success" and coords_are_valid(lat, lon, ciudad, provincia, pais)

        if success:
            final_status = "done"
            cache_status = "success"
            error_message = None
            store_lat = to_float(lat)
            store_lon = to_float(lon)
        else:
            final_status = "failed"
            cache_status = "error"
            error_message = result.error_message or "geocoding_sin_coordenadas_validas"
            store_lat = None
            store_lon = None

        # Cache en geocoding_results (sin duplicar)
        if not geocoding_result_exists(cur, staging_id, direccion_geocoding):
            insert_geocoding_result(
                cur,
                {
                    "propiedad_id": staging_id,
                    "direccion_geocoding": direccion_geocoding,
                    "latitud": store_lat,
                    "longitud": store_lon,
                    "precision_geocoding": result.precision_geocoding,
                    "proveedor": result.proveedor,
                    "raw_response": _augment_raw_response(result.raw_response),
                    "status": cache_status,
                    "error_message": error_message,
                },
            )

        update_staging_geocoding(cur, staging_id, store_lat, store_lon, final_status)
        cur.execute("RELEASE SAVEPOINT geocode_staging_row")
        return final_status, requests_used
    except Exception as exc:  # noqa: BLE001 - aislar fila, no abortar la corrida
        cur.execute("ROLLBACK TO SAVEPOINT geocode_staging_row")
        cur.execute("RELEASE SAVEPOINT geocode_staging_row")
        print(f"  staging_id={staging_id} | error_proceso={type(exc).__name__}: {exc}")
        return "failed", 0


def describe_dry_run_action(staging: Dict[str, Any]) -> Tuple[str, str]:
    """Devuelve (accion, readiness) sin llamar a Nominatim ni escribir."""
    geo_row = build_geocoder_row(staging)
    if is_garbage_address(geo_row.get("direccion")):
        return "skipped", "garbage_address"
    cleaning = prepare_address_for_geocoding(geo_row)
    if cleaning.readiness != "geocoding_ready_safe":
        return "skipped", cleaning.readiness
    queries = build_query_variants(geo_row)
    if not queries:
        return "skipped", "sin_query"
    return "probe", cleaning.readiness


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Geocodificar propiedades_staging en Neon (Etapa 6.5)"
    )
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de filas a leer")
    parser.add_argument("--max-requests", type=int, default=30, help="Tope de llamadas a Nominatim por corrida")
    parser.add_argument("--dry-run", action="store_true", help="Leer y mostrar acciones sin llamar Nominatim ni escribir")
    parser.add_argument("--commit", action="store_true", help="Geocodificar y persistir en Neon")
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.max_requests <= 0:
        raise SystemExit("--max-requests debe ser mayor a 0")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    db_url = internal_db_config()

    read_count = 0
    requests_used = 0
    results: Counter[str] = Counter()

    print("=" * 72)
    print("GEOCODE STAGING")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"limit={args.limit}")
    print(f"max_requests={args.max_requests}")
    print("target=internal_db")
    print("-" * 72)

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            rows = fetch_staging_rows(cur, args.limit)
            read_count = len(rows)

            if args.dry_run:
                provider = None
            else:
                provider = NominatimProvider()

            for staging in rows:
                staging_id = staging.get("id")
                titulo = clean_text(staging.get("titulo")) or "-"
                direccion = clean_text(staging.get("direccion_normalizada")) or "-"

                if args.dry_run:
                    action, readiness = describe_dry_run_action(staging)
                    results[action] += 1
                    print(
                        f"  staging_id={staging_id} | titulo={titulo[:60]} | "
                        f"direccion={direccion[:80]} | readiness={readiness} | accion={action}"
                    )
                    continue

                if requests_used >= args.max_requests:
                    print(
                        f"  staging_id={staging_id} | tope max_requests alcanzado "
                        f"({requests_used}/{args.max_requests}); se detiene el geocoding"
                    )
                    break

                action, used = process_row_commit(cur, provider, staging)
                requests_used += used
                results[action] += 1
                print(
                    f"  staging_id={staging_id} | titulo={titulo[:60]} | "
                    f"direccion={direccion[:80]} | resultado={action} | requests={used}"
                )

        if args.commit:
            conn.commit()
            final_action = "commit"
        else:
            conn.rollback()
            final_action = "rollback"

    print("-" * 72)
    print(f"filas_leidas={read_count}")
    print(f"done={results.get('done', 0)}")
    print(f"failed={results.get('failed', 0)}")
    print(f"skipped={results.get('skipped', 0)}")
    if args.dry_run:
        print(f"probe={results.get('probe', 0)}")
    print(f"requests_usados={requests_used}")
    print(f"accion_final={final_action}")
    print("=" * 72)


if __name__ == "__main__":
    main()

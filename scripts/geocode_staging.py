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
import re
import sys
from collections import Counter
from datetime import datetime
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

try:
    from scraper.scraper_propiedades import normalize_location_fields as pipeline_normalize_location_fields  # type: ignore
except Exception:
    pipeline_normalize_location_fields = None  # type: ignore


STAGING_SELECT_SQL = """
SELECT
  s.id,
  s.inmobiliaria_id,
  s.hash_dedup,
  s.titulo,
  s.url,
  s.direccion_normalizada,
  s.barrio,
  s.ciudad,
  s.provincia,
  s.pais,
  s.validation_score,
  s.geocoding_status,
  s.status
FROM public.propiedades_staging
WHERE s.geocoding_status = 'pending'
  AND s.status = 'staging'
ORDER BY s.validation_score DESC, s.id ASC
LIMIT %s
"""

STAGING_SELECT_COLUMNS = """
SELECT
  s.id,
  s.inmobiliaria_id,
  s.hash_dedup,
  s.titulo,
  s.url,
  s.direccion_normalizada,
  s.barrio,
  s.ciudad,
  s.provincia,
  s.pais,
  s.validation_score,
  s.geocoding_status,
  s.status
FROM public.propiedades_staging s
"""

SOURCE_FILTERS = {
    "captured_json": (
        "JOIN public.propiedades_raw r ON r.id = s.raw_id",
        "r.datos_extra->>'imported_by' = %s",
        "scripts/import_captured_props_to_neon.py",
    ),
}


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
    return psycopg.connect(
        db_url,
        row_factory=dict_row,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=30,
    )


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
PROPERTY_TYPE_PREFIX_RE = re.compile(
    r"^(?:"
    r"casa(?:\s+(?:con\s+local|para\s+2\s+familias|ph))?|"
    r"departamento(?:\s+tipo\s+casa)?|terreno(?:\s+industrial)?|local(?:\s+con\s+vivienda)?|"
    r"cochera|fondo\s+comercio|galp[oó]n(?:\s+con\s+vivienda)?|duplex|ph|oficina|"
    r"campo|quinta|chacra|lote|semipiso|monoambiente|fracci[oó]n|vivienda\s+en\s+blocks"
    r")\s+(?:en\s+)?(?:venta|alquiler|alquiler\s+temporario)\s+en\s+",
    re.IGNORECASE,
)


def normalize_address_for_geocoding(value: Optional[str]) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    text = PROPERTY_TYPE_PREFIX_RE.sub("", text).strip(" -,.")
    text = re.sub(
        r"^en\s+(?:venta|alquiler|alquiler\s+temporario)\s+en\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def build_geocoder_row(staging: Dict[str, Any]) -> Dict[str, Any]:
    direccion = normalize_address_for_geocoding(staging.get("direccion_normalizada"))
    ciudad = clean_text(staging.get("ciudad"))
    provincia = clean_text(staging.get("provincia"))
    if callable(pipeline_normalize_location_fields):
        try:
            normalized = pipeline_normalize_location_fields(
                staging.get("titulo"),
                direccion,
                staging.get("barrio"),
                ciudad,
                provincia,
                staging.get("pais") or "Argentina",
                staging.get("url"),
                None,
            )
        except Exception:
            normalized = None
        if isinstance(normalized, dict) and normalized.get("location_normalized"):
            ciudad = clean_text(normalized.get("ciudad")) or ciudad
            provincia = clean_text(normalized.get("provincia")) or provincia
    pais = clean_text(staging.get("pais")) or "Argentina"
    return {
        "propiedad_id": staging.get("id"),
        "direccion": direccion,
        "direccion_limpia": direccion,
        "direccion_geocoding_limpia": direccion,
        "titulo": clean_text(staging.get("titulo")),
        "barrio": clean_text(staging.get("barrio")),
        "ciudad_final": ciudad,
        "ciudad": ciudad,
        "provincia_final": provincia,
        "provincia": provincia,
        "pais": pais,
    }


def is_garbage_address(direccion: Optional[str]) -> bool:
    """True si la direccion claramente no vale la pena geocodificar."""
    text = clean_text(direccion)
    if not text:
        return True
    lowered = text.lower()
    noisy_patterns = [
        "inicio propiedades",
        "conocenos",
        "administración",
        "administracion",
        "servicios contacto",
        "alquileres servicios contacto",
        "tasaciones contacto",
        "bienes raices",
        "bienes raíces",
        "enviar msj",
        ".com",
        "de negocios ©",
        "oficinas:",
        "telefono:",
        "teléfono:",
        "superficie lote",
        "superficie cubierta",
        "vivienda de ",
        "casa en alquiler vivienda",
        "ingresando por calle",
        "m. al sur",
        "nombre de calle y altura",
        "contacto ",
        "contacto",
        "propiedades",
        "inmobiliaria",
        "inmobiliario",
        "u$s",
        "consultar precio",
        "nuestra oficina",
        "estudio inmobiliario",
        "contacta venta",
        "llamar contacta",
        "por mes",
        "d consultar",
        "venta alquiler",
        "navigation",
        "usd ",
        "u$s ",
        "etapa se ofrece",
        "excelente lote",
        "cuenta con una superficie",
        "en un tercer piso",
        "la casa cuenta",
        "hipotecario con",
        "no acepta hipotecario",
        "acepta hipotecario",
        "lote en venta de",
        "nave industrial",
        "pais :",
        "país :",
        "ciudad :",
        "precio venta",
        "inicio 01",
        "estilo a ",
        "intente mas tarde",
        "envianos un mensaje",
        "consultar ventas",
        "de expensas",
        "vendo ",
        "terreno de ",
        "renta. metros",
        "terminando en ",
        "patios y cochera",
        "etc financiacion",
        "instagram facebook",
        "departamento n",
        "venta contacto",
        "alquiler contacto",
        "local en venta en ,",
        "departamento en venta en ,",
        "casa en alquiler en ,",
        "local en alquiler en ,",
        "quinta en alquiler en ,",
        "detalles de la propiedad",
        "totales ",
        "con servicio de",
        "completo.",
        "cuenta con ",
        "lote de ",
        "el barrio tiene seguridad",
        "temporada de polo",
        "country club. en sus",
        "matricula",
        "mat ",
        "un barrio con seguridad",
        "apto descarga",
        "featured share",
        "dormitorios:",
        "baños:",
        "banos:",
        "cmcpsi",
        "november december",
        "select year",
        "coordina tu visita",
        "mayor a ",
        "construida sobre",
        "pendiente positiva",
        "luz y gas natural",
        "seguridad 24",
        "seguridad las 24",
        "country cerrado",
        "con comercios cerca",
        "posee servicio de seguridad",
        "exclusivo barrio",
        "al paseo.",
        "a la calle.",
        "en planta baja",
        "superficie total",
        "terreno total",
        "cuenta con un terreno",
        "la propiedad cuenta con",
        "del inmueble lote en venta",
        "del inmueble casa en venta",
        "del inmueble casa en alquiler",
        "detalle del inmueble",
        "publicado:",
        "actualizado",
        "visto ",
    ]
    if any(pattern in lowered for pattern in noisy_patterns):
        return True
    if re.fullmatch(r"(?:u\$s|usd|\$|ars)?\s*[\d.,]{2,}(?:\s*(?:usd|ars|pesos?))?", lowered):
        return True
    if re.match(r"^(domicilio\s+)?(\.{2,}|parcela\s+\d+\b)", lowered):
        return True
    if re.search(r"\bgrupo\s+[a-z0-9]+\s+\d+\b", lowered):
        return True
    if re.match(r"^entre\s+\d+\b", lowered):
        return True
    if re.match(r"^ref\s+\d+\b", lowered):
        return True
    if re.match(r"^calle\s+\d+\b", lowered):
        return True
    if re.match(r"^chalet\s+\d+\b", lowered):
        return True
    if re.match(r"^terreno\s+\d+\b", lowered):
        return True
    if re.match(r"^direccion\s+\d{3,5}\b", lowered):
        return True
    if re.match(r"^mts\s+\d+\b", lowered):
        return True
    if re.match(r"^esquina\s+\d+\b", lowered):
        return True
    if len(text) < 5:
        return True
    if not any(ch.isdigit() for ch in text):
        return True
    return False


def source_filter_parts(source: Optional[str]) -> Tuple[str, Optional[str], Optional[str]]:
    if not source:
        return "", None, None
    if source not in SOURCE_FILTERS:
        valid = ", ".join(sorted(SOURCE_FILTERS))
        raise SystemExit(f"--source invalido: {source}. Valores validos: {valid}")
    return SOURCE_FILTERS[source]


def fetch_staging_rows(cur, limit: int, source: Optional[str] = None, ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    join_sql, source_clause, source_value = source_filter_parts(source)
    clauses = ["s.geocoding_status = 'pending'", "s.status = 'staging'"]
    params: List[Any] = []
    if source_clause:
        clauses.append(source_clause)
        params.append(source_value)
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        clauses.append(f"s.id IN ({placeholders})")
        params.extend(ids)
    params.append(limit)
    where_sql = " AND ".join(clauses)
    sql = f"""
{STAGING_SELECT_COLUMNS}
{join_sql}
WHERE {where_sql}
ORDER BY s.validation_score DESC, s.id ASC
LIMIT %s
"""
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def fetch_source_geocoding_status(cur, source: Optional[str], limit: int = 1000) -> Counter[str]:
    join_sql, source_clause, source_value = source_filter_parts(source)
    params: List[Any] = []
    clauses: List[str] = []
    if source_clause:
        clauses.append(source_clause)
        params.append(source_value)
    params.append(limit)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(
        f"""
        SELECT s.geocoding_status
        FROM public.propiedades_staging s
        {join_sql}
        {where_sql}
        ORDER BY s.id ASC
        LIMIT %s
        """,
        params,
    )
    return Counter(str(row["geocoding_status"]) for row in cur.fetchall())


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


def render_report(summary: Dict[str, Any]) -> str:
    result_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["results"].items())) or "- none: 0"
    readiness_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["readiness"].items())) or "- none: 0"
    status_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(summary["status_summary"].items())) or "- none: 0"
    return f"""# Geocode imported staging

Fecha: {summary['timestamp']}
Modo: {summary['mode']}
Origen: {summary['source'] or 'all_staging'}
Proveedor: Nominatim

## Resumen

- pendientes_detectadas: {summary['read_count']}
- candidatas_geocodificables: {summary['probe_count']}
- descartadas_por_direccion_ambigua: {summary['skipped_count']}
- ya_geocodificadas_lote: {summary['already_done']}
- done: {summary['results'].get('done', 0)}
- failed: {summary['results'].get('failed', 0)}
- skipped: {summary['results'].get('skipped', 0)}
- requests_usados: {summary['requests_used']}
- max_requests: {summary['max_requests']}
- accion_final: {summary['final_action']}

## Estados del lote

{status_lines}

## Resultados de esta corrida

{result_lines}

## Readiness / errores esperados

{readiness_lines}

## Seguridad

- no_toca_supabase: true
- no_publica_supabase: true
- no_toca_publish_queue: true
- no_modifica_env: true
- no_borra_datos: true
- no_commit_git: true
- no_push_git: true
"""


def safe_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def write_report(summary: Dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(summary), encoding="utf-8")


def update_master_progress(summary: Dict[str, Any], report_path: Path) -> None:
    master_path = REPO_ROOT / "reports" / "scraping_autofix" / "master_progress.md"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n\n## Geocode imported staging {summary['timestamp']}\n\n"
        f"- Modo: {summary['mode']}\n"
        f"- Origen: {summary['source'] or 'all_staging'}\n"
        f"- Pendientes detectadas: {summary['read_count']}\n"
        f"- Candidatas geocodificables: {summary['probe_count']}\n"
        f"- Descartadas por direccion ambigua: {summary['skipped_count']}\n"
        f"- Done: {summary['results'].get('done', 0)}\n"
        f"- Failed: {summary['results'].get('failed', 0)}\n"
        f"- Skipped: {summary['results'].get('skipped', 0)}\n"
        f"- Requests usados: {summary['requests_used']} / {summary['max_requests']}\n"
        f"- Accion final: {summary['final_action']}\n"
        f"- Reporte: {safe_relative_path(report_path)}\n"
        f"- Confirmacion: no .env, no borrado, no commit, no push, no publicacion masiva Supabase, no publish_queue, no pipeline commit, no cambios destructivos.\n"
    )
    try:
        if master_path.exists():
            current = master_path.read_text(encoding="utf-8", errors="ignore")
        else:
            current = "# Scraping autofix master progress\n"
        master_path.write_text(current.rstrip() + entry + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"warning: no pude actualizar master_progress.md: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Geocodificar propiedades_staging en Neon (Etapa 6.5)"
    )
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de filas a leer")
    parser.add_argument("--max-requests", type=int, default=30, help="Tope de llamadas a Nominatim por corrida")
    parser.add_argument("--source", choices=sorted(SOURCE_FILTERS), help="Filtrar staging por origen seguro")
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="CSV con columna 'staging_id' — geocodifica SOLO esos IDs. "
             "Garantiza que no se toquen otros rows aunque haya miles de pending.",
    )
    parser.add_argument("--report", type=Path, help="Ruta de reporte markdown")
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

    # Load explicit ID list from --ids-file if provided
    target_ids: Optional[List[int]] = None
    if args.ids_file:
        import csv as _csv
        ids_path = args.ids_file if args.ids_file.is_absolute() else REPO_ROOT / args.ids_file
        if not ids_path.exists():
            raise SystemExit(f"--ids-file no encontrado: {ids_path}")
        target_ids = []
        with ids_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                raw_id = row.get("staging_id") or row.get("id") or ""
                try:
                    target_ids.append(int(raw_id.strip()))
                except ValueError:
                    pass
        if not target_ids:
            raise SystemExit(f"--ids-file no contiene staging_id validos: {ids_path}")
        print(f"ids_file={ids_path} ({len(target_ids)} IDs cargados)")

    db_url = internal_db_config()

    read_count = 0
    requests_used = 0
    results: Counter[str] = Counter()
    readiness_counts: Counter[str] = Counter()
    status_summary: Counter[str] = Counter()

    print("=" * 72)
    print("GEOCODE STAGING")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"limit={args.limit}")
    print(f"max_requests={args.max_requests}")
    print(f"source={args.source or 'all_staging'}")
    print("provider=Nominatim")
    print("target=internal_db")
    print("-" * 72)

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            status_summary = fetch_source_geocoding_status(cur, args.source)
            rows = fetch_staging_rows(cur, args.limit, args.source, target_ids)
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
                    readiness_counts[readiness] += 1
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
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = args.report or (
        REPO_ROOT / "reports" / "scraping_autofix" / f"geocode_imported_staging_{timestamp}.md"
    )
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": "commit" if args.commit else "dry-run",
        "source": args.source,
        "read_count": read_count,
        "probe_count": results.get("probe", 0) if args.dry_run else results.get("done", 0) + results.get("failed", 0),
        "skipped_count": results.get("skipped", 0),
        "already_done": status_summary.get("done", 0),
        "results": results,
        "readiness": readiness_counts,
        "status_summary": status_summary,
        "requests_used": requests_used,
        "max_requests": args.max_requests,
        "final_action": final_action,
    }
    write_report(summary, report_path)
    update_master_progress(summary, report_path)
    print(f"report={report_path}")
    print("=" * 72)


if __name__ == "__main__":
    main()

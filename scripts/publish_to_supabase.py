#!/usr/bin/env python
"""Publish Neon publish_queue entries to Supabase.

This script reads the internal Neon queue, revalidates associated staging rows,
and delegates the actual Supabase write to SupabasePropiedades.save_propiedades.
Default mode is dry-run; pass --commit to persist changes.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario"}

QUEUE_SELECT_DRY_RUN_SQL = """
SELECT
  id,
  staging_id,
  priority,
  attempts,
  status
FROM public.publish_queue
WHERE status = 'pending'
ORDER BY priority ASC, queued_at ASC
LIMIT %s
"""

QUEUE_CLAIM_SQL = """
SELECT
  id,
  staging_id,
  priority,
  attempts,
  status
FROM public.publish_queue
WHERE status = 'pending'
ORDER BY priority ASC, queued_at ASC
LIMIT %s
FOR UPDATE SKIP LOCKED
"""

STAGING_SELECT_SQL = """
SELECT
  id,
  inmobiliaria_id,
  hash_dedup,
  titulo,
  descripcion,
  precio,
  moneda,
  tipo_propiedad,
  operacion,
  superficie_total,
  superficie_cubierta,
  direccion_normalizada,
  barrio,
  ciudad,
  provincia,
  pais,
  latitud,
  longitud,
  imagenes,
  url,
  url_normalizada,
  geocoding_status,
  validation_score,
  status
FROM public.propiedades_staging
WHERE id = ANY(%s)
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


def create_supabase_client():
    from scraper.scraper_propiedades import SupabasePropiedades

    return SupabasePropiedades()


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except Exception:
        return default


def truncate_error(value: Any) -> str:
    return str(value or "")[:500]


def fetch_queue_rows(
    cur,
    limit: int,
    *,
    commit: bool,
    staging_ids_filter: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    base_sql = QUEUE_CLAIM_SQL if commit else QUEUE_SELECT_DRY_RUN_SQL
    if staging_ids_filter:
        filtered_sql = base_sql.replace(
            "WHERE status = 'pending'",
            "WHERE status = 'pending'\nAND staging_id = ANY(%s)",
        )
        cur.execute(filtered_sql, [staging_ids_filter, limit])
    else:
        cur.execute(base_sql, [limit])
    return [dict(row) for row in cur.fetchall()]


def mark_queue_publishing(cur, queue_ids: Sequence[int]) -> None:
    if not queue_ids:
        return
    cur.execute(
        """
        UPDATE public.publish_queue
        SET status = 'publishing',
            last_attempt_at = now()
        WHERE id = ANY(%s)
        """,
        [list(queue_ids)],
    )


def fetch_staging_rows(cur, staging_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    if not staging_ids:
        return {}
    cur.execute(STAGING_SELECT_SQL, [list(staging_ids)])
    rows: Dict[int, Dict[str, Any]] = {}
    for row in cur.fetchall():
        data = dict(row)
        try:
            rows[int(data["id"])] = data
        except Exception:
            continue
    return rows


def validation_skip_reason(
    staging: Optional[Dict[str, Any]],
    *,
    min_score: int,
    allow_pending_geo: bool,
) -> Optional[str]:
    if not staging:
        return "missing_staging"
    if (clean_text(staging.get("status")) or "").lower() != "queued":
        return "invalid_staging_status"
    if not clean_text(staging.get("hash_dedup")):
        return "missing_hash"
    try:
        inmobiliaria_id = int(staging.get("inmobiliaria_id"))
        if inmobiliaria_id <= 0:
            return "missing_inmobiliaria"
    except Exception:
        return "missing_inmobiliaria"
    if not clean_text(staging.get("url")) and not clean_text(staging.get("url_normalizada")):
        return "missing_url"
    if not clean_text(staging.get("titulo")):
        return "missing_title"
    operacion = (clean_text(staging.get("operacion")) or "").lower()
    if operacion not in VALID_OPERATIONS:
        return "invalid_operation"
    geocoding_status = (clean_text(staging.get("geocoding_status")) or "").lower()
    allowed_geo = {"done", "skipped"}
    if allow_pending_geo:
        allowed_geo.add("pending")
    if geocoding_status not in allowed_geo:
        return "geocoding_pending"
    if to_int(staging.get("validation_score")) < min_score:
        return "low_score"
    return None


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def staging_to_prop(staging: Dict[str, Any]) -> Dict[str, Any]:
    prop = {
        "inmobiliaria_id": staging.get("inmobiliaria_id"),
        "hash_dedup": staging.get("hash_dedup"),
        "titulo": staging.get("titulo"),
        "descripcion": staging.get("descripcion"),
        "precio": staging.get("precio"),
        "moneda": staging.get("moneda"),
        "tipo_propiedad": staging.get("tipo_propiedad"),
        "operacion": staging.get("operacion"),
        "superficie_total": staging.get("superficie_total"),
        "superficie_cubierta": staging.get("superficie_cubierta"),
        "direccion": staging.get("direccion_normalizada"),
        "barrio": staging.get("barrio"),
        "ciudad": staging.get("ciudad"),
        "provincia": staging.get("provincia"),
        "pais": staging.get("pais"),
        "latitud": staging.get("latitud"),
        "longitud": staging.get("longitud"),
        "imagenes": staging.get("imagenes") if isinstance(staging.get("imagenes"), list) else [],
        "url": staging.get("url"),
        "url_normalizada": staging.get("url_normalizada"),
    }
    return _json_safe(prop)


def mark_queue_failed(cur, queue_id: int, error_message: str) -> None:
    cur.execute(
        """
        UPDATE public.publish_queue
        SET status = 'failed',
            attempts = attempts + 1,
            error_message = %s,
            last_attempt_at = now()
        WHERE id = %s
        """,
        [truncate_error(error_message), queue_id],
    )


def mark_queue_done(cur, queue_id: int) -> None:
    cur.execute(
        """
        UPDATE public.publish_queue
        SET status = 'done',
            error_message = NULL,
            last_attempt_at = now()
        WHERE id = %s
        """,
        [queue_id],
    )


def mark_staging_published(cur, staging_id: int) -> None:
    cur.execute(
        "UPDATE public.propiedades_staging SET status = 'published' WHERE id = %s",
        [staging_id],
    )


def publish_one(db: Any, prop: Dict[str, Any]) -> Tuple[int, int]:
    total, nuevas = db.save_propiedades([prop])
    if total <= 0:
        raise RuntimeError("save_propiedades no confirmo insercion/actualizacion")
    return total, nuevas


def main() -> None:
    parser = argparse.ArgumentParser(description="Publicar publish_queue pendiente desde Neon a Supabase")
    parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima de filas de queue a evaluar")
    parser.add_argument("--max-supabase-writes", type=int, default=10, help="Maximo de escrituras Supabase")
    parser.add_argument("--min-score", type=int, default=60, help="Score minimo para publicar")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pausa despues de cada publicacion")
    parser.add_argument("--allow-pending-geo", action="store_true", help="Aceptar geocoding_status=pending")
    parser.add_argument("--dry-run", action="store_true", help="Leer y validar sin escribir")
    parser.add_argument("--commit", action="store_true", help="Publicar y actualizar estados")
    parser.add_argument(
        "--staging-ids-file", type=str, default=None,
        help="CSV con columna 'staging_id' o 'id' — filtra la queue SOLO a esos staging IDs.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.max_supabase_writes <= 0:
        raise SystemExit("--max-supabase-writes debe ser mayor a 0")
    if args.min_score < 0:
        raise SystemExit("--min-score debe ser mayor o igual a 0")
    if args.sleep < 0:
        raise SystemExit("--sleep debe ser mayor o igual a 0")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    db_url = internal_db_config()
    claim_limit = min(args.limit, args.max_supabase_writes) if args.commit else args.limit

    # Load optional staging IDs filter
    import csv as _csv
    staging_ids_filter: Optional[List[int]] = None
    if args.staging_ids_file:
        ids_path = Path(args.staging_ids_file)
        if not ids_path.exists():
            raise SystemExit(f"--staging-ids-file no encontrado: {ids_path}")
        with open(ids_path, newline="", encoding="utf-8") as _f:
            _reader = _csv.DictReader(_f)
            _col = "staging_id" if "staging_id" in (_reader.fieldnames or []) else "id"
            staging_ids_filter = [int(row[_col]) for row in _reader if row.get(_col, "").strip()]
        if not staging_ids_filter:
            raise SystemExit("--staging-ids-file esta vacio o no tiene columna staging_id/id")

    skipped: Counter[str] = Counter()
    rows_read = 0
    valid_props = 0
    published_ok = 0
    failed = 0
    writes_used = 0
    action_final = "rollback" if args.dry_run else "commit"

    print("=" * 72)
    print("PUBLISH TO SUPABASE")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"limit={args.limit}")
    print(f"max_supabase_writes={args.max_supabase_writes}")
    print(f"min_score={args.min_score}")
    print(f"allow_pending_geo={args.allow_pending_geo}")
    if staging_ids_filter is not None:
        print(f"staging_ids_filter={len(staging_ids_filter)} IDs (from {args.staging_ids_file})")
    print("-" * 72)

    db = create_supabase_client() if args.commit else None

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            queue_rows = fetch_queue_rows(cur, claim_limit, commit=args.commit, staging_ids_filter=staging_ids_filter)
            rows_read = len(queue_rows)
            queue_ids = [int(row["id"]) for row in queue_rows]
            staging_ids = [int(row["staging_id"]) for row in queue_rows if row.get("staging_id") is not None]

            if args.commit:
                mark_queue_publishing(cur, queue_ids)

            staging_by_id = fetch_staging_rows(cur, staging_ids)

            for queue_row in queue_rows:
                queue_id = int(queue_row["id"])
                staging_id = int(queue_row["staging_id"]) if queue_row.get("staging_id") is not None else 0
                staging = staging_by_id.get(staging_id)
                reason = validation_skip_reason(
                    staging,
                    min_score=args.min_score,
                    allow_pending_geo=args.allow_pending_geo,
                )
                if reason:
                    skipped[reason] += 1
                    failed += 1
                    if args.commit:
                        mark_queue_failed(cur, queue_id, f"validation_failed:{reason}")
                    continue

                prop = staging_to_prop(staging or {})
                valid_props += 1

                if args.dry_run:
                    print(
                        "DRY-RUN would publish "
                        f"queue_id={queue_id} staging_id={staging_id} "
                        f"hash={prop.get('hash_dedup')} url={prop.get('url') or prop.get('url_normalizada')}"
                    )
                    continue

                if writes_used >= args.max_supabase_writes:
                    skipped["write_limit_reached"] += 1
                    mark_queue_failed(cur, queue_id, "write_limit_reached")
                    failed += 1
                    continue

                try:
                    publish_one(db, prop)
                    writes_used += 1
                    published_ok += 1
                    mark_queue_done(cur, queue_id)
                    mark_staging_published(cur, staging_id)
                    if args.sleep:
                        time.sleep(args.sleep)
                except Exception as exc:
                    failed += 1
                    mark_queue_failed(cur, queue_id, exc)
                    continue

        if args.commit:
            conn.commit()
        else:
            conn.rollback()

    print("-" * 72)
    print(f"filas_queue_leidas={rows_read}")
    print(f"props_validas={valid_props}")
    print(f"publicadas_ok={published_ok}")
    print(f"failed={failed}")
    print("omitidas_por_validacion:")
    if skipped:
        for reason, count in sorted(skipped.items()):
            print(f"  {reason}: {count}")
    else:
        print("  none: 0")
    print(f"writes_supabase_usados={writes_used}")
    print(f"accion_final={action_final}")
    print("=" * 72)


if __name__ == "__main__":
    main()

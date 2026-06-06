#!/usr/bin/env python
"""Build Neon publish_queue entries from propiedades_staging.

This script only uses INTERNAL_DB_URL. It never reads or writes Supabase.
Default mode is dry-run; pass --commit to persist changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario"}

STAGING_SELECT_SQL = """
SELECT
  id,
  inmobiliaria_id,
  hash_dedup,
  url,
  url_normalizada,
  operacion,
  precio,
  validation_score,
  geocoding_status,
  status
FROM public.propiedades_staging
WHERE status = 'staging'
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


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    return float(normalized)


def fetch_staging_rows(cur, limit: int, ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"""
            SELECT id, inmobiliaria_id, hash_dedup, url, url_normalizada,
                   operacion, precio, validation_score, geocoding_status, status
            FROM public.propiedades_staging
            WHERE status = 'staging' AND id IN ({placeholders})
            ORDER BY validation_score DESC, id ASC
            LIMIT %s
            """,
            ids + [limit],
        )
    else:
        cur.execute(STAGING_SELECT_SQL, [limit])
    return [dict(row) for row in cur.fetchall()]


def fetch_existing_queue_staging_ids(cur, staging_ids: List[int]) -> Set[int]:
    if not staging_ids:
        return set()
    placeholders = ", ".join(["%s"] * len(staging_ids))
    cur.execute(
        f"""
        SELECT staging_id
        FROM public.publish_queue
        WHERE staging_id IN ({placeholders})
          AND status IN ('pending','publishing','done')
        """,
        staging_ids,
    )
    result: Set[int] = set()
    for row in cur.fetchall():
        try:
            result.add(int(row["staging_id"]))
        except Exception:
            continue
    return result


def compute_priority(row: Dict[str, Any]) -> int:
    validation_score = to_int(row.get("validation_score"))
    geocoding_status = (clean_text(row.get("geocoding_status")) or "").lower()
    precio = to_float(row.get("precio"))
    if validation_score >= 90 and geocoding_status == "done" and precio is not None and precio > 0:
        return 1
    if validation_score >= 70 or (geocoding_status == "done" and precio is None):
        return 2
    return 3


def queue_skip_reason(row: Dict[str, Any], *, min_score: int, allow_pending_geo: bool) -> Optional[str]:
    if not clean_text(row.get("hash_dedup")):
        return "skip_missing_hash"
    try:
        inmobiliaria_id = int(row.get("inmobiliaria_id"))
        if inmobiliaria_id <= 0:
            return "skip_missing_inmobiliaria"
    except Exception:
        return "skip_missing_inmobiliaria"
    if not clean_text(row.get("url")) and not clean_text(row.get("url_normalizada")):
        return "skip_missing_url"
    operacion = (clean_text(row.get("operacion")) or "").lower()
    if operacion not in VALID_OPERATIONS:
        return "skip_invalid_operation"
    if to_int(row.get("validation_score")) < min_score:
        return "skip_low_score"
    geocoding_status = (clean_text(row.get("geocoding_status")) or "").lower()
    allowed_geo = {"done", "skipped"}
    if allow_pending_geo:
        allowed_geo.add("pending")
    if geocoding_status not in allowed_geo:
        return "skip_geocoding_pending"
    return None


def insert_publish_queue(cur, staging_id: int, priority: int) -> None:
    cur.execute(
        """
        INSERT INTO public.publish_queue (
            staging_id,
            propiedad_supabase_id,
            action,
            priority,
            attempts,
            status
        ) VALUES (%s, NULL, 'upsert', %s, 0, 'pending')
        """,
        [staging_id, priority],
    )


def update_staging_queued(cur, staging_id: int) -> None:
    cur.execute(
        "UPDATE public.propiedades_staging SET status = 'queued' WHERE id = %s",
        [staging_id],
    )


def process_row(
    cur,
    row: Dict[str, Any],
    *,
    existing_queue_ids: Set[int],
    min_score: int,
    allow_pending_geo: bool,
) -> Tuple[str, Optional[int]]:
    staging_id = int(row["id"])
    cur.execute("SAVEPOINT build_publish_queue_row")
    try:
        if staging_id in existing_queue_ids:
            update_staging_queued(cur, staging_id)
            cur.execute("RELEASE SAVEPOINT build_publish_queue_row")
            return "skip_already_queued", None

        reason = queue_skip_reason(row, min_score=min_score, allow_pending_geo=allow_pending_geo)
        if reason:
            cur.execute("RELEASE SAVEPOINT build_publish_queue_row")
            return reason, None

        priority = compute_priority(row)
        insert_publish_queue(cur, staging_id, priority)
        update_staging_queued(cur, staging_id)
        cur.execute("RELEASE SAVEPOINT build_publish_queue_row")
        return "queued", priority
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT build_publish_queue_row")
        cur.execute("RELEASE SAVEPOINT build_publish_queue_row")
        return "process_error", None


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear publish_queue desde propiedades_staging en Neon")
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de staging rows a evaluar")
    parser.add_argument("--min-score", type=int, default=60, help="Score minimo para encolar")
    parser.add_argument("--allow-pending-geo", action="store_true", help="Aceptar geocoding_status=pending")
    parser.add_argument("--dry-run", action="store_true", help="Procesar y hacer rollback")
    parser.add_argument("--commit", action="store_true", help="Persistir cambios en Neon")
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="CSV con columna 'staging_id' — evalua SOLO esos IDs. "
             "Garantiza que no se procesen otros rows del staging historico.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.min_score < 0:
        raise SystemExit("--min-score debe ser mayor o igual a 0")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    # Cargar IDs explícitos desde --ids-file si se provee
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

    db_url = internal_db_config()
    skipped: Counter[str] = Counter()
    priorities: Counter[int] = Counter()
    read_count = 0
    queued_count = 0
    already_queued_count = 0

    print("=" * 72)
    print("BUILD PUBLISH QUEUE")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"limit={args.limit}")
    print(f"min_score={args.min_score}")
    print(f"allow_pending_geo={args.allow_pending_geo}")
    if args.ids_file:
        print(f"ids_file={args.ids_file} ({len(target_ids)} IDs)")
    print("target=internal_db")
    print("-" * 72)

    with connect_internal_db(db_url) as conn:
        with conn.cursor() as cur:
            rows = fetch_staging_rows(cur, args.limit, ids=target_ids)
            read_count = len(rows)
            staging_ids = []
            for row in rows:
                try:
                    staging_ids.append(int(row["id"]))
                except Exception:
                    continue
            existing_queue_ids = fetch_existing_queue_staging_ids(cur, staging_ids)

            for row in rows:
                result, priority = process_row(
                    cur,
                    row,
                    existing_queue_ids=existing_queue_ids,
                    min_score=args.min_score,
                    allow_pending_geo=args.allow_pending_geo,
                )
                if result == "queued":
                    queued_count += 1
                    if priority is not None:
                        priorities[priority] += 1
                elif result == "skip_already_queued":
                    already_queued_count += 1
                    skipped[result] += 1
                else:
                    skipped[result] += 1

        if args.commit:
            conn.commit()
            final_action = "commit"
        else:
            conn.rollback()
            final_action = "rollback"

    print(f"filas_leidas={read_count}")
    print(f"encoladas={queued_count}")
    print(f"ya_en_cola={already_queued_count}")
    print("omitidas_por_motivo:")
    if skipped:
        for reason, count in sorted(skipped.items()):
            print(f"  {reason}: {count}")
    else:
        print("  none: 0")
    print("priorities:")
    for priority in (1, 2, 3):
        print(f"  {priority}: {priorities[priority]}")
    print(f"accion_final={final_action}")
    print("=" * 72)


if __name__ == "__main__":
    main()

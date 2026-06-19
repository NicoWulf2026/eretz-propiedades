#!/usr/bin/env python
"""Build Neon publish_queue entries from propiedades_staging.

This script only uses INTERNAL_DB_URL. It never reads or writes Supabase.
Default mode is dry-run; pass --commit to persist changes.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
# FASE 1 — Sprint A: ampliado con consultar y venta_y_alquiler.
# Todas las operaciones normalizadas son válidas para publicar.
VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario", "consultar", "venta_y_alquiler"}

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
FROM propiedades_staging
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


def internal_db_schema() -> str:
    """Schema de las tablas del pipeline.

    Default 'public' (Neon dedicado). 'internal_scraping' para Supabase Pro.
    Se valida como identificador simple para poder usarlo en SET search_path.
    """
    schema = (os.getenv("INTERNAL_DB_SCHEMA", "public").strip() or "public")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
        raise SystemExit(f"INTERNAL_DB_SCHEMA invalido: {schema!r}")
    return schema


def internal_db_config() -> Tuple[str, str]:
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not env_flag("USE_INTERNAL_DB", default=False):
        raise SystemExit("USE_INTERNAL_DB no esta en true; abortando para no usar una DB equivocada.")
    if not db_url:
        raise SystemExit("Falta INTERNAL_DB_URL; abortando.")
    return db_url, internal_db_schema()


def connect_internal_db(db_url: str, schema: str = "public"):
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Falta instalar psycopg/psycopg-binary para usar INTERNAL_DB_URL.") from exc
    conn = psycopg.connect(db_url, row_factory=dict_row)
    # Las queries usan nombres sin calificar; search_path decide el schema destino.
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}")
    return conn


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


def latest_finished_run_id(cur) -> Optional[int]:
    """Último scraping_run TERMINADO (status='finished').

    Supuesto: scraping_runs.status existe con CHECK ('running','finished','error',
    'cancelled') — confirmado en internal_db_schema.sql. Usamos 'finished' para NO
    encolar un run incompleto/en curso. Si no hay ninguno finished, devuelve None
    (el caller aborta pidiendo --run-id o --include-backlog explícito).
    """
    cur.execute("SELECT MAX(id) AS n FROM scraping_runs WHERE status = 'finished'")
    row = cur.fetchone()
    return int(row["n"]) if row and row.get("n") is not None else None


def determine_selection_mode(target_ids, include_backlog: bool, run_id: Optional[int]) -> Tuple[str, Optional[int]]:
    """Decide el modo de selección de staging (pura, sin DB; testeable con mocks).

    Prioridad: ids_file > include_backlog > run explícito > run_latest (default seguro).
    Para 'run_latest' el run_id se resuelve luego con latest_finished_run_id(cur).
    """
    if target_ids is not None:
        return "ids_file", None
    if include_backlog:
        return "backlog", None
    if run_id is not None:
        return "run", run_id
    return "run_latest", None


def count_staging_backlog(cur) -> int:
    """COUNT(*) de staging pendiente. Usa idx_propiedades_staging_status (barato),
    pero genera I/O: SOLO se llama en dry-run si se pasó --show-backlog-count."""
    cur.execute("SELECT COUNT(*) AS n FROM propiedades_staging WHERE status = 'staging'")
    return int(cur.fetchone()["n"])


def fetch_staging_rows_by_run(cur, run_id: int, limit: int) -> List[Dict[str, Any]]:
    """Staging en estado 'staging' cuyas raw pertenecen al scraping_run dado.
    Acota el encolado a un run (evita tomar el backlog histórico completo)."""
    cur.execute(
        """
        SELECT s.id, s.inmobiliaria_id, s.hash_dedup, s.url, s.url_normalizada,
               s.operacion, s.precio, s.validation_score, s.geocoding_status, s.status
        FROM propiedades_staging s
        WHERE s.status = 'staging'
          AND s.raw_id IN (
            SELECT r.id FROM propiedades_raw r
            JOIN scraping_run_items sri ON sri.id = r.scraping_run_item_id
            WHERE sri.scraping_run_id = %s
          )
        ORDER BY s.validation_score DESC, s.id ASC
        LIMIT %s
        """,
        [run_id, limit],
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_staging_rows(cur, limit: int, ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
    if ids:
        placeholders = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"""
            SELECT id, inmobiliaria_id, hash_dedup, url, url_normalizada,
                   operacion, precio, validation_score, geocoding_status, status
            FROM propiedades_staging
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
        FROM publish_queue
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
        allowed_geo.update({"pending", "failed"})
    if geocoding_status not in allowed_geo:
        return "skip_geocoding_pending"
    return None


def classify_row(
    row: Dict[str, Any],
    *,
    existing_queue_ids: Set[int],
    min_score: int,
    allow_pending_geo: bool,
) -> Tuple[str, Optional[int]]:
    """Decide el destino de una fila SIN tocar la base (validación en memoria).

    Devuelve (resultado, priority). Mismos resultados y motivos de skip que la
    versión fila-por-fila anterior; lo único que cambia es que no ejecuta SQL.
    La escritura se hace luego en bloque (bulk) en `main`.
    """
    staging_id = int(row["id"])
    if staging_id in existing_queue_ids:
        return "skip_already_queued", None
    reason = queue_skip_reason(row, min_score=min_score, allow_pending_geo=allow_pending_geo)
    if reason:
        return reason, None
    return "queued", compute_priority(row)


def bulk_insert_publish_queue(cur, items: List[Tuple[int, int]]) -> None:
    """Inserta todas las filas a encolar en un solo statement (VALUES multi-fila)."""
    if not items:
        return
    values_sql = ", ".join(["(%s, NULL, 'upsert', %s, 0, 'pending')"] * len(items))
    args: List[Any] = []
    for staging_id, priority in items:
        args.extend([staging_id, priority])
    cur.execute(
        "INSERT INTO publish_queue "
        "(staging_id, propiedad_supabase_id, action, priority, attempts, status) "
        f"VALUES {values_sql}",
        args,
    )


def bulk_mark_staging_queued(cur, staging_ids: List[int]) -> None:
    """Marca status='queued' para todos los staging_ids en un solo UPDATE."""
    if not staging_ids:
        return
    cur.execute(
        "UPDATE propiedades_staging SET status = 'queued' WHERE id = ANY(%s)",
        [staging_ids],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear publish_queue desde propiedades_staging en Neon")
    parser.add_argument("--limit", type=int, default=20, help="Cantidad maxima de staging rows a evaluar")
    parser.add_argument("--min-score", type=int, default=0, help="Score minimo para encolar (0 = publicar todas las props validas)")
    parser.add_argument("--allow-pending-geo", dest="allow_pending_geo", action="store_true", default=True, help="Aceptar geocoding_status=pending (activo por defecto)")
    parser.add_argument("--no-allow-pending-geo", dest="allow_pending_geo", action="store_false", help="Requerir geocoding_status=done o skipped")
    parser.add_argument("--dry-run", action="store_true", help="Procesar y hacer rollback")
    parser.add_argument("--commit", action="store_true", help="Persistir cambios en Neon")
    parser.add_argument(
        "--ids-file",
        type=Path,
        default=None,
        help="CSV con columna 'staging_id' — evalua SOLO esos IDs. "
             "Garantiza que no se procesen otros rows del staging historico.",
    )
    parser.add_argument("--run-id", type=int, default=None,
                        help="Encolar SOLO staging cuyas raw pertenecen a este scraping_run (modo controlado).")
    parser.add_argument("--include-backlog", action="store_true", default=False,
                        help="EXPLÍCITO: encolar TODO el staging histórico (backlog completo). Por defecto NO.")
    parser.add_argument("--show-backlog-count", action="store_true", default=False,
                        help="En dry-run, ejecutar COUNT(*) del backlog (genera I/O). Por defecto NO se consulta.")
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.min_score < 0:
        raise SystemExit("--min-score debe ser mayor o igual a 0")
    if args.run_id is not None and args.include_backlog:
        raise SystemExit("Usar --run-id o --include-backlog, no ambos")
    if args.run_id is not None and args.run_id <= 0:
        raise SystemExit("--run-id debe ser mayor a 0")
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

    db_url, db_schema = internal_db_config()
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
    print(f"target=internal_db (schema={db_schema})")
    print("-" * 72)

    timings: Dict[str, float] = {}
    with connect_internal_db(db_url, db_schema) as conn:
        with conn.cursor() as cur:
            # --- Bloque 0: determinar modo (DEFAULT SEGURO: último run finished) ---
            selection_mode, effective_run_id = determine_selection_mode(
                target_ids, args.include_backlog, args.run_id
            )
            if selection_mode == "run_latest":
                effective_run_id = latest_finished_run_id(cur)
                if effective_run_id is None:
                    raise SystemExit("No hay scraping_runs finished; usar --run-id o --include-backlog.")
            print(f"selection_mode={selection_mode} run_id={effective_run_id}")
            if selection_mode == "backlog":
                print("*** ADVERTENCIA FUERTE: --include-backlog encola TODO el staging histórico (backlog completo). ***")

            # --- Bloque 1: fetch staging según modo (1 query) ---
            t0 = time.perf_counter()
            if selection_mode in ("run", "run_latest"):
                rows = fetch_staging_rows_by_run(cur, effective_run_id, args.limit)
            elif selection_mode == "ids_file":
                rows = fetch_staging_rows(cur, args.limit, ids=target_ids)
            else:  # backlog
                rows = fetch_staging_rows(cur, args.limit, ids=None)
            read_count = len(rows)
            staging_ids = []
            for row in rows:
                try:
                    staging_ids.append(int(row["id"]))
                except Exception:
                    continue
            timings["fetch_staging"] = time.perf_counter() - t0

            # --- Bloque 1b: info de dry-run (no toca publish_queue; COUNT solo si se pide) ---
            if args.dry_run:
                if args.show_backlog_count:
                    backlog_total = count_staging_backlog(cur)
                    print(f"[dry-run] backlog_total_staging={backlog_total}")
                    print(f"[dry-run] quedarian_fuera={max(0, backlog_total - read_count)}")
                else:
                    print("[dry-run] backlog_total_staging=no_consultado (usar --show-backlog-count)")
                print(f"[dry-run] encolaria={read_count}")
                if selection_mode in ("run", "run_latest"):
                    print(f"[dry-run] del_run_actual={read_count} (run_id={effective_run_id})")
                if read_count >= args.limit:
                    print(f"[dry-run] ADVERTENCIA: alcanzó --limit ({args.limit}); puede haber más del run.")

            # --- Bloque 2: lookup publish_queue existente (1 query) ---
            t0 = time.perf_counter()
            existing_queue_ids = fetch_existing_queue_staging_ids(cur, staging_ids)
            timings["lookup_queue"] = time.perf_counter() - t0

            # --- Bloque 3: validación/clasificación en memoria (0 queries) ---
            t0 = time.perf_counter()
            to_insert: List[Tuple[int, int]] = []   # (staging_id, priority)
            already_queued_ids: List[int] = []
            for row in rows:
                result, priority = classify_row(
                    row,
                    existing_queue_ids=existing_queue_ids,
                    min_score=args.min_score,
                    allow_pending_geo=args.allow_pending_geo,
                )
                if result == "queued":
                    queued_count += 1
                    if priority is not None:
                        priorities[priority] += 1
                        to_insert.append((int(row["id"]), priority))
                elif result == "skip_already_queued":
                    already_queued_count += 1
                    skipped[result] += 1
                    already_queued_ids.append(int(row["id"]))
                else:
                    skipped[result] += 1
            timings["validate_memory"] = time.perf_counter() - t0

            # --- Bloque 4: escritura bulk (1 INSERT + 1 UPDATE) ---
            t0 = time.perf_counter()
            bulk_insert_publish_queue(cur, to_insert)
            # Marca queued tanto las recién insertadas como las que ya estaban en cola.
            bulk_mark_staging_queued(cur, [sid for sid, _ in to_insert] + already_queued_ids)
            timings["bulk_write"] = time.perf_counter() - t0

        # --- Bloque 5: commit/rollback (1 round-trip) ---
        t0 = time.perf_counter()
        if args.commit:
            conn.commit()
            final_action = "commit"
        else:
            conn.rollback()
            final_action = "rollback"
        timings["finalize"] = time.perf_counter() - t0

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
    print("timings_seconds:")
    for label in ("fetch_staging", "lookup_queue", "validate_memory", "bulk_write", "finalize"):
        if label in timings:
            print(f"  {label}: {timings[label]:.3f}")
    print(f"  total: {sum(timings.values()):.3f}")
    print("=" * 72)


if __name__ == "__main__":
    main()

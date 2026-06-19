#!/usr/bin/env python
"""Publish Neon publish_queue entries to Supabase.

This script reads the internal Neon queue, revalidates associated staging rows,
and delegates the actual Supabase write to SupabasePropiedades.save_propiedades.
Default mode is dry-run; pass --commit to persist changes.
"""

from __future__ import annotations

import argparse
import os
import random
import re
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

# Fase A-bis — logger de errores (best-effort, nunca rompe el publish).
try:
    from scraper.error_logger import log_error as _log_error
except Exception:  # pragma: no cover
    def _log_error(**_kw):  # fallback inerte si el módulo no estuviera disponible
        return None

# db_url para el insert best-effort en internal_scraping.error_log (seteado en main()).
# El logger usa una conexión EFÍMERA propia con este URL; nunca la transacción del publish.
_ABIS_DB_URL = None

from scripts.image_quality import normalize_property_images

# FASE 1 — Sprint A: ampliado con consultar y venta_y_alquiler.
# Debe mantenerse en sync con build_publish_queue.py::VALID_OPERATIONS.
VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario", "consultar", "venta_y_alquiler"}

QUEUE_SELECT_DRY_RUN_SQL = """
SELECT
  id,
  staging_id,
  propiedad_supabase_id,
  action,
  priority,
  attempts,
  status
FROM publish_queue
WHERE status = 'pending'
ORDER BY priority ASC, queued_at ASC
LIMIT %s
"""

QUEUE_CLAIM_SQL = """
SELECT
  id,
  staging_id,
  propiedad_supabase_id,
  action,
  priority,
  attempts,
  status
FROM publish_queue
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
FROM propiedades_staging
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


def internal_db_schema() -> str:
    """Schema de las tablas internas (publish_queue, propiedades_staging).

    Default 'public' (Neon). 'internal_scraping' para Supabase Pro.
    No afecta la escritura a public.propiedades, que va por REST API.
    """
    schema = (os.getenv("INTERNAL_DB_SCHEMA", "public").strip() or "public")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
        raise SystemExit(f"INTERNAL_DB_SCHEMA invalido: {schema!r}")
    return schema


def connect_internal_db(db_url: str):
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Falta instalar psycopg/psycopg-binary para usar INTERNAL_DB_URL.") from exc
    conn = psycopg.connect(db_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {internal_db_schema()}")
    return conn


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
        UPDATE publish_queue
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
        allowed_geo.update({"pending", "failed"})
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
    images, _discarded_images = normalize_property_images(staging.get("imagenes"))
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
        "imagenes": images,
        "url": staging.get("url"),
        "url_normalizada": staging.get("url_normalizada"),
        "estado": staging.get("estado") or "activa",
    }
    return _json_safe(prop)


def mark_queue_failed(cur, queue_id: int, error_message: str) -> None:
    cur.execute(
        """
        UPDATE publish_queue
        SET status = 'failed',
            attempts = attempts + 1,
            error_message = %s,
            last_attempt_at = now()
        WHERE id = %s
        """,
        [truncate_error(error_message), queue_id],
    )
    # Fase A-bis: registro persistente del error de publicación.
    # JSONL siempre; tabla best-effort vía conexión efímera propia del logger
    # (NO usa la transacción/conexión de este publish, no la ensucia ni hace rollback).
    _log_error(
        fase="publish",
        error_type="publish_failed",
        severidad="warning",
        mensaje=error_message,
        recuperable=False,
        estado_final="failed",
        afecto_publicacion=False,
        requiere_revision_manual=False,
        queue_id=queue_id,
        db_url=_ABIS_DB_URL,
    )


def mark_queue_done(cur, queue_id: int) -> None:
    cur.execute(
        """
        UPDATE publish_queue
        SET status = 'done',
            error_message = NULL,
            last_attempt_at = now()
        WHERE id = %s
        """,
        [queue_id],
    )


def mark_staging_published(cur, staging_id: int) -> None:
    cur.execute(
        "UPDATE propiedades_staging SET status = 'published' WHERE id = %s",
        [staging_id],
    )


def publish_one(db: Any, prop: Dict[str, Any]) -> Tuple[int, int]:
    total, nuevas = db.save_propiedades([prop])
    if total <= 0:
        raise RuntimeError("save_propiedades no confirmo insercion/actualizacion")
    return total, nuevas


# ---------------------------------------------------------------------------
# Fase B.1 — Robustez: clasificación de errores, retry, reclaim, claim atómico
# ---------------------------------------------------------------------------

# Marcadores de error transitorio (reintentable). 429 SÍ es transitorio.
_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504",
    "timeout", "timed out", "connection reset", "connectionreset",
    "max retries", "remotedisconnected", "connection aborted",
    "temporarily unavailable", "10054", "read timed out",
)
# 4xx permanentes (NO reintentar). 429 se excluye explícitamente (es transitorio).
_PERMANENT_4XX = ("400", "401", "403", "404", "409", "422")


def is_transient_error(exc: Any) -> bool:
    """True si el error es transitorio (vale la pena reintentar). Conservador:
    ante un 4xx permanente (no-429) devuelve False y no se reintenta."""
    # Tipos de excepción de requests/urllib3 = transitorios de red.
    try:
        import requests  # type: ignore
        if isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout,
                            requests.exceptions.ChunkedEncodingError)):
            return True
    except Exception:
        pass
    if isinstance(exc, (ConnectionResetError, TimeoutError)):
        return True
    msg = str(exc or "").lower()
    if "429" in msg:
        return True  # rate-limit: transitorio
    if any(code in msg for code in _PERMANENT_4XX):
        return False  # 4xx permanente: no reintentar
    return any(m in msg for m in _TRANSIENT_MARKERS)


def publish_with_retry(
    db: Any,
    prop: Dict[str, Any],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    queue_id: Optional[int] = None,
    run_id: Optional[int] = None,
    worker: Optional[str] = None,
) -> Tuple[int, int, int]:
    """Publica con retry para transitorios. Devuelve (total, nuevas, reintentos).

    Idempotente: publish_one -> save_propiedades hace upsert por url_normalizada,
    así que reintentar no duplica. Re-lanza si el error es permanente o se agotan
    los retries (el caller marca failed). Cada retry/recuperación/agotamiento se
    registra en error_log (best-effort, nunca rompe).
    """
    attempt = 0
    while True:
        try:
            total, nuevas = publish_one(db, prop)
            if attempt > 0:
                _log_error(
                    fase="publish", error_type="transient_recovered",
                    severidad="warning", recuperable=True, reintentos=attempt,
                    accion_tomada="retry", estado_final="done",
                    afecto_publicacion=True, queue_id=queue_id, run_id=run_id,
                    worker=worker, db_url=_ABIS_DB_URL,
                    mensaje=f"recuperado tras {attempt} reintento(s)",
                )
            return total, nuevas, attempt
        except Exception as exc:
            transient = is_transient_error(exc)
            if not transient or attempt >= max_retries:
                _log_error(
                    fase="publish",
                    error_type=("transient_exhausted" if transient else "permanent_error"),
                    severidad="warning", recuperable=False, reintentos=attempt,
                    accion_tomada="give_up", estado_final="failed",
                    afecto_publicacion=False, queue_id=queue_id, run_id=run_id,
                    worker=worker, mensaje=str(exc), db_url=_ABIS_DB_URL,
                )
                raise
            attempt += 1
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter
            _log_error(
                fase="publish", error_type="transient_retry",
                severidad="warning", recuperable=True, reintentos=attempt,
                accion_tomada=f"retry_in_{delay:.1f}s", estado_final="retrying",
                afecto_publicacion=False, queue_id=queue_id, run_id=run_id,
                worker=worker, mensaje=str(exc), db_url=_ABIS_DB_URL,
            )
            time.sleep(delay)


def reclaim_stale_publishing(cur, older_than_minutes: int = 30, max_attempts: int = 5) -> int:
    """Devuelve a 'pending' las filas 'publishing' viejas (proceso anterior cortado).

    Incrementa attempts en cada reclaim para que NO se reintente infinito; las que
    ya alcanzaron max_attempts quedan en 'publishing' para revisión manual (no se
    resetean). Registra el reclaim en error_log. NO commitea (el caller commitea).
    """
    cur.execute(
        """
        UPDATE publish_queue
        SET status = 'pending',
            attempts = attempts + 1
        WHERE status = 'publishing'
          AND COALESCE(last_attempt_at, queued_at) < now() - make_interval(mins => %s)
          AND attempts < %s
        RETURNING id
        """,
        [older_than_minutes, max_attempts],
    )
    n = len(cur.fetchall())
    if n:
        _log_error(
            fase="publish", error_type="reclaim_stale_publishing",
            severidad="warning", recuperable=True, accion_tomada="reset_to_pending_attempts+1",
            estado_final="pending", afecto_publicacion=False, db_url=_ABIS_DB_URL,
            mensaje=f"reclamadas {n} filas publishing > {older_than_minutes}min",
        )
    return n


def claim_one_pending(cur, staging_ids_filter: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
    """Reclama UNA fila pending de forma atómica y la marca 'publishing'.

    FOR UPDATE SKIP LOCKED garantiza que dos workers nunca reclamen la misma fila.
    Retorna el dict de la fila o None si no hay pending. NO commitea (caller commitea).
    """
    extra = "AND staging_id = ANY(%(sids)s)" if staging_ids_filter else ""
    cur.execute(
        f"""
        UPDATE publish_queue
        SET status = 'publishing', last_attempt_at = now()
        WHERE id = (
            SELECT id FROM publish_queue
            WHERE status = 'pending' {extra}
            ORDER BY priority ASC, queued_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, staging_id, propiedad_supabase_id, action, priority, attempts, status
        """,
        {"sids": staging_ids_filter} if staging_ids_filter else {},
    )
    row = cur.fetchone()
    return dict(row) if row else None


def deactivate_one(db: Any, propiedad_supabase_id: int) -> None:
    """PATCH estado=no_detectada_en_ultimo_scraping en Supabase para una prop por ID.

    Usa la sesion autenticada del cliente db (SupabasePropiedades) para no
    duplicar la gestion de credenciales. Solo se llama cuando action='deactivate'.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    if not supabase_url:
        raise RuntimeError("SUPABASE_URL no esta configurada; no se puede deactivar.")
    r = db.session.patch(
        f"{supabase_url}/rest/v1/propiedades?id=eq.{propiedad_supabase_id}",
        headers=db._headers_minimal,
        json={"estado": "no_detectada_en_ultimo_scraping"},
        timeout=20,
    )
    if r.status_code not in (200, 204):
        raise RuntimeError(
            f"deactivate PATCH fallo: status={r.status_code} "
            f"prop_id={propiedad_supabase_id} body={r.text[:300]}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Publicar publish_queue pendiente desde Neon a Supabase")
    parser.add_argument("--limit", type=int, default=5, help="Cantidad maxima de filas de queue a evaluar")
    parser.add_argument("--max-supabase-writes", type=int, default=100, help="Maximo de escrituras Supabase")
    parser.add_argument("--min-score", type=int, default=0, help="Score minimo para publicar (0 = publicar todas las props validas)")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pausa despues de cada publicacion")
    parser.add_argument("--allow-pending-geo", dest="allow_pending_geo", action="store_true", default=True, help="Aceptar geocoding_status=pending (activo por defecto)")
    parser.add_argument("--no-allow-pending-geo", dest="allow_pending_geo", action="store_false", help="Requerir geocoding_status=done o skipped")
    parser.add_argument("--dry-run", action="store_true", help="Leer y validar sin escribir")
    parser.add_argument("--commit", action="store_true", help="Publicar y actualizar estados")
    parser.add_argument(
        "--staging-ids-file", type=str, default=None,
        help="CSV con columna 'staging_id' o 'id' — filtra la queue SOLO a esos staging IDs.",
    )
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Reintentos para errores transitorios por fila (default 3)")
    parser.add_argument("--reclaim-minutes", type=int, default=30,
                        help="Edad (min) para reclamar filas 'publishing' stale en preflight (default 30)")
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
    global _ABIS_DB_URL
    _ABIS_DB_URL = db_url  # habilita el insert best-effort en error_log (conexión efímera propia)
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
    deactivated_ok = 0
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
    retry_attempts = 0
    worker = f"pid{os.getpid()}"

    # ----------------------------------------------------------------------
    # DRY-RUN: SOLO lectura. NO reclaim, NO claim, NO publishing, NO REST,
    # NO done/failed. Solo informa lo que se publicaría; termina en rollback.
    # ----------------------------------------------------------------------
    if args.dry_run:
        with connect_internal_db(db_url) as conn:
            with conn.cursor() as cur:
                queue_rows = fetch_queue_rows(
                    cur, claim_limit, commit=False, staging_ids_filter=staging_ids_filter
                )
                rows_read = len(queue_rows)
                staging_ids = [int(r["staging_id"]) for r in queue_rows
                               if r.get("staging_id") is not None]
                staging_by_id = fetch_staging_rows(cur, staging_ids)
                for queue_row in queue_rows:
                    queue_id = int(queue_row["id"])
                    action = (clean_text(queue_row.get("action")) or "upsert").lower()
                    if action == "deactivate":
                        print(f"DRY-RUN would deactivate queue_id={queue_id} "
                              f"propiedad_supabase_id={queue_row.get('propiedad_supabase_id')}")
                        continue
                    staging_id = int(queue_row["staging_id"]) if queue_row.get("staging_id") is not None else 0
                    staging = staging_by_id.get(staging_id)
                    reason = validation_skip_reason(
                        staging, min_score=args.min_score, allow_pending_geo=args.allow_pending_geo
                    )
                    if reason:
                        skipped[reason] += 1
                        continue
                    prop = staging_to_prop(staging or {})
                    valid_props += 1
                    print(f"DRY-RUN would publish queue_id={queue_id} staging_id={staging_id} "
                          f"hash={prop.get('hash_dedup')} url={prop.get('url') or prop.get('url_normalizada')}")
            conn.rollback()
    else:
        # ------------------------------------------------------------------
        # COMMIT: Modelo B — reclaim preflight + claim atómico por fila +
        # commit por fila. Una fila claimada nunca queda 'publishing' tras
        # procesarse: termina 'done' o 'failed', siempre commiteada.
        # El cap --max-supabase-writes cuenta SOLO escrituras exitosas.
        # ------------------------------------------------------------------
        with connect_internal_db(db_url) as conn:
            with conn.cursor() as cur:
                reclaimed = reclaim_stale_publishing(cur, older_than_minutes=args.reclaim_minutes)
            conn.commit()
            if reclaimed:
                print(f"reclaim_stale_publishing={reclaimed}")

            processed = 0
            while processed < args.limit and writes_used < args.max_supabase_writes:
                # 1) claim atómico de UNA fila + commit (estado 'publishing' persistido)
                with conn.cursor() as cur:
                    queue_row = claim_one_pending(cur, staging_ids_filter)
                conn.commit()
                if queue_row is None:
                    break  # no hay más pending
                processed += 1
                rows_read += 1
                queue_id = int(queue_row["id"])
                action = (clean_text(queue_row.get("action")) or "upsert").lower()

                # 2) procesar la fila en su propia transacción (SIEMPRE commitea:
                #    nunca queda 'publishing' colgada)
                with conn.cursor() as cur:
                    if action == "deactivate":
                        sup_id_raw = queue_row.get("propiedad_supabase_id")
                        if not sup_id_raw:
                            skipped["deactivate_missing_supabase_id"] += 1
                            failed += 1
                            mark_queue_failed(cur, queue_id, "deactivate_missing_supabase_id")
                        else:
                            try:
                                deactivate_one(db, int(sup_id_raw))
                                writes_used += 1
                                deactivated_ok += 1
                                mark_queue_done(cur, queue_id)
                                if args.sleep:
                                    time.sleep(args.sleep)
                            except Exception as exc:
                                failed += 1
                                mark_queue_failed(cur, queue_id, truncate_error(exc))
                        conn.commit()
                        continue

                    # action='upsert' (default)
                    staging_id = int(queue_row["staging_id"]) if queue_row.get("staging_id") is not None else 0
                    staging_by_id = fetch_staging_rows(cur, [staging_id]) if staging_id else {}
                    staging = staging_by_id.get(staging_id)
                    reason = validation_skip_reason(
                        staging, min_score=args.min_score, allow_pending_geo=args.allow_pending_geo
                    )
                    if reason:
                        # Validación falla -> 'failed' (la fila NO queda 'publishing').
                        skipped[reason] += 1
                        failed += 1
                        mark_queue_failed(cur, queue_id, f"validation_failed:{reason}")
                        conn.commit()
                        continue
                    prop = staging_to_prop(staging or {})
                    valid_props += 1
                    try:
                        _t, _n, reint = publish_with_retry(
                            db, prop, max_retries=args.max_retries,
                            queue_id=queue_id, worker=worker,
                        )
                        retry_attempts += reint
                        writes_used += 1  # cap = solo escrituras exitosas
                        published_ok += 1
                        mark_queue_done(cur, queue_id)
                        mark_staging_published(cur, staging_id)
                        if args.sleep:
                            time.sleep(args.sleep)
                    except Exception as exc:
                        failed += 1
                        mark_queue_failed(cur, queue_id, exc)
                    conn.commit()

    print("-" * 72)
    print(f"filas_queue_leidas={rows_read}")
    print(f"props_validas={valid_props}")
    print(f"publicadas_ok={published_ok}")
    print(f"desactivadas_ok={deactivated_ok}")
    print(f"failed={failed}")
    print("omitidas_por_validacion:")
    if skipped:
        for reason, count in sorted(skipped.items()):
            print(f"  {reason}: {count}")
    else:
        print("  none: 0")
    print(f"writes_supabase_usados={writes_used}")
    print(f"retry_attempts={retry_attempts}")
    print(f"accion_final={action_final}")
    print("=" * 72)


if __name__ == "__main__":
    main()

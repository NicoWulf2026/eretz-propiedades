#!/usr/bin/env python
"""Create scraping_run_items from public.v_next_scraping_batch.

This script is intentionally narrow:
- v_next_scraping_batch.inmobiliaria_id is treated as inmobiliarias_main.id.
- Existing pending/running items are skipped.
- No scraping is executed here.

Use --dry-run first, then --commit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_VIEW = "v_next_scraping_batch"
ACTIVE_ITEM_STATUSES = {"pending", "running"}


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


def supabase_config() -> tuple[str, str]:
    load_env()
    base_url = (
        os.getenv("SUPABASE_URL")
        or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    if not base_url or not key:
        raise SystemExit("Faltan SUPABASE_URL/SUPABASE_KEY en el entorno.")
    return base_url, key


def internal_db_config() -> tuple[bool, str]:
    # La DB interna es deliberadamente opt-in para evitar activacion accidental:
    # requiere USE_INTERNAL_DB=true e INTERNAL_DB_URL. Tambien requiere schema y
    # funciones compatibles antes de usarse en corridas reales.
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    enabled = env_flag("USE_INTERNAL_DB", default=False) and bool(db_url)
    return enabled, db_url


class InternalRunDBClient:
    """Cliente minimo para crear scraping_runs/items en PostgreSQL interno."""

    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def _connect(self):
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "USE_INTERNAL_DB=true e INTERNAL_DB_URL esta configurado, "
                "pero falta instalar psycopg/psycopg-binary."
            ) from exc
        return psycopg.connect(self.db_url, row_factory=dict_row)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            try:
                from psycopg.types.json import Jsonb  # type: ignore
                return Jsonb(value)
            except Exception:
                return json.dumps(value, ensure_ascii=False)
        return value

    @staticmethod
    def _insert_sql(table: str, payload: Dict[str, Any], *, returning: bool = False) -> tuple[str, List[Any]]:
        columns = list(payload.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(columns)
        suffix = " RETURNING id" if returning else ""
        values = [InternalRunDBClient._json_value(payload[column]) for column in columns]
        return f"INSERT INTO public.{table} ({column_sql}) VALUES ({placeholders}){suffix}", values

    def fetch_existing_active_item_agency_ids(self) -> Set[int]:
        query = (
            "SELECT inmobiliaria_id FROM public.scraping_run_items "
            "WHERE status IN ('pending', 'running') ORDER BY created_at ASC"
        )
        result: Set[int] = set()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                for row in cur.fetchall():
                    try:
                        result.add(int(row["inmobiliaria_id"]))
                    except Exception:
                        continue
        return result

    def insert_run_and_items(
        self,
        *,
        run_payload: Dict[str, Any],
        item_candidates: Sequence[Dict[str, Any]],
        insert_batch_size: int,
    ) -> tuple[int, int]:
        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    run_sql, run_values = self._insert_sql("scraping_runs", run_payload, returning=True)
                    cur.execute(run_sql, run_values)
                    run_row = cur.fetchone()
                    if not run_row:
                        raise RuntimeError("La DB interna no devolvio la scraping_run creada.")
                    run_id = int(run_row["id"])
                    item_payloads = build_item_payloads(run_id, item_candidates)
                    inserted = 0
                    for batch in chunks(item_payloads, insert_batch_size):
                        if not batch:
                            continue
                        first = dict(batch[0])
                        columns = list(first.keys())
                        placeholders = ", ".join(["%s"] * len(columns))
                        column_sql = ", ".join(columns)
                        sql = f"INSERT INTO public.scraping_run_items ({column_sql}) VALUES ({placeholders})"
                        values = [
                            [self._json_value(dict(item).get(column)) for column in columns]
                            for item in batch
                        ]
                        cur.executemany(sql, values)
                        inserted += len(batch)
                conn.commit()
                return run_id, inserted
            except Exception:
                conn.rollback()
                raise


def make_headers(key: str, *, prefer: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    headers: Dict[str, str],
    params: Optional[Dict[str, Any]] = None,
    json_payload: Any = None,
    timeout: int = 30,
) -> Any:
    response = session.request(
        method,
        url,
        headers=headers,
        params=params,
        json=json_payload,
        timeout=timeout,
    )
    if response.status_code not in {200, 201, 204}:
        raise RuntimeError(f"{method} {url} fallo {response.status_code}: {response.text[:1000]}")
    if response.status_code == 204 or not response.text.strip():
        return None
    return response.json()


def fetch_all(
    session: requests.Session,
    base_url: str,
    key: str,
    table_or_view: str,
    *,
    params: Dict[str, Any],
    page_size: int = 1000,
    max_rows: Optional[int] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        limit = page_size
        if max_rows is not None:
            remaining = max_rows - len(rows)
            if remaining <= 0:
                break
            limit = min(limit, remaining)
        page_params = dict(params)
        page_params["limit"] = limit
        page_params["offset"] = offset
        page = request_json(
            session,
            "GET",
            f"{base_url}/rest/v1/{table_or_view}",
            headers=make_headers(key),
            params=page_params,
            timeout=45,
        )
        if not page:
            break
        rows.extend(page)
        if len(page) < limit:
            break
        offset += len(page)
    return rows


def fetch_existing_active_item_agency_ids(session: requests.Session, base_url: str, key: str) -> Set[int]:
    rows = fetch_all(
        session,
        base_url,
        key,
        "scraping_run_items",
        params={
            "select": "inmobiliaria_id,status",
            "status": "in.(pending,running)",
            "order": "created_at.asc",
        },
        page_size=1000,
    )
    result: Set[int] = set()
    for row in rows:
        try:
            result.add(int(row["inmobiliaria_id"]))
        except Exception:
            continue
    return result


_CANDIDATE_SELECT = (
    "inmobiliaria_id,nombre,ciudad,provincia,pais,web,url_listado,"
    "cms_detectado,estrategia_scraping,total_propiedades,"
    "total_propiedades_normalizado,prioridad_scraping_score,"
    "prioridad_scraping,lista_para_batch,tipo_paginacion,"
    "necesidades_detectadas,recomendacion,tiene_antibot"
)
_CANDIDATE_ORDER = (
    "prioridad_scraping_score.desc.nullslast,"
    "total_propiedades_normalizado.desc.nullslast,"
    "inmobiliaria_id.asc"
)


def _filter_and_collect(
    rows: List[Dict[str, Any]],
    selected: List[Dict[str, Any]],
    seen: Set[int],
    active_agency_ids: Set[int],
    desired_limit: int,
) -> None:
    for row in rows:
        if len(selected) >= desired_limit:
            break
        try:
            agency_id = int(row["inmobiliaria_id"])
        except Exception:
            continue
        if agency_id in active_agency_ids or agency_id in seen:
            continue
        if not row.get("web") and not row.get("url_listado"):
            continue
        if row.get("tiene_antibot"):
            continue
        seen.add(agency_id)
        selected.append(row)


def fetch_candidates(
    session: requests.Session,
    base_url: str,
    key: str,
    *,
    desired_limit: int,
    source_view: str,
    active_agency_ids: Set[int],
    include_new: bool = False,
) -> List[Dict[str, Any]]:
    # Primera pasada: agencias lista_para_batch=true
    rows = fetch_all(
        session,
        base_url,
        key,
        source_view,
        params={
            "select": _CANDIDATE_SELECT,
            "lista_para_batch": "eq.true",
            "order": _CANDIDATE_ORDER,
        },
        page_size=500,
        max_rows=max(desired_limit * 5, desired_limit + 100),
    )
    selected: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    _filter_and_collect(rows, selected, seen, active_agency_ids, desired_limit)

    # Segunda pasada: agencias nuevas (nunca scrapeadas o sin estrategia) si faltan lugares
    if include_new and len(selected) < desired_limit:
        remaining = desired_limit - len(selected)
        new_rows = fetch_all(
            session,
            base_url,
            key,
            source_view,
            params={
                "select": _CANDIDATE_SELECT,
                "lista_para_batch": "eq.false",
                "tiene_web": "eq.true",
                "tiene_antibot": "eq.false",
                "order": _CANDIDATE_ORDER,
            },
            page_size=500,
            max_rows=max(remaining * 5, remaining + 50),
        )
        _filter_and_collect(new_rows, selected, seen, active_agency_ids, desired_limit)

    return selected


def build_run_payload(limit: int, run_type: str, source_view: str, notes: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_type": run_type,
        "status": "running",
        "started_at": now,
        "total_inmobiliarias_planificadas": limit,
        "total_inmobiliarias_procesadas": 0,
        "total_inmobiliarias_exitosas": 0,
        "total_inmobiliarias_error": 0,
        "total_propiedades_detectadas": 0,
        "total_propiedades_nuevas": 0,
        "total_propiedades_actualizadas": 0,
        "total_propiedades_sin_cambios": 0,
        "total_propiedades_error": 0,
        "source_view": source_view,
        "notes": notes,
    }


def build_item_payloads(run_id: int, candidates: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    created_at = datetime.now(timezone.utc).isoformat()
    payloads: List[Dict[str, Any]] = []
    for row in candidates:
        metadata = {
            "created_from": "scripts/create_scraping_run_from_next_batch.py",
            "source_view": DEFAULT_SOURCE_VIEW,
            "batch_created_at": created_at,
            "priority": {
                "prioridad_scraping_score": row.get("prioridad_scraping_score"),
                "prioridad_scraping": row.get("prioridad_scraping"),
                "total_propiedades": row.get("total_propiedades"),
                "total_propiedades_normalizado": row.get("total_propiedades_normalizado"),
                "tipo_paginacion": row.get("tipo_paginacion"),
                "necesidades_detectadas": row.get("necesidades_detectadas"),
                "recomendacion": row.get("recomendacion"),
            },
            "id_space": {
                "inmobiliaria_id_source": "inmobiliarias_main.id",
                "propiedades_inmobiliaria_id_expected": "inmobiliarias_main.id",
            },
        }
        payloads.append({
            "scraping_run_id": run_id,
            "inmobiliaria_id": int(row["inmobiliaria_id"]),
            "inmobiliaria_nombre": row.get("nombre"),
            "ciudad": row.get("ciudad"),
            "provincia": row.get("provincia"),
            "web": row.get("web"),
            "url_listado": row.get("url_listado"),
            "cms_detectado": row.get("cms_detectado"),
            "status": "pending",
            "metadata": metadata,
        })
    return payloads


def chunks(values: Sequence[Dict[str, Any]], size: int) -> Iterable[Sequence[Dict[str, Any]]]:
    for idx in range(0, len(values), size):
        yield values[idx:idx + size]


def insert_run_and_items(
    session: requests.Session,
    base_url: str,
    key: str,
    *,
    run_payload: Dict[str, Any],
    item_candidates: Sequence[Dict[str, Any]],
    insert_batch_size: int,
) -> tuple[int, int]:
    run_rows = request_json(
        session,
        "POST",
        f"{base_url}/rest/v1/scraping_runs",
        headers=make_headers(key, prefer="return=representation"),
        json_payload=run_payload,
        timeout=30,
    )
    if not isinstance(run_rows, list) or not run_rows:
        raise RuntimeError("Supabase no devolvio la scraping_run creada.")
    run_id = int(run_rows[0]["id"])
    item_payloads = build_item_payloads(run_id, item_candidates)
    inserted = 0
    try:
        for batch in chunks(item_payloads, insert_batch_size):
            rows = request_json(
                session,
                "POST",
                f"{base_url}/rest/v1/scraping_run_items",
                headers=make_headers(key, prefer="return=representation"),
                json_payload=list(batch),
                timeout=60,
            )
            inserted += len(rows or batch)
    except Exception:
        try:
            request_json(
                session,
                "PATCH",
                f"{base_url}/rest/v1/scraping_runs",
                headers=make_headers(key),
                params={"id": f"eq.{run_id}"},
                json_payload={
                    "status": "error",
                    "notes": f"{run_payload.get('notes') or ''} | Fallo insertando items; revisar run incompleta.",
                },
                timeout=20,
            )
        finally:
            raise
    return run_id, inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear scraping_run desde v_next_scraping_batch")
    parser.add_argument("--limit", type=int, default=100, help="Cantidad de items a crear")
    parser.add_argument("--source-view", default=DEFAULT_SOURCE_VIEW, help="Vista origen")
    parser.add_argument("--run-type", default=None, help="run_type explicito")
    parser.add_argument("--notes", default=None, help="Notas para scraping_runs")
    parser.add_argument("--insert-batch-size", type=int, default=100, help="Tamanio de insert de items")
    parser.add_argument("--dry-run", action="store_true", help="No escribe en Supabase")
    parser.add_argument("--commit", action="store_true", help="Crear la run y los items")
    parser.add_argument(
        "--include-new", action="store_true",
        help="Complementar con agencias nuevas (lista_para_batch=false, tienen web, sin antibot) si no hay suficientes listas",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")
    if args.insert_batch_size <= 0:
        raise SystemExit("--insert-batch-size debe ser mayor a 0")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    base_url, key = supabase_config()
    use_internal_db, internal_db_url = internal_db_config()
    session = requests.Session()
    internal_client = InternalRunDBClient(internal_db_url) if use_internal_db else None

    if internal_client:
        print("[internal-db] enabled: creating scraping_runs/items in INTERNAL_DB_URL")
        active_agency_ids = internal_client.fetch_existing_active_item_agency_ids()
    elif os.getenv("INTERNAL_DB_URL", "").strip() and not env_flag("USE_INTERNAL_DB", default=False):
        print("[internal-db] disabled: USE_INTERNAL_DB is not true; creating queue in Supabase")
        active_agency_ids = fetch_existing_active_item_agency_ids(session, base_url, key)
    else:
        print("[internal-db] disabled: creating queue in Supabase")
        active_agency_ids = fetch_existing_active_item_agency_ids(session, base_url, key)
    candidates = fetch_candidates(
        session,
        base_url,
        key,
        desired_limit=args.limit,
        source_view=args.source_view,
        active_agency_ids=active_agency_ids,
        include_new=args.include_new,
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_type = args.run_type or f"auto_batch_{args.limit}_{ts}"
    notes = args.notes or (
        f"Tanda automatica de {args.limit} inmobiliarias desde {args.source_view}; "
        "IDs canonicos inmobiliarias_main.id."
    )
    run_payload = build_run_payload(len(candidates), run_type, args.source_view, notes)

    print("=" * 72)
    print("CREATE SCRAPING RUN FROM NEXT BATCH")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"queue_target={'internal_db' if internal_client else 'supabase'}")
    print(f"source_view={args.source_view}")
    print(f"requested_limit={args.limit}")
    print(f"active_pending_or_running_agencies={len(active_agency_ids)}")
    print(f"include_new={args.include_new}")
    print(f"selected_candidates={len(candidates)}")
    print(f"run_type={run_type}")
    print("-" * 72)
    for row in candidates[:20]:
        print(
            f"{row.get('inmobiliaria_id')} | {row.get('nombre')} | "
            f"{row.get('cms_detectado') or '-'} | score={row.get('prioridad_scraping_score')} | "
            f"web={row.get('url_listado') or row.get('web')}"
        )
    if len(candidates) > 20:
        print(f"... {len(candidates) - 20} mas")

    if len(candidates) < args.limit:
        print(f"WARNING: solo hay {len(candidates)} candidatos disponibles para limit={args.limit}.")

    if args.dry_run:
        print("DRY-RUN: no se creo scraping_run ni scraping_run_items.")
        print("=" * 72)
        return

    if internal_client:
        run_id, inserted = internal_client.insert_run_and_items(
            run_payload=run_payload,
            item_candidates=candidates,
            insert_batch_size=args.insert_batch_size,
        )
    else:
        run_id, inserted = insert_run_and_items(
            session,
            base_url,
            key,
            run_payload=run_payload,
            item_candidates=candidates,
            insert_batch_size=args.insert_batch_size,
        )
    print("-" * 72)
    print(f"CREATED run_id={run_id}")
    print(f"INSERTED scraping_run_items={inserted}")
    print("=" * 72)


if __name__ == "__main__":
    main()

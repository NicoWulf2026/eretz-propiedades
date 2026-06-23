#!/usr/bin/env python
"""Crear un scraping_run de REINTENTO copiando items de error previos.

Lee filas de ``internal_scraping.scraping_run_items`` con ``status='error'`` y un
``error_type`` permitido (familia timeout), y crea un nuevo ``scraping_run`` con
nuevos ``scraping_run_items`` en ``status='pending'`` copiando los datos
historicos. No depende de ``v_next_scraping_batch``, no hace backfill, no toca
``inmobiliarias_scraping`` ni ``public.propiedades``, no corre scraping ni
Playwright.

Modo dry-run por default: sin ``--commit`` no escribe nada.

Uso tipico:

    python scripts/create_retry_run_from_error_items.py \
        --ids-file timeouts5.csv --error-type timeout \
        --limit 5 --source-run-min 16 --source-run-max 63 --dry-run

Solo INTERNAL_DB_URL (schema internal_scraping). Nunca lee/escribe Supabase REST
ni Neon directamente fuera de INTERNAL_DB_URL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Reglas de seguridad (constantes puras, testeables sin DB)
# ---------------------------------------------------------------------------
ALLOWED_ERROR_TYPES = frozenset({"timeout", "item_timeout", "static_timeout"})

# Rechazo explicito (para mensajes claros; cualquier otro tampoco se permite).
REJECTED_ERROR_TYPES = frozenset({
    "requires_playwright",
    "site_down_confirmed",
    "skipped_invalid_source",
    "no_property_links",
    "no_property_links_confirmed",
    "sin_propiedades",
    "strategy_quality_failed",
})

PROHIBITED_CMS = frozenset({"zonaprop", "argenprop"})

ITEM_COPY_FIELDS = (
    "inmobiliaria_id",
    "inmobiliaria_nombre",
    "ciudad",
    "provincia",
    "web",
    "url_listado",
    "cms_detectado",
)

CREATED_FROM = "create_retry_run_from_error_items"


# ---------------------------------------------------------------------------
# Funciones puras (sin DB) — el grueso de los tests apunta aca
# ---------------------------------------------------------------------------
def parse_error_types(raw: Optional[str]) -> List[str]:
    """Parsea ``--error-type`` (coma-separado) y valida contra la allowlist.

    Lanza SystemExit con mensaje claro si algun valor no esta permitido.
    """
    if not raw:
        return sorted(ALLOWED_ERROR_TYPES)
    values = [v.strip() for v in str(raw).split(",") if v.strip()]
    if not values:
        return sorted(ALLOWED_ERROR_TYPES)
    invalid = [v for v in values if v not in ALLOWED_ERROR_TYPES]
    if invalid:
        raise SystemExit(
            "--error-type invalido: "
            + ", ".join(invalid)
            + f". Permitidos: {', '.join(sorted(ALLOWED_ERROR_TYPES))}"
        )
    # dedup preservando orden estable
    return sorted(set(values))


def skip_reason_for_row(row: Dict[str, Any], allowed_types: Sequence[str]) -> Optional[str]:
    """Devuelve el motivo de skip (str) o None si la fila es elegible.

    Reglas: error_type permitido, web y url_listado presentes, cms no prohibido.
    """
    error_type = str(row.get("error_type") or "").strip()
    if error_type not in set(allowed_types):
        if error_type in REJECTED_ERROR_TYPES:
            return f"error_type_rechazado:{error_type}"
        return f"error_type_no_permitido:{error_type or 'null'}"
    web = str(row.get("web") or "").strip()
    if not web:
        return "sin_web"
    url_listado = str(row.get("url_listado") or "").strip()
    if not url_listado:
        return "sin_url_listado"
    cms = str(row.get("cms_detectado") or "").strip().lower()
    if cms in PROHIBITED_CMS:
        return f"cms_prohibido:{cms}"
    return None


def build_retry_item_payload(
    run_id: int,
    row: Dict[str, Any],
    notes: Optional[str],
    created_at_iso: str,
) -> Dict[str, Any]:
    """Construye el payload de un scraping_run_items nuevo copiando la fila de error."""
    metadata = {
        "created_from": CREATED_FROM,
        "retry_of_run_id": row.get("scraping_run_id"),
        "original_run_item_id": row.get("id"),
        "original_error_type": row.get("error_type"),
        "created_at": created_at_iso,
        "notes": notes,
    }
    payload: Dict[str, Any] = {
        "scraping_run_id": run_id,
        "status": "pending",
        "metadata": metadata,
    }
    for field in ITEM_COPY_FIELDS:
        payload[field] = row.get(field)
    payload["inmobiliaria_id"] = int(row["inmobiliaria_id"])
    return payload


def select_candidates(
    rows: Sequence[Dict[str, Any]],
    allowed_types: Sequence[str],
    existing_pending_ids: set,
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filtra filas de error en (a_crear, skips). Pura, sin DB.

    - Aplica skip_reason_for_row.
    - Dedup contra pending existentes y contra ya seleccionadas en este lote.
    - Respeta limit.
    """
    to_create: List[Dict[str, Any]] = []
    skips: List[Dict[str, Any]] = []
    seen_agency_ids: set = set()
    for row in rows:
        if len(to_create) >= max(int(limit), 0) and limit > 0:
            break
        reason = skip_reason_for_row(row, allowed_types)
        if reason is not None:
            skips.append({"row": row, "reason": reason})
            continue
        try:
            agency_id = int(row["inmobiliaria_id"])
        except (TypeError, ValueError, KeyError):
            skips.append({"row": row, "reason": "inmobiliaria_id_invalido"})
            continue
        if agency_id in existing_pending_ids:
            skips.append({"row": row, "reason": "ya_tiene_pending"})
            continue
        if agency_id in seen_agency_ids:
            skips.append({"row": row, "reason": "duplicado_en_lote"})
            continue
        seen_agency_ids.add(agency_id)
        to_create.append(row)
    return to_create, skips


def load_ids_file(path: Path) -> List[int]:
    """Carga IDs desde CSV con header 'id' o 'inmobiliaria_id'."""
    if not path.exists():
        raise SystemExit(f"--ids-file no encontrado: {path}")
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        key = "inmobiliaria_id" if "inmobiliaria_id" in cols else ("id" if "id" in cols else None)
        if key is None:
            raise SystemExit(
                f"--ids-file debe tener header 'id' o 'inmobiliaria_id'. Columnas: {cols}"
            )
        ids = [int(r[key]) for r in reader if str(r.get(key, "")).strip().lstrip("-").isdigit()]
    if not ids:
        raise SystemExit("--ids-file no contiene IDs validos")
    return ids


# ---------------------------------------------------------------------------
# Capa DB (psycopg, INTERNAL_DB_URL) — fina, separada de la logica pura
# ---------------------------------------------------------------------------
def _connect():
    import psycopg  # import diferido: los tests de logica pura no requieren psycopg

    try:
        from dotenv import load_dotenv  # import diferido
        load_dotenv(REPO_ROOT / ".env")
    except Exception:
        pass

    url = os.environ.get("INTERNAL_DB_URL", "").strip()
    if not url:
        raise SystemExit("INTERNAL_DB_URL no esta definido en el entorno")
    schema = os.environ.get("INTERNAL_DB_SCHEMA", "internal_scraping").strip() or "internal_scraping"
    conn = psycopg.connect(url, autocommit=False)
    conn.execute(f"SET search_path TO {schema}, public")
    return conn


def fetch_error_rows(
    cur,
    allowed_types: Sequence[str],
    ids: Optional[Sequence[int]],
    run_min: Optional[int],
    run_max: Optional[int],
    fetch_limit: int,
) -> List[Dict[str, Any]]:
    """Lee la ultima fila de error por inmobiliaria que matchea los filtros."""
    clauses = ["status = 'error'", "error_type = ANY(%s)"]
    params: List[Any] = [list(allowed_types)]
    if ids:
        clauses.append("inmobiliaria_id = ANY(%s)")
        params.append(list(ids))
    if run_min is not None:
        clauses.append("scraping_run_id >= %s")
        params.append(run_min)
    if run_max is not None:
        clauses.append("scraping_run_id <= %s")
        params.append(run_max)
    where_sql = " AND ".join(clauses)
    sql = f"""
        SELECT DISTINCT ON (inmobiliaria_id)
               id, scraping_run_id, inmobiliaria_id, inmobiliaria_nombre,
               ciudad, provincia, web, url_listado, cms_detectado, error_type
        FROM scraping_run_items
        WHERE {where_sql}
        ORDER BY inmobiliaria_id, scraping_run_id DESC, id DESC
        LIMIT %s
    """
    params.append(max(int(fetch_limit), 1))
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def fetch_pending_agency_ids(cur) -> set:
    cur.execute("SELECT DISTINCT inmobiliaria_id FROM scraping_run_items WHERE status='pending'")
    return {int(r[0]) for r in cur.fetchall() if r[0] is not None}


def count_pending(cur) -> int:
    cur.execute("SELECT COUNT(*) FROM scraping_run_items WHERE status='pending'")
    return int(cur.fetchone()[0])


def insert_retry_run(cur, run_type: str, notes: Optional[str], planned: int) -> int:
    cur.execute(
        """
        INSERT INTO scraping_runs
            (run_type, status, started_at, total_inmobiliarias_planificadas, source_view, notes)
        VALUES (%s, 'running', now(), %s, %s, %s)
        RETURNING id
        """,
        [run_type, planned, "scraping_run_items(error)", notes],
    )
    return int(cur.fetchone()[0])


def insert_retry_items(cur, payloads: Sequence[Dict[str, Any]]) -> int:
    inserted = 0
    for p in payloads:
        cur.execute(
            """
            INSERT INTO scraping_run_items
                (scraping_run_id, inmobiliaria_id, inmobiliaria_nombre, ciudad, provincia,
                 web, url_listado, cms_detectado, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                p["scraping_run_id"], p["inmobiliaria_id"], p.get("inmobiliaria_nombre"),
                p.get("ciudad"), p.get("provincia"), p.get("web"), p.get("url_listado"),
                p.get("cms_detectado"), "pending", json.dumps(p["metadata"]),
            ],
        )
        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crear scraping_run de reintento desde scraping_run_items con error (familia timeout)"
    )
    parser.add_argument("--ids-file", type=Path, help="CSV con header 'id' o 'inmobiliaria_id' (scope exacto)")
    parser.add_argument("--error-type", type=str, default=None,
                        help="Coma-separado; allowlist: timeout,item_timeout,static_timeout")
    parser.add_argument("--limit", type=int, default=5, help="Maximo de items a crear")
    parser.add_argument("--source-run-min", type=int, default=None, help="run_id origen minimo")
    parser.add_argument("--source-run-max", type=int, default=None, help="run_id origen maximo")
    parser.add_argument("--dry-run", action="store_true", help="No escribe (default si no se pasa --commit)")
    parser.add_argument("--commit", action="store_true", help="Crear run e items reales")
    parser.add_argument("--notes", type=str, default=None, help="Notas para el run/items")
    args = parser.parse_args()

    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.commit:
        args.dry_run = True  # default seguro
    if args.limit <= 0:
        raise SystemExit("--limit debe ser mayor a 0")

    allowed_types = parse_error_types(args.error_type)
    ids = load_ids_file(args.ids_file) if args.ids_file else None
    created_at_iso = datetime.now(timezone.utc).isoformat()

    print("=" * 72)
    print("CREATE RETRY RUN FROM ERROR ITEMS")
    print(f"mode={'commit' if args.commit else 'dry-run'}")
    print(f"error_types={allowed_types}")
    print(f"ids_file={args.ids_file or '-'} ({len(ids) if ids else 0} IDs)")
    print(f"source_run_range=[{args.source_run_min}, {args.source_run_max}]")
    print(f"limit={args.limit}")
    print("target=internal_db (scraping_run_items error -> nuevo run pending)")
    print("-" * 72)

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # fetch_limit holgado para poder descartar y aun llenar limit
            fetch_limit = max(int(args.limit) * 8, 50)
            rows = fetch_error_rows(
                cur, allowed_types, ids, args.source_run_min, args.source_run_max, fetch_limit
            )
            existing_pending = fetch_pending_agency_ids(cur)
            global_pending = count_pending(cur)

        to_create, skips = select_candidates(rows, allowed_types, existing_pending, args.limit)

        if global_pending > 0:
            print(f"ADVERTENCIA: hay {global_pending} scraping_run_items en 'pending' (el scraper toma todos los pending).")

        print(f"candidatos_leidos={len(rows)}")
        print(f"a_crear={len(to_create)}")
        print(f"skips={len(skips)}")
        if skips:
            from collections import Counter
            reasons = Counter(s["reason"] for s in skips)
            for reason, cnt in reasons.most_common():
                print(f"  skip[{reason}]={cnt}")

        print("-" * 72)
        print("ITEMS A CREAR:")
        payloads_preview = [build_retry_item_payload(0, r, args.notes, created_at_iso) for r in to_create]
        for r, p in zip(to_create, payloads_preview):
            print(
                f"  inmo={r['inmobiliaria_id']} | {str(r.get('inmobiliaria_nombre'))[:28]:<28}"
                f" | err_orig={r.get('error_type')} run_orig={r.get('scraping_run_id')}"
                f" | cms={r.get('cms_detectado')} | {str(r.get('web'))[:38]}"
            )
            print(f"        url_listado={r.get('url_listado')}")

        if not args.commit:
            print("-" * 72)
            print("DRY-RUN: no se creo scraping_run ni scraping_run_items.")
            conn.rollback()
            print("accion_final=rollback")
            return

        if not to_create:
            print("Nada para crear; no se crea run vacio.")
            conn.rollback()
            print("accion_final=rollback")
            return

        with conn.cursor() as cur:
            run_type = "retry_error_items"
            run_id = insert_retry_run(cur, run_type, args.notes, len(to_create))
            payloads = [build_retry_item_payload(run_id, r, args.notes, created_at_iso) for r in to_create]
            inserted = insert_retry_items(cur, payloads)
        conn.commit()
        print("-" * 72)
        print(f"created_run_id={run_id}")
        print(f"inserted_items={inserted}")
        print("accion_final=commit")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Encolar desactivaciones de propiedades que desaparecieron del listado.

Compara las propiedades publicadas en Supabase (estado activa/activo) para una
inmobiliaria con los hash_dedup de su ultimo scraping exitoso en Neon. Las que
estan en Supabase pero no en el ultimo scraping se encolan como action='deactivate'
en publish_queue para ser procesadas por publish_to_supabase.py.

Esta logica es complementaria (y auditada) a mark_inactivos() del scraper.
mark_inactivos() actua en linea durante el scraping; este script puede correr
despues del scraping para revisar lo que quedo pendiente o en corridas de
reconciliacion manuales.

Restricciones de seguridad:
- Solo lee datos (dry-run).
- Con --commit escribe solo en Neon (publish_queue), no toca Supabase ni staging.
- No borra ni modifica propiedades; solo agrega entradas a la cola.
- Requiere USE_INTERNAL_DB=true e INTERNAL_DB_URL.

Uso tipico:
    python scripts/enqueue_deactivations.py --inmobiliaria-id 3531 --dry-run
    python scripts/enqueue_deactivations.py --inmobiliaria-id 3531 --commit
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]

# FASE 1 Sprint B/C: estados que se consideran "activas" en Supabase para el
# baseline de comparacion. "desconocida" no se incluye — no sabemos si estaba
# activa o no, asi que no la deactivamos por ausencia.
BASELINE_ESTADOS = {"activa", "activo"}


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
        raise SystemExit("USE_INTERNAL_DB no esta en true; abortando.")
    if not db_url:
        raise SystemExit("Falta INTERNAL_DB_URL; abortando.")
    return db_url


def supabase_config() -> tuple[str, str]:
    base_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    )
    if not base_url or not key:
        raise SystemExit("Faltan SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY en el entorno.")
    return base_url, key


def internal_db_schema() -> str:
    """Schema interno. Default 'public' (Neon); 'internal_scraping' para Supabase."""
    schema = (os.getenv("INTERNAL_DB_SCHEMA", "public").strip() or "public")
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
        raise SystemExit(f"INTERNAL_DB_SCHEMA invalido: {schema!r}")
    return schema


def connect_internal_db(db_url: str):
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Falta instalar psycopg/psycopg-binary.") from exc
    conn = psycopg.connect(db_url, row_factory=dict_row)
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {internal_db_schema()}")
    return conn


# ---------------------------------------------------------------------------
# Neon: obtener hashes del ultimo scraping exitoso para una inmobiliaria
# ---------------------------------------------------------------------------

LAST_RUN_HASHES_SQL = """
SELECT DISTINCT pr.hash_dedup
FROM propiedades_raw pr
JOIN scraping_run_items sri ON sri.id = pr.scraping_run_item_id
WHERE sri.inmobiliaria_id = %s
  AND sri.status = 'success'
  AND sri.scraping_run_id = (
      SELECT MAX(sri2.scraping_run_id)
      FROM scraping_run_items sri2
      WHERE sri2.inmobiliaria_id = %s
        AND sri2.status = 'success'
  )
  AND pr.hash_dedup IS NOT NULL
"""

LAST_RUN_INFO_SQL = """
SELECT
  sri.id             AS item_id,
  sri.scraping_run_id,
  sri.status,
  sri.finished_at,
  sri.propiedades_detectadas,
  sri.metadata,
  sr.run_type,
  sr.started_at      AS run_started_at
FROM scraping_run_items sri
JOIN scraping_runs sr ON sr.id = sri.scraping_run_id
WHERE sri.inmobiliaria_id = %s
  AND sri.status = 'success'
ORDER BY sri.scraping_run_id DESC
LIMIT 1
"""

EXISTING_DEACTIVATE_SQL = """
SELECT propiedad_supabase_id
FROM publish_queue
WHERE action = 'deactivate'
  AND status IN ('pending', 'publishing', 'done')
  AND propiedad_supabase_id = ANY(%s)
"""


def _parse_metadata(raw: Any) -> Dict[str, Any]:
    """Convierte el campo metadata (dict, str JSON o None) a dict seguro."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _is_partial_run(
    run_info: Optional[Dict[str, Any]],
    min_ratio: float,
) -> Tuple[bool, str]:
    """Retorna (es_parcial, razon) para proteger contra falsas deactivations.

    Checks en orden de prioridad:
    1. metadata.partial_extraction == True  (flag explícito del scraper)
    2. metadata.completion_ratio < min_ratio
    3. propiedades_detectadas / metadata.expected_count < min_ratio (fallback)
    """
    if not run_info:
        return False, ""

    meta = _parse_metadata(run_info.get("metadata"))

    # Check 1: flag explícito del scraper
    if meta.get("partial_extraction"):
        ratio = meta.get("completion_ratio")
        ratio_str = f"{ratio:.3f}" if ratio is not None else "?"
        return True, f"partial_extraction=True completion_ratio={ratio_str}"

    # Check 2: completion_ratio vs umbral configurable
    raw_ratio = meta.get("completion_ratio")
    if raw_ratio is not None:
        try:
            ratio = float(raw_ratio)
            if ratio < min_ratio:
                return True, f"completion_ratio={ratio:.3f} < min_ratio={min_ratio}"
        except (TypeError, ValueError):
            pass

    # Check 3: detectadas / expected_count como fallback
    expected = meta.get("expected_count") or meta.get("expected_properties_count")
    detectadas = run_info.get("propiedades_detectadas")
    if expected and detectadas is not None:
        try:
            ratio_calc = int(detectadas) / int(expected)
            if ratio_calc < min_ratio:
                return (
                    True,
                    f"detectadas={detectadas} expected={expected} "
                    f"ratio={ratio_calc:.3f} < min_ratio={min_ratio}",
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    return False, ""


def fetch_last_run_hashes(cur, inmobiliaria_id: int) -> Set[str]:
    cur.execute(LAST_RUN_HASHES_SQL, [inmobiliaria_id, inmobiliaria_id])
    return {str(row["hash_dedup"]) for row in cur.fetchall() if row["hash_dedup"]}


def fetch_last_run_info(cur, inmobiliaria_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(LAST_RUN_INFO_SQL, [inmobiliaria_id])
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_existing_deactivate_ids(cur, supabase_ids: List[int]) -> Set[int]:
    if not supabase_ids:
        return set()
    cur.execute(EXISTING_DEACTIVATE_SQL, [supabase_ids])
    return {int(row["propiedad_supabase_id"]) for row in cur.fetchall() if row["propiedad_supabase_id"]}


# ---------------------------------------------------------------------------
# Supabase REST: obtener props activas de una inmobiliaria
# ---------------------------------------------------------------------------

def fetch_active_supabase_props(
    session: requests.Session,
    base_url: str,
    key: str,
    inmobiliaria_id: int,
) -> List[Dict[str, Any]]:
    """Devuelve [{id, hash_dedup, url, estado}] para props activas en Supabase."""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }
    estados_filter = "in.(" + ",".join(BASELINE_ESTADOS) + ")"
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        r = session.get(
            f"{base_url}/rest/v1/propiedades",
            headers=headers,
            params={
                "select": "id,hash_dedup,url,estado",
                "inmobiliaria_id": f"eq.{inmobiliaria_id}",
                "estado": estados_filter,
                "limit": page_size,
                "offset": offset,
            },
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(
                f"Supabase query fallo: status={r.status_code} body={r.text[:300]}"
            )
        page = r.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return rows


# ---------------------------------------------------------------------------
# Neon: insertar entradas en publish_queue
# ---------------------------------------------------------------------------

def insert_deactivate_entry(cur, propiedad_supabase_id: int) -> None:
    cur.execute(
        """
        INSERT INTO publish_queue (
            staging_id,
            propiedad_supabase_id,
            action,
            priority,
            attempts,
            status
        ) VALUES (NULL, %s, 'deactivate', 3, 0, 'pending')
        """,
        [propiedad_supabase_id],
    )


# ---------------------------------------------------------------------------
# Neon: obtener agencias de una corrida especifica
# ---------------------------------------------------------------------------

RUN_AGENCY_IDS_SQL = """
SELECT DISTINCT inmobiliaria_id
FROM scraping_run_items
WHERE scraping_run_id = %s
  AND status = 'success'
ORDER BY inmobiliaria_id
"""


def fetch_run_agency_ids(cur, scraping_run_id: int) -> List[int]:
    """Retorna IDs de inmobiliarias con scraping exitoso en la corrida indicada."""
    cur.execute(RUN_AGENCY_IDS_SQL, [scraping_run_id])
    return [int(row["inmobiliaria_id"]) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Procesamiento por agencia (helper compartido entre modos)
# ---------------------------------------------------------------------------

def process_agency(
    cur,
    session: requests.Session,
    base_url: str,
    key: str,
    inmobiliaria_id: int,
    *,
    dry_run: bool,
    verbose: bool = False,
    min_completion_ratio: float = 0.5,
) -> Dict[str, int]:
    """Procesa una inmobiliaria; retorna counters con {enqueued, disappeared,
    already_queued, no_run, error, skipped_partial}."""
    counters: Dict[str, int] = {
        "enqueued": 0,
        "disappeared": 0,
        "already_queued": 0,
        "no_run": 0,
        "error": 0,
        "skipped_partial": 0,
    }

    run_info = fetch_last_run_info(cur, inmobiliaria_id)
    if not run_info:
        print(f"  inm={inmobiliaria_id}: no hay scraping exitoso en Neon.")
        counters["no_run"] = 1
        return counters

    # Proteccion: no encolar deactivations si la extraccion fue parcial.
    # Mismo criterio que mark_inactivos() en el scraper.
    is_partial, partial_reason = _is_partial_run(run_info, min_completion_ratio)
    if is_partial:
        print(
            f"  inm={inmobiliaria_id} run_id={run_info['scraping_run_id']}: "
            f"SKIP deactivations — extraccion parcial / {partial_reason}"
        )
        counters["skipped_partial"] = 1
        return counters

    last_hashes = fetch_last_run_hashes(cur, inmobiliaria_id)
    if verbose:
        print(
            f"  inm={inmobiliaria_id} run_id={run_info['scraping_run_id']} "
            f"hashes={len(last_hashes)} finished_at={run_info['finished_at']}"
        )

    try:
        supabase_props = fetch_active_supabase_props(session, base_url, key, inmobiliaria_id)
    except Exception as exc:
        print(f"  inm={inmobiliaria_id} ERROR Supabase: {exc}")
        counters["error"] = 1
        return counters

    disappeared: List[Dict[str, Any]] = [
        prop for prop in supabase_props
        if not str(prop.get("hash_dedup") or "")
        or str(prop.get("hash_dedup") or "") not in last_hashes
    ]
    counters["disappeared"] = len(disappeared)

    if not disappeared:
        if verbose:
            print(f"  inm={inmobiliaria_id}: ninguna desaparecida (activas={len(supabase_props)})")
        return counters

    sup_ids = [int(p["id"]) for p in disappeared if p.get("id")]
    already_queued_ids = fetch_existing_deactivate_ids(cur, sup_ids)
    to_enqueue = [p for p in disappeared if int(p.get("id", 0)) not in already_queued_ids]
    counters["already_queued"] = len(already_queued_ids)

    if verbose:
        print(
            f"  inm={inmobiliaria_id} activas={len(supabase_props)} "
            f"desaparecidas={len(disappeared)} ya_en_cola={len(already_queued_ids)} "
            f"a_encolar={len(to_enqueue)}"
        )

    if dry_run:
        return counters

    enqueued = 0
    for item in to_enqueue:
        try:
            insert_deactivate_entry(cur, int(item["id"]))
            enqueued += 1
        except Exception as exc:
            print(f"  inm={inmobiliaria_id} ERROR encolando sup_id={item.get('id')}: {exc}")
    counters["enqueued"] = enqueued
    return counters


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encolar desactivaciones de props desaparecidas del ultimo scraping"
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--inmobiliaria-id",
        type=int,
        default=None,
        help="ID de la inmobiliaria a revisar (modo individual)",
    )
    mode_group.add_argument(
        "--all-from-run",
        type=int,
        default=None,
        metavar="RUN_ID",
        help="Procesar todas las inmobiliarias con scraping exitoso en la corrida RUN_ID",
    )
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no escribir")
    parser.add_argument("--commit", action="store_true", help="Insertar en publish_queue")
    parser.add_argument(
        "--min-completion-ratio",
        type=float,
        default=0.5,
        metavar="RATIO",
        help=(
            "Umbral minimo de completitud de extraccion (0-1). Si el run tuvo "
            "completion_ratio menor a este valor se omiten las deactivations para "
            "esa agencia. Default: 0.5"
        ),
    )
    args = parser.parse_args()

    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos.")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    db_url = internal_db_config()
    base_url, key = supabase_config()
    session = requests.Session()

    if args.all_from_run is not None:
        # ---------------------------------------------------------------
        # Modo batch: todas las agencias de una corrida
        # ---------------------------------------------------------------
        print("=" * 72)
        print("ENQUEUE DEACTIVATIONS — ALL FROM RUN")
        print(f"mode={'commit' if args.commit else 'dry-run'}")
        print(f"scraping_run_id={args.all_from_run}")
        print(f"baseline_estados={sorted(BASELINE_ESTADOS)}")
        print(f"min_completion_ratio={args.min_completion_ratio}")
        print("-" * 72)

        with connect_internal_db(db_url) as conn:
            with conn.cursor() as cur:
                agency_ids = fetch_run_agency_ids(cur, args.all_from_run)
            conn.rollback()

        if not agency_ids:
            print(f"RESULTADO: no hay items 'success' en scraping_run_id={args.all_from_run}.")
            print("=" * 72)
            return

        print(f"agencias_a_procesar={len(agency_ids)}")
        print("-" * 72)

        total_disappeared = 0
        total_already_queued = 0
        total_enqueued = 0
        total_no_run = 0
        total_errors = 0
        total_skipped_partial = 0

        for inm_id in agency_ids:
            with connect_internal_db(db_url) as conn:
                with conn.cursor() as cur:
                    counters = process_agency(
                        cur, session, base_url, key, inm_id,
                        dry_run=args.dry_run,
                        verbose=True,
                        min_completion_ratio=args.min_completion_ratio,
                    )
                    if args.commit and counters["enqueued"] > 0:
                        conn.commit()
                    else:
                        conn.rollback()

            total_disappeared += counters["disappeared"]
            total_already_queued += counters["already_queued"]
            total_enqueued += counters["enqueued"]
            total_no_run += counters["no_run"]
            total_errors += counters["error"]
            total_skipped_partial += counters["skipped_partial"]

        print("-" * 72)
        print(f"total_desaparecidas={total_disappeared}")
        print(f"total_ya_en_cola={total_already_queued}")
        print(f"total_encoladas_ok={total_enqueued}")
        print(f"total_sin_run={total_no_run}")
        print(f"total_skipped_partial={total_skipped_partial}")
        print(f"total_errors={total_errors}")
        if args.dry_run:
            print("DRY-RUN: no se escribio en publish_queue.")
        print("=" * 72)

    else:
        # ---------------------------------------------------------------
        # Modo individual: una sola inmobiliaria (output verbose)
        # ---------------------------------------------------------------
        print("=" * 72)
        print("ENQUEUE DEACTIVATIONS")
        print(f"mode={'commit' if args.commit else 'dry-run'}")
        print(f"inmobiliaria_id={args.inmobiliaria_id}")
        print(f"baseline_estados={sorted(BASELINE_ESTADOS)}")
        print(f"min_completion_ratio={args.min_completion_ratio}")
        print("-" * 72)

        with connect_internal_db(db_url) as conn:
            with conn.cursor() as cur:
                # 1. Info de la ultima corrida exitosa
                run_info = fetch_last_run_info(cur, args.inmobiliaria_id)
                if not run_info:
                    print("RESULTADO: no hay scraping exitoso en Neon para esta inmobiliaria.")
                    print("No se puede calcular baseline de comparacion.")
                    print("=" * 72)
                    conn.rollback()
                    return

                print(
                    f"ultimo_run_exitoso: run_id={run_info['scraping_run_id']} "
                    f"item_id={run_info['item_id']} "
                    f"finished_at={run_info['finished_at']} "
                    f"props_detectadas={run_info['propiedades_detectadas']}"
                )

                # Proteccion: no encolar deactivations si la extraccion fue parcial
                is_partial, partial_reason = _is_partial_run(run_info, args.min_completion_ratio)
                if is_partial:
                    print(
                        f"SKIP deactivations — extraccion parcial / {partial_reason}"
                    )
                    print("RESULTADO: deactivations omitidas para proteger contra falsos negativos.")
                    print("Usar --min-completion-ratio 0 para forzar (solo si la extraccion fue completa).")
                    print("=" * 72)
                    conn.rollback()
                    return

                # 2. Hashes del ultimo scraping
                last_hashes = fetch_last_run_hashes(cur, args.inmobiliaria_id)
                print(f"hashes_ultimo_scraping={len(last_hashes)}")

                # 3. Props activas en Supabase
                try:
                    supabase_props = fetch_active_supabase_props(
                        session, base_url, key, args.inmobiliaria_id
                    )
                except Exception as exc:
                    print(f"ERROR al consultar Supabase: {exc}")
                    conn.rollback()
                    return

                print(f"props_activas_en_supabase={len(supabase_props)}")

                # 4. Calcular desaparecidas
                disappeared: List[Dict[str, Any]] = []
                for prop in supabase_props:
                    h = str(prop.get("hash_dedup") or "")
                    if not h or h not in last_hashes:
                        disappeared.append(prop)

                print(f"props_desaparecidas={len(disappeared)}")
                print("-" * 72)

                if not disappeared:
                    print("RESULTADO: ninguna propiedad activa desaparecio del ultimo scraping.")
                    conn.rollback()
                    print("=" * 72)
                    return

                # 5. Excluir las que ya tienen deactivate encolado
                sup_ids = [int(p["id"]) for p in disappeared if p.get("id")]
                already_queued = fetch_existing_deactivate_ids(cur, sup_ids)
                to_enqueue = [p for p in disappeared if int(p.get("id", 0)) not in already_queued]

                print(f"ya_en_cola_deactivate={len(already_queued)}")
                print(f"a_encolar={len(to_enqueue)}")
                print("-" * 72)

                for item in to_enqueue[:10]:
                    print(
                        f"  sup_id={item.get('id')} "
                        f"hash={str(item.get('hash_dedup') or '')[:20]}... "
                        f"url={str(item.get('url') or '')[:60]}"
                    )
                if len(to_enqueue) > 10:
                    print(f"  ... {len(to_enqueue) - 10} mas")

                if args.dry_run:
                    print("-" * 72)
                    print("DRY-RUN: no se escribio en publish_queue.")
                    conn.rollback()
                else:
                    enqueued = 0
                    for item in to_enqueue:
                        try:
                            insert_deactivate_entry(cur, int(item["id"]))
                            enqueued += 1
                        except Exception as exc:
                            print(f"  ERROR encolando sup_id={item.get('id')}: {exc}")
                    conn.commit()
                    print("-" * 72)
                    print(f"encoladas_ok={enqueued}")

        print("=" * 72)


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Controlled daily orchestrator for the ERETZ Propiedades dual pipeline.

This script coordinates existing scripts by subprocess. It does not reimplement
scraping, validation, queue building, or Supabase publishing logic.
Default mode is dry-run; pass --commit to run write phases.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
STALE_INTERVAL_SQL = "2 hours"
LOG_LIMIT = 4000


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


def config() -> Tuple[str, str, str]:
    load_env()
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    internal_db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    missing = []
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not supabase_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not internal_db_url:
        missing.append("INTERNAL_DB_URL")
    if missing:
        raise SystemExit("Faltan variables requeridas: " + ", ".join(missing))
    if not env_flag("USE_INTERNAL_DB", default=False):
        raise SystemExit("USE_INTERNAL_DB no esta en true; abortando pipeline dual.")
    return supabase_url, supabase_key, internal_db_url


def internal_db_schema() -> str:
    """Schema de las tablas del pipeline.

    Default 'public' (Neon dedicado). 'internal_scraping' para Supabase Pro.
    Se valida como identificador simple para usarlo en SET search_path.
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
    # Las queries del pipeline usan nombres sin calificar; search_path elige schema.
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {internal_db_schema()}")
    return conn


def truncate(text: str, limit: int = LOG_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... truncated {len(text) - limit} chars"


def print_command(label: str, command: Sequence[str]) -> None:
    print(f"[{label}] " + " ".join(command))


def playwright_is_installed() -> bool:
    """Safe, read-only check. Never installs anything."""
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:
        return False


def assert_playwright_available() -> None:
    if not playwright_is_installed():
        raise SystemExit(
            "Se pidio --allow-playwright pero Playwright no parece instalado.\n"
            "Instalar manualmente (no lo hago automaticamente):\n"
            "  pip install playwright\n"
            "  python -m playwright install\n"
            "Luego volver a correr con --allow-playwright."
        )


def pipeline_env(internal_db_url: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["USE_INTERNAL_DB"] = "true"
    env["INTERNAL_DB_URL"] = internal_db_url
    # Propagar el schema a los subprocesos (scraper, validate, build-queue, ...)
    env["INTERNAL_DB_SCHEMA"] = internal_db_schema()
    return env


class StepTimeoutError(RuntimeError):
    """Una fase (subprocess) excedió su timeout.

    Hereda de RuntimeError: el manejo genérico de errores del pipeline lo trata
    igual que antes. Solo la FASE 2 lo captura específicamente para decidir si
    continuar (si el scraping_run ya quedó finished) o abortar.
    """


def run_step(
    label: str,
    command: Sequence[str],
    *,
    env: Dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    print_command(label, command)
    try:
        result = subprocess.run(
            list(command),
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = truncate(exc.stdout or "")
        stderr = truncate(exc.stderr or "")
        if stdout:
            print(f"[{label}] stdout:\n{stdout}")
        if stderr:
            print(f"[{label}] stderr:\n{stderr}")
        raise StepTimeoutError(f"{label} timeout despues de {timeout}s") from exc
    if result.stdout:
        print(f"[{label}] stdout:\n{truncate(result.stdout)}")
    if result.stderr:
        print(f"[{label}] stderr:\n{truncate(result.stderr)}")
    if result.returncode != 0:
        raise RuntimeError(f"{label} fallo con returncode={result.returncode}")
    return result


def parse_key_values(stdout: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            values[key] = value
    return values


def parse_int(values: Dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(values.get(key, default)))
    except Exception:
        return default


def parse_created(stdout: str) -> Tuple[Optional[int], int]:
    run_id: Optional[int] = None
    inserted = 0
    for line in stdout.splitlines():
        match = re.search(r"CREATED\s+run_id=(\d+)", line)
        if match:
            run_id = int(match.group(1))
        match = re.search(r"INSERTED\s+scraping_run_items=(\d+)", line)
        if match:
            inserted = int(match.group(1))
    return run_id, inserted


def supabase_health_check(supabase_url: str, supabase_key: str) -> float:
    url = f"{supabase_url}/rest/v1/inmobiliarias_main?select=id&limit=1"
    request = Request(
        url,
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        },
        method="GET",
    )
    started = time.monotonic()
    try:
        with urlopen(request, timeout=10) as response:
            status = response.getcode()
            response.read(512)
    except HTTPError as exc:
        status = exc.code
    except URLError as exc:
        raise RuntimeError(f"Health check Supabase fallo: {exc}") from exc
    latency = time.monotonic() - started
    if status != 200:
        raise RuntimeError(f"Health check Supabase status={status}")
    if latency > 8:
        raise RuntimeError(f"Health check Supabase lento: {latency:.2f}s")
    return latency


def preflight_neon(cur) -> None:
    cur.execute("SELECT 1")
    cur.fetchone()


def fetch_stuck(cur, table: str, status: str) -> List[int]:
    cur.execute(f"SELECT id FROM {table} WHERE status = %s LIMIT 5", [status])
    return [int(row["id"]) for row in cur.fetchall()]


def reclaim_stale(cur) -> Tuple[int, int]:
    cur.execute(
        """
        UPDATE scraping_run_items
        SET status = 'pending',
            updated_at = now()
        WHERE status = 'running'
          AND COALESCE(started_at, updated_at, created_at) < now() - INTERVAL '2 hours'
        RETURNING id
        """
    )
    scraping_reset = len(cur.fetchall())
    cur.execute(
        """
        UPDATE publish_queue
        SET status = 'pending',
            error_message = NULL
        WHERE status = 'publishing'
          AND COALESCE(last_attempt_at, queued_at) < now() - INTERVAL '2 hours'
        RETURNING id
        """
    )
    publishing_reset = len(cur.fetchall())
    return scraping_reset, publishing_reset


def run_preflight(args: argparse.Namespace, supabase_url: str, supabase_key: str, internal_db_url: str) -> None:
    print("=" * 72)
    print("FASE 0 - PRE-FLIGHT")
    latency = supabase_health_check(supabase_url, supabase_key)
    print(f"supabase_health=ok latency_seconds={latency:.2f}")
    with connect_internal_db(internal_db_url) as conn:
        with conn.cursor() as cur:
            preflight_neon(cur)
            print("neon_health=ok")
            running = fetch_stuck(cur, "scraping_run_items", "running")
            publishing = fetch_stuck(cur, "publish_queue", "publishing")
            if running or publishing:
                if args.reclaim_stale and args.commit:
                    scraping_reset, publishing_reset = reclaim_stale(cur)
                    conn.commit()
                    print(f"reclaim_stale scraping_reset={scraping_reset} publishing_reset={publishing_reset}")
                    running = fetch_stuck(cur, "scraping_run_items", "running")
                    publishing = fetch_stuck(cur, "publish_queue", "publishing")
                else:
                    conn.rollback()
                    raise RuntimeError(
                        "Hay filas atascadas: "
                        f"scraping_run_items.running={running} publish_queue.publishing={publishing}. "
                        "Usar --reclaim-stale --commit solo si corresponde."
                    )
            if running or publishing:
                conn.rollback()
                raise RuntimeError(
                    "Quedaron filas atascadas no viejas tras reclaim: "
                    f"scraping_run_items.running={running} publish_queue.publishing={publishing}"
                )
        conn.rollback()


def load_scraping_run_summary(cur, run_id: int) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT
          id,
          total_inmobiliarias_procesadas,
          total_inmobiliarias_exitosas,
          total_inmobiliarias_error,
          total_propiedades_detectadas,
          total_propiedades_nuevas,
          total_propiedades_actualizadas,
          duration_seconds
        FROM scraping_runs
        WHERE id = %s
        LIMIT 1
        """,
        [run_id],
    )
    row = cur.fetchone()
    return dict(row) if row else {}


def upsert_daily_summary(
    cur,
    *,
    run_date: date,
    summary: Dict[str, Any],
    duration_seconds: int,
    notes: str,
) -> None:
    payload = {
        "run_date": run_date,
        "inmobiliarias_intentadas": summary.get("inmobiliarias_intentadas", 0),
        "inmobiliarias_ok": summary.get("inmobiliarias_ok", 0),
        "inmobiliarias_error": summary.get("inmobiliarias_error", 0),
        "propiedades_scraped": summary.get("propiedades_scraped", 0),
        "propiedades_nuevas": summary.get("propiedades_nuevas", 0),
        "propiedades_actualizadas": summary.get("propiedades_actualizadas", 0),
        "propiedades_publicadas": summary.get("propiedades_publicadas", 0),
        "propiedades_rechazadas": summary.get("propiedades_rechazadas", 0),
        "geocoding_ok": summary.get("geocoding_ok", 0),
        "geocoding_failed": summary.get("geocoding_failed", 0),
        "duracion_segundos": duration_seconds,
        "notas": notes,
    }
    columns = list(payload.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column != "run_date")
    cur.execute(
        f"""
        INSERT INTO daily_update_summary ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (run_date) DO UPDATE SET {updates}
        """,
        [payload[column] for column in columns],
    )


def sleep_phase(args: argparse.Namespace) -> None:
    if args.phase_sleep > 0:
        time.sleep(args.phase_sleep)


def print_dry_run_plan(args: argparse.Namespace, run_day: date) -> None:
    notes = f"daily {run_day.isoformat()}"
    create_cmd = [
        sys.executable,
        "scripts/create_scraping_run_from_next_batch.py",
        "--limit",
        str(args.inmobiliarias),
        "--include-new",
        "--notes",
        notes,
        "--commit",
    ]
    scrape_cmd = [
        sys.executable,
        "scraper/scraper_propiedades.py",
        "--max-items",
        str(args.inmobiliarias),
        "--workers",
        str(args.workers),
    ]
    if args.allow_playwright:
        scrape_cmd.append("--allow-playwright")
    validate_cmd = [
        sys.executable,
        "scripts/validate_raw_properties.py",
        "--limit",
        str(args.validate_limit),
        "--commit",
    ]
    geocode_cmd = [
        sys.executable,
        "scripts/geocode_staging.py",
        "--limit",
        str(args.geocode_limit),
        "--max-requests",
        str(args.max_geocode_requests),
        "--commit",
    ]
    queue_cmd = [
        sys.executable,
        "scripts/build_publish_queue.py",
        "--limit",
        str(args.queue_limit),
        "--min-score",
        str(args.min_score),
        "--commit",
    ]
    publish_cmd = [
        sys.executable,
        "scripts/publish_to_supabase.py",
        "--limit",
        str(args.publish_limit),
        "--max-supabase-writes",
        str(args.max_writes_per_tanda),
        "--min-score",
        str(args.min_score),
        "--sleep",
        str(args.publish_sleep),
        "--commit",
    ]
    if args.allow_pending_geo:
        queue_cmd.append("--allow-pending-geo")
        publish_cmd.append("--allow-pending-geo")

    print("=" * 72)
    print("DRY-RUN PLAN ONLY")
    print("No se ejecutan subprocess ni escrituras en dry-run.")
    print(f"inmobiliarias={args.inmobiliarias}")
    print(f"workers={args.workers}")
    print(f"validate_limit={args.validate_limit}")
    print(f"geocode_limit={args.geocode_limit}")
    print(f"max_geocode_requests={args.max_geocode_requests}")
    print(f"geocode_timeout={args.geocode_timeout}")
    print(f"queue_limit={args.queue_limit}")
    print(f"publish_limit={args.publish_limit}")
    print(f"max_validate_iterations={args.max_validate_iterations}")
    print(f"max_geocode_iterations={args.max_geocode_iterations}")
    print(f"max_queue_iterations={args.max_queue_iterations}")
    print(f"max_publish_iterations={args.max_publish_iterations}")
    print(f"max_writes_per_tanda={args.max_writes_per_tanda}")
    print(f"max_writes_total={args.max_writes_total}")
    print(f"min_score={args.min_score}")
    print(f"allow_pending_geo={args.allow_pending_geo}")
    print(f"allow_playwright={args.allow_playwright}")
    if args.allow_playwright:
        print("playwright=HABILITADO (scraper recibe --allow-playwright)")
    else:
        print("playwright=DESHABILITADO (comportamiento por defecto, sin --allow-playwright)")
    print("-" * 72)
    print_command("FASE 1 create-queue", create_cmd)
    print_command("FASE 2 scraper", scrape_cmd)
    if args.with_deactivations:
        print_command(
            "FASE 2.5 enqueue-deactivations",
            [sys.executable, "scripts/enqueue_deactivations.py", "--all-from-run", "{RUN_ID}", "--commit"],
        )
    else:
        print("FASE 2.5 - DESACTIVACIONES: deshabilitado (usar --with-deactivations para activar)")
    print_command("FASE 3 validate-raw", validate_cmd)
    print("FASE 3.5 - GEOCODING STAGING")
    print_command("FASE 3.5 geocode-staging", geocode_cmd)
    print_command("FASE 4 build-queue", queue_cmd)
    print_command("FASE 5 publish", publish_cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestador diario controlado del pipeline dual")
    parser.add_argument("--inmobiliarias", type=int, default=10)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--validate-limit", type=int, default=50)
    parser.add_argument("--geocode-limit", type=int, default=20)
    parser.add_argument("--max-geocode-requests", type=int, default=30)
    parser.add_argument("--max-geocode-iterations", type=int, default=3)
    parser.add_argument("--queue-limit", type=int, default=20)
    parser.add_argument("--publish-limit", type=int, default=5)
    parser.add_argument("--max-writes-per-tanda", type=int, default=10)
    parser.add_argument("--max-writes-total", type=int, default=100)
    parser.add_argument("--max-validate-iterations", type=int, default=5)
    parser.add_argument("--max-queue-iterations", type=int, default=5)
    parser.add_argument("--max-publish-iterations", type=int, default=5)
    parser.add_argument("--min-score", type=int, default=0, help="Score minimo para encolar/publicar (0 = publicar todas las props validas)")
    parser.add_argument("--publish-sleep", type=float, default=1.5)
    parser.add_argument("--phase-sleep", type=float, default=5)
    parser.add_argument("--step-timeout", type=int, default=600)
    parser.add_argument("--geocode-timeout", type=int, default=1800, help="Timeout en segundos para FASE 3.5 geocoding (default 1800)")
    parser.add_argument("--scraper-timeout", type=int, default=7200)
    parser.add_argument("--max-error-rate", type=float, default=0.40)
    parser.add_argument("--max-publish-fail-rate", type=float, default=0.20)
    parser.add_argument("--allow-pending-geo", dest="allow_pending_geo", action="store_true", default=True, help="Aceptar geocoding_status=pending (activo por defecto)")
    parser.add_argument("--no-allow-pending-geo", dest="allow_pending_geo", action="store_false", help="Requerir geocoding_status=done o skipped")
    parser.add_argument(
        "--allow-playwright",
        action="store_true",
        help="Pasar --allow-playwright al scraper para sitios que requieren render JS",
    )
    parser.add_argument("--reclaim-stale", action="store_true")
    parser.add_argument(
        "--with-deactivations",
        action="store_true",
        help="Agregar FASE 2.5: encolar desactivaciones de props desaparecidas post-scraping",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if args.commit and args.dry_run:
        raise SystemExit("Usar --dry-run o --commit, no ambos")
    if not args.commit:
        args.dry_run = True
    for name in ("inmobiliarias", "workers", "validate_limit", "geocode_limit", "queue_limit", "publish_limit"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} debe ser mayor a 0")
    if args.max_geocode_requests <= 0:
        raise SystemExit("--max-geocode-requests debe ser mayor a 0")
    if args.max_writes_per_tanda <= 0 or args.max_writes_total <= 0:
        raise SystemExit("--max-writes-per-tanda y --max-writes-total deben ser mayores a 0")
    for name in ("max_validate_iterations", "max_geocode_iterations", "max_queue_iterations", "max_publish_iterations"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} debe ser mayor a 0")
    if args.allow_playwright:
        assert_playwright_available()

    started = time.monotonic()
    run_day = date.today()
    mode = "commit" if args.commit else "dry-run"
    summary: Dict[str, Any] = {
        "inmobiliarias_intentadas": args.inmobiliarias,
        "inmobiliarias_ok": 0,
        "inmobiliarias_error": 0,
        "propiedades_scraped": 0,
        "propiedades_nuevas": 0,
        "propiedades_actualizadas": 0,
        "propiedades_publicadas": 0,
        "propiedades_rechazadas": 0,
        "geocoding_ok": 0,
        "geocoding_failed": 0,
    }
    run_id: Optional[int] = None
    inserted_items = 0
    stopped_reason = "completed"
    validate_iterations_used = 0
    geocode_iterations_used = 0
    queue_iterations_used = 0
    publish_iterations_used = 0
    geocoding_done_total = 0
    geocoding_failed_total = 0
    geocoding_skipped_total = 0
    geocoding_requests_total = 0

    supabase_url, supabase_key, internal_db_url = config()
    env = pipeline_env(internal_db_url)

    print("=" * 72)
    print("RUN DAILY PIPELINE")
    print(f"mode={mode}")
    print(f"run_date={run_day.isoformat()}")
    print(f"allow_playwright={args.allow_playwright}")
    print(f"max_validate_iterations={args.max_validate_iterations}")
    print(f"max_geocode_iterations={args.max_geocode_iterations}")
    print(f"max_queue_iterations={args.max_queue_iterations}")
    print(f"max_publish_iterations={args.max_publish_iterations}")
    print(f"max_writes_total={args.max_writes_total}")
    print("=" * 72)

    try:
        run_preflight(args, supabase_url, supabase_key, internal_db_url)
        if args.dry_run:
            stopped_reason = "plan_only"
            print_dry_run_plan(args, run_day)
            return
        sleep_phase(args)

        print("=" * 72)
        print("FASE 1 - CREAR COLA")
        notes = f"daily {run_day.isoformat()}"
        create_cmd = [
            sys.executable,
            "scripts/create_scraping_run_from_next_batch.py",
            "--limit",
            str(args.inmobiliarias),
            "--include-new",
            "--notes",
            notes,
            "--commit",
        ]
        if args.dry_run:
            print_command("create-queue dry-run", create_cmd)
            print("DRY-RUN: no se crea scraping_run ni scraping_run_items.")
        else:
            create_result = run_step("create-queue", create_cmd, env=env, timeout=args.step_timeout)
            run_id, inserted_items = parse_created(create_result.stdout)
            print(f"created_run_id={run_id}")
            print(f"inserted_items={inserted_items}")
            if inserted_items == 0:
                stopped_reason = "no_items_inserted"
                return
        sleep_phase(args)

        print("=" * 72)
        print("FASE 2 - SCRAPING")
        scrape_cmd = [
            sys.executable,
            "scraper/scraper_propiedades.py",
            "--max-items",
            str(args.inmobiliarias),
            "--workers",
            str(args.workers),
        ]
        if args.allow_playwright:
            scrape_cmd.append("--allow-playwright")
        if args.dry_run:
            print_command("scraper dry-run", scrape_cmd)
            print("DRY-RUN: no se ejecuta scraping real.")
        else:
            try:
                run_step("scraper", scrape_cmd, env=env, timeout=args.scraper_timeout)
            except StepTimeoutError:
                # El scraper excedió el timeout del subprocess. Si la run ya quedó
                # finished (todos los items procesados), el trabajo está hecho:
                # continuar fases 3-5 en vez de abortar y forzar un recovery manual.
                run_finished = False
                if run_id is not None:
                    with connect_internal_db(internal_db_url) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT status FROM scraping_runs WHERE id = %s", [run_id]
                            )
                            row = cur.fetchone()
                            run_finished = bool(row and row.get("status") == "finished")
                        conn.rollback()
                if not run_finished:
                    raise
                print(
                    "WARNING scraper_subprocess_timeout_but_run_finished "
                    f"run_id={run_id}: el scraper excedió scraper_timeout pero la run "
                    "quedó finished; se continúan las fases 3-5."
                )
            if run_id is not None:
                with connect_internal_db(internal_db_url) as conn:
                    with conn.cursor() as cur:
                        run_summary = load_scraping_run_summary(cur, run_id)
                    conn.rollback()
                summary["inmobiliarias_ok"] = int(run_summary.get("total_inmobiliarias_exitosas") or 0)
                summary["inmobiliarias_error"] = int(run_summary.get("total_inmobiliarias_error") or 0)
                summary["propiedades_scraped"] = int(run_summary.get("total_propiedades_detectadas") or 0)
                summary["propiedades_nuevas"] = int(run_summary.get("total_propiedades_nuevas") or 0)
                summary["propiedades_actualizadas"] = int(run_summary.get("total_propiedades_actualizadas") or 0)
                processed = int(run_summary.get("total_inmobiliarias_procesadas") or 0)
                error_rate = (summary["inmobiliarias_error"] / processed) if processed else 0.0
                print(f"scraping_error_rate={error_rate:.2f}")
                if error_rate > args.max_error_rate:
                    raise RuntimeError(
                        f"error_rate {error_rate:.2f} supera max_error_rate {args.max_error_rate:.2f}"
                    )
        sleep_phase(args)

        if args.with_deactivations and run_id is not None:
            print("=" * 72)
            print("FASE 2.5 - ENCOLAR DESACTIVACIONES")
            deact_cmd = [
                sys.executable,
                "scripts/enqueue_deactivations.py",
                "--all-from-run",
                str(run_id),
                "--commit",
            ]
            run_step("enqueue-deactivations", deact_cmd, env=env, timeout=args.step_timeout)
            sleep_phase(args)
        elif args.with_deactivations and run_id is None:
            print("FASE 2.5 - ENCOLAR DESACTIVACIONES: omitida (run_id no disponible)")

        print("=" * 72)
        print("FASE 3 - VALIDAR RAW")
        validate_cmd_base = [
            sys.executable,
            "scripts/validate_raw_properties.py",
            "--limit",
            str(args.validate_limit),
        ]
        if args.dry_run:
            validate_iterations_used = 1
            run_step("validate-raw dry-run", validate_cmd_base + ["--dry-run"], env=env, timeout=args.step_timeout)
        else:
            for idx in range(args.max_validate_iterations):
                validate_iterations_used = idx + 1
                result = run_step("validate-raw", validate_cmd_base + ["--commit"], env=env, timeout=args.step_timeout)
                values = parse_key_values(result.stdout)
                read_count = parse_int(values, "filas_leidas")
                validated = parse_int(values, "validadas")
                rejected = parse_int(values, "rechazadas")
                summary["propiedades_rechazadas"] += rejected
                if read_count == 0 or (validated + rejected) == 0:
                    break
                print(f"validate_iteration={idx + 1}")
        sleep_phase(args)

        print("=" * 72)
        print("FASE 3.5 - GEOCODING STAGING")
        geocode_cmd_base = [
            sys.executable,
            "scripts/geocode_staging.py",
            "--limit",
            str(args.geocode_limit),
            "--max-requests",
            str(args.max_geocode_requests),
        ]
        if args.dry_run:
            geocode_iterations_used = 1
            print_command("geocode-staging dry-run", geocode_cmd_base + ["--dry-run"])
            print("DRY-RUN: no se ejecuta geocoding real.")
        else:
            for idx in range(args.max_geocode_iterations):
                geocode_iterations_used = idx + 1
                result = run_step("geocode-staging", geocode_cmd_base + ["--commit"], env=env, timeout=args.geocode_timeout)
                values = parse_key_values(result.stdout)
                read_count = parse_int(values, "filas_leidas")
                done = parse_int(values, "done")
                failed = parse_int(values, "failed")
                skipped = parse_int(values, "skipped")
                requests_used = parse_int(values, "requests_usados")
                geocoding_done_total += done
                geocoding_failed_total += failed
                geocoding_skipped_total += skipped
                geocoding_requests_total += requests_used
                print(
                    f"geocode_iteration={idx + 1} done={done} failed={failed} "
                    f"skipped={skipped} requests={requests_used}"
                )
                if read_count == 0:
                    break
                if (done + failed + skipped) == 0:
                    break
            summary["geocoding_ok"] = geocoding_done_total
            summary["geocoding_failed"] = geocoding_failed_total
        sleep_phase(args)

        print("=" * 72)
        print("FASE 4 - BUILD PUBLISH QUEUE")
        queue_cmd_base = [
            sys.executable,
            "scripts/build_publish_queue.py",
            "--limit",
            str(args.queue_limit),
            "--min-score",
            str(args.min_score),
        ]
        if args.allow_pending_geo:
            queue_cmd_base.append("--allow-pending-geo")
        if args.dry_run:
            queue_iterations_used = 1
            run_step("build-queue dry-run", queue_cmd_base + ["--dry-run"], env=env, timeout=args.step_timeout)
        else:
            for idx in range(args.max_queue_iterations):
                queue_iterations_used = idx + 1
                result = run_step("build-queue", queue_cmd_base + ["--commit"], env=env, timeout=args.step_timeout)
                values = parse_key_values(result.stdout)
                encoladas = parse_int(values, "encoladas")
                print(f"build_queue_iteration={idx + 1} encoladas={encoladas}")
                if encoladas == 0:
                    break
        sleep_phase(args)

        print("=" * 72)
        print("FASE 5 - PUBLICAR")
        publish_cmd_base = [
            sys.executable,
            "scripts/publish_to_supabase.py",
            "--limit",
            str(args.publish_limit),
            "--min-score",
            str(args.min_score),
            "--sleep",
            str(args.publish_sleep),
        ]
        if args.allow_pending_geo:
            publish_cmd_base.append("--allow-pending-geo")
        if args.dry_run:
            run_step(
                "publish dry-run",
                publish_cmd_base + ["--max-supabase-writes", str(args.max_writes_per_tanda), "--dry-run"],
                env=env,
                timeout=args.step_timeout,
            )
            publish_iterations_used = 1
        else:
            writes_total = 0
            while writes_total < args.max_writes_total and publish_iterations_used < args.max_publish_iterations:
                publish_iterations_used += 1
                remaining = args.max_writes_total - writes_total
                writes_limit = min(remaining, args.max_writes_per_tanda)
                result = run_step(
                    "publish",
                    publish_cmd_base + ["--max-supabase-writes", str(writes_limit), "--commit"],
                    env=env,
                    timeout=args.step_timeout,
                )
                values = parse_key_values(result.stdout)
                published_ok = parse_int(values, "publicadas_ok")
                failed = parse_int(values, "failed")
                writes_used = parse_int(values, "writes_supabase_usados")
                summary["propiedades_publicadas"] += published_ok
                writes_total += writes_used
                total_attempted = published_ok + failed
                fail_rate = (failed / total_attempted) if total_attempted else 0.0
                print(f"publish_fail_rate={fail_rate:.2f} writes_total={writes_total}")
                if total_attempted and fail_rate > args.max_publish_fail_rate:
                    raise RuntimeError(
                        f"publish_fail_rate {fail_rate:.2f} supera "
                        f"max_publish_fail_rate {args.max_publish_fail_rate:.2f}"
                    )
                if writes_total >= args.max_writes_total:
                    break
                if published_ok == 0 and failed == 0:
                    break
        sleep_phase(args)

    except Exception as exc:
        stopped_reason = str(exc)
        print(f"PIPELINE_STOPPED reason={stopped_reason}")
    finally:
        duration_seconds = int(time.monotonic() - started)
        print("=" * 72)
        print("FASE 6 - DAILY UPDATE SUMMARY")
        summary_notes = {
            "mode": mode,
            "run_id": run_id,
            "inserted_items": inserted_items,
            "stopped_reason": stopped_reason,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if args.dry_run:
            print("DRY-RUN: daily_update_summary no se escribe.")
            print(json.dumps({**summary, "duracion_segundos": duration_seconds, "notas": summary_notes}, indent=2))
        else:
            with connect_internal_db(internal_db_url) as conn:
                with conn.cursor() as cur:
                    upsert_daily_summary(
                        cur,
                        run_date=run_day,
                        summary=summary,
                        duration_seconds=duration_seconds,
                        notes=json.dumps(summary_notes, ensure_ascii=False),
                    )
                conn.commit()
            print("daily_update_summary=upserted")
        print("=" * 72)
        print("RESUMEN FINAL")
        print(f"mode={mode}")
        print(f"run_id={run_id}")
        print(f"allow_playwright={args.allow_playwright}")
        print(f"inserted_items={inserted_items}")
        print(f"validate_iterations_used={validate_iterations_used}")
        print(f"geocode_iterations_used={geocode_iterations_used}")
        print(f"queue_iterations_used={queue_iterations_used}")
        print(f"publish_iterations_used={publish_iterations_used}")
        print(f"geocoding_done={geocoding_done_total}")
        print(f"geocoding_failed={geocoding_failed_total}")
        print(f"geocoding_skipped={geocoding_skipped_total}")
        print(f"geocoding_requests_used={geocoding_requests_total}")
        for key in sorted(summary):
            print(f"{key}={summary[key]}")
        print(f"duracion_segundos={duration_seconds}")
        print(f"stopped_reason={stopped_reason}")
        print("=" * 72)


if __name__ == "__main__":
    main()

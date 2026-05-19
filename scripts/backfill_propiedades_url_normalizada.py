"""
Backfill seguro de propiedades.url_normalizada.

Usa exactamente normalize_property_url_for_dedup() del scraper principal.
Por defecto corre en dry-run. Solo actualiza con --commit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.scraper_propiedades import normalize_property_url_for_dedup  # noqa: E402


@dataclass
class BackfillReport:
    filas_leidas: int = 0
    procesadas: int = 0
    con_url_normalizada: int = 0
    sin_url_normalizable: int = 0
    actualizadas: int = 0
    actualizarian: int = 0
    sin_cambios: int = 0
    errores: int = 0
    duplicate_groups: int = 0
    duplicate_rows: int = 0
    columna_url_normalizada_existe: bool = False
    only_missing: bool = False
    ejemplos_actualizadas: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_sin_cambios: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_duplicados: List[Dict[str, Any]] = field(default_factory=list)
    ejemplos_errores: List[Dict[str, Any]] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)

    def add_example(self, field_name: str, value: Dict[str, Any], limit: int = 10) -> None:
        bucket = getattr(self, field_name)
        if len(bucket) < limit:
            bucket.append(value)


def load_env() -> Tuple[str, str]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT / ".env.local")
    else:
        for env_path in (ROOT / ".env", ROOT / ".env.local"):
            if not env_path.exists():
                continue
            for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.strip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY en .env")
    return url, key


def make_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def make_headers(key: str, prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


def check_url_normalizada_column(session: requests.Session, base_url: str, headers: Dict[str, str]) -> bool:
    response = session.get(
        f"{base_url}/rest/v1/propiedades",
        headers=headers,
        params={"select": "url_normalizada", "limit": 1},
        timeout=20,
    )
    if response.status_code == 200:
        return True
    if response.status_code in {400, 404} and "url_normalizada" in response.text:
        return False
    return False


def fetch_properties_page(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    has_url_normalizada: bool,
    limit: int,
    offset: int,
    agency_id: Optional[int] = None,
    only_missing: bool = False,
) -> List[Dict[str, Any]]:
    columns = ["id", "inmobiliaria_id", "url"]
    if has_url_normalizada:
        columns.append("url_normalizada")

    params: Dict[str, Any] = {
        "select": ",".join(columns),
        "url": "not.is.null",
        "order": "id.asc",
        "limit": limit,
        "offset": offset,
    }
    if agency_id is not None:
        params["inmobiliaria_id"] = f"eq.{agency_id}"
    if only_missing and has_url_normalizada:
        params["or"] = "(url_normalizada.is.null,url_normalizada.eq.)"

    response = session.get(
        f"{base_url}/rest/v1/propiedades",
        headers=headers,
        params=params,
        timeout=40,
    )
    if response.status_code != 200:
        raise RuntimeError(f"fetch propiedades fallo {response.status_code}: {response.text[:500]}")
    return response.json()


def collect_candidates(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    report: BackfillReport,
    batch_size: int,
    max_rows: Optional[int],
    agency_id: Optional[int],
    only_missing: bool,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    offset = 0
    remaining = max_rows

    while True:
        page_limit = batch_size if remaining is None else min(batch_size, remaining)
        if page_limit <= 0:
            break
        rows = fetch_properties_page(
            session=session,
            base_url=base_url,
            headers=headers,
            has_url_normalizada=report.columna_url_normalizada_existe,
            limit=page_limit,
            offset=offset,
            agency_id=agency_id,
            only_missing=only_missing,
        )
        if not rows:
            break

        report.filas_leidas += len(rows)
        for row in rows:
            report.procesadas += 1
            normalized = normalize_property_url_for_dedup(row.get("url"))
            if not normalized:
                report.sin_url_normalizable += 1
                continue
            row["_url_normalizada_calculada"] = normalized
            report.con_url_normalizada += 1
            current = row.get("url_normalizada")
            if current == normalized:
                report.sin_cambios += 1
                report.add_example("ejemplos_sin_cambios", {
                    "id": row.get("id"),
                    "inmobiliaria_id": row.get("inmobiliaria_id"),
                    "url_normalizada": normalized,
                })
            else:
                candidates.append(row)

        if remaining is not None:
            remaining -= len(rows)
            if remaining <= 0:
                break
        if len(rows) < page_limit:
            break
        offset += len(rows)

    report.actualizarian = len(candidates)
    return candidates


def detect_duplicates(rows: List[Dict[str, Any]], report: BackfillReport) -> None:
    grouped: Dict[Tuple[Any, str], List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        normalized = row.get("_url_normalizada_calculada") or normalize_property_url_for_dedup(row.get("url"))
        if not normalized:
            continue
        grouped[(row.get("inmobiliaria_id"), normalized)].append(row)

    duplicates = {key: group for key, group in grouped.items() if len(group) > 1}
    report.duplicate_groups = len(duplicates)
    report.duplicate_rows = sum(len(group) for group in duplicates.values())
    for (agency_id, normalized), group in list(duplicates.items())[:10]:
        report.add_example("ejemplos_duplicados", {
            "inmobiliaria_id": agency_id,
            "url_normalizada": normalized,
            "cantidad": len(group),
            "ids": [row.get("id") for row in group[:20]],
            "urls": [row.get("url") for row in group[:5]],
        })


def update_url_normalizada(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    candidates: List[Dict[str, Any]],
    report: BackfillReport,
) -> None:
    for row in candidates:
        normalized = row.get("_url_normalizada_calculada")
        if not normalized:
            continue
        response = session.patch(
            f"{base_url}/rest/v1/propiedades",
            headers=headers,
            params={"id": f"eq.{row['id']}"},
            json={"url_normalizada": normalized},
            timeout=20,
        )
        if response.status_code not in {200, 204}:
            report.errores += 1
            report.add_example("ejemplos_errores", {
                "id": row.get("id"),
                "status_code": response.status_code,
                "message": response.text[:500],
            })
            continue
        report.actualizadas += 1
        report.add_example("ejemplos_actualizadas", {
            "id": row.get("id"),
            "inmobiliaria_id": row.get("inmobiliaria_id"),
            "url": row.get("url"),
            "url_normalizada": normalized,
        })


def run(args: argparse.Namespace) -> BackfillReport:
    base_url, key = load_env()
    session = make_session()
    headers = make_headers(key)
    report = BackfillReport()
    report.only_missing = bool(args.only_missing)
    report.columna_url_normalizada_existe = check_url_normalizada_column(session, base_url, headers)

    if not report.columna_url_normalizada_existe:
        report.advertencias.append(
            "La columna propiedades.url_normalizada no existe. Ejecutar primero el SQL de preparacion. "
            "El dry-run puede calcular y detectar duplicados, pero --commit se aborta."
        )
        if args.commit:
            raise RuntimeError("No se puede ejecutar --commit sin la columna propiedades.url_normalizada")

    candidates = collect_candidates(
        session=session,
        base_url=base_url,
        headers=headers,
        report=report,
        batch_size=args.batch_size,
        max_rows=args.limit,
        agency_id=args.agency_id,
        only_missing=args.only_missing,
    )
    # Detecta duplicados potenciales sobre todas las filas leidas, no solo sobre las que cambiarian.
    all_rows_for_duplicate_scan = collect_all_rows_for_duplicate_scan(
        session=session,
        base_url=base_url,
        headers=headers,
        report=report,
        batch_size=args.batch_size,
        max_rows=args.limit,
        agency_id=args.agency_id,
        only_missing=args.only_missing,
    )
    detect_duplicates(all_rows_for_duplicate_scan, report)

    if report.duplicate_groups:
        report.advertencias.append(
            "Hay duplicados potenciales por inmobiliaria_id + url_normalizada. "
            "No se actualiza nada con --commit y no se debe crear el indice unico hasta resolverlos."
        )
        if args.commit:
            report.advertencias.append("Commit abortado: duplicados potenciales detectados antes de actualizar.")
            return report
    if args.limit is not None:
        report.advertencias.append(
            "El --limit hace que la deteccion de duplicados sea parcial. "
            "Para habilitar indice unico, correr sin --limit."
        )

    if args.commit:
        update_url_normalizada(session, base_url, headers, candidates, report)
    return report


def collect_all_rows_for_duplicate_scan(
    session: requests.Session,
    base_url: str,
    headers: Dict[str, str],
    report: BackfillReport,
    batch_size: int,
    max_rows: Optional[int],
    agency_id: Optional[int],
    only_missing: bool,
) -> List[Dict[str, Any]]:
    """Lee filas para detectar duplicados sin alterar contadores de procesamiento."""
    rows_all: List[Dict[str, Any]] = []
    offset = 0
    remaining = max_rows
    while True:
        page_limit = batch_size if remaining is None else min(batch_size, remaining)
        if page_limit <= 0:
            break
        rows = fetch_properties_page(
            session=session,
            base_url=base_url,
            headers=headers,
            has_url_normalizada=report.columna_url_normalizada_existe,
            limit=page_limit,
            offset=offset,
            agency_id=agency_id,
            only_missing=only_missing,
        )
        if not rows:
            break
        for row in rows:
            row["_url_normalizada_calculada"] = normalize_property_url_for_dedup(row.get("url"))
            rows_all.append(row)
        if remaining is not None:
            remaining -= len(rows)
            if remaining <= 0:
                break
        if len(rows) < page_limit:
            break
        offset += len(rows)
    return rows_all


def print_report(report: BackfillReport, commit: bool) -> None:
    payload = {
        "mode": "commit" if commit else "dry-run",
        "only_missing": report.only_missing,
        "columna_url_normalizada_existe": report.columna_url_normalizada_existe,
        "filas_leidas": report.filas_leidas,
        "procesadas": report.procesadas,
        "con_url_normalizada": report.con_url_normalizada,
        "sin_url_normalizable": report.sin_url_normalizable,
        "actualizadas": report.actualizadas,
        "actualizaria": report.actualizarian if not commit else None,
        "sin_cambios": report.sin_cambios,
        "errores": report.errores,
        "duplicate_groups": report.duplicate_groups,
        "duplicate_rows": report.duplicate_rows,
        "advertencias": report.advertencias,
        "ejemplos_actualizadas": report.ejemplos_actualizadas,
        "ejemplos_sin_cambios": report.ejemplos_sin_cambios,
        "ejemplos_duplicados": report.ejemplos_duplicados,
        "ejemplos_errores": report.ejemplos_errores,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill seguro de propiedades.url_normalizada")
    parser.add_argument("--dry-run", action="store_true", help="No escribe cambios (default)")
    parser.add_argument("--commit", action="store_true", help="Aplica PATCH de url_normalizada")
    parser.add_argument("--limit", type=int, default=None, help="Limite de filas para prueba")
    parser.add_argument("--batch-size", type=int, default=500, help="Tamaño de pagina de lectura")
    parser.add_argument("--agency-id", type=int, default=None, help="Opcional: limitar a una inmobiliaria_id")
    parser.add_argument("--only-missing", action="store_true", help="Procesar solo filas con url_normalizada NULL o vacia")
    args = parser.parse_args()
    if args.commit and args.dry_run:
        parser.error("Usar --dry-run o --commit, no ambos")
    if args.batch_size <= 0:
        parser.error("--batch-size debe ser mayor a 0")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit debe ser mayor a 0")
    return args


if __name__ == "__main__":
    args = parse_args()
    report = run(args)
    print_report(report, commit=bool(args.commit))

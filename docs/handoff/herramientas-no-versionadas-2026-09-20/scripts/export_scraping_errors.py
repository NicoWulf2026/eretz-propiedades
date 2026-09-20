"""Exporta una tanda real de errores de scraping a un CSV local, en SOLO LECTURA.

Lee de `scraping_run_items` (Supabase REST) los items con status=error de las
runs mas recientes y los vuelca a un CSV con el formato que consume
`scripts/diagnose_scraping_errors.py`:

    url,error_type,inmobiliaria_id,nombre,status,id

Garantias de seguridad (por diseno):
  - Solo GET (lectura). NO escribe en Supabase ni en Neon.
  - NO usa Prefer: count=exact (paginado por limit/offset).
  - NO consume la cola productiva, NO corre pipeline, NO publica, NO borra.
  - Solo lee .env para tomar las credenciales (no lo modifica).

Uso:
    python scripts/export_scraping_errors.py --max 1000
    python scripts/export_scraping_errors.py --max 1000 --dedup-url \
        --out data/scraping_errors_export.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    or os.environ.get("SUPABASE_KEY", "")
)

# Familias no-codigo: se exportan igual pero se marcan para no testear en masa.
NON_CODE_FAMILIES = {"blocked", "site_down", "site_down_confirmed"}

PAGE = 1000


def _headers() -> dict:
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}


def fetch_error_items(session: requests.Session, max_rows: int, start_offset: int = 0) -> list:
    """GET paginado de scraping_run_items con status=error, mas recientes primero.
    Sin count=exact. Devuelve hasta max_rows filas."""
    select = (
        "id,inmobiliaria_id,inmobiliaria_nombre,web,url_listado,final_url,"
        "error_type,error_message,status,http_status,cms_detectado,metadata,scraping_run_id"
    )
    out: list = []
    offset = max(0, start_offset)
    while len(out) < max_rows:
        page = min(PAGE, max_rows - len(out))
        url = (
            f"{SUPABASE_URL}/rest/v1/scraping_run_items"
            f"?status=eq.error&select={select}"
            f"&order=id.desc&limit={page}&offset={offset}"
        )
        r = session.get(url, headers=_headers(), timeout=60)
        if r.status_code != 200:
            print(f"ERROR HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
            break
        batch = r.json()
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < page:
            break
        offset += page
    return out[:max_rows]


def _pick_url(row: dict) -> str:
    return (row.get("url_listado") or row.get("web") or row.get("final_url") or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Export read-only de errores de scraping a CSV.")
    ap.add_argument("--max", type=int, default=1000, help="Maximo de filas a exportar (default 1000).")
    ap.add_argument("--offset", type=int, default=0, help="Offset de lectura REST para continuar con tandas posteriores.")
    ap.add_argument("--dedup-url", action="store_true", help="Quedarse con una fila por URL.")
    ap.add_argument("--out", default=None, help="Ruta del CSV de salida.")
    args = ap.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("FALTAN credenciales SUPABASE_URL / SUPABASE_KEY en .env", file=sys.stderr)
        return 2

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else (PROJECT_ROOT / "data" / f"scraping_errors_export_{ts}.csv")

    session = requests.Session()
    rows = fetch_error_items(session, args.max, args.offset)
    print(f"Items error traidos: {len(rows)}")

    # Mapear + (opcional) dedup por URL
    mapped: "OrderedDict[str, dict]" = OrderedDict()
    skipped_no_url = 0
    for row in rows:
        url = _pick_url(row)
        if not url:
            skipped_no_url += 1
            continue
        rec = {
            "url": url,
            "inmobiliaria_id": row.get("inmobiliaria_id") or "",
            "inmobiliaria_nombre": (row.get("inmobiliaria_nombre") or "").strip(),
            "web": (row.get("web") or "").strip(),
            "url_listado": (row.get("url_listado") or "").strip(),
            "final_url": (row.get("final_url") or "").strip(),
            "error_type": (row.get("error_type") or "").strip(),
            "error_message": (row.get("error_message") or "").strip(),
            "status": row.get("status") or "error",
            "metadata": row.get("metadata") or {},
            "cms_detectado": (row.get("cms_detectado") or "").strip(),
            "http_status": row.get("http_status") or "",
            "id": row.get("id") or "",
        }
        key = url if args.dedup_url else str(row.get("id"))
        if key not in mapped:
            mapped[key] = rec

    records = list(mapped.values())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "id",
            "inmobiliaria_id",
            "inmobiliaria_nombre",
            "web",
            "url_listado",
            "final_url",
            "error_type",
            "error_message",
            "status",
            "metadata",
            "cms_detectado",
            "http_status",
            "url",
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for rec in records:
            rec = dict(rec)
            rec["metadata"] = json.dumps(rec.get("metadata") or {}, ensure_ascii=False)
            w.writerow(rec)

    fam = Counter(r["error_type"] or "(vacio)" for r in records)
    code_fam = {k: v for k, v in fam.items() if k not in NON_CODE_FAMILIES}
    print(f"Escrito: {out_path}  (filas={len(records)}, sin_url={skipped_no_url})")
    print("Por familia (top 15):")
    for k, v in sorted(fam.items(), key=lambda x: -x[1])[:15]:
        flag = "  [no-codigo]" if k in NON_CODE_FAMILIES else ""
        print(f"  {v:5d}  {k}{flag}")
    print(f"Familias de codigo: {sum(code_fam.values())} filas / {len(code_fam)} familias")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

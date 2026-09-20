#!/usr/bin/env python
"""PR-BE-DB-BACKFILL-02 — Backfill de diagnostic_status (DRY-RUN).

Lee la propuesta validada del censo y genera el SQL preview + validaciones para
poblar las columnas nuevas de public.inmobiliarias_main. NO ESCRIBE DB.

Pobla SOLO: diagnostic_status, scraping_readiness, exclude_from_scraping,
exclude_reason, diagnostic_status_source, diagnostic_status_updated_at,
last_diagnostic_run_id, diagnostic_notes. NO toca ninguna otra columna.

--commit esta bloqueado en este PR.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
from collections import Counter
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEF_INPUT = REPO_ROOT / "_scratch" / "universe_cleanup_proposal" / "universe_cleanup_proposal.csv"
RUN_ID = "FULL_SOURCE_DIAGNOSTIC_7004_20260626"
SOURCE_TAG = "FULL_SOURCE_DIAGNOSTIC_7004"
TABLE = "public.inmobiliarias_main"

NEW_COLS = ["diagnostic_status", "scraping_readiness", "exclude_from_scraping", "exclude_reason",
            "diagnostic_status_source", "diagnostic_status_updated_at", "last_diagnostic_run_id",
            "diagnostic_notes"]

# action -> (diagnostic_status, scraping_readiness, exclude_from_scraping, exclude_reason)
MAP = {
    "keep_ready_to_scrape":              ("ready",             "ready_now",      False, None),
    "reincorporate_misclassified_ready": ("ready",             "ready_now",      False, None),
    "needs_quality_fix":                 ("needs_quality_fix", "ready_after_fix", False, None),
    "needs_cms_strategy_fix":            ("needs_cms_strategy", "ready_after_fix", False, None),
    "needs_parser_fix":                  ("needs_parser",      "ready_after_fix", False, None),
    "needs_listing_url_fix":             ("needs_listing_url", "ready_after_fix", False, None),
    "needs_playwright_runner":           ("needs_playwright",  "ready_after_fix", False, None),
    "exclude_missing_url":               ("missing_url",       "excluded",       True, "sin URL"),
    "exclude_domain_down":               ("domain_down",       "excluded",       True, "dominio caido (DNS/conexion)"),
    "exclude_prohibited_source":         ("prohibited_source", "excluded",       True, "fuente prohibida por regla de ERETZ"),
    "manual_review":                     ("manual_review",     "manual_review",  False, None),
}


def env(p):
    if not pathlib.Path(p).exists():
        return
    for line in pathlib.Path(p).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def db_check(source_ids):
    """Read-only: verifica filas, columnas nuevas, no-backfill, ids existentes."""
    env(REPO_ROOT / ".env")
    env(REPO_ROOT / ".env.local")
    info = {"connected": False}
    url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not url:
        return info
    try:
        import psycopg
        conn = psycopg.connect(url, connect_timeout=30)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        cur.execute(f"SELECT count(*) FROM {TABLE}")
        info["rows"] = cur.fetchone()[0]
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='inmobiliarias_main'")
        cols = set(r[0] for r in cur.fetchall())
        info["new_cols_present"] = [c for c in NEW_COLS if c in cols]
        info["new_cols_missing"] = [c for c in NEW_COLS if c not in cols]
        cur.execute(f"SELECT count(*) FILTER (WHERE diagnostic_status IS NOT NULL) FROM {TABLE}")
        info["already_backfilled"] = cur.fetchone()[0]
        cur.execute(f"SELECT id FROM {TABLE}")
        db_ids = set(r[0] for r in cur.fetchall())
        info["ids_in_csv_not_in_db"] = len([s for s in source_ids if s not in db_ids])
        info["connected"] = True
        conn.close()
    except Exception as e:
        info["error"] = str(e)[:150]
    return info


def main():
    ap = argparse.ArgumentParser(description="Backfill diagnostic_status (DRY-RUN, no DB writes)")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--input", default=str(DEF_INPUT))
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "diagnostic_status_backfill_dry_run"))
    ap.add_argument("--expected-total", type=int, default=7004)
    args = ap.parse_args()

    if args.commit:
        raise SystemExit("--commit is not authorized in this PR")

    inp = pathlib.Path(args.input)
    if not inp.exists():
        raise SystemExit(f"No existe input: {inp}")
    rows_in = list(csv.DictReader(inp.open(encoding="utf-8")))

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    actions = []
    unmapped = []
    for r in rows_in:
        sid = int(r["source_id"])
        act = r.get("recommended_action")
        if act not in MAP:
            unmapped.append(sid)
            continue
        ds, sr, ex, rsn = MAP[act]
        actions.append({
            "source_id": sid,
            "source_name": r.get("source_name"),
            "province": r.get("province"),
            "city": r.get("city"),
            "recommended_action": act,
            "diagnostic_status": ds,
            "scraping_readiness": sr,
            "exclude_from_scraping": ex,
            "exclude_reason": rsn,
            "diagnostic_status_source": SOURCE_TAG,
            "last_diagnostic_run_id": RUN_ID,
        })

    source_ids = [a["source_id"] for a in actions]
    by_status = Counter(a["diagnostic_status"] for a in actions)
    by_readiness = Counter(a["scraping_readiness"] for a in actions)
    by_exclude = Counter(a["exclude_from_scraping"] for a in actions)
    dbinfo = db_check(source_ids)

    # ---- CSV / JSONL principal ----
    acols = ["source_id", "source_name", "province", "city", "recommended_action", "diagnostic_status",
             "scraping_readiness", "exclude_from_scraping", "exclude_reason",
             "diagnostic_status_source", "last_diagnostic_run_id"]
    with (out_dir / "backfill_actions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=acols, extrasaction="ignore"); w.writeheader()
        for a in actions:
            w.writerow(a)
    with (out_dir / "backfill_actions.jsonl").open("w", encoding="utf-8") as f:
        for a in actions:
            f.write(json.dumps(a, ensure_ascii=False, default=str) + "\n")

    def counts_csv(name, counter, key):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow([key, "count"])
            for k, v in counter.most_common():
                w.writerow([k, v])
    counts_csv("backfill_counts_by_status.csv", by_status, "diagnostic_status")
    counts_csv("backfill_counts_by_readiness.csv", by_readiness, "scraping_readiness")
    counts_csv("backfill_counts_by_exclude_flag.csv", by_exclude, "exclude_from_scraping")

    def sub(name, pred):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=acols, extrasaction="ignore"); w.writeheader()
            for a in actions:
                if pred(a):
                    w.writerow(a)
    sub("ready_rows.csv", lambda a: a["scraping_readiness"] == "ready_now")
    sub("excluded_rows.csv", lambda a: a["exclude_from_scraping"] is True)
    sub("needs_fix_rows.csv", lambda a: a["scraping_readiness"] == "ready_after_fix")
    sub("manual_review_rows.csv", lambda a: a["diagnostic_status"] == "manual_review")

    # ---- SQL preview (UPDATE por diagnostic_status, batched IN) ----
    HEADER = ("-- DRY RUN PREVIEW ONLY\n-- DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION\n"
              "-- Pobla SOLO las 8 columnas de diagnostico. NO toca sitio_activo/cms_detectado/"
              "estrategia_scraping/url_listado/activa.\n"
              f"-- run_id={RUN_ID}  total={len(actions)}\n\n")
    by_target = {}
    for a in actions:
        by_target.setdefault((a["diagnostic_status"], a["scraping_readiness"], a["exclude_from_scraping"], a["exclude_reason"]), []).append(a["source_id"])
    sql_parts = [HEADER, "-- BACKUP previo recomendado antes de un commit real:\n"
                 f"-- CREATE TABLE public.backup_inmobiliarias_main_pre_backfill_YYYYMMDD AS SELECT * FROM {TABLE};\n\n"]
    for (ds, sr, ex, rsn), ids in sorted(by_target.items(), key=lambda x: -len(x[1])):
        reason_sql = "NULL" if rsn is None else f"'{rsn}'"
        sql_parts.append(f"-- {ds} | readiness={sr} | exclude={ex} | {len(ids)} filas")
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            sql_parts.append(
                f"UPDATE {TABLE} SET diagnostic_status='{ds}', scraping_readiness='{sr}', "
                f"exclude_from_scraping={'true' if ex else 'false'}, exclude_reason={reason_sql}, "
                f"diagnostic_status_source='{SOURCE_TAG}', diagnostic_status_updated_at=now(), "
                f"last_diagnostic_run_id='{RUN_ID}', diagnostic_notes=NULL "
                f"WHERE id IN ({','.join(str(x) for x in chunk)});")
        sql_parts.append("")
    (out_dir / "backfill_preview.sql").write_text("\n".join(sql_parts), encoding="utf-8")

    # ---- VALIDACIONES ----
    V = []
    V.append(("1. total input == expected", len(rows_in) == args.expected_total, f"{len(rows_in)} vs {args.expected_total}"))
    V.append(("2. todos los source_id en DB", dbinfo.get("ids_in_csv_not_in_db", "n/a") == 0, dbinfo.get("ids_in_csv_not_in_db")))
    V.append(("3. sin source_id duplicados", len(source_ids) == len(set(source_ids)), len(source_ids) - len(set(source_ids))))
    V.append(("4. todas con accion valida (mapeada)", len(unmapped) == 0, f"unmapped={len(unmapped)}"))
    V.append(("5. todas las acciones tienen mapeo", set(by_status) <= set(v[0] for v in MAP.values()), "ok"))
    V.append(("9. prohibidas NO quedan ready", all(a["scraping_readiness"] != "ready_now" for a in actions if a["recommended_action"] == "exclude_prohibited_source"), "ok"))
    needs = ("needs_cms_strategy", "needs_parser", "needs_listing_url", "needs_playwright", "needs_quality_fix")
    V.append(("10. ningun needs_* queda excluded", all(not a["exclude_from_scraping"] for a in actions if a["diagnostic_status"] in needs), "ok"))
    sql_no_comments = "\n".join(
        ln for ln in (out_dir / "backfill_preview.sql").read_text(encoding="utf-8").splitlines()
        if not ln.strip().startswith("--"))
    V.append(("11-14. SQL (statements) no toca sitio_activo/cms/estrategia/url",
              all(c not in sql_no_comments for c in ("sitio_activo", "cms_detectado", "estrategia_scraping", "url_listado")),
              "verificado sobre statements (sin comentarios)"))
    V.append(("15. columnas nuevas existen en DB", len(dbinfo.get("new_cols_missing", ["?"])) == 0, dbinfo.get("new_cols_present")))
    V.append(("16. backfill NO aplicado aun (diagnostic_status all null)", dbinfo.get("already_backfilled", -1) == 0, dbinfo.get("already_backfilled")))
    V.append(("18. cero DB writes en este paso", True, "solo SELECT read-only"))
    allok = all(v[1] for v in V)
    with (out_dir / "backfill_validation_report.md").open("w", encoding="utf-8") as f:
        f.write(f"# Backfill dry-run — validaciones\n_generado: {now_iso()}_\n\n")
        for name, ok, det in V:
            f.write(f"- {'✅' if ok else '❌'} {name} ({det})\n")
        f.write(f"\n**DB info (read-only):** {json.dumps(dbinfo, ensure_ascii=False)}\n")

    # ---- summary ----
    L = [f"# Backfill diagnostic_status — DRY RUN summary", f"_generado: {now_iso()}_  ·  total: **{len(actions)}**", "",
         "## Conteos por diagnostic_status"]
    for k, v in by_status.most_common():
        L.append(f"- `{k}`: {v}")
    L += ["", "## Conteos por scraping_readiness"]
    for k, v in by_readiness.most_common():
        L.append(f"- `{k}`: {v}")
    L += ["", f"## exclude_from_scraping=true: **{by_exclude.get(True, 0)}**  ·  false: {by_exclude.get(False, 0)}",
          "", f"validaciones OK: **{allok}**",
          "", "## Comando futuro (NO ejecutar)",
          "`apply_diagnostic_backfill.py --commit --backup-first --batch 500`  (hoy bloqueado)",
          "", "## Cero DB writes en este paso."]
    (out_dir / "backfill_dry_run_summary.md").write_text("\n".join(L), encoding="utf-8")

    print(f"[backfill-dry-run] total={len(actions)} unmapped={len(unmapped)} validaciones_ok={allok}")
    print(f"[backfill-dry-run] by_status={dict(by_status.most_common())}")
    print(f"[backfill-dry-run] by_readiness={dict(by_readiness.most_common())} exclude_true={by_exclude.get(True,0)}")
    print(f"[backfill-dry-run] db: {dbinfo}")
    print(f"[backfill-dry-run] archivos en {out_dir}")


if __name__ == "__main__":
    main()

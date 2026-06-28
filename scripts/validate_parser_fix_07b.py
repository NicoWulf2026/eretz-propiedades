#!/usr/bin/env python
"""PR-BE-PARSER-07b local validation.

Compares the previous parse_cards implementation from git HEAD against the
current working-tree implementation on diagnostic HTML fetches. Local outputs
only; no DB, no publish, no raw/staging, no productive runs.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import pathlib
import random
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import requests
import urllib3


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRAPER_DIR = REPO_ROOT / "scraper"
if str(SCRAPER_DIR) not in sys.path:
    sys.path.insert(0, str(SCRAPER_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from playwright_scraper import parse_cards as new_parse_cards  # noqa: E402


DEFAULT_NEEDS = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "needs_parser_fix.csv"
DEFAULT_RESULTS = REPO_ROOT / "_scratch" / "url_listing_post_update_validation" / "post_update_validation_results.csv"
DEFAULT_GAP = REPO_ROOT / "_scratch" / "parser_gap_analysis_pr_be_parser_07" / "parser_gap_results.csv"
DEFAULT_OUT = REPO_ROOT / "_scratch" / "parser_fix_pr_be_parser_07b"
EXPECTED_NEEDS = 413
USER_AGENT = "ERETZ-ParserFixValidation/07b (+diagnostic; no DB writes)"


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(clean(value)))
    except Exception:
        return default


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing required input: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: pathlib.Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_old_parse_cards(out: pathlib.Path):
    old_path = out / "_old_playwright_scraper_head.py"
    old_source = subprocess.check_output(
        ["git", "show", "HEAD:scraper/playwright_scraper.py"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    old_path.write_text(old_source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("old_playwright_scraper_head", old_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load old parse_cards")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_cards


def site_base(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if not parsed.netloc:
        return url
    return urllib.parse.urlunsplit((parsed.scheme or "https", parsed.netloc, "", "", ""))


def operation_from_url(url: str) -> str:
    low = url.lower()
    if "alquiler" in low or "rent" in low:
        return "alquiler"
    return "venta"


def merge_rows(needs: list[dict[str, str]], gap_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    gap_by_id = {clean(row.get("source_id")): row for row in gap_rows}
    out = []
    for row in needs:
        sid = clean(row.get("source_id"))
        gap = gap_by_id.get(sid, {})
        url = clean(row.get("new_url_listado") or row.get("url_listado"))
        out.append({
            "source_id": sid,
            "source_name": clean(row.get("source_name")),
            "website_url": clean(row.get("website_url")) or site_base(url),
            "url_listado": url,
            "family": clean(gap.get("detected_family")) or "unknown",
            "estimated_property_yield": clean(row.get("estimated_property_yield")),
            "previous_property_links": clean(row.get("property_links_detected")),
        })
    return out


def regression_rows(all_results: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    rows = [
        row for row in all_results
        if clean(row.get("new_status")) in {"success_after_url_fix", "partial_after_url_fix"}
        and to_int(row.get("property_links_detected")) > 0
    ]
    rows.sort(key=lambda r: (to_int(r.get("estimated_property_yield")), to_int(r.get("property_links_detected"))), reverse=True)
    if limit and len(rows) > limit:
        rows = rows[:limit]
    out = []
    for row in rows:
        url = clean(row.get("new_url_listado") or row.get("url_listado"))
        out.append({
            "source_id": clean(row.get("source_id")),
            "source_name": clean(row.get("source_name")),
            "website_url": clean(row.get("website_url")) or site_base(url),
            "url_listado": url,
            "family": "regression_baseline",
            "estimated_property_yield": clean(row.get("estimated_property_yield")),
            "previous_property_links": clean(row.get("property_links_detected")),
        })
    return out


def prop_urls(props: list[Any]) -> set[str]:
    out = set()
    for prop in props:
        url = clean(getattr(prop, "url", ""))
        if url:
            out.add(url)
    return out


def parse_count(parser, html: str, row: dict[str, str]) -> tuple[int, str]:
    try:
        props = parser(
            html,
            operation_from_url(row["url_listado"]),
            f"diagnostic_{row['source_id']}",
            row.get("website_url") or site_base(row["url_listado"]),
            "Argentina",
        )
        urls = prop_urls(props)
        return len(urls), " | ".join(sorted(urls)[:5])
    except Exception as exc:
        return 0, f"parse_error:{type(exc).__name__}"


def validate_one(row: dict[str, str], old_parser, session: requests.Session, timeout: float, group: str, max_html_chars: int) -> dict[str, Any]:
    status = 0
    final_url = ""
    html = ""
    error = ""
    started = time.perf_counter()
    try:
        resp = session.get(row["url_listado"], timeout=timeout, allow_redirects=True, verify=False)
        status = resp.status_code
        final_url = resp.url
        ctype = resp.headers.get("content-type", "")
        if "html" in ctype or "text" in ctype or not ctype:
            html = (resp.text or "")[:max_html_chars]
    except Exception as exc:
        error = type(exc).__name__
    elapsed = round(time.perf_counter() - started, 3)
    old_count, old_sample = parse_count(old_parser, html, row) if html else (0, "")
    new_count, new_sample = parse_count(new_parse_cards, html, row) if html else (0, "")
    status_after = "still_failed"
    if new_count >= 3:
        status_after = "success_after_parser_fix"
    elif new_count > 0:
        status_after = "partial_after_parser_fix"
    recovered = old_count == 0 and new_count > 0
    regression = group == "regression" and old_count > 0 and new_count == 0
    return {
        "source_id": row["source_id"],
        "source_name": row["source_name"],
        "group": group,
        "family": row.get("family", ""),
        "website_url": row.get("website_url", ""),
        "url_listado": row["url_listado"],
        "http_status": status,
        "final_url_after_redirect": final_url,
        "html_size": len(html),
        "old_parse_cards_count": old_count,
        "new_parse_cards_count": new_count,
        "delta": new_count - old_count,
        "status_after": status_after,
        "recovered": recovered,
        "regression": regression,
        "estimated_property_yield": to_int(row.get("estimated_property_yield")),
        "previous_property_links": to_int(row.get("previous_property_links")),
        "old_sample": old_sample,
        "new_sample": new_sample,
        "error": error,
        "elapsed_seconds": elapsed,
    }


def md_table(rows: list[dict[str, Any]], fields: list[str], limit: int = 20) -> str:
    subset = rows[:limit]
    if not subset:
        return "_Sin filas._"
    lines = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in subset:
        vals = []
        for field in fields:
            value = clean(row.get(field)).replace("|", "\\|")
            if len(value) > 120:
                value = value[:117] + "..."
            vals.append(value)
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_docs(out: pathlib.Path, needs_results: list[dict[str, Any]], regression: list[dict[str, Any]], test_result: str) -> None:
    success = [r for r in needs_results if r["status_after"] == "success_after_parser_fix"]
    partial = [r for r in needs_results if r["status_after"] == "partial_after_parser_fix"]
    failed = [r for r in needs_results if r["status_after"] == "still_failed"]
    recovered = [r for r in needs_results if r["recovered"]]
    regressions = [r for r in regression if r["regression"]]
    family_recovered = Counter(r["family"] for r in recovered)
    before_links = sum(to_int(r["old_parse_cards_count"]) for r in needs_results)
    after_links = sum(to_int(r["new_parse_cards_count"]) for r in needs_results)
    family_lines = "\n".join(f"- {family}: {count}" for family, count in family_recovered.most_common())
    top_recovered = sorted(recovered, key=lambda r: (to_int(r["estimated_property_yield"]), to_int(r["new_parse_cards_count"])), reverse=True)
    top_failed = sorted(failed, key=lambda r: (to_int(r["estimated_property_yield"]), -to_int(r["new_parse_cards_count"])), reverse=True)

    write_csv(out / "parser_fix_before_after.csv", needs_results)
    write_csv(out / "recovered_after_parser_fix.csv", recovered)
    write_csv(out / "still_failed_after_parser_fix.csv", failed)
    write_csv(out / "regression_check.csv", regression)
    write_csv(out / "top_recovered_by_yield.csv", top_recovered[:100])
    write_csv(out / "top_still_failed_by_yield.csv", top_failed[:100])

    summary = f"""# PR-BE-PARSER-07b parser fix summary

Generated: {datetime.now(timezone.utc).isoformat()}

## Resultado sobre 413 needs_parser_fix
- Total fuentes validadas: **{len(needs_results)}**
- success_after_parser_fix: **{len(success)}**
- partial_after_parser_fix: **{len(partial)}**
- still_failed: **{len(failed)}**
- recovered old=0 new>0: **{len(recovered)}**
- property links antes: **{before_links}**
- property links despues: **{after_links}**
- delta property links: **{after_links - before_links}**

## Recuperadas por familia
{family_lines or "_Sin recuperadas._"}

## Regresion
- Fuentes de regresion evaluadas: **{len(regression)}**
- Regresiones old>0 new=0: **{len(regressions)}**

## Top 20 recuperadas
{md_table(top_recovered, ['source_id', 'source_name', 'family', 'estimated_property_yield', 'old_parse_cards_count', 'new_parse_cards_count', 'delta', 'url_listado'])}

## Top 20 todavia fallidas
{md_table(top_failed, ['source_id', 'source_name', 'family', 'estimated_property_yield', 'old_parse_cards_count', 'new_parse_cards_count', 'http_status', 'error', 'url_listado'])}

## Guardrails
- DB writes: 0
- UPDATE: 0
- Publish: 0
- Scraping productivo/runs: 0
- Push/deploy/frontend: 0
- `--include-backlog`: no usado
"""
    (out / "parser_fix_summary.md").write_text(summary, encoding="utf-8")
    (out / "test_results.md").write_text(test_result, encoding="utf-8")
    (out / "risk_assessment.md").write_text(
        """# Risk assessment

- El fix amplia candidatos de URL, pero exige senales fuertes de card para evitar links de navegacion.
- La regresion compara old/new parse_cards sobre el mismo HTML; cualquier regression marcada debe revisarse antes de productivizar.
- La validacion es diagnostica local: no visita fichas completas ni escribe raw/staging.
- Algunos sitios pueden variar por timeout, region o user-agent.
""",
        encoding="utf-8",
    )
    (out / "next_step_recommendation.md").write_text(
        """# Next step recommendation

Revisar `regression_check.csv`. Si no hay regresiones bloqueantes, el siguiente paso es PR-BE-PARSER-07c: minilote diagnostico sin DB writes sobre las fuentes recuperadas para verificar parseo de detalle antes de cualquier corrida productiva.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate PR-BE-PARSER-07b parser fix locally")
    parser.add_argument("--needs-parser", default=str(DEFAULT_NEEDS))
    parser.add_argument("--post-results", default=str(DEFAULT_RESULTS))
    parser.add_argument("--parser-gap", default=str(DEFAULT_GAP))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=12)
    parser.add_argument("--regression-limit", type=int, default=627)
    parser.add_argument("--max-html-chars", type=int, default=1_000_000)
    parser.add_argument("--seed", type=int, default=717)
    parser.add_argument("--include-backlog", action="store_true")
    args = parser.parse_args()

    if args.include_backlog:
        raise SystemExit("--include-backlog is not authorized in PR-BE-PARSER-07b")

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    old_parser = load_old_parse_cards(out)
    needs = merge_rows(read_csv(pathlib.Path(args.needs_parser)), read_csv(pathlib.Path(args.parser_gap)))
    if len(needs) != EXPECTED_NEEDS:
        raise SystemExit(f"Expected {EXPECTED_NEEDS} needs_parser rows, got {len(needs)}")
    regression = regression_rows(read_csv(pathlib.Path(args.post_results)), args.regression_limit)

    random.seed(args.seed)
    work = [("needs", row) for row in needs] + [("regression", row) for row in regression]
    random.shuffle(work)
    results: list[dict[str, Any]] = []
    completed = 0
    lock = threading.Lock()
    thread_local = threading.local()

    def get_session() -> requests.Session:
        if not hasattr(thread_local, "session"):
            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            thread_local.session = session
        return thread_local.session

    def worker(item: tuple[str, dict[str, str]]) -> dict[str, Any]:
        group, row = item
        return validate_one(row, old_parser, get_session(), args.timeout, group, args.max_html_chars)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(worker, item) for item in work]
        for future in as_completed(futures):
            results.append(future.result())
            with lock:
                completed += 1
                if completed % 100 == 0 or completed == len(work):
                    print(f"validated={completed}/{len(work)}")

    needs_results = sorted([r for r in results if r["group"] == "needs"], key=lambda r: to_int(r["source_id"]))
    regression_results = sorted([r for r in results if r["group"] == "regression"], key=lambda r: to_int(r["source_id"]))
    test_result = (out / "test_results.md").read_text(encoding="utf-8") if (out / "test_results.md").exists() else "# Test results\n\n_Not populated yet._\n"
    write_docs(out, needs_results, regression_results, test_result)

    success = sum(1 for r in needs_results if r["status_after"] == "success_after_parser_fix")
    partial = sum(1 for r in needs_results if r["status_after"] == "partial_after_parser_fix")
    failed = sum(1 for r in needs_results if r["status_after"] == "still_failed")
    recovered = sum(1 for r in needs_results if r["recovered"])
    regressions = sum(1 for r in regression_results if r["regression"])
    print(f"total_needs={len(needs_results)}")
    print(f"success_after_parser_fix={success}")
    print(f"partial_after_parser_fix={partial}")
    print(f"still_failed={failed}")
    print(f"recovered={recovered}")
    print(f"regression_rows={len(regression_results)}")
    print(f"regressions={regressions}")
    print(f"old_links={sum(to_int(r['old_parse_cards_count']) for r in needs_results)}")
    print(f"new_links={sum(to_int(r['new_parse_cards_count']) for r in needs_results)}")
    print(f"out={out}")
    print("db_writes=0")
    print("publish=0")
    print("scraping_productivo=0")
    print("runs=0")
    print("push_deploy_frontend=0")


if __name__ == "__main__":
    main()

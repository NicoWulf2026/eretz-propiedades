"""
Batch retest for strategy_quality_failed sites.
Runs --test-url for each site, captures result, writes summary.
"""
import csv, subprocess, sys, os, json, re, time
from pathlib import Path
from datetime import datetime

PYTHON = sys.executable
SCRAPER = str(Path(__file__).parent.parent.parent.parent / "scraper" / "scraper_propiedades.py")
BATCH_CSV = str(Path(__file__).parent / "quality_failed_retest_batch.csv")
OUT_DIR = Path(__file__).parent / "quality_retest_20260607"
OUT_DIR.mkdir(exist_ok=True)
(OUT_DIR / "raw_logs").mkdir(exist_ok=True)
(OUT_DIR / "captured").mkdir(exist_ok=True)
STDOUT_LOG = OUT_DIR / "batch_stdout.log"


def slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", url.lower())[:60].strip("_")


def parse_result(stderr: str) -> dict:
    """Extract key info from scraper stderr."""
    lines = stderr.splitlines()
    diag = next((l for l in lines if "Diagnostico:" in l), "")
    strategy = next((l for l in lines if "Estrategia elegida:" in l), "")
    score_line = next((l for l in lines if "score=" in l.lower()), "")
    presupuesto = next((l for l in lines if "presupuesto de item" in l), "")
    return {
        "diagnostico": diag.split("Diagnostico:")[-1].strip() if diag else "",
        "estrategia": strategy.split("Estrategia elegida:")[-1].strip() if strategy else "",
        "score": score_line,
        "presupuesto": presupuesto,
    }


def run_site(idx: int, total: int, inmo_id: str, nombre: str, url: str) -> dict:
    site_slug = f"{idx:04d}_{slug(url)}"
    log_path = OUT_DIR / "raw_logs" / f"{site_slug}.log"
    props_json = OUT_DIR / "captured" / f"{site_slug}.json"
    meta_json = OUT_DIR / "captured" / f"{site_slug}.metadata.json"

    cmd = [
        PYTHON, SCRAPER,
        "--test-url", url,
        "--workers", "1",
        "--dump-props-json", str(props_json),
        "--dump-metadata-json", str(meta_json),
        "--allow-static-detail",
    ]

    print(f"[{idx}/{total}] {nombre} | {url[:60]}", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=280, encoding="utf-8", errors="replace")
    elapsed = round(time.time() - t0, 1)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    # Parse props count from stdout (JSON lines)
    props_count = 0
    try:
        if props_json.exists():
            data = json.loads(props_json.read_text(encoding="utf-8"))
            props_count = len(data) if isinstance(data, list) else 0
    except Exception:
        pass

    # Determine status from stderr
    status = "unknown"
    if "strategy_quality_failed" in stderr:
        status = "strategy_quality_failed"
    elif "item_timeout" in stderr or "ItemTimeoutError" in stderr:
        status = "item_timeout"
    elif "timeout" in stderr.lower() and props_count == 0:
        status = "timeout"
    elif "no_property_links" in stderr:
        status = "no_property_links"
    elif props_count > 0:
        status = "ok"
    elif result.returncode != 0:
        status = f"error_{result.returncode}"
    else:
        status = "ok_0props"

    parsed = parse_result(stderr)

    log_path.write_text(
        f"CMD: {' '.join(cmd)}\n\n=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n",
        encoding="utf-8",
    )

    row = {
        "idx": idx,
        "inmobiliaria_id": inmo_id,
        "nombre": nombre,
        "url": url,
        "status": status,
        "props": props_count,
        "elapsed_s": elapsed,
        "diagnostico": parsed["diagnostico"],
        "estrategia": parsed["estrategia"],
    }
    summary_line = f"[{idx}/{total}] {status} props={props_count} elapsed={elapsed}s url={url}"
    print(f"  -> {summary_line}", flush=True)
    with open(STDOUT_LOG, "a", encoding="utf-8") as f:
        f.write(summary_line + "\n")
    return row


def main():
    with open(BATCH_CSV, encoding="utf-8") as f:
        sites = list(csv.DictReader(f))

    total = len(sites)
    results = []
    print(f"Starting retest of {total} strategy_quality_failed sites")
    print(f"Output: {OUT_DIR}")
    print("=" * 60)

    for i, site in enumerate(sites, 1):
        try:
            row = run_site(i, total, site["inmobiliaria_id"], site["inmobiliaria_nombre"], site["url_listado"])
        except subprocess.TimeoutExpired:
            row = {
                "idx": i, "inmobiliaria_id": site["inmobiliaria_id"],
                "nombre": site["inmobiliaria_nombre"], "url": site["url_listado"],
                "status": "item_timeout_hard", "props": 0, "elapsed_s": 280,
                "diagnostico": "", "estrategia": "",
            }
            print(f"  → [HARD TIMEOUT] {site['url_listado']}", flush=True)
        results.append(row)

    # Write results CSV
    results_csv = OUT_DIR / "results.csv"
    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["idx","inmobiliaria_id","nombre","url","status","props","elapsed_s","diagnostico","estrategia"])
        w.writeheader()
        w.writerows(results)

    # Summary
    from collections import Counter
    counts = Counter(r["status"] for r in results)
    ok = sum(r["props"] for r in results if r["status"] == "ok")
    print("\n" + "=" * 60)
    print("RETEST SUMMARY")
    print("=" * 60)
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    print(f"  Total props captured: {ok}")
    print(f"Results: {results_csv}")


if __name__ == "__main__":
    main()

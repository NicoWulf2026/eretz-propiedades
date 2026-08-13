#!/usr/bin/env python
"""FULL_SCRAPE_COVERAGE_7004 — PASADA 2 (Playwright).

Re-intenta con Chromium las fuentes que el HTTP dejó como candidatas a JS/render/bloqueo/no-links.
Extracción REAL (no muestras de 3): renderiza el listado, descubre links, parsea propiedades
hasta un cap de seguridad REGISTRADO. NO escribe DB. NO publica. Solo _scratch. Checkpoint/resume.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import pathlib
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HTTP_JSONL = REPO_ROOT / "_scratch" / "full_scrape_coverage_7004" / "source_results.jsonl"

from playwright.async_api import async_playwright  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ANTIBOT = ("just a moment", "cf-browser-verification", "challenge-platform", "_cf_chl",
           "attention required", "datadome", "perimeterx", "incapsula")
CAPTCHA = ("recaptcha", "hcaptcha", "g-recaptcha", "captcha")
LOGIN = ("iniciar sesion", "iniciar sesión", "ingresar al sistema", "acceso restringido")
PROP_RE = re.compile(r"(propiedad|propiedades|inmueble|inmuebles|ficha|detalle|emprendimiento|"
                     r"/p/|/prop/|listing|property|/aviso|/venta/|/alquiler/)", re.I)
PRICE_RE = re.compile(r"(u\$s|us\$|usd|ar\$|\$|pesos|dolar)\s*\.?\s*[\d][\d\.\,]{2,}", re.I)
COORD_RE = re.compile(r"(\"lat(itude)?\"\s*[:=]\s*-?\d{1,2}\.\d{3,}|maps[^\"']{0,40}-?\d{1,2}\.\d{3,},-?\d)", re.I)
IMG_BLOCK = re.compile(r"(logo|placeholder|no-?photo|no-?image|sin-?imagen|prop-icons|footer|banner|avatar|icon)", re.I)

CANDIDATE_STATUSES = ("requires_playwright", "antibot", "forbidden", "captcha", "no_property_links", "parser_error")

FIELDS = [
    "campaign_run_id", "source_id", "source_name", "previous_http_status", "playwright_attempted",
    "playwright_loaded", "playwright_final_status", "start_time", "end_time", "duration_seconds",
    "listing_url", "final_url_after_redirect", "http_status", "page_title", "console_errors_count",
    "captcha_detected", "cloudflare_detected", "login_required", "antibot_confirmed",
    "property_links_detected", "property_links_count", "properties_detected", "properties_parsed",
    "properties_failed", "partial_due_to_cap", "truncated_by_timeout", "truncated_by_max_pages",
    "truncated_by_max_items", "quality_score_avg", "missing_title_count", "missing_price_count",
    "missing_operation_count", "missing_type_count", "missing_location_count", "missing_images_count",
    "error_category", "error_subcategory", "error_detail_short", "error_detail_long",
    "stack_trace_or_exception", "recommended_fix_family", "recommended_next_action", "notes",
]
LOCK = asyncio.Lock()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def detect_fields(html):
    low = html.lower()
    f = {k: False for k in ("title", "price", "operation", "ptype", "location", "images", "coord")}
    if "<title" in low or "<h1" in low:
        f["title"] = True
    if PRICE_RE.search(low):
        f["price"] = True
    if re.search(r"\b(venta|alquiler|alquila|vende|temporario)\b", low):
        f["operation"] = True
    if re.search(r"\b(casa|departamento|depto|ph|terreno|lote|local|oficina|galpon|campo|cochera)\b", low):
        f["ptype"] = True
    if re.search(r"(\"addresslocality\"|\"streetaddress\"|provincia|localidad|\bcalle\b|\bavenida\b)", low):
        f["location"] = True
    if re.search(r"(<img|og:image)", low) and not re.search(r"only.{0,10}(logo|icon)", low):
        f["images"] = True
    if COORD_RE.search(low):
        f["coord"] = True
    return f


def fix_family(cat):
    return {"playwright_success": "playwright", "playwright_success_low_quality": "playwright",
            "playwright_partial_due_to_cap": "playwright", "playwright_no_property_links": "parser",
            "playwright_zero_properties": "parser", "playwright_parser_error": "parser",
            "playwright_true_antibot": "antibot", "playwright_captcha": "antibot",
            "playwright_login_required": "antibot", "playwright_timeout": "infra",
            "playwright_domain_down": "url", "playwright_error": "manual"}.get(cat, "manual")


def base_rec(src, run_id):
    r = {k: None for k in FIELDS}
    r.update({"campaign_run_id": run_id, "source_id": src["source_id"], "source_name": src.get("source_name"),
              "previous_http_status": src.get("final_status"), "listing_url": src.get("listing_url") or src.get("website_url"),
              "playwright_attempted": True, "playwright_loaded": False, "property_links_detected": False,
              "property_links_count": 0, "properties_detected": 0, "properties_parsed": 0, "properties_failed": 0,
              "partial_due_to_cap": False, "truncated_by_timeout": False, "truncated_by_max_pages": False,
              "truncated_by_max_items": False, "captcha_detected": False, "cloudflare_detected": False,
              "login_required": False, "antibot_confirmed": False, "console_errors_count": 0,
              "missing_title_count": 0, "missing_price_count": 0, "missing_operation_count": 0,
              "missing_type_count": 0, "missing_location_count": 0, "missing_images_count": 0})
    return r


async def diagnose(browser, src, cfg, run_id, shots):
    r = base_rec(src, run_id)
    t0 = time.monotonic(); r["start_time"] = now_iso()

    def fin(cat, sub="", short="", long="", action="manual_review", notes=""):
        r["playwright_final_status"] = cat; r["error_category"] = cat; r["error_subcategory"] = sub
        r["error_detail_short"] = short; r["error_detail_long"] = long
        r["recommended_fix_family"] = fix_family(cat); r["recommended_next_action"] = action
        r["notes"] = notes; r["end_time"] = now_iso(); r["duration_seconds"] = round(time.monotonic() - t0, 2)
        return r

    target = (src.get("listing_url") or src.get("website_url") or "").strip()
    if not target:
        return fin("playwright_domain_down", short="sin URL", action="skip")
    if not re.match(r"^https?://", target, re.I):
        target = "https://" + target
    console_errors = []
    ctx = await browser.new_context(user_agent=UA, ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    page = await ctx.new_page()
    page.on("console", lambda m: console_errors.append(1) if m.type == "error" else None)
    try:
        resp = await page.goto(target, timeout=cfg["lt"] * 1000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        r["playwright_loaded"] = True
        r["http_status"] = resp.status if resp else None
        r["final_url_after_redirect"] = page.url
        r["page_title"] = (await page.title())[:160]
        html = await page.content(); low = html.lower()
        text = re.sub(r"<[^>]+>", " ", html); tlen = len(text.strip())
        r["console_errors_count"] = len(console_errors)
        r["cloudflare_detected"] = "cloudflare" in low or "_cf_chl" in low
        r["captcha_detected"] = any(x in low for x in CAPTCHA)
        r["login_required"] = any(x in low for x in LOGIN) and tlen < 1500
        if any(x in low for x in ANTIBOT) and tlen < 1500:
            r["antibot_confirmed"] = True
            try:
                sp = shots / f"{src['source_id']}_antibot.png"; await page.screenshot(path=str(sp))
            except Exception:
                pass
            await ctx.close()
            return fin("playwright_true_antibot", short="antibot tras JS", action="requires_antibot_review")
        if r["login_required"]:
            await ctx.close()
            return fin("playwright_login_required", action="manual_review")
        # links (con scroll para infinite)
        try:
            hrefs = await page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)")
        except Exception:
            hrefs = []
        host = urlparse(page.url).netloc.lower()
        links, seen = [], set()

        def collect(hs):
            for h in hs:
                if not h or not PROP_RE.search(h):
                    continue
                if urlparse(h).netloc.lower() not in ("", host):
                    continue
                p = urlparse(h).path
                if p.count("/") < 2 and not re.search(r"\d{2,}", p):
                    continue
                if h not in seen:
                    seen.add(h); links.append(h)
        collect(hrefs)
        before = len(links)
        try:
            await page.mouse.wheel(0, 5000); await page.wait_for_timeout(1200)
            collect(await page.eval_on_selector_all("a[href]", "els=>els.map(e=>e.href)"))
        except Exception:
            pass
        r["property_links_count"] = len(links)
        r["properties_detected"] = len(links)
        r["property_links_detected"] = len(links) > 0
        if not links:
            try:
                sp = shots / f"{src['source_id']}_nolinks.png"; await page.screenshot(path=str(sp))
            except Exception:
                pass
            await ctx.close()
            return fin("playwright_zero_properties" if tlen < 800 else "playwright_no_property_links",
                       short=f"0 links tras JS (tlen={tlen})", action="fix_parser")
        # extraccion real (cap max_items)
        sample = links[: cfg["mi"]]
        if len(links) > cfg["mi"]:
            r["partial_due_to_cap"] = True; r["truncated_by_max_items"] = True
        agg = Counter(); parsed = failed = 0; last = None
        for purl in sample:
            try:
                fp = await ctx.new_page()
                rr = await fp.goto(purl, timeout=cfg["pt"] * 1000, wait_until="domcontentloaded")
                if rr and rr.status < 400:
                    fh = await fp.content(); ff = detect_fields(fh); parsed += 1
                    for k, v in ff.items():
                        if v:
                            agg[k] += 1
                else:
                    failed += 1; last = f"http_{rr.status if rr else '?'}"
                await fp.close()
            except Exception as e:
                failed += 1; last = type(e).__name__
                try:
                    await fp.close()
                except Exception:
                    pass
        r["properties_parsed"] = parsed; r["properties_failed"] = failed
        n = max(parsed, 1)
        r["missing_title_count"] = parsed - agg["title"]; r["missing_price_count"] = parsed - agg["price"]
        r["missing_operation_count"] = parsed - agg["operation"]; r["missing_type_count"] = parsed - agg["ptype"]
        r["missing_location_count"] = parsed - agg["location"]; r["missing_images_count"] = parsed - agg["images"]
        await ctx.close()
        if parsed == 0:
            return fin("playwright_parser_error", sub=last or "", short="links pero 0 parseadas", action="fix_parser")
        score = int(round(100 * (0.22 * agg["title"] / n + 0.22 * agg["price"] / n + 0.16 * agg["operation"] / n +
                                 0.14 * agg["ptype"] / n + 0.10 * agg["location"] / n + 0.08 * agg["images"] / n +
                                 0.08 * agg["coord"] / n)))
        r["quality_score_avg"] = score
        if r["partial_due_to_cap"]:
            return fin("playwright_partial_due_to_cap", short=f"q={score} {parsed}/{len(links)}",
                       action="requires_playwright_runner")
        if score >= 55:
            return fin("playwright_success", short=f"q={score} n={parsed}", action="requires_playwright_runner")
        return fin("playwright_success_low_quality", short=f"q={score} n={parsed}", action="fix_parser")
    except Exception as e:
        et = type(e).__name__
        try:
            await ctx.close()
        except Exception:
            pass
        if "Timeout" in et:
            r["truncated_by_timeout"] = True
            return fin("playwright_timeout", sub=et, short="pw timeout", action="retry_later")
        return fin("playwright_domain_down" if "net::" in str(e) else "playwright_error",
                   sub=et, short=str(e)[:120], action="manual_review")


def load_candidates(only):
    recs = [json.loads(l) for l in HTTP_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    cats = set(only.split(",")) if only else set(CANDIDATE_STATUSES)
    out = []
    for r in recs:
        if r.get("final_status") in cats:
            out.append({"source_id": r["source_id"], "source_name": r.get("source_name"),
                        "listing_url": r.get("listing_url"), "website_url": r.get("website_url"),
                        "final_status": r.get("final_status")})
    return out


def write_outputs(out_dir):
    jl = out_dir / "playwright_source_results.jsonl"
    recs = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines() if l.strip()] if jl.exists() else []
    with (out_dir / "playwright_source_results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader()
        for r in recs:
            w.writerow(r)
    SUB = ["source_id", "source_name", "previous_http_status", "playwright_final_status",
           "property_links_count", "properties_parsed", "quality_score_avg", "recommended_fix_family", "error_detail_short"]

    def sub(name, pred):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUB, extrasaction="ignore"); w.writeheader()
            for r in sorted([x for x in recs if pred(x)], key=lambda x: x.get("properties_detected") or 0, reverse=True):
                w.writerow(r)
    recovered = lambda r: r["playwright_final_status"] in ("playwright_success", "playwright_success_low_quality", "playwright_partial_due_to_cap")
    sub("playwright_success_sources.csv", lambda r: r["playwright_final_status"] == "playwright_success")
    sub("playwright_partial_success_sources.csv", lambda r: r["playwright_final_status"] == "playwright_partial_due_to_cap")
    sub("playwright_recovered_sources.csv", recovered)
    sub("playwright_failed_sources.csv", lambda r: not recovered(r))
    sub("playwright_true_antibot.csv", lambda r: r["playwright_final_status"] == "playwright_true_antibot")
    sub("playwright_no_property_links.csv", lambda r: r["playwright_final_status"] in ("playwright_no_property_links", "playwright_zero_properties"))
    sub("playwright_parser_errors.csv", lambda r: r["playwright_final_status"] == "playwright_parser_error")
    sub("playwright_timeout_sources.csv", lambda r: r["playwright_final_status"] == "playwright_timeout")
    sub("playwright_quality_issues.csv", lambda r: r["playwright_final_status"] == "playwright_success_low_quality")
    errs = [r for r in recs if not recovered(r)]
    with (out_dir / "playwright_errors_detailed.jsonl").open("w", encoding="utf-8") as f:
        for r in errs:
            f.write(json.dumps({k: r.get(k) for k in ("source_id", "source_name", "playwright_final_status",
                    "error_category", "error_subcategory", "error_detail_short", "recommended_fix_family")}, ensure_ascii=False) + "\n")
    with (out_dir / "playwright_errors_detailed.csv").open("w", encoding="utf-8", newline="") as f:
        c = ["source_id", "source_name", "playwright_final_status", "error_category", "error_subcategory", "error_detail_short", "recommended_fix_family"]
        w = csv.DictWriter(f, fieldnames=c, extrasaction="ignore"); w.writeheader()
        for r in errs:
            w.writerow(r)
    freq = Counter(r["playwright_final_status"] for r in errs)
    with (out_dir / "playwright_top_errors_by_frequency.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["status", "count"]); [w.writerow(x) for x in freq.most_common()]
    imp = defaultdict(int)
    for r in errs:
        imp[r["playwright_final_status"]] += int(r.get("properties_detected") or 0)
    with (out_dir / "playwright_top_errors_by_impact.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["status", "links_sum"]); [w.writerow(x) for x in sorted(imp.items(), key=lambda y: -y[1])]
    fam = Counter(r["recommended_fix_family"] for r in recs)
    (out_dir / "playwright_recommended_fixes_by_family.md").write_text(
        "# Playwright pass — fixes por familia\n\n" + "\n".join(f"- `{k}`: {v}" for k, v in fam.most_common()), encoding="utf-8")
    (out_dir / "playwright_rerun_plan_after_fixes.md").write_text(
        "# Rerun plan (Playwright)\n\n1. Construir runner Playwright productivo para las recuperadas.\n"
        "2. Fix parser para no_property_links/parser_error.\n3. Revisar true_antibot caso por caso.\n", encoding="utf-8")
    st = Counter(r["playwright_final_status"] for r in recs)
    rec_n = sum(1 for r in recs if recovered(r))
    L = [f"# Playwright pass — summary ({now_iso()})", f"total: **{len(recs)}** · recuperadas: **{rec_n}**", "", "## Por status"]
    for k, v in st.most_common():
        L.append(f"- `{k}`: {v}")
    (out_dir / "playwright_campaign_summary.md").write_text("\n".join(L), encoding="utf-8")
    return {"total": len(recs), "recovered": rec_n, "status": dict(st.most_common())}


async def main_async(args):
    out_dir = pathlib.Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    shots = out_dir / "screenshots"; shots.mkdir(exist_ok=True)
    jl = out_dir / "playwright_source_results.jsonl"; logf = out_dir / "playwright_execution.log"
    if args.fresh and jl.exists():
        jl.rename(out_dir / f"playwright_source_results.prev_{int(time.time())}.jsonl")
    run_id = f"FULL_COVERAGE_PW_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cfg = {"lt": args.listing_timeout, "pt": args.property_timeout, "mi": args.max_items, "mp": args.max_pages}
    cands = load_candidates(args.only)
    done = set()
    if args.resume and jl.exists():
        for line in jl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["source_id"])
                except Exception:
                    pass
    pending = [c for c in cands if c["source_id"] not in done]
    if args.limit:
        pending = pending[: args.limit]
    print(f"[pw-campaign] run_id={run_id} candidatas={len(cands)} pending={len(pending)} workers={args.playwright_workers} max_items={args.max_items}")
    counts = Counter(); processed = [0]; t0 = time.monotonic()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        sem = asyncio.Semaphore(args.playwright_workers)

        async def worker(c):
            async with sem:
                try:
                    rec = await asyncio.wait_for(diagnose(browser, c, cfg, run_id, shots),
                                                 timeout=cfg["lt"] + cfg["pt"] * cfg["mi"] + 40)
                except Exception as e:
                    rec = base_rec(c, run_id)
                    rec.update({"playwright_final_status": "playwright_error", "error_category": "playwright_error",
                                "error_detail_short": str(e)[:150], "recommended_fix_family": "manual",
                                "start_time": now_iso(), "end_time": now_iso()})
                    async with LOCK:
                        with logf.open("a", encoding="utf-8") as f:
                            f.write(f"{c['source_id']}: {repr(e)[:200]}\n")
                async with LOCK:
                    with jl.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                    counts[rec["playwright_final_status"]] += 1; processed[0] += 1
                    n = processed[0]
                    if n % 50 == 0:
                        (out_dir / "playwright_progress.json").write_text(json.dumps(
                            {"updated_at": now_iso(), "processed": n, "pending": len(pending),
                             "rate_per_s": round(n / max(time.monotonic() - t0, 0.1), 2), "by_status": dict(counts)},
                            ensure_ascii=False, indent=2), encoding="utf-8")
                    if n % 250 == 0 or n == len(pending):
                        rate = n / max(time.monotonic() - t0, 0.1)
                        print(f"  [{n}/{len(pending)}] {rate:.2f}/s ETA~{(len(pending)-n)/max(rate,0.01)/60:.0f}min top={dict(counts.most_common(6))}")
        await asyncio.gather(*[worker(c) for c in pending])
        await browser.close()
    res = write_outputs(out_dir)
    print(f"[pw-campaign] LISTO en {(time.monotonic()-t0)/60:.1f} min. {res}")


def main():
    ap = argparse.ArgumentParser(description="FULL_SCRAPE_COVERAGE Playwright pass (no DB writes, no publish)")
    ap.add_argument("--full-extract", action="store_true")
    ap.add_argument("--only", default=",".join(CANDIDATE_STATUSES))
    ap.add_argument("--playwright-workers", type=int, default=4)
    ap.add_argument("--listing-timeout", type=int, default=25)
    ap.add_argument("--property-timeout", type=int, default=18)
    ap.add_argument("--max-items", type=int, default=15, help="cap fichas parseadas por inmobiliaria (registrado)")
    ap.add_argument("--max-pages", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "full_scrape_coverage_7004_playwright_pass"))
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

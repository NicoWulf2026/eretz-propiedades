#!/usr/bin/env python
"""FULL_SOURCE_DIAGNOSTIC_7004 — PASADA 2 (Playwright).

Diagnostica con Playwright (Chromium headless) las fuentes que el censo HTTP marco
requires_playwright / antibot / forbidden / captcha. Verifica si se recuperan al
renderizar JS, o si son antibot reales.

GARANTIAS:
- NO escribe DB. NO publica. NO toca colas.
- Escribe SOLO archivos locales en --out. Checkpoint/resume por source_id.
- try/except por fuente: una nunca corta la pasada.
- Limites: <=3 fichas/inmobiliaria, <=2 paginas listado, <=60 links, timeouts por etapa.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import pathlib
import re
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
HTTP_JSONL = REPO_ROOT / "_scratch" / "full_source_diagnostic_7004" / "diagnostic_results.jsonl"

from playwright.async_api import async_playwright  # noqa: E402

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
ANTIBOT_SIGNS = ("just a moment", "cf-browser-verification", "challenge-platform", "_cf_chl",
                 "attention required", "datadome", "perimeterx", "incapsula",
                 "verifique que es un humano", "verificando que")
CAPTCHA_SIGNS = ("recaptcha", "hcaptcha", "g-recaptcha", "captcha")
LOGIN_SIGNS = ("iniciar sesion", "iniciar sesión", "ingresar al sistema", "acceso restringido",
               "debe iniciar sesion")
PROP_LINK_RE = re.compile(r"(propiedad|propiedades|inmueble|inmuebles|ficha|detalle|emprendimiento|"
                          r"/p/|/prop/|listing|property|/aviso|/venta/|/alquiler/)", re.I)
PRICE_RE = re.compile(r"(u\$s|us\$|usd|ar\$|\$|pesos|dolar)\s*\.?\s*[\d][\d\.\,]{2,}", re.I)
COORD_RE = re.compile(r"(\"lat(itude)?\"\s*[:=]\s*-?\d{1,2}\.\d{3,}|maps[^\"']{0,40}-?\d{1,2}\.\d{3,},-?\d{1,2}\.\d{3,})", re.I)
IMG_BLOCK_RE = re.compile(r"(logo|placeholder|no-?photo|no-?image|sin-?imagen|prop-icons|footer|banner|avatar|icon)", re.I)

FIELD_ORDER = [
    "diagnostic_run_id", "diagnosed_at", "source_id", "source_name", "website_url", "listing_url",
    "final_status_http", "expected_property_yield",
    "playwright_attempted", "playwright_loaded", "playwright_http_status", "playwright_final_url",
    "playwright_response_time_ms", "playwright_page_title", "playwright_text_sample",
    "playwright_dom_ready", "playwright_network_idle", "playwright_screenshot_saved",
    "playwright_console_errors_count", "playwright_console_errors_sample",
    "playwright_requests_blocked_count", "playwright_captcha_detected", "playwright_cloudflare_detected",
    "playwright_login_required", "playwright_antibot_confirmed", "playwright_property_links_detected",
    "playwright_property_links_count", "playwright_property_links_unique_count",
    "playwright_property_links_sample", "playwright_pagination_detected", "playwright_infinite_scroll_detected",
    "playwright_sample_property_urls", "playwright_sample_property_count_attempted",
    "playwright_sample_property_count_loaded", "playwright_sample_property_count_parsed",
    "playwright_sample_has_title", "playwright_sample_has_price", "playwright_sample_has_currency",
    "playwright_sample_has_operation", "playwright_sample_has_property_type", "playwright_sample_has_description",
    "playwright_sample_has_city", "playwright_sample_has_province", "playwright_sample_has_address",
    "playwright_sample_has_images", "playwright_sample_has_coordinates", "playwright_quality_score_0_100",
    "playwright_final_status", "playwright_recovered", "recommended_action_after_playwright",
    "recommended_fix_family_after_playwright", "priority_after_playwright", "notes",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def detect_fields(html):
    low = html.lower()
    f = {k: False for k in ("title", "price", "currency", "operation", "property_type", "description",
                            "city", "province", "address", "images", "coordinates")}
    if "<title" in low or "<h1" in low:
        f["title"] = True
    if PRICE_RE.search(low):
        f["price"] = True
        f["currency"] = bool(re.search(r"(u\$s|us\$|usd|ar\$|pesos|dolar)", low))
    if re.search(r"\b(venta|alquiler|alquila|vende|temporario|en pozo)\b", low):
        f["operation"] = True
    if re.search(r"\b(casa|departamento|depto|ph|terreno|lote|local|oficina|galpon|campo|cochera|duplex|chalet)\b", low):
        f["property_type"] = True
    if re.search(r"(name=\"description\"|og:description)", low):
        f["description"] = True
    if re.search(r"(\"addresslocality\"|\"streetaddress\"|provincia|localidad)", low):
        f["city"] = True; f["address"] = True
    if re.search(r"(\"addressregion\"|provincia)", low):
        f["province"] = True
    if re.search(r"\b(calle|av\.|avenida|ruta|barrio)\b", low):
        f["address"] = True
    if re.search(r"(<img|og:image)", low):
        f["images"] = True
    if COORD_RE.search(low):
        f["coordinates"] = True
    return f


def quality_score(agg, n):
    if n == 0:
        return 0
    core = {"title": 18, "price": 18, "operation": 14, "property_type": 12}
    extra = {"description": 8, "city": 8, "address": 6, "images": 8, "coordinates": 8}
    sc = sum(w * (agg.get(k, 0) / n) for k, w in core.items())
    sc += sum(w * (agg.get(k, 0) / n) for k, w in extra.items())
    return int(round(sc))


def base_rec(src):
    r = {k: None for k in FIELD_ORDER}
    r["source_id"] = src["source_id"]
    r["source_name"] = src["source_name"]
    r["website_url"] = src.get("website_url")
    r["listing_url"] = src.get("listing_url")
    r["final_status_http"] = src.get("final_status")
    r["expected_property_yield"] = src.get("expected_property_yield")
    for k in ("playwright_attempted", "playwright_loaded", "playwright_dom_ready", "playwright_network_idle",
              "playwright_captcha_detected", "playwright_cloudflare_detected", "playwright_login_required",
              "playwright_antibot_confirmed", "playwright_property_links_detected", "playwright_pagination_detected",
              "playwright_infinite_scroll_detected", "playwright_recovered"):
        r[k] = False
    for k in ("playwright_property_links_count", "playwright_property_links_unique_count",
              "playwright_console_errors_count", "playwright_requests_blocked_count",
              "playwright_sample_property_count_attempted", "playwright_sample_property_count_loaded",
              "playwright_sample_property_count_parsed"):
        r[k] = 0
    return r


async def diagnose(browser, src, cfg, shots_dir):
    r = base_rec(src)
    r["diagnostic_run_id"] = cfg["run_id"]
    r["diagnosed_at"] = now_iso()
    r["playwright_attempted"] = True
    target = src.get("listing_url") or src.get("website_url") or ""
    if not target:
        r["playwright_final_status"] = "playwright_domain_down"
        r["recommended_action_after_playwright"] = "skip_not_real_estate"
        r["recommended_fix_family_after_playwright"] = "url"; r["priority_after_playwright"] = "low"
        return r
    if not re.match(r"^https?://", target, re.I):
        target = "https://" + target
    console_errors = []
    blocked = [0]
    context = await browser.new_context(user_agent=UA, ignore_https_errors=True,
                                        viewport={"width": 1366, "height": 900})
    page = await context.new_page()
    page.on("console", lambda m: console_errors.append(m.text[:160]) if m.type == "error" else None)
    page.on("requestfailed", lambda req: blocked.__setitem__(0, blocked[0] + 1))
    t0 = time.monotonic()
    try:
        resp = await page.goto(target, timeout=cfg["listing_timeout"] * 1000, wait_until="domcontentloaded")
        r["playwright_dom_ready"] = True
        r["playwright_http_status"] = resp.status if resp else None
        try:
            await page.wait_for_load_state("networkidle", timeout=cfg["idle_timeout"] * 1000)
            r["playwright_network_idle"] = True
        except Exception:
            r["playwright_network_idle"] = False
        r["playwright_loaded"] = True
        r["playwright_final_url"] = page.url
        r["playwright_response_time_ms"] = int((time.monotonic() - t0) * 1000)
        r["playwright_page_title"] = (await page.title())[:160]
        html = await page.content()
        low = html.lower()
        text = re.sub(r"<[^>]+>", " ", html)
        r["playwright_text_sample"] = re.sub(r"\s+", " ", text).strip()[:300]
        text_len = len(text.strip())
        r["playwright_console_errors_count"] = len(console_errors)
        r["playwright_console_errors_sample"] = json.dumps(console_errors[:3], ensure_ascii=False)
        r["playwright_requests_blocked_count"] = blocked[0]
        r["playwright_cloudflare_detected"] = "cloudflare" in low or "_cf_chl" in low
        r["playwright_captcha_detected"] = any(x in low for x in CAPTCHA_SIGNS)
        r["playwright_login_required"] = any(x in low for x in LOGIN_SIGNS) and text_len < 1500

        # antibot real: tras render JS, sigue siendo challenge con poco contenido
        if any(x in low for x in ANTIBOT_SIGNS) and text_len < 1500:
            r["playwright_antibot_confirmed"] = True
            shot = shots_dir / f"{src['source_id']}_antibot.png"
            try:
                await page.screenshot(path=str(shot)); r["playwright_screenshot_saved"] = shot.name
            except Exception:
                pass
            r["playwright_final_status"] = "playwright_true_antibot"
            r["recommended_action_after_playwright"] = "requires_antibot_review"
            r["recommended_fix_family_after_playwright"] = "antibot"; r["priority_after_playwright"] = "high"
            await context.close()
            return r
        if r["playwright_login_required"]:
            r["playwright_final_status"] = "playwright_login_required"
            r["recommended_action_after_playwright"] = "manual_review"
            r["recommended_fix_family_after_playwright"] = "antibot"; r["priority_after_playwright"] = "low"
            await context.close()
            return r

        # links de propiedad (DOM renderizado)
        try:
            hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception:
            hrefs = []
        base_host = urlparse(page.url).netloc.lower()
        links, seen = [], set()
        for h in hrefs:
            if not h or not PROP_LINK_RE.search(h):
                continue
            if urlparse(h).netloc.lower() not in ("", base_host):
                continue
            path = urlparse(h).path
            if path.count("/") < 2 and not re.search(r"\d{2,}", path):
                continue
            if h in seen:
                continue
            seen.add(h); links.append(h)
            if len(links) >= cfg["max_links"]:
                break
        # infinite scroll: scrollear y re-contar
        before = len(links)
        try:
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1200)
            hrefs2 = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            extra = set(h for h in hrefs2 if PROP_LINK_RE.search(h or "") and h not in seen
                        and urlparse(h).netloc.lower() in ("", base_host))
            if extra:
                for h in list(extra)[: cfg["max_links"] - len(links)]:
                    links.append(h); seen.add(h)
                r["playwright_infinite_scroll_detected"] = len(links) > before
        except Exception:
            pass
        r["playwright_pagination_detected"] = bool(re.search(r"(\?page=|/page/|pagina=|rel=\"next\")", low))
        r["playwright_property_links_count"] = len(links)
        r["playwright_property_links_unique_count"] = len(set(links))
        r["playwright_property_links_detected"] = len(links) > 0
        r["playwright_property_links_sample"] = json.dumps(links[:5], ensure_ascii=False)

        if not links:
            shot = shots_dir / f"{src['source_id']}_nolinks.png"
            try:
                await page.screenshot(path=str(shot)); r["playwright_screenshot_saved"] = shot.name
            except Exception:
                pass
            r["playwright_quality_score_0_100"] = 0
            if text_len < 800:
                r["playwright_final_status"] = "playwright_zero_properties"
            else:
                r["playwright_final_status"] = "playwright_no_property_links"
            r["recommended_action_after_playwright"] = "requires_parser_fix"
            r["recommended_fix_family_after_playwright"] = "parser"; r["priority_after_playwright"] = "medium"
            await context.close()
            return r

        # parse de muestra (<=N fichas)
        sample = links[: cfg["sample_n"]]
        r["playwright_sample_property_urls"] = json.dumps(sample, ensure_ascii=False)
        r["playwright_sample_property_count_attempted"] = len(sample)
        agg = Counter()
        loaded = parsed = 0
        for purl in sample:
            try:
                fp = await context.new_page()
                resp2 = await fp.goto(purl, timeout=cfg["fiche_timeout"] * 1000, wait_until="domcontentloaded")
                if resp2 and resp2.status < 400:
                    loaded += 1
                    fhtml = await fp.content()
                    fields = detect_fields(fhtml)
                    if any(fields.values()):
                        parsed += 1
                        for k, v in fields.items():
                            if v:
                                agg[k] += 1
                await fp.close()
            except Exception:
                try:
                    await fp.close()
                except Exception:
                    pass
                continue
        r["playwright_sample_property_count_loaded"] = loaded
        r["playwright_sample_property_count_parsed"] = parsed
        for fk, rk in [("title", "playwright_sample_has_title"), ("price", "playwright_sample_has_price"),
                       ("currency", "playwright_sample_has_currency"), ("operation", "playwright_sample_has_operation"),
                       ("property_type", "playwright_sample_has_property_type"),
                       ("description", "playwright_sample_has_description"), ("city", "playwright_sample_has_city"),
                       ("province", "playwright_sample_has_province"), ("address", "playwright_sample_has_address"),
                       ("images", "playwright_sample_has_images"), ("coordinates", "playwright_sample_has_coordinates")]:
            r[rk] = (agg.get(fk, 0) > 0) if parsed else False
        score = quality_score(agg, parsed)
        r["playwright_quality_score_0_100"] = score
        if parsed == 0:
            r["playwright_final_status"] = "playwright_parser_error"
            r["recommended_action_after_playwright"] = "requires_parser_fix"
            r["recommended_fix_family_after_playwright"] = "parser"; r["priority_after_playwright"] = "high"
        elif score >= 55:
            r["playwright_final_status"] = "playwright_success"
            r["playwright_recovered"] = True
            r["recommended_action_after_playwright"] = "requires_playwright_runner"
            r["recommended_fix_family_after_playwright"] = "playwright"; r["priority_after_playwright"] = "high"
        else:
            r["playwright_final_status"] = "playwright_success_low_quality"
            r["playwright_recovered"] = True
            r["recommended_action_after_playwright"] = "requires_parser_fix"
            r["recommended_fix_family_after_playwright"] = "parser"; r["priority_after_playwright"] = "medium"
        await context.close()
        return r
    except Exception as e:
        et = type(e).__name__
        r["playwright_final_status"] = ("playwright_timeout" if "Timeout" in et else "playwright_domain_down"
                                        if "net::" in str(e) or "ERR" in str(e) else "playwright_unexpected_error")
        r["recommended_action_after_playwright"] = "retry_later"
        r["recommended_fix_family_after_playwright"] = "infra"; r["priority_after_playwright"] = "low"
        r["notes"] = str(e)[:160]
        try:
            await context.close()
        except Exception:
            pass
        return r


def flatten(rec):
    out = {}
    for k in FIELD_ORDER:
        v = rec.get(k)
        out[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
    return out


def build_outputs(out_dir):
    jsonl = out_dir / "playwright_results.jsonl"
    recs = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()] if jsonl.exists() else []
    with (out_dir / "playwright_results.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELD_ORDER, extrasaction="ignore"); w.writeheader()
        for r in recs:
            w.writerow(flatten(r))

    def subset(name, pred):
        cols = ["source_id", "source_name", "website_url", "listing_url", "final_status_http",
                "playwright_final_status", "playwright_property_links_count", "playwright_quality_score_0_100",
                "expected_property_yield", "recommended_action_after_playwright", "priority_after_playwright"]
        rows = [r for r in recs if pred(r)]
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c) for c in cols})
        return len(rows)

    subset("playwright_recovered_sources.csv", lambda r: r.get("playwright_recovered"))
    subset("playwright_ready_to_scrape.csv", lambda r: r.get("playwright_final_status") == "playwright_success")
    subset("playwright_low_quality.csv", lambda r: r.get("playwright_final_status") == "playwright_success_low_quality")
    subset("playwright_true_antibot.csv", lambda r: r.get("playwright_final_status") == "playwright_true_antibot")
    subset("playwright_still_requires_antibot.csv", lambda r: r.get("playwright_antibot_confirmed") or r.get("playwright_final_status") in ("playwright_true_antibot", "playwright_captcha", "playwright_login_required"))
    subset("playwright_parser_errors.csv", lambda r: r.get("playwright_final_status") in ("playwright_parser_error", "playwright_no_property_links"))

    cat = Counter(r.get("playwright_final_status") for r in recs)
    rec_n = sum(1 for r in recs if r.get("playwright_recovered"))
    qs = [r.get("playwright_quality_score_0_100") for r in recs if r.get("playwright_recovered") and r.get("playwright_quality_score_0_100")]
    avgq = round(sum(qs) / len(qs), 1) if qs else 0
    lines = [f"# Playwright Pass 2 — summary", f"_generado: {now_iso()}_  ·  total: **{len(recs)}**  ·  recuperadas: **{rec_n}**  ·  calidad prom recuperadas: {avgq}", "", "## Por playwright_final_status"]
    for k, v in cat.most_common():
        lines.append(f"- `{k}`: {v}")
    (out_dir / "playwright_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return {"total": len(recs), "recovered": rec_n, "avg_quality": avgq, "by_status": dict(cat)}


def load_targets(sanity):
    recs = [json.loads(l) for l in HTTP_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    tgt = [{"source_id": r["source_id"], "source_name": r["source_name"], "website_url": r.get("website_url"),
            "listing_url": r.get("listing_url"), "final_status": r["final_status"],
            "expected_property_yield": r.get("expected_property_yield")}
           for r in recs if r["final_status"] in ("requires_playwright", "antibot", "forbidden", "captcha")]

    def y(t):
        try:
            return int(t.get("expected_property_yield") or 0)
        except Exception:
            return 0
    # orden: requires_playwright primero, luego antibot/forbidden/captcha; dentro por yield desc
    tgt.sort(key=lambda t: (0 if t["final_status"] == "requires_playwright" else 1, -y(t)))
    if sanity:
        rp = [t for t in tgt if t["final_status"] == "requires_playwright"]
        ab = [t for t in tgt if t["final_status"] in ("antibot", "forbidden", "captcha")]
        pick = rp[:5] + ab[:3]
        # 2 de mayor yield global no ya incluidos
        for t in sorted(tgt, key=y, reverse=True):
            if t not in pick:
                pick.append(t)
            if len(pick) >= 10:
                break
        return pick
    return tgt


async def main_async(args):
    out_dir = pathlib.Path(args.out)
    shots_dir = out_dir / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    shots_dir.mkdir(exist_ok=True)
    jsonl = out_dir / "playwright_results.jsonl"
    err_log = out_dir / "playwright_errors.log"
    if args.fresh and jsonl.exists():
        jsonl.rename(out_dir / f"playwright_results.prev_{int(time.time())}.jsonl")

    run_id = f"PLAYWRIGHT_PASS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cfg = {"run_id": run_id, "listing_timeout": args.listing_timeout, "idle_timeout": args.idle_timeout,
           "fiche_timeout": args.fiche_timeout, "sample_n": args.sample_properties, "max_links": args.max_links}
    targets = load_targets(args.sanity)
    done = set()
    if args.resume and jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["source_id"])
                except Exception:
                    pass
    pending = [t for t in targets if t["source_id"] not in done]
    if args.limit:
        pending = pending[: args.limit]
    print(f"[pw] run_id={run_id} | targets={len(targets)} done={len(done)} pending={len(pending)} workers={args.workers}")

    lock = asyncio.Lock()
    counts = Counter()
    processed = [0]
    t0 = time.monotonic()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        sem = asyncio.Semaphore(args.workers)

        async def worker(src):
            async with sem:
                try:
                    rec = await asyncio.wait_for(diagnose(browser, src, cfg, shots_dir), timeout=cfg["listing_timeout"] + cfg["fiche_timeout"] * cfg["sample_n"] + 30)
                except Exception as e:
                    rec = base_rec(src)
                    rec.update({"diagnostic_run_id": run_id, "diagnosed_at": now_iso(),
                                "playwright_final_status": "playwright_unexpected_error",
                                "recommended_action_after_playwright": "retry_later", "notes": str(e)[:150]})
                    async with lock:
                        with err_log.open("a", encoding="utf-8") as f:
                            f.write(f"{src['source_id']}: {repr(e)[:300]}\n")
                async with lock:
                    with jsonl.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                    counts[rec.get("playwright_final_status")] += 1
                    processed[0] += 1
                    n = processed[0]
                    if n % 25 == 0:
                        (out_dir / "playwright_progress.json").write_text(json.dumps(
                            {"updated_at": now_iso(), "processed": n, "pending": len(pending),
                             "rate_per_s": round(n / max(time.monotonic() - t0, 0.1), 2),
                             "by_status": dict(counts)}, ensure_ascii=False, indent=2), encoding="utf-8")
                    if n % 25 == 0 or n == len(pending):
                        rate = n / max(time.monotonic() - t0, 0.1)
                        print(f"  [{n}/{len(pending)}] {rate:.2f}/s recovered={sum(1 for k,v in counts.items() if k in ('playwright_success','playwright_success_low_quality') for _ in range(v))} top={dict(counts.most_common(5))}")

        await asyncio.gather(*[worker(t) for t in pending])
        await browser.close()

    res = build_outputs(out_dir)
    print(f"[pw] LISTO en {(time.monotonic()-t0)/60:.1f} min. {res}")


def main():
    ap = argparse.ArgumentParser(description="Playwright Pass 2 diagnostic (no DB writes, no publish)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sanity", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--listing-timeout", type=int, default=25)
    ap.add_argument("--idle-timeout", type=int, default=8)
    ap.add_argument("--fiche-timeout", type=int, default=18)
    ap.add_argument("--sample-properties", type=int, default=3)
    ap.add_argument("--max-links", type=int, default=60)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "full_source_diagnostic_7004_playwright_pass"))
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

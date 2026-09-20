#!/usr/bin/env python
"""PR-BE-CMS-STRATEGY-05 — Propuesta de clasificacion CMS/estrategia para cms_unknown.

SOLO PROPUESTA. NO escribe DB. NO toca scrapers. NO publica. Re-fetchea (1 GET) las
fuentes cms_unknown del censo y propone plataforma + estrategia + familia de fix,
agrupando por patrones. --commit bloqueado.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_env(p):
    pp = pathlib.Path(p)
    if not pp.exists():
        return
    for line in pp.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(REPO_ROOT / ".env")
load_env(REPO_ROOT / ".env.local")

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from scraper.network_security import secure_get  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}

# superset de _CMS_FIRMAS (scraper/enrich_pipeline.py) + SPA
CMS_FIRMAS = {
    "tokko": ["tokkobroker.com", "tokkowidget", "tokko_key", "api.tokkobroker", "tokko-widget", "data-tokko", "tokko.com"],
    "wordpress": ["wp-content/", "wp-includes/", "/wp-json/", "wp-login.php", "wp-content"],
    "wix": ["wix.com", "_wixcidx", "static.wixstatic.com", "wixsite.com", "parastorage"],
    "webflow": ["webflow.com", "assets-global.website-files.com", "w-webflow"],
    "squarespace": ["squarespace.com", "sqspcdn.com", "static1.squarespace"],
    "shopify": ["cdn.shopify.com", "myshopify.com"],
    "nexo": ["nexoinmuebles.com", "nexo.com.ar"],
    "inmoweb": ["inmoweb.com.ar"],
}
SPA_FIRMAS = {"next_spa": ["__next_data__", "/_next/"], "nuxt": ["window.__nuxt__", "/_nuxt/"],
              "react_spa": ["data-reactroot", 'id="root"></div>', 'id="app"></div>'], "angular": ["ng-version"]}
WP_PLUGINS = {"wordpress_essential_real_estate_detail": ["essential-real-estate", "essential_real_estate", "ere_"],
              "wordpress_estatik_detail": ["estatik", "es_property", "esp_"],
              "wordpress_realhomes_detail": ["real-homes", "realhomes", "inspiry"],
              "wordpress_houzez_detail": ["houzez"], "wordpress_wpresidence_detail": ["wpresidence", "wp-residence"]}
PROP_PATTERNS = [("/propiedad/", "propiedad"), ("/propiedades/", "propiedades"), ("/properties/", "properties"),
                 ("/property/", "property"), ("/inmueble", "inmueble"), ("/ficha", "ficha"), ("/detalle", "detalle"),
                 ("/aviso", "aviso"), ("/emprendimiento", "emprendimiento"), ("/prop/", "prop"), ("/p/", "p_short")]
TOKKO_KEY_RE = re.compile(r"(tokko[_\-]?key|api[_\-]?key)\s*[=:'\"]+\s*['\"]?([a-z0-9\-]{20,50})", re.I)

LOCK = threading.Lock()

FIELDS = ["source_id", "source_name", "website_url", "listing_url", "current_cms_detectado",
          "current_estrategia_scraping", "http_final_status", "playwright_final_status", "detected_platform",
          "detected_cms_candidate", "detected_strategy_candidate", "confidence", "evidence", "html_signals",
          "url_patterns", "api_signals", "property_link_patterns", "recommended_cms_detectado",
          "recommended_estrategia_scraping", "recommended_fix_family", "requires_code_change",
          "requires_db_change_later", "requires_playwright", "requires_listing_url_fix", "requires_manual_review",
          "estimated_property_yield", "priority", "risk", "notes"]


def classify(src, yld):
    r = {k: None for k in FIELDS}
    r.update({"source_id": src["source_id"], "source_name": src.get("source_name"),
              "website_url": src.get("website_url"), "listing_url": src.get("listing_url"),
              "current_cms_detectado": src.get("current_cms"), "current_estrategia_scraping": src.get("current_estrat"),
              "http_final_status": src.get("http_final_status"), "playwright_final_status": src.get("pw_final_status"),
              "estimated_property_yield": yld, "requires_code_change": False, "requires_db_change_later": True,
              "requires_playwright": False, "requires_listing_url_fix": False, "requires_manual_review": False})
    target = (src.get("listing_url") or src.get("website_url") or "").strip()
    if target and not re.match(r"^https?://", target, re.I):
        target = "https://" + target
    if not target:
        r.update({"detected_platform": "no_url", "recommended_fix_family": "url", "confidence": "alta",
                  "requires_listing_url_fix": True, "evidence": "sin URL", "priority": "low", "risk": "ninguno"})
        return r
    try:
        resp = secure_get(requests, target, timeout=(5, 12), headers=UA)
        html = resp.text or ""; status = resp.status_code; final = resp.url
    except Exception as e:
        r.update({"detected_platform": "fetch_fail", "recommended_fix_family": "infra", "confidence": "baja",
                  "evidence": f"fetch {type(e).__name__}", "priority": "low", "risk": "ninguno",
                  "notes": "no respondio en re-fetch", "requires_manual_review": True})
        return r
    low = html.lower(); blob = (low + " " + final.lower())
    signals = []
    platform = "custom"
    for cms, firmas in CMS_FIRMAS.items():
        if any(f in blob for f in firmas):
            platform = cms; signals.append(cms); break
    spa = None
    for s, firmas in SPA_FIRMAS.items():
        if any(f in low for f in firmas):
            spa = s; signals.append(s); break
    # property link patterns
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    host = urlparse(final).netloc.lower()
    pat_count = Counter()
    for a in soup.find_all("a", href=True):
        h = a["href"].lower()
        for pat, name in PROP_PATTERNS:
            if pat in h:
                pat_count[name] += 1
    top_pat = pat_count.most_common(1)[0][0] if pat_count else None
    has_links = sum(pat_count.values()) > 0
    api = []
    if "/wp-json/" in low:
        api.append("wp-json")
    if TOKKO_KEY_RE.search(html) or "api.tokkobroker" in low:
        api.append("tokko_api")
    if "/api/" in low or "graphql" in low:
        api.append("generic_api")
    path = urlparse(final).path.rstrip("/")
    home_as_listing = (path in ("", "/")) and not has_links
    text_len = len(re.sub(r"<[^>]+>", " ", html).strip())

    # ---- recomendacion ----
    rec_cms, rec_strat, fam, conf, manual, pw, urlfix = platform, None, "cms", "media", False, False, False
    if platform == "tokko":
        rec_cms = "tokko"
        if "tokko_api" in api or TOKKO_KEY_RE.search(html):
            rec_strat = "tokko_api"; conf = "alta"
        else:
            rec_strat = "tokko_html"; conf = "alta"; pw = True
    elif platform == "wordpress":
        rec_cms = "wordpress"; conf = "alta"
        rec_strat = "wordpress_generic_detail"
        for strat, sigs in WP_PLUGINS.items():
            if any(s in low for s in sigs):
                rec_strat = strat; break
        if not has_links:
            fam = "parser"; rec_strat = rec_strat  # wordpress pero parser no encuentra links
    elif spa in ("next_spa", "nuxt", "react_spa", "angular") or platform in ("wix", "webflow", "squarespace"):
        rec_cms = platform if platform in ("wix", "webflow", "squarespace") else (spa or "next_spa")
        rec_strat = "playwright_dynamic"; fam = "playwright"; pw = True; conf = "alta"
    elif home_as_listing:
        rec_cms = "custom"; rec_strat = None; fam = "url"; urlfix = True; conf = "media"
    elif has_links:
        rec_cms = "custom"; rec_strat = "custom_listing_detail"; fam = "parser"; conf = "media"
    elif text_len < 600:
        rec_cms = spa or "custom"; rec_strat = "playwright_dynamic" if spa else None
        fam = "playwright" if spa else "manual"; pw = bool(spa); manual = not bool(spa); conf = "baja"
    else:
        rec_cms = "custom"; rec_strat = None; fam = "manual"; manual = True; conf = "baja"

    r.update({
        "detected_platform": platform if platform != "custom" else (spa or "custom"),
        "detected_cms_candidate": rec_cms, "detected_strategy_candidate": rec_strat,
        "confidence": conf, "evidence": ",".join(signals) or ("links:" + (top_pat or "none")),
        "html_signals": ",".join(signals), "url_patterns": top_pat or "",
        "api_signals": ",".join(api), "property_link_patterns": json.dumps(dict(pat_count), ensure_ascii=False),
        "recommended_cms_detectado": rec_cms, "recommended_estrategia_scraping": rec_strat,
        "recommended_fix_family": fam, "requires_code_change": fam in ("cms", "parser"),
        "requires_db_change_later": fam in ("cms",) or rec_strat is not None,
        "requires_playwright": pw, "requires_listing_url_fix": urlfix, "requires_manual_review": manual,
        "priority": "high" if (yld or 0) >= 500 else ("medium" if (yld or 0) >= 100 else "low"),
        "risk": "bajo", "notes": f"http={status} links={sum(pat_count.values())} tlen={text_len}",
    })
    return r


def main():
    ap = argparse.ArgumentParser(description="Propuesta CMS/estrategia (no DB writes, no scrapers)")
    ap.add_argument("--input-source-results", default=str(REPO_ROOT / "_scratch" / "full_scrape_coverage_7004" / "source_results.jsonl"))
    ap.add_argument("--input-playwright-results", default=str(REPO_ROOT / "_scratch" / "full_scrape_coverage_7004_playwright_pass" / "playwright_source_results.jsonl"))
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "cms_strategy_proposal"))
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()
    if args.commit:
        raise SystemExit("--commit is not implemented in this PR")

    http = [json.loads(l) for l in pathlib.Path(args.input_source_results).read_text(encoding="utf-8").splitlines() if l.strip()]
    pwmap = {}
    pp = pathlib.Path(args.input_playwright_results)
    if pp.exists():
        for l in pp.read_text(encoding="utf-8").splitlines():
            if l.strip():
                r = json.loads(l); pwmap[r["source_id"]] = r.get("playwright_final_status")
    cms_unknown = [{"source_id": h["source_id"], "source_name": h.get("source_name"),
                    "website_url": h.get("website_url"), "listing_url": h.get("listing_url"),
                    "current_cms": h.get("cms_detectado"), "current_estrat": h.get("estrategia_scraping"),
                    "http_final_status": h.get("final_status"), "pw_final_status": pwmap.get(h["source_id"])}
                   for h in http if h.get("final_status") == "cms_unknown"]
    # yield read-only
    yld = {}
    try:
        import psycopg
        c = psycopg.connect(os.getenv("INTERNAL_DB_URL"), connect_timeout=30); c.autocommit = True
        cur = c.cursor(); cur.execute("SET default_transaction_read_only=on")
        cur.execute("SELECT id,coalesce(total_propiedades,0) FROM public.inmobiliarias_main")
        yld = {r[0]: r[1] for r in cur.fetchall()}; c.close()
    except Exception as e:
        print("[warn] sin yield:", str(e)[:80])

    if args.limit:
        cms_unknown = cms_unknown[: args.limit]
    out_dir = pathlib.Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[cms-proposal] cms_unknown={len(cms_unknown)} workers={args.workers}")
    rows = []; t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(classify, s, yld.get(s["source_id"], 0)): s for s in cms_unknown}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rows.append(fut.result())
            except Exception:
                pass
            if i % 200 == 0:
                print(f"  [{i}/{len(cms_unknown)}] {i/max(time.monotonic()-t0,0.1):.1f}/s")

    with (out_dir / "cms_strategy_proposal.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader()
        for r in rows:
            w.writerow(r)
    with (out_dir / "cms_strategy_proposal.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def y(r):
        try:
            return int(r.get("estimated_property_yield") or 0)
        except Exception:
            return 0
    SUB = ["source_id", "source_name", "website_url", "listing_url", "detected_platform",
           "recommended_cms_detectado", "recommended_estrategia_scraping", "recommended_fix_family",
           "confidence", "estimated_property_yield", "evidence", "notes"]

    def sub(name, pred):
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUB, extrasaction="ignore"); w.writeheader()
            for r in sorted([x for x in rows if pred(x)], key=y, reverse=True):
                w.writerow(r)
    sub("wordpress_candidates.csv", lambda r: r["recommended_cms_detectado"] == "wordpress")
    sub("tokko_candidates.csv", lambda r: r["recommended_cms_detectado"] == "tokko")
    sub("custom_candidates.csv", lambda r: r["recommended_cms_detectado"] == "custom" and r["recommended_fix_family"] == "parser")
    sub("next_spa_candidates.csv", lambda r: r["recommended_estrategia_scraping"] == "playwright_dynamic" and r["detected_platform"] in ("next_spa", "nuxt", "react_spa", "angular"))
    sub("wix_candidates.csv", lambda r: r["recommended_cms_detectado"] == "wix")
    sub("webflow_squarespace_candidates.csv", lambda r: r["recommended_cms_detectado"] in ("webflow", "squarespace"))
    sub("listing_url_problem_candidates.csv", lambda r: r["requires_listing_url_fix"])
    sub("manual_review_candidates.csv", lambda r: r["requires_manual_review"])

    plat = Counter(r["detected_platform"] for r in rows)
    strat = Counter(r["recommended_estrategia_scraping"] for r in rows)
    fam = Counter(r["recommended_fix_family"] for r in rows)
    with (out_dir / "cms_unknown_by_detected_pattern.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["detected_platform", "count"]); [w.writerow(x) for x in plat.most_common()]
    with (out_dir / "cms_unknown_by_recommended_strategy.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["recommended_estrategia_scraping", "count"]); [w.writerow(x) for x in strat.most_common()]
    imp = defaultdict(int)
    for r in rows:
        imp[r["recommended_fix_family"]] += y(r)
    with (out_dir / "top_cms_strategy_by_impact.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["recommended_fix_family", "impacto_yield", "n"])
        for k, v in sorted(imp.items(), key=lambda x: -x[1]):
            w.writerow([k, v, fam[k]])
    print(f"[cms-proposal] LISTO en {(time.monotonic()-t0)/60:.1f} min | plataformas={dict(plat.most_common())}")
    print(f"[cms-proposal] estrategias={dict(strat.most_common())}")
    print(f"[cms-proposal] familias={dict(fam.most_common())}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""Run a CSV scraping batch through the safe --test-url capture path.

This runner does not consume the production queue and does not write Supabase or
Neon. It calls scraper_propiedades.py with --test-url and --dump-props-json, so
use import_captured_props_to_neon.py afterwards to persist useful captures into
the internal Neon flow.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRAPER_PATH = REPO_ROOT / "scraper" / "scraper_propiedades.py"
REPORT_DIR = REPO_ROOT / "reports" / "scraping_autofix"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "scraping_batches"
NON_CODE_FAMILIES = {"blocked", "site_down", "site_down_confirmed"}

RE_STRATEGY = re.compile(r"Estrategia usada:\s*(.+)")
RE_PROPS = re.compile(r"Propiedades detectadas:\s*(\d+)")
RE_ERROR = re.compile(r"TEST URL ERROR \(([^)]+)\):\s*(.+)")
SOURCE_LISTING_SIGNAL_RE = re.compile(
    r"(propiedades?|properties?|inmuebles?|venta|ventas|alquiler(?:es)?|"
    r"list(?:ado|ados|ing|ings)|buscar|busqueda|catalogo|portfolio|"
    r"emprendimientos?|desarrollos?|ficha|detalle)",
    re.I,
)
SOURCE_ADMIN_PATH_RE = re.compile(r"(^|/)(admin|wp-admin|login|panel|dashboard)(/|$)", re.I)
SOURCE_INSTITUTIONAL_PATH_RE = re.compile(
    r"(^|/)(vender|vende|servicios?|contacto|contact|empresa|nosotros|"
    r"quienes-somos|quienes_somos|tasaciones?|tasacion|inicio|home)"
    r"(/|\.[a-z]{2,4}|$)",
    re.I,
)
SOURCE_DEVELOPER_SIGNAL_RE = re.compile(
    r"(constructora|construccion|construcci[oó]n|desarrollos?|emprendimientos?|loteos?|"
    r"steel|retak|obras?|constructor)",
    re.I,
)
SOURCE_REALESTATE_SIGNAL_RE = re.compile(
    r"(inmobiliaria|propiedades|inmuebles|raices|raíces|real\s*estate|remax|broker|martillero)",
    re.I,
)
SOURCE_LINK_HUB_RE = re.compile(
    r"(^|\.)linktr\.ee$|(^|\.)linktree\.com$|(^|\.)beacons\.ai$|(^|\.)bio\.link$|"
    r"(^|\.)allmylinks\.com$|(^|\.)start\.page$",
    re.I,
)
# Portales siempre prohibidos: nunca scrapear, sin importar la URL o señales de listado.
# Decisión de producto: InmoCapital no scrapea portales de terceros.
SOURCE_PROHIBITED_PORTAL_RE = re.compile(
    r"(^|\.)(?:zonaprop|argenprop)\.com\.ar$",
    re.I,
)
# Paths que se saltan siempre, antes de evaluar listing signals.
# Evitan que palabras de listado (alquileres, venta) dentro de la ruta los rescaten.
SOURCE_UNCONDITIONAL_SKIP_PATH_RE = re.compile(
    r"(^|/)calculadora(?:-[a-z]+)*(/|\.[a-z]{2,4}|$)|"
    r"(^|/)tasacion(?:-de-[a-z][a-z-]*)(/|\.[a-z]{2,4}|$)",
    re.I,
)
SOURCE_EXTERNAL_PORTAL_RE = re.compile(
    r"(^|\.)(?:mercadolibre|navent|buscainmueble|properati|"
    r"infobae\.com|clarin\.com|lanacion\.com\.ar)(?:\.|$)",
    re.I,
)
SOURCE_FAKE_DOMAIN_RE = re.compile(
    r"^(?:admin|login|panel|vender|vende|alquiler|contacto|servicios?|empresa|home|inicio|"
    r"tasacion|tasaciones?|quienes-somos|nosotros|galeria|portfolio|emprendimientos?|"
    r"desarrollos?|noticias|blog|equipo|propiedades|inmuebles|web|sitio|pagina)$",
    re.I,
)
SOURCE_COMMERCIAL_PATH_RE = re.compile(
    r"(^|/)(garantias?-alquiler|garantias?_alquiler|"
    r"list-with-(?:us|me|you)|sell-with-us|work-with-us|partner-with-us|"
    r"list-your-property|publicar-tu-propiedad|"
    r"lista-con-nosotros|publicar-gratis|publicidad|"
    r"calculadora(?:-de)?-alquileres?|calculadora|"
    r"invertir|franquicia|franquicias|descargables?|"
    r"politica-de-privacidad|terminos-y-condiciones|legales?)(/|\.[a-z]{2,4}|$)",
    re.I,
)
_KNOWN_JS_DOMAINS_RE = re.compile(
    r"(^|\.)(?:redremax|tokkobroker|tokko\.io|proppit|imovelweb|infocasas|properati|"
    r"inmuebles24|laanunciadora)(?:\.|$)",
    re.I,
)


def normalize_url_for_preflight(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    # Anchor-only and relative paths cannot be scraped independently
    if raw.startswith("#"):
        return ""
    if raw.startswith("/") and not raw.startswith("//"):
        return ""
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw.lstrip("/")
    return raw


def classify_source_preflight(url: str, agency_name: str = "") -> Dict[str, Any]:
    normalized = normalize_url_for_preflight(url)
    parsed = urlparse(normalized)
    domain = parsed.netloc.lower()
    path_key = unquote(parsed.path or "").lower().strip("/")
    query = unquote(parsed.query or "").lower()
    fragment = unquote(parsed.fragment or "").lower().strip()
    combined = " ".join([domain, path_key, query, fragment, str(agency_name or "").lower()])
    signals: List[str] = []
    if re.search(r"(^|\.)remax(?:-|\.|$)|redremax", domain):
        signals.append("remax_api_detected")
    if SOURCE_LISTING_SIGNAL_RE.search(" ".join([path_key, query])):
        signals.append("listing_signal_in_url")
    if SOURCE_REALESTATE_SIGNAL_RE.search(combined):
        signals.append("real_estate_signal")
    if SOURCE_DEVELOPER_SIGNAL_RE.search(combined):
        signals.append("developer_or_construction_signal")

    def skipped(subfamily: str, reason: str) -> Dict[str, Any]:
        return {
            "skip": True,
            "error_type": "skipped_invalid_source",
            "error_family": "invalid_source",
            "error_subfamily": subfamily,
            "reason": reason,
            "signals": signals,
            "domain": domain,
            "normalized_url": normalized,
        }

    if not normalized or not domain:
        return skipped("invalid_source_url", "url_no_normalizable")
    # Hostname con un solo token y sin TLD (ej: https://vender, https://admin)
    if "." not in domain:
        return skipped("fake_domain", f"dominio_sintetico_sin_tld: {domain}")
    if SOURCE_ADMIN_PATH_RE.search(path_key):
        return skipped("admin_url", "url_apunta_a_admin_o_login")
    if fragment and not path_key:
        return skipped("anchor_only_url", f"url_solo_con_ancla: #{fragment}")
    if SOURCE_LINK_HUB_RE.search(domain):
        return skipped("link_hub", "url_hub_de_links_no_es_listado_propio")
    # Paths que siempre son no-listado aunque contengan palabras de listado.
    if SOURCE_UNCONDITIONAL_SKIP_PATH_RE.search(path_key):
        return skipped("non_listing_page", "pagina_no_listado_aunque_contenga_listing_keyword")
    # Portales siempre prohibidos: bloquear sin importar señales de listado en la URL.
    if SOURCE_PROHIBITED_PORTAL_RE.search(domain):
        return skipped("prohibited_external_portal", "portal_externo_prohibido_por_politica_de_producto")
    if SOURCE_EXTERNAL_PORTAL_RE.search(domain) and "listing_signal_in_url" not in signals:
        return skipped("external_portal", "portal_externo_sin_senal_de_listado_propio")
    if SOURCE_COMMERCIAL_PATH_RE.search(path_key) and "listing_signal_in_url" not in signals:
        return skipped("commercial_service_page", "pagina_comercial_o_legal_sin_senal_de_listado")
    if SOURCE_INSTITUTIONAL_PATH_RE.search(path_key) and "listing_signal_in_url" not in signals:
        return skipped("institutional_page", "pagina_institucional_sin_senal_de_listado")
    if "developer_or_construction_signal" in signals and "listing_signal_in_url" not in signals:
        return skipped("possible_developer_without_listings", "fuente_constructora_desarrolladora_sin_senal_de_listado")

    return {
        "skip": False,
        "error_type": "",
        "error_family": "",
        "error_subfamily": "no_listing_signals" if not (
            "listing_signal_in_url" in signals
            or "real_estate_signal" in signals
            or "remax_api_detected" in signals
        ) else "",
        "reason": "",
        "signals": signals,
        "domain": domain,
        "normalized_url": normalized,
    }


def classify_url_lane(preflight: Dict[str, Any]) -> str:
    """Classify URL into processing lane without making any network request.

    bad_source  — skip entirely (already caught by preflight).
    needs_js    — known JS-heavy platform; needs Playwright to extract listings.
    fast_http   — try HTTP first; no browser.
    """
    if preflight.get("skip"):
        return "bad_source"
    domain = (preflight.get("domain") or "").lower()
    signals = set(preflight.get("signals") or [])
    if "remax_api_detected" in signals or _KNOWN_JS_DOMAINS_RE.search(domain):
        return "needs_js"
    return "fast_http"


def resolve_run_config(
    preflight: Dict[str, Any],
    base_timeout: int,
    args: argparse.Namespace,
) -> Tuple[List[str], int, str]:
    """Return (extra_cmd_flags, effective_timeout_seconds, lane).

    fast_http lane: HTTP only, shorter timeout (max 120s unless base is lower).
    needs_js lane:  Playwright/API allowed, longer timeout (min 180s).
    bad_source:     No subprocess to launch; caller handles skip.

    --force-js-lane promotes any non-bad_source URL to needs_js so that
    batches of already-identified JS candidates receive browser flags.
    """
    lane = classify_url_lane(preflight)
    if lane == "bad_source":
        return [], 0, lane
    if getattr(args, "force_js_lane", False):
        lane = "needs_js"
    if lane == "needs_js":
        flags: List[str] = []
        if args.allow_playwright:
            flags.append("--allow-playwright")
        if args.allow_visible_api:
            flags.append("--allow-visible-api")
        if args.allow_network_interception:
            flags.append("--allow-network-interception")
        if args.allow_static_detail:
            flags.append("--allow-static-detail")
        return flags, max(base_timeout, 180), lane
    # fast_http: static detail is cheap (just HTTP); skip browser flags
    flags = []
    if args.allow_static_detail:
        flags.append("--allow-static-detail")
    return flags, min(base_timeout, 120), lane


def _extractor_family_from_strategy(strategy_current: str, error_subfamily: str = "") -> str:
    """Derive a human-readable extractor family from strategy_current for reporting."""
    s = (strategy_current or "").lower()
    e = (error_subfamily or "").lower()
    if "tokko" in s:              return "tokko"
    if "remax" in s:              return "remax_api"
    if "playwright" in s:         return "playwright"
    if "estatik" in s:            return "wordpress_estatik"
    if "sitemap" in s:            return "wordpress_sitemap"
    if "wordpress" in s:          return "wordpress_generic"
    if "static_html" in s:        return "static_html"
    if "json_ld" in s:            return "json_ld"
    if "visible_api" in s:        return "visible_api"
    if "network_interception" in s: return "network_interception"
    if "dynamic_site_no_cards" in e: return "playwright_required"
    return "unknown"


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r"^https?://", "", value or "")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return (text[:80] or fallback).strip("_")


def read_batch(path: Path, limit: int, offset: int, include_non_code: bool) -> List[Dict[str, str]]:
    csv.field_size_limit(1024 * 1024 * 64)
    rows: List[Dict[str, str]] = []
    seen = 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            url = (raw.get("url") or raw.get("url_listado") or raw.get("web") or "").strip()
            if not url:
                continue
            family = (raw.get("error_type") or "").strip()
            if not include_non_code and family in NON_CODE_FAMILIES:
                continue
            if seen < offset:
                seen += 1
                continue
            row = dict(raw)
            row["url"] = url
            rows.append(row)
            seen += 1
            if limit and len(rows) >= limit:
                break
    return rows


def parse_output(stdout: str, stderr: str) -> Dict[str, Any]:
    text = f"{stdout or ''}\n{stderr or ''}"
    result: Dict[str, Any] = {"strategy": None, "props": 0, "error_type": None, "error_message": None}
    match = RE_STRATEGY.search(text)
    if match:
        result["strategy"] = match.group(1).strip()
    match = RE_PROPS.search(text)
    if match:
        try:
            result["props"] = int(match.group(1))
        except ValueError:
            result["props"] = 0
    match = RE_ERROR.search(text)
    if match:
        result["error_type"] = match.group(1).strip()
        result["error_message"] = match.group(2).strip()[:300]
    return result


def read_json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def domain_from_url(url: str) -> str:
    return urlparse(normalize_url_for_preflight(url)).netloc.lower()


def is_remax_signal(url: str, text: str = "", metadata: Optional[Dict[str, Any]] = None) -> bool:
    domain = domain_from_url(url)
    if re.search(r"(^|\.)remax(?:-|\.|$)|redremax", domain):
        return True
    combined = f"{text or ''} {json.dumps(metadata or {}, ensure_ascii=False)[:4000]}".lower()
    return "api-ar.redremax.com" in combined or "redremax" in combined


def metadata_summary(metadata_payload: Any) -> Dict[str, Any]:
    if not isinstance(metadata_payload, dict):
        return {}
    metadata = metadata_payload.get("metadata") if isinstance(metadata_payload.get("metadata"), dict) else {}
    diagnostic = metadata.get("diagnostico_inicial") if isinstance(metadata.get("diagnostico_inicial"), dict) else {}
    strategy_plan = metadata.get("strategy_plan") if isinstance(metadata.get("strategy_plan"), dict) else {}
    progress = metadata.get("strategy_progress") if isinstance(metadata.get("strategy_progress"), dict) else {}
    last_stage = metadata_payload.get("last_stage") or metadata.get("last_stage") or metadata.get("estrategia_actual")
    last_status = metadata_payload.get("last_stage_status") or metadata.get("last_stage_status")
    current_strategy = metadata_payload.get("strategy") or metadata.get("estrategia_actual") or metadata.get("estrategia_final")
    if not last_stage and progress:
        try:
            latest = sorted(
                progress.values(),
                key=lambda item: str(item.get("updated_at") or ""),
            )[-1]
            last_stage = latest.get("strategy")
            last_status = latest.get("status")
        except Exception:
            pass
    endpoints: List[str] = []
    for value in (
        metadata.get("visible_api_endpoint_urls"),
        metadata.get("api_endpoints_detectados"),
        diagnostic.get("api_endpoints_detectados"),
        diagnostic.get("rest_api_probada"),
    ):
        if isinstance(value, list):
            endpoints.extend(str(item) for item in value)
    return {
        "last_stage": last_stage or "",
        "last_stage_status": last_status or "",
        "strategy_current": current_strategy or strategy_plan.get("primary_strategy") or "",
        "strategy_plan": strategy_plan.get("primary_strategy") or "",
        "classification": diagnostic.get("classification") or "",
        "error_subfamily": (
            metadata.get("error_subfamily")
            or diagnostic.get("no_property_links_subfamily")
            or diagnostic.get("source_preflight_reason")
            or ""
        ),
        "source_preflight_reason": diagnostic.get("source_preflight_reason") or "",
        "source_preflight_signals": diagnostic.get("source_preflight_signals") or [],
        "timeout_internal_expected_seconds": metadata.get("timeout_internal_expected_seconds") or metadata_payload.get("timeout_internal_expected_seconds") or "",
        "timeout_mode": metadata.get("timeout_mode") or metadata_payload.get("timeout_mode") or "",
        "remax_api_detected": bool(diagnostic.get("remax_api_detected")),
        "detected_api_endpoints": list(dict.fromkeys(endpoints))[:10],
    }


def kill_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort process tree cleanup for stuck scraper children."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def run_one(
    row: Dict[str, str],
    idx: int,
    args: argparse.Namespace,
    capture_dir: Path,
    raw_log_dir: Path,
) -> Dict[str, Any]:
    url = row["url"]
    slug = f"{idx:04d}_{slugify(url, 'url')}"
    json_path = capture_dir / f"{slug}.json"
    metadata_path = capture_dir / f"{slug}.metadata.json"
    log_path = raw_log_dir / f"{slug}.log"
    agency_name = row.get("inmobiliaria_nombre") or row.get("nombre") or ""
    preflight = classify_source_preflight(url, agency_name)
    if preflight.get("skip"):
        log_path.write_text(
            "PREFLIGHT SKIP\n"
            f"url={url}\n"
            f"reason={preflight.get('reason')}\n"
            f"subfamily={preflight.get('error_subfamily')}\n"
            f"signals={preflight.get('signals')}\n"
            "supabase_write=false\n",
            encoding="utf-8",
        )
        return {
            "idx": idx,
            "id": row.get("id") or "",
            "inmobiliaria_id": row.get("inmobiliaria_id") or "",
            "inmobiliaria_nombre": agency_name,
            "url": url,
            "domain": preflight.get("domain") or domain_from_url(url),
            "family_before": row.get("error_type") or "",
            "success": False,
            "skipped": True,
            "status": "skipped",
            "props": 0,
            "strategy": "",
            "strategy_current": "",
            "lane": "bad_source",
            "error_type": preflight.get("error_type") or "skipped_invalid_source",
            "error_family": preflight.get("error_family") or "invalid_source",
            "error_subfamily": preflight.get("error_subfamily") or "invalid_source_url",
            "error_message": preflight.get("reason") or "",
            "last_stage": "preflight",
            "last_stage_status": "skipped",
            "timeout_external_seconds": 0,
            "timeout_internal_expected_seconds": "",
            "returncode": 0,
            "elapsed_seconds": 0.0,
            "json_path": "",
            "metadata_path": "",
            "raw_log": str(log_path.relative_to(REPO_ROOT)),
            "preflight": preflight,
            "remax_api_detected": "remax_api_detected" in (preflight.get("signals") or []),
            "detected_api_endpoints": [],
            "used_playwright": False,
            "used_network_interception": False,
            "used_visible_api": False,
            "used_static_detail": False,
            "extractor_family": "",
        }
    run_flags, run_timeout, lane = resolve_run_config(preflight, args.timeout_seconds, args)
    used_playwright          = "--allow-playwright" in run_flags
    used_network_interception = "--allow-network-interception" in run_flags
    used_visible_api         = "--allow-visible-api" in run_flags
    used_static_detail       = "--allow-static-detail" in run_flags
    cmd = [
        sys.executable,
        str(SCRAPER_PATH),
        "--test-url",
        url,
        "--workers",
        "1",
        "--dump-props-json",
        str(json_path),
        "--dump-metadata-json",
        str(metadata_path),
    ] + run_flags

    env = os.environ.copy()
    # Defensive: --test-url is no-DB, but keep internal DB disabled in children.
    env["USE_INTERNAL_DB"] = "false"

    started = time.time()
    timed_out = False
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
        stdout, stderr = proc.communicate(timeout=run_timeout)
        stdout = stdout or ""
        stderr = stderr or ""
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        kill_process_tree(proc)
        stdout_tail, stderr_tail = proc.communicate()
        stdout = (exc.stdout if isinstance(exc.stdout, str) else "") or (stdout_tail or "")
        stderr = (exc.stderr if isinstance(exc.stderr, str) else "") or (stderr_tail or "")
        returncode = -1
        timed_out = True
    elapsed = round(time.time() - started, 1)
    log_path.write_text(
        f"CMD: {' '.join(cmd)}\n\n=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n",
        encoding="utf-8",
    )
    parsed = parse_output(stdout, stderr)
    props_count = parsed["props"]
    metadata_payload = read_json_file(metadata_path, {}) if metadata_path.exists() else {}
    meta = metadata_summary(metadata_payload)
    if json_path.exists():
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            props = payload.get("props") if isinstance(payload, dict) else None
            if isinstance(props, list):
                props_count = len(props)
        except Exception:
            pass
    success = props_count > 0 and not parsed["error_type"] and not timed_out
    combined_text = f"{stdout}\n{stderr}"
    remax_detected = is_remax_signal(url, combined_text, metadata_payload)
    error_type = "item_timeout" if timed_out else parsed["error_type"]
    if timed_out and remax_detected:
        error_type = "remax_timeout"
    error_message = "timeout_proceso" if timed_out else parsed["error_message"]
    if timed_out:
        error_message = (
            f"timeout_proceso last_stage={meta.get('last_stage') or 'unknown'} "
            f"strategy={meta.get('strategy_current') or parsed['strategy'] or 'unknown'} "
            f"external_timeout={run_timeout}s lane={lane} "
            f"internal_expected={meta.get('timeout_internal_expected_seconds') or 'unknown'}s"
        )
    error_subfamily = meta.get("error_subfamily") or ""
    if not error_subfamily and parsed["error_message"]:
        match = re.search(r"subfamily=([a-z0-9_ -]+)", parsed["error_message"], re.I)
        if match:
            error_subfamily = match.group(1).strip()
    if not error_subfamily and error_type in {"no_property_links", "no_property_links_confirmed", "sin_propiedades"}:
        error_subfamily = preflight.get("error_subfamily") or "unknown_no_property_links"
    return {
        "idx": idx,
        "id": row.get("id") or "",
        "inmobiliaria_id": row.get("inmobiliaria_id") or "",
        "inmobiliaria_nombre": row.get("inmobiliaria_nombre") or row.get("nombre") or "",
        "url": url,
        "domain": domain_from_url(url),
        "family_before": row.get("error_type") or "",
        "success": success,
        "skipped": False,
        "status": "success" if success else "error",
        "props": props_count,
        "strategy": parsed["strategy"],
        "strategy_current": meta.get("strategy_current") or parsed["strategy"] or "",
        "lane": lane,
        "error_type": error_type,
        "error_family": "timeout" if error_type in {"item_timeout", "timeout", "remax_timeout"} else "",
        "error_subfamily": error_subfamily,
        "error_message": error_message,
        "last_stage": meta.get("last_stage") or ("process_timeout" if timed_out else ""),
        "last_stage_status": meta.get("last_stage_status") or "",
        "timeout_external_seconds": run_timeout,
        "timeout_internal_expected_seconds": meta.get("timeout_internal_expected_seconds") or "",
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "json_path": str(json_path.relative_to(REPO_ROOT)) if json_path.exists() else "",
        "metadata_path": str(metadata_path.relative_to(REPO_ROOT)) if metadata_path.exists() else "",
        "raw_log": str(log_path.relative_to(REPO_ROOT)),
        "preflight": preflight,
        "remax_api_detected": bool(remax_detected or meta.get("remax_api_detected")),
        "detected_api_endpoints": meta.get("detected_api_endpoints") or [],
        "used_playwright": used_playwright,
        "used_network_interception": used_network_interception,
        "used_visible_api": used_visible_api,
        "used_static_detail": used_static_detail,
        "extractor_family": _extractor_family_from_strategy(
            meta.get("strategy_current") or parsed.get("strategy") or "",
            error_subfamily,
        ),
    }


def write_reports(run_dir: Path, capture_dir: Path, results: List[Dict[str, Any]], args: argparse.Namespace) -> None:
    report_json = run_dir / "batch_results.json"
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = [r for r in results if r["success"]]
    skipped = [r for r in results if r.get("skipped")]
    failed = [r for r in results if not r["success"] and not r.get("skipped")]
    families = Counter((r.get("error_subfamily") or r.get("error_type") or r["family_before"] or "ok") for r in results)
    agency_csv = run_dir / "agency_results.csv"
    failures_csv = run_dir / "failures.csv"
    agency_fields = [
        "idx", "inmobiliaria_id", "inmobiliaria_nombre", "url", "domain", "status",
        "success", "skipped", "props", "strategy", "strategy_current", "lane",
        "extractor_family",
        "used_playwright", "used_network_interception", "used_visible_api", "used_static_detail",
        "error_type", "error_family", "error_subfamily", "error_message",
        "last_stage", "last_stage_status", "elapsed_seconds",
        "timeout_external_seconds", "timeout_internal_expected_seconds",
        "remax_api_detected", "json_path", "metadata_path", "raw_log",
    ]
    write_csv(agency_csv, results, agency_fields)
    write_csv(failures_csv, [r for r in results if not r["success"]], agency_fields)
    lines = [
        "# Internal scraping batch",
        "",
        f"- Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Input: `{args.input}`",
        f"- Capture dir: `{capture_dir.relative_to(REPO_ROOT)}`",
        f"- Ejecutadas: {len(results)}",
        f"- OK: {len(ok)}",
        f"- Error: {len(failed)}",
        f"- Skipped invalid source: {len(skipped)}",
        f"- Propiedades capturadas: {sum(int(r['props'] or 0) for r in ok)}",
        f"- Workers: {args.workers}",
        f"- Timeout por URL: {args.timeout_seconds}s",
        f"- Supabase write: false",
        "",
        "## Familias",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(families.items()))
    lines.extend(["", "## OK", ""])
    for item in ok:
        lines.append(f"- {item['inmobiliaria_id']} | {item['inmobiliaria_nombre']} | props={item['props']} | {item['url']}")
    lines.extend(["", "## Errores", ""])
    for item in failed:
        lines.append(
            f"- {item['inmobiliaria_id']} | {item['family_before']} -> {item['error_type'] or 'sin_clasificar'} "
            f"/ {item.get('error_subfamily') or '-'} | stage={item.get('last_stage') or '-'} | "
            f"{item['url']} | {item['error_message'] or ''}"
        )
    lines.extend(["", "## Skipped", ""])
    for item in skipped:
        lines.append(
            f"- {item['inmobiliaria_id']} | {item.get('error_subfamily') or item.get('error_type')} | "
            f"{item['url']} | {item['error_message'] or ''}"
        )
    lines.extend([
        "",
        "## Archivos",
        "",
        f"- Agency results CSV: `{agency_csv.relative_to(REPO_ROOT)}`",
        f"- Failures CSV: `{failures_csv.relative_to(REPO_ROOT)}`",
        f"- Batch results JSON: `{report_json.relative_to(REPO_ROOT)}`",
    ])
    (run_dir / "batch_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe internal scraping batch via --test-url captures")
    parser.add_argument("--input", required=True, help="CSV de tanda exportada")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de URLs a ejecutar; 0=todas")
    parser.add_argument("--offset", type=int, default=0, help="Cantidad de filas utiles a saltear")
    parser.add_argument("--workers", type=int, default=2, help="Subprocesos concurrentes bajos")
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--include-non-code", action="store_true")
    parser.add_argument("--allow-playwright", action="store_true")
    parser.add_argument("--allow-visible-api", action="store_true")
    parser.add_argument("--allow-static-detail", action="store_true")
    parser.add_argument("--allow-network-interception", action="store_true")
    parser.add_argument(
        "--force-js-lane",
        action="store_true",
        help="Force all non-skipped URLs to the needs_js lane. Use when the input CSV "
             "contains JS candidates (dynamic_cards, generic_playwright, etc.) whose "
             "domains do not match the built-in JS-domain heuristics.",
    )
    parser.add_argument("--out-dir", default=None, help="Directorio base de salida")
    args = parser.parse_args()

    if args.workers <= 0 or args.workers > 3:
        raise SystemExit("--workers debe estar entre 1 y 3")
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = REPO_ROOT / input_path
    rows = read_batch(input_path, args.limit, args.offset, args.include_non_code)
    if not rows:
        raise SystemExit("No hay filas para ejecutar.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_base = Path(args.out_dir) if args.out_dir else DEFAULT_OUTPUT_ROOT / f"internal_batch_{timestamp}"
    if not out_base.is_absolute():
        out_base = REPO_ROOT / out_base
    capture_dir = out_base / "captured"
    raw_log_dir = out_base / "raw_logs"
    report_dir = REPORT_DIR / f"batch_{timestamp}"
    capture_dir.mkdir(parents=True, exist_ok=True)
    raw_log_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 72)
    print("INTERNAL SCRAPING BATCH")
    print(f"input={input_path}")
    print(f"urls={len(rows)}")
    print(f"offset={args.offset}")
    print(f"workers={args.workers}")
    print(f"capture_dir={capture_dir}")
    print("supabase_write=false")
    print("-" * 72)

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(run_one, row, idx, args, capture_dir, raw_log_dir): row
            for idx, row in enumerate(rows, 1)
        }
        for done, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            status = "OK" if result["success"] else (result["error_type"] or "ERR")
            print(f"[{done}/{len(rows)}] {status} props={result['props']} url={result['url']}")

    results.sort(key=lambda item: item["idx"])
    write_reports(report_dir, capture_dir, results, args)
    ok_count = sum(1 for r in results if r["success"])
    skipped_count = sum(1 for r in results if r.get("skipped"))
    props_count = sum(int(r["props"] or 0) for r in results if r["success"])
    print("-" * 72)
    print(f"ok={ok_count}")
    print(f"errors={len(results) - ok_count - skipped_count}")
    print(f"skipped_invalid_source={skipped_count}")
    print(f"props_captured={props_count}")
    print(f"report={report_dir / 'batch_report.md'}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

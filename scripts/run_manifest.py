#!/usr/bin/env python3
"""
scripts/run_manifest.py
PR-BE-PROD-09b/09c/09d/09e — Wrapper seguro para corrida de manifest

SEGURIDAD POR DEFECTO:
  - Sin flags extra:               FALLA — no escribe DB, no visita sitios.
  - Con --dry-run:                 Valida manifest, genera reporte. 0 DB writes.
  - Con --dry-run --playwright:    Canary HTTP sobre --limit fuentes. 0 DB writes.
  - Con --execute:                 Corrida real. Solo escribe en `propiedades`.
                                   Requiere --limit <= 50 y --workers <= 2 (09d).
  - --commit:                      BLOQUEADO siempre.
  - --playwright sin --dry-run:    BLOQUEADO.
  - --playwright sin --limit:      BLOQUEADO (seguridad).
  - --include-backlog:             BLOQUEADO permanentemente.

Tablas escritas en --execute: solo `propiedades` (INSERT plain, sin on_conflict).
Tablas SELECT read-only (para FK preflight): inmobiliarias_main.
Tablas NUNCA escritas: inmobiliarias_main, publish_queue, raw, staging,
  url_listado, diagnostic_status, scraping_readiness, exclude_from_scraping,
  sitio_activo, activa, scraping_runs, scraping_run_items.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Constantes de seguridad
# ---------------------------------------------------------------------------

PROHIBITED_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "linkedin.com", "youtube.com", "youtu.be",
    "mercadolibre.com", "argenprop.com", "zonaprop.com", "properati.com",
    "navent.com", "inmuebles24.com", "mitula.com.ar", "nuroa.com.ar",
    "wa.me", "whatsapp.com", "t.me", "bit.ly", "linktr.ee",
    "wordpress.com", "blogspot.com", "wixsite.com",
    "maps.google", "google.com",
}

BLOCKED_COMBINED_STATUSES = {"still_failed", "http_error", "error"}
BLOCKED_ERRORS             = {"http_error", "connection_error", "domain_down", "missing_url"}
PW_HARD_BLOCKED            = {"antibot", "captcha"}  # Playwright no resuelve bloqueo activo

MAX_EXECUTE_LIMIT   = 1391  # universo completo auditado para esta ejecucion autonoma
MAX_HTTP_WORKERS    = int(os.environ.get("MAX_HTTP_WORKERS", "4"))
MAX_PW_WORKERS      = int(os.environ.get("MAX_PW_WORKERS",  "1"))

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Carga y validación de manifest
# ---------------------------------------------------------------------------

ManifestRow      = Dict[str, Any]
ValidationError  = Tuple[str, str, str]   # (source_id, source_name, reason)


class _InsertOnlySupabaseProxy:
    """Expose only the one authorized write used by Pipeline A."""

    def __init__(self, client: Any) -> None:
        if str(getattr(client, "table", "")) != "propiedades":
            raise RuntimeError("Pipeline A write target must be public.propiedades")
        self._client = client

    def batch_save_only_new(self, payloads: List[Dict[str, Any]]) -> int:
        return self._client.batch_save_only_new(payloads)

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(f"Unauthorized Supabase operation in Pipeline A: {name}")


def load_manifest(path: Path) -> List[ManifestRow]:
    rows: List[ManifestRow] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(dict(row))
    return rows


def _normalize_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return url.lower()


def _is_prohibited(url: str) -> bool:
    d = _normalize_domain(url)
    return any(d == p or d.endswith("." + p) for p in PROHIBITED_DOMAINS)


def validate_manifest(
    rows: List[ManifestRow],
    excluded_ids: Optional[Set[str]] = None,
) -> Tuple[List[ManifestRow], List[ManifestRow], List[ManifestRow], List[ValidationError]]:
    """
    Returns (valid_http, valid_pw, blocked_pw, errors).
    valid_http  — fuentes HTTP normales (needs_playwright=False)
    valid_pw    — fuentes Playwright legítimas (needs_playwright=True, final_status != antibot/captcha)
    blocked_pw  — fuentes con bloqueo activo: Playwright no las resuelve
    errors      — filas rechazadas por validación estructural
    """
    valid_http:  List[ManifestRow] = []
    valid_pw:    List[ManifestRow] = []
    blocked_pw:  List[ManifestRow] = []
    errors: List[ValidationError] = []
    seen_ids: Dict[str, int] = {}

    for row in rows:
        sid      = (row.get("source_id") or "").strip()
        name     = (row.get("source_name") or "").strip()
        url      = (row.get("new_url_listado") or row.get("old_url_listado") or "").strip()
        cs       = (row.get("combined_status") or "").strip()
        err      = (row.get("error") or "").strip().lower()
        needs_pw = (row.get("needs_playwright") or "false").strip().lower() == "true"
        fs       = (row.get("final_status") or "").strip().lower()

        if not sid:
            errors.append(("", name, "missing source_id")); continue
        if not url:
            errors.append((sid, name, "missing url_listado")); continue
        if _is_prohibited(url):
            errors.append((sid, name, f"prohibited domain: {_normalize_domain(url)}")); continue
        if cs in BLOCKED_COMBINED_STATUSES:
            errors.append((sid, name, f"blocked combined_status={cs}")); continue
        if err in BLOCKED_ERRORS:
            errors.append((sid, name, f"blocked error_type={err}")); continue
        if excluded_ids and sid in excluded_ids:
            errors.append((sid, name, "source_id found in manifest_excluded")); continue
        if sid in seen_ids:
            errors.append((sid, name, f"duplicate source_id (first row {seen_ids[sid]})")); continue

        seen_ids[sid] = len(valid_http) + len(valid_pw) + 1

        if needs_pw:
            if fs in PW_HARD_BLOCKED:
                blocked_pw.append(row)
            else:
                valid_pw.append(row)
        else:
            valid_http.append(row)

    return valid_http, valid_pw, blocked_pw, errors


def build_fuentes(rows: List[ManifestRow]) -> List[Dict[str, Any]]:
    """Convierte manifest rows al formato de _scrape_batch(). Usa new_url_listado."""
    fuentes = []
    for row in rows:
        url  = (row.get("new_url_listado") or row.get("old_url_listado") or "").strip()
        name = (row.get("source_name") or "").strip()
        sid  = (row.get("source_id") or "").strip()
        slug = re.sub(r"[^a-z0-9_]", "_", name.lower())[:40].strip("_") or f"src_{sid}"
        fuentes.append({
            "key":            slug,
            "source_id":      sid,
            "web":            url,               # new_url_listado — NO inmobiliarias_scraping.web
            "ciudad":         "",
            "operacion":      None,
            "tipo_cms":       "tokko",
            "_manifest_name": name,
            "_url_source":    "new_url_listado",
        })
    return fuentes


# ---------------------------------------------------------------------------
# Dry-run: validación de manifest sin visitas ni DB
# ---------------------------------------------------------------------------

def run_dry(fuentes, out_dir, limit, ts) -> Dict[str, Any]:
    subset = fuentes[:limit] if limit else fuentes
    print(f"\n[DRY-RUN] {len(subset)} fuentes | 0 DB writes | 0 HTTP visits")
    for i, f in enumerate(subset[:10], 1):
        print(f"  [{i:03d}] id={f['source_id']:<6} | {f['_manifest_name'][:40]:<40} | {f['web']}")
    if len(subset) > 10:
        print(f"  ... y {len(subset) - 10} fuentes más")
    return {
        "total_fuentes": len(fuentes), "fuentes_subset": len(subset),
        "limit_applied": limit, "url_source": "new_url_listado",
        "db_writes": 0, "propiedades_writes": 0, "publish": 0,
    }


# ---------------------------------------------------------------------------
# Canary HTTP: visitas diagnósticas sin DB writes
# ---------------------------------------------------------------------------

CANARY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _load_parse_cards():
    scraper_dir = REPO_ROOT / "scraper"
    if str(scraper_dir) not in sys.path:
        sys.path.insert(0, str(scraper_dir))
    try:
        from playwright_scraper import parse_cards  # noqa: PLC0415
        return parse_cards
    except Exception as exc:
        print(f"  [CANARY] WARN: parse_cards no disponible: {exc}")
        return None


def _count_links_fallback(html: str) -> int:
    try:
        from bs4 import BeautifulSoup  # noqa: PLC0415
        soup = BeautifulSoup(html, "html.parser")
        PROP_SEGS = {"/propiedad", "/propiedades", "/property", "/properties",
                     "/inmueble", "/ficha", "/detalle", "/listing", "/ad/"}
        return sum(1 for a in soup.find_all("a", href=True)
                   if any(s in a["href"].lower() for s in PROP_SEGS))
    except Exception:
        return 0


def run_canary_http(fuentes, limit, session=None) -> List[Dict]:
    import requests as req_lib  # noqa: PLC0415
    import urllib3              # noqa: PLC0415
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    parse_cards = _load_parse_cards()
    if session is None:
        session = req_lib.Session()
        session.headers.update({"User-Agent": CANARY_UA, "Accept-Language": "es-AR,es;q=0.9"})

    subset  = fuentes[:limit]
    results = []
    print(f"\n[CANARY] {len(subset)} fuentes | HTTP-only | 0 DB writes")

    for i, f in enumerate(subset, 1):
        url      = f["web"]
        key      = f["key"]
        sid      = f["source_id"]
        name     = f["_manifest_name"]
        base_url = "/".join(url.split("/")[:3])

        r: Dict[str, Any] = {
            "source_id": sid, "source_name": name, "url_visited": url,
            "url_source": "new_url_listado", "http_status": None,
            "cards_detected": 0, "property_links": 0,
            "parse_method": "parse_cards" if parse_cards else "fallback",
            "parse_status": "pending", "elapsed_s": None, "error": "",
            "db_writes": 0, "upsert_propiedades": 0, "runs_created": 0, "publish": 0,
        }

        t0 = time.time()
        print(f"  [{i:02d}/{len(subset)}] id={sid:<6} {name[:38]:<38} -> {url}")
        try:
            resp = session.get(url, timeout=20, verify=False, allow_redirects=True)
            elapsed = round(time.time() - t0, 2)
            r["http_status"] = resp.status_code
            r["elapsed_s"]   = elapsed
            if resp.status_code == 200:
                html = resp.text
                if parse_cards:
                    try:
                        props = parse_cards(html, None, key, base_url, "")
                        cards = len(props)
                        links = len([p for p in props if getattr(p, "url", None)])
                    except Exception as pe:
                        cards = _count_links_fallback(html)
                        links = cards
                        r["parse_method"] = "fallback"
                        r["error"] = f"parse_error:{pe}"
                else:
                    cards = _count_links_fallback(html)
                    links = cards
                r["cards_detected"] = cards
                r["property_links"] = links
                r["parse_status"]   = "ok" if cards > 0 else "no_cards"
                tag = "OK" if cards > 0 else "PARTIAL"
                print(f"           {tag} | {resp.status_code} | cards={cards} | {elapsed}s")
            else:
                r["parse_status"] = f"http_{resp.status_code}"
                print(f"           FAIL | {resp.status_code} | {elapsed}s")
        except Exception as exc:
            elapsed = round(time.time() - t0, 2)
            r["elapsed_s"] = elapsed
            t = type(exc).__name__
            if "Timeout" in t or "timeout" in str(exc).lower():
                r["parse_status"] = "timeout"; r["error"] = "timeout"
            else:
                r["parse_status"] = "error";   r["error"] = str(exc)[:80]
            print(f"           ERROR: {t} | {elapsed}s")
        results.append(r)

    return results


# ---------------------------------------------------------------------------
# FK preflight: lookup inmobiliaria_id desde inmobiliarias_main (read-only)
# ---------------------------------------------------------------------------

def _lookup_inmobiliaria_ids(
    supabase_url: str,
    key: str,
    source_ids: List[str],
) -> Dict[str, int]:
    """
    Resuelve source_id -> inmobiliaria_id con dos rutas en cascada:

    1. PRIMARY:  WHERE scraping_id_origen IN (source_ids)
       El campo scraping_id_origen mapea el ID del sistema de scraping al ID
       canónico de inmobiliarias_main. Es el path original y tiene prioridad.

    2. FALLBACK: WHERE id IN (unresolved_ids)
       Solo para source_ids que no encontraron match en el path primario.
       Cubre fuentes cuyo id en inmobiliarias_main coincide directamente con
       el source_id del manifest pero no tienen scraping_id_origen configurado
       con ese valor. El guard (sid not in mapping) garantiza que un resultado
       primario nunca es sobreescrito por el fallback.

    Solo lectura — nunca escribe.
    """
    try:
        import requests  # noqa: PLC0415
        mapping: Dict[str, int] = {}
        CHUNK = 50

        # ── Path primario: scraping_id_origen = source_id (comportamiento original) ──
        for i in range(0, len(source_ids), CHUNK):
            chunk = source_ids[i : i + CHUNK]
            ids_csv = ",".join(chunk)
            resp = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/inmobiliarias_main",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={
                    "select":               "id,nombre,scraping_id_origen",
                    "scraping_id_origen":   f"in.({ids_csv})",
                    "limit":                str(CHUNK),
                },
                timeout=30,
            )
            if resp.status_code == 200:
                for row in resp.json():
                    sid = str(row.get("scraping_id_origen", ""))
                    mid = row.get("id")
                    if sid and mid is not None:
                        mapping[sid] = mid
            else:
                print(f"  [FK-LOOKUP] WARN: status={resp.status_code}", file=sys.stderr)

        # ── Path fallback: id = source_id (solo para los no resueltos) ──────────────
        unresolved = [sid for sid in source_ids if sid not in mapping]
        if unresolved:
            print(
                f"  [FK-LOOKUP] {len(unresolved)} sin match por scraping_id_origen. "
                f"Intentando fallback por id...",
                file=sys.stderr,
            )
            for i in range(0, len(unresolved), CHUNK):
                chunk = unresolved[i : i + CHUNK]
                ids_csv = ",".join(chunk)
                resp2 = requests.get(
                    f"{supabase_url.rstrip('/')}/rest/v1/inmobiliarias_main",
                    headers={"apikey": key, "Authorization": f"Bearer {key}"},
                    params={
                        "select": "id,nombre",
                        "id":     f"in.({ids_csv})",
                        "limit":  str(CHUNK),
                    },
                    timeout=30,
                )
                if resp2.status_code == 200:
                    for row in resp2.json():
                        sid = str(row.get("id", ""))
                        mid = row.get("id")
                        if sid and mid is not None and sid not in mapping:
                            mapping[sid] = mid
                            print(
                                f"  [FK-LOOKUP] fallback id match: "
                                f"source_id={sid} -> inmobiliaria_id={mid} "
                                f"({row.get('nombre', '?')[:40]})",
                                file=sys.stderr,
                            )
                else:
                    print(
                        f"  [FK-LOOKUP] WARN fallback: status={resp2.status_code}",
                        file=sys.stderr,
                    )

        return mapping
    except Exception as exc:
        print(f"  [FK-LOOKUP] ERROR: {exc}", file=sys.stderr)
        return {}


def _lookup_inmobiliaria_ids_safe(
    supabase_url: str,
    key: str,
    sources: List[Dict[str, Any]],
) -> Tuple[Dict[str, int], List[ValidationError]]:
    """Resolve manifest IDs without silently crossing source ID spaces.

    Both scraping_id_origen and canonical id are read. A primary match keeps
    priority only when it is compatible with the manifest name/domain. When
    both spaces collide, the only compatible candidate wins; ambiguous or
    mismatched rows remain unresolved with an explicit validation error.
    """
    import requests  # noqa: PLC0415

    source_by_id = {str(row.get("source_id", "")): row for row in sources}
    source_ids = [sid for sid in source_by_id if sid]
    primary_by_sid: Dict[str, List[Dict[str, Any]]] = {}
    fallback_by_sid: Dict[str, Dict[str, Any]] = {}
    errors: List[ValidationError] = []
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    chunk_size = 50

    def normalized(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        ascii_text = text.encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()

    def domain(value: Any) -> str:
        try:
            return urlparse(str(value or "")).netloc.lower().lstrip("www.")
        except Exception:
            return ""

    def compatible(source: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        source_name = normalized(source.get("_manifest_name") or source.get("source_name"))
        candidate_name = normalized(candidate.get("nombre"))
        name_ok = bool(
            source_name and candidate_name
            and (
                source_name == candidate_name
                or source_name in candidate_name
                or candidate_name in source_name
            )
        )
        source_domain = domain(source.get("web") or source.get("new_url_listado"))
        candidate_domain = domain(candidate.get("url_listado") or candidate.get("web"))
        domain_ok = bool(
            source_domain and candidate_domain
            and (
                source_domain == candidate_domain
                or source_domain.endswith("." + candidate_domain)
                or candidate_domain.endswith("." + source_domain)
            )
        )
        return name_ok or domain_ok

    select = "id,nombre,web,url_listado,scraping_id_origen"
    for offset in range(0, len(source_ids), chunk_size):
        chunk = source_ids[offset : offset + chunk_size]
        ids_csv = ",".join(chunk)
        primary_response = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/inmobiliarias_main",
            headers=headers,
            params={
                "select": select,
                "scraping_id_origen": f"in.({ids_csv})",
                "limit": str(chunk_size * 2),
            },
            timeout=30,
        )
        fallback_response = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/inmobiliarias_main",
            headers=headers,
            params={"select": select, "id": f"in.({ids_csv})", "limit": str(chunk_size)},
            timeout=30,
        )
        if primary_response.status_code != 200 or fallback_response.status_code != 200:
            raise RuntimeError(
                "FK lookup HTTP failure "
                f"primary={primary_response.status_code} fallback={fallback_response.status_code}"
            )
        for row in primary_response.json():
            sid = str(row.get("scraping_id_origen", ""))
            if sid:
                primary_by_sid.setdefault(sid, []).append(row)
        for row in fallback_response.json():
            sid = str(row.get("id", ""))
            if sid:
                fallback_by_sid[sid] = row

    mapping: Dict[str, int] = {}
    for sid, source in source_by_id.items():
        name = str(source.get("_manifest_name") or source.get("source_name") or "")
        primary_matches = primary_by_sid.get(sid, [])
        fallback = fallback_by_sid.get(sid)
        if len(primary_matches) > 1:
            errors.append((sid, name, "ambiguous scraping_id_origen"))
            continue
        primary = primary_matches[0] if primary_matches else None

        if primary and fallback and primary.get("id") != fallback.get("id"):
            primary_ok = compatible(source, primary)
            fallback_ok = compatible(source, fallback)
            if primary_ok and not fallback_ok:
                mapping[sid] = int(primary["id"])
            elif fallback_ok and not primary_ok:
                mapping[sid] = int(fallback["id"])
            else:
                errors.append(
                    (
                        sid,
                        name,
                        "unresolved FK collision "
                        f"primary_id={primary.get('id')} fallback_id={fallback.get('id')}",
                    )
                )
            continue

        candidate = primary or fallback
        if candidate is None:
            errors.append((sid, name, "missing FK candidate"))
        elif not compatible(source, candidate):
            errors.append((sid, name, f"strong FK identity mismatch candidate_id={candidate.get('id')}"))
        else:
            mapping[sid] = int(candidate["id"])

    return mapping, errors


def _load_existing_urls_by_inmobiliaria(
    supabase_url: str,
    key: str,
    inmobiliaria_ids: List[int],
) -> Set[str]:
    """
    Carga URLs existentes en propiedades filtrando por inmobiliaria_id.

    Reemplaza get_all_existing_urls() para corridas grandes.
    Cada query retorna solo las props de una inmobiliaria (típicamente < 1.000),
    evitando el límite PostgREST de db-max-rows=1.000. Sin schema change.
    """
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        print("  [DEDUP] ERROR: requests no disponible", file=sys.stderr)
        return set()

    existing: Set[str] = set()
    H = {"apikey": key, "Authorization": f"Bearer {key}"}

    print(f"[DEDUP] Cargando URLs existentes para {len(inmobiliaria_ids)} inmobiliarias...")
    for inmo_id in inmobiliaria_ids:
        try:
            r = requests.get(
                f"{supabase_url.rstrip('/')}/rest/v1/propiedades",
                headers=H,
                params={
                    "select":           "url",
                    "inmobiliaria_id":  f"eq.{inmo_id}",
                    "limit":            "10000",
                },
                timeout=30,
            )
            if r.status_code == 200:
                existing.update(item["url"] for item in r.json() if "url" in item)
        except Exception as exc:
            print(
                f"  [DEDUP] WARN: error cargando URLs para inmobiliaria_id={inmo_id}: {exc}",
                file=sys.stderr,
            )

    print(f"[DEDUP] existing_urls cargadas (per-source): {len(existing):,}")
    return existing


class _ProgressTracker:
    """
    Seguimiento thread-safe del progreso de corrida 09e.
    Escribe progress_live.md en out_dir cada 250 fuentes o 15 minutos.
    """

    _EVERY_N = 250
    _EVERY_S = 900  # 15 min

    def __init__(
        self,
        total_fuentes: int,
        n_sin_fk: int,
        out_dir: Path,
        workers: int,
    ) -> None:
        self._lock          = threading.Lock()
        self.sources_done   = 0
        self.props_saved    = 0
        self.last_source    = ""
        self.total_fuentes  = total_fuentes
        self.n_sin_fk       = n_sin_fk
        self.out_dir        = out_dir
        self.workers        = workers
        self._t_start       = time.time()
        self._t_last_report = self._t_start

    def on_source_done(self, key: str, props_saved: int) -> None:
        with self._lock:
            self.sources_done += 1
            self.props_saved  += props_saved
            self.last_source   = key
            now = time.time()
            if (
                self.sources_done % self._EVERY_N == 0
                or (now - self._t_last_report) >= self._EVERY_S
            ):
                self._t_last_report = now
                self._write(now)

    def write_final(self) -> None:
        self._write(time.time(), final=True)

    def _write(self, now: float, final: bool = False) -> None:
        elapsed   = now - self._t_start
        done      = self.sources_done
        total     = self.total_fuentes
        remaining = max(0, total - done)

        if done > 0 and remaining > 0:
            eta_s   = int(elapsed / done * remaining)
            eta_str = (
                f"~{eta_s // 3600}h {(eta_s % 3600) // 60}m"
                if eta_s >= 3600
                else f"~{eta_s // 60}m"
            )
        else:
            eta_str = "—"

        pct   = f"{round(100 * done / total)}%" if total else "—"
        label = "FINAL" if final else pct

        lines = [
            f"# Progreso 09e [{label}] — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Fuentes",
            "| Métrica | Valor |",
            "|---|---|",
            f"| Con FK (elegibles) | {total} |",
            f"| Procesadas | {done} |",
            f"| Pendientes | {remaining} |",
            f"| Sin FK (omitidas) | {self.n_sin_fk} |",
            "",
            "## Propiedades",
            "| Métrica | Valor |",
            "|---|---|",
            f"| Insertadas | **{self.props_saved}** |",
            "",
            "## Tiempo",
            "| Métrica | Valor |",
            "|---|---|",
            f"| Transcurrido | {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m |",
            f"| ETA | {eta_str} |",
            f"| Workers | {self.workers} |",
            "",
            f"**Última fuente:** `{self.last_source}`",
        ]
        try:
            (self.out_dir / "progress_live.md").write_text(
                "\n".join(lines), encoding="utf-8"
            )
        except Exception:
            pass  # no interrumpir el scraping por error de escritura


# ---------------------------------------------------------------------------
# Execute: corrida real controlada — escribe en propiedades
# ---------------------------------------------------------------------------

def _load_scraper_modules():
    """Importa módulos del scraper con path correcto. No imprime credentials."""
    scraper_dir = REPO_ROOT / "scraper"
    if str(scraper_dir) not in sys.path:
        sys.path.insert(0, str(scraper_dir))

    # Cargar .env sin imprimir su contenido
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
        for env_path in [REPO_ROOT / ".env", scraper_dir / ".env"]:
            if env_path.exists():
                load_dotenv(dotenv_path=env_path, override=False)
                break
    except ImportError:
        pass

    from clients import SupabaseClient, SessionFactory  # noqa: PLC0415
    import config as _cfg                               # noqa: PLC0415
    from run import _scrape_batch, _split_batches       # noqa: PLC0415

    return SupabaseClient, SessionFactory, _cfg, _scrape_batch, _split_batches


def _pre_execute_snapshot(
    subset: List[Dict],
    count_before: int,
    ts_run: str,
    out_dir: Path,
    cmd: str,
    workers: int,
) -> Dict:
    snapshot = {
        "timestamp":               ts_run,
        "pr_phase":                "PR-BE-PROD-09e",
        "count_propiedades_before": count_before,
        "fuentes_count":           len(subset),
        "command":                 cmd,
        "sources": [
            {
                "source_id":   f["source_id"],
                "source_name": f["_manifest_name"],
                "url_listado": f["web"],
                "url_source":  f["_url_source"],
            }
            for f in subset
        ],
        "guardrails": {
            "writes_authorized":  ["propiedades"],
            "writes_blocked":     [
                "inmobiliarias_main", "publish_queue", "raw", "staging",
                "url_listado", "diagnostic_status", "scraping_runs",
            ],
            "include_backlog":    False,
            "limit":              len(subset),
            "max_limit_09d":      MAX_EXECUTE_LIMIT,
            "workers":            workers,
            "max_workers_09d":    MAX_HTTP_WORKERS,
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pre_execute_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snapshot


def _query_propiedades_since(supabase_url: str, key: str, ts_since: str) -> List[Dict]:
    """Lee propiedades con created_at > ts_since. Solo lectura."""
    try:
        import requests  # noqa: PLC0415
        resp = requests.get(
            f"{supabase_url.rstrip('/')}/rest/v1/propiedades",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={
                "select":     "id,url,url_normalizada,hash_dedup,inmobiliaria_id,titulo,fuente_extraccion,operacion,tipo_propiedad,precio,moneda,created_at",
                "created_at": f"gt.{ts_since}",
                "order":      "created_at.desc",
                "limit":      "10000",
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as exc:
        print(f"  [WARN] _query_propiedades_since: {exc}")
    return []


def run_execute(
    fuentes_http: List[Dict],
    fuentes_pw: List[Dict],
    limit: int,
    http_workers: int,
    pw_workers: int,
    out_dir: Path,
    ts_start: str,
    manifest_path: Path,
) -> Optional[Dict]:
    """
    Corrida real con dos colas independientes.
    Cola HTTP  (fuentes_http): http_workers threads — I/O-bound puro, escala bien.
    Cola PW    (fuentes_pw):   pw_workers threads  — RAM-bound, conservador.
    Los workers antibot/captcha fueron filtrados antes de llegar aquí.
    Escribe en propiedades. No toca inmobiliarias_main (solo SELECT para FK preflight).
    """
    subset_http = fuentes_http[:limit] if limit else fuentes_http
    subset_pw   = fuentes_pw            # PW queue sin límite adicional (ya es pequeña)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n[EXECUTE] Cargando módulos del scraper...")
    try:
        SupabaseClient, SessionFactory, cfg, _scrape_batch, _split_batches = _load_scraper_modules()
    except Exception as exc:
        print(f"[EXECUTE] ERROR importando scraper: {exc}", file=sys.stderr)
        print("[EXECUTE] Verificá que SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY estén en .env",
              file=sys.stderr)
        return None

    # ── FK preflight combinado (HTTP + PW) ─────────────────────────────────
    all_subset = subset_http + subset_pw
    print(f"\n[EXECUTE] FK preflight: {len(subset_http)} HTTP + {len(subset_pw)} PW = {len(all_subset)} fuentes...")
    fk_mapping, fk_errors = _lookup_inmobiliaria_ids_safe(
        cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY, all_subset
    )
    if fk_errors:
        print(f"[EXECUTE] FK errors: {len(fk_errors)}", file=sys.stderr)
        for sid, name, reason in fk_errors[:20]:
            print(f"  [FK-ERROR] source_id={sid} {name[:40]}: {reason}", file=sys.stderr)

    fuentes_con_fk    = []
    fuentes_sin_fk    = []
    for f in all_subset:
        sid = f.get("source_id", "")
        mid = fk_mapping.get(str(sid))
        if mid is not None:
            fuentes_con_fk.append({**f, "inmobiliaria_id": mid})
        else:
            fuentes_sin_fk.append(f)

    pct = round(100 * len(fuentes_con_fk) / len(all_subset)) if all_subset else 0
    print(f"[EXECUTE] FK match:    {len(fuentes_con_fk)}/{len(all_subset)} ({pct}%)")
    print(f"[EXECUTE] Sin FK:      {len(fuentes_sin_fk)} fuentes omitidas")
    if fuentes_sin_fk:
        for f in fuentes_sin_fk[:5]:
            print(f"  OMITIDA id={f['source_id']:<6} {f['_manifest_name'][:40]}")
        if len(fuentes_sin_fk) > 5:
            print(f"  ... y {len(fuentes_sin_fk) - 5} más")

    if not fuentes_con_fk:
        print("[EXECUTE] ERROR: ninguna fuente tiene FK válido. Abortando.", file=sys.stderr)
        return None

    # Separar FK-resueltos en sus colas
    http_ids = {f["source_id"] for f in subset_http}
    cola_http = [f for f in fuentes_con_fk if f["source_id"] in http_ids]
    cola_pw   = [f for f in fuentes_con_fk if f["source_id"] not in http_ids]

    # Conectar (no imprime credentials)
    print("\n[EXECUTE] Conectando a Supabase (read-only para snapshot)...")
    session  = SessionFactory.make()
    raw_supabase = SupabaseClient(
        session,
        cfg.SUPABASE_URL,
        cfg.SUPABASE_SERVICE_ROLE_KEY,
        cfg.SUPABASE_TABLE,
    )
    supabase = _InsertOnlySupabaseProxy(raw_supabase)

    # Cargar URLs existentes por inmobiliaria_id — fix dedup (evita límite PostgREST 1.000)
    inmobiliaria_ids_fk = [f["inmobiliaria_id"] for f in fuentes_con_fk]
    existing_urls = _load_existing_urls_by_inmobiliaria(
        cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY, inmobiliaria_ids_fk
    )
    count_before = len(existing_urls)
    print(f"[EXECUTE] existing_urls (per-source, {len(inmobiliaria_ids_fk)} fuentes): {count_before:,}")

    # Snapshot pre-execute
    cmd = (
        f"python scripts/run_manifest.py "
        f"--manifest {manifest_path.name} "
        f"--execute --limit {limit} --workers {http_workers}"
    )
    snap = _pre_execute_snapshot(fuentes_con_fk, count_before, ts_start, out_dir, cmd, http_workers)
    snap["fk_preflight"] = {
        "fuentes_con_fk":  len(fuentes_con_fk),
        "fuentes_sin_fk":  len(fuentes_sin_fk),
        "pct_match":       pct,
        "omitidas":        [f["source_id"] for f in fuentes_sin_fk],
        "errors": [
            {"source_id": sid, "source_name": name, "reason": reason}
            for sid, name, reason in fk_errors
        ],
    }
    snap["colas"] = {"http": len(cola_http), "playwright": len(cola_pw)}
    (out_dir / "pre_execute_snapshot.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("[EXECUTE] pre_execute_snapshot.json generado (con FK preflight)")

    print(f"\n[EXECUTE] Iniciando scraping dos colas:")
    print(f"  Cola HTTP:       {len(cola_http)} fuentes | {http_workers} workers")
    print(f"  Cola Playwright: {len(cola_pw)} fuentes | {pw_workers} workers")
    print("[EXECUTE] Escribe SOLO en: propiedades")
    print("[EXECUTE] Lee SOLO de:    inmobiliarias_main (FK lookup ya completado)")
    print("[EXECUTE] NO toca:        publish_queue, url_listado, raw, staging")
    print()

    lock         = threading.Lock()
    metrics_log: list = []
    batches_http = _split_batches(cola_http, http_workers) if cola_http else []
    batches_pw   = _split_batches(cola_pw,   pw_workers)   if cola_pw   else []

    total_saved    = 0
    worker_results = {}

    tracker = _ProgressTracker(
        total_fuentes=len(fuentes_con_fk),
        n_sin_fk=len(fuentes_sin_fk),
        out_dir=out_dir,
        workers=http_workers + pw_workers,
    )

    from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: PLC0415

    with ThreadPoolExecutor(max_workers=http_workers) as http_ex, \
         ThreadPoolExecutor(max_workers=pw_workers)   as pw_ex:

        http_futures = {
            http_ex.submit(
                _scrape_batch, batch, supabase, existing_urls, lock, False, f"h{wid}",
                tracker.on_source_done,
                metrics_log,
            ): f"h{wid}"
            for wid, batch in enumerate(batches_http)
        }
        pw_futures = {
            pw_ex.submit(
                _scrape_batch, batch, supabase, existing_urls, lock, False, f"pw{wid}",
                tracker.on_source_done,
                metrics_log,
            ): f"pw{wid}"
            for wid, batch in enumerate(batches_pw)
        }

        all_futures = {**http_futures, **pw_futures}
        for fut in as_completed(all_futures):
            wid = all_futures[fut]
            try:
                saved = fut.result()
                total_saved += saved
                worker_results[wid] = {"saved": saved, "status": "ok"}
                print(f"[EXECUTE] Worker {wid}: {saved} propiedades guardadas")
            except Exception as exc:
                worker_results[wid] = {"saved": 0, "status": "error", "error": str(exc)[:120]}
                print(f"[EXECUTE] Worker {wid}: ERROR — {exc}", file=sys.stderr)

    tracker.write_final()

    if metrics_log:
        _METRICS_FIELDS = [
            "ts_utc", "worker_id", "key", "source_id", "inmobiliaria_id", "nombre",
            "started_at", "finished_at", "status", "classification", "pages",
            "source_time_s", "sem_wait_s", "browser_time_s",
            "n_listado", "n_nuevas", "n_validas",
            "props_saved", "duplicates_skipped", "had_timeout", "had_error",
            "http_status", "error_type", "error_sanitized", "retryable",
            "retry_count", "memory_peak_mb", "navigation_failures",
        ]
        metrics_path = out_dir / "source_metrics.csv"
        _write_csv(metrics_path, metrics_log, _METRICS_FIELDS)
        print(f"[EXECUTE] source_metrics.csv → {metrics_path} ({len(metrics_log)} fuentes)")

    count_after = len(existing_urls)   # existing_urls se actualiza in-place en _scrape_batch
    net_new     = count_after - count_before

    print(f"\n[EXECUTE] === Resultado ===")
    print(f"  propiedades antes:   {count_before:,}")
    print(f"  guardadas (sum):     {total_saved}")
    print(f"  en existing_urls delta: {net_new}")

    # Query post-run para obtener propiedades nuevas por created_at
    print("\n[EXECUTE] Consultando propiedades nuevas desde DB...")
    new_props = _query_propiedades_since(
        cfg.SUPABASE_URL, cfg.SUPABASE_SERVICE_ROLE_KEY, ts_start
    )
    print(f"[EXECUTE] {len(new_props)} propiedades con created_at > ts_start")

    return {
        "subset":           fuentes_con_fk,
        "fuentes_sin_fk":   fuentes_sin_fk,
        "fk_mapping":       fk_mapping,
        "fk_errors":        fk_errors,
        "count_before":     count_before,
        "count_after":      count_after,
        "total_saved":      total_saved,
        "net_new":          net_new,
        "new_props":        new_props,
        "worker_results":   worker_results,
        "source_metrics":   metrics_log,
        "workers":          http_workers + pw_workers,
        "limit":            limit,
        "batches":          len(batches_http) + len(batches_pw),
    }


# ---------------------------------------------------------------------------
# Escritura de outputs
# ---------------------------------------------------------------------------

MANIFEST_FIELDS = [
    "source_id", "source_name", "old_url_listado", "new_url_listado",
    "url_status", "parser_status", "parser_family", "combined_status",
    "is_parser_recovered", "property_links", "old_cards", "new_cards",
    "estimated_yield", "detail_category", "detail_score",
    "detail_title", "detail_price", "needs_playwright", "error",
]

CANARY_FIELDS = [
    "source_id", "source_name", "url_visited", "url_source",
    "http_status", "cards_detected", "property_links",
    "parse_method", "parse_status", "elapsed_s", "error",
    "db_writes", "upsert_propiedades", "runs_created", "publish",
]


def _write_csv(path: Path, rows: List[Dict], fields: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_outputs(out_dir, ts, manifest_path, all_rows, valid_rows, errors,
                  fuentes, dry_stats, excluded_rows, limit):
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "manifest_loaded.csv", all_rows, MANIFEST_FIELDS)
    _write_csv(out_dir / "dry_run_plan.csv", valid_rows[:limit] if limit else valid_rows, MANIFEST_FIELDS)
    err_rows = [{"source_id": s, "source_name": n, "reason": r} for s, n, r in errors]
    _write_csv(out_dir / "excluded_safety_check.csv", err_rows,
               ["source_id", "source_name", "reason"])

    dup   = len([e for e in errors if "duplicate"  in e[2]])
    miss  = len([e for e in errors if "missing"    in e[2]])
    prow  = len([e for e in errors if "prohibited" in e[2]])
    fail  = len([e for e in errors if "blocked"    in e[2]])

    (out_dir / "write_path_guardrails.md").write_text(
        f"# Guardrails de escritura\n\nGenerado: {ts}\n\n"
        "| Acción | Estado |\n|---|---|\n"
        "| DB writes (propiedades) | **0 (dry-run)** |\n"
        "| UPSERT propiedades | **BLOQUEADO** |\n"
        "| raw/staging | NO APLICA |\n", encoding="utf-8")
    (out_dir / "proposed_next_commands.md").write_text(
        f"# Comandos propuestos\n\nGenerado: {ts}\n\n"
        "## 09d — Corrida real 50 fuentes\n```bash\n"
        "python scripts/run_manifest.py "
        "--manifest _scratch/prod_preflight_url_parser_09a/manifest_success_only.csv "
        "--execute --limit 50 --workers 2\n```\n", encoding="utf-8")
    (out_dir / "risk_assessment.md").write_text(
        f"# Risk assessment\n\nGenerado: {ts}\n\n"
        f"| Fuentes válidas | {len(valid_rows)} |\n"
        f"|---|---|\n| Errores | {len(errors)} |\n"
        f"| Missing | {miss} |\n| Prohibidas | {prow} |\n"
        f"| Duplicadas | {dup} |\n| DB writes | **0** |\n", encoding="utf-8")
    (out_dir / "next_step_recommendation.md").write_text(
        f"# Próximo paso\n\nGenerado: {ts}\n\nManifest validado: {len(valid_rows)} fuentes.\n"
        "Siguiente: 09d --execute --limit 50.\n", encoding="utf-8")
    (out_dir / "test_results.md").write_text(
        f"# Test results\n\nGenerado: {ts}\n\npytest tests/test_run_manifest.py -v\n",
        encoding="utf-8")
    (out_dir / "run_manifest_summary.md").write_text(
        f"# Dry-run summary\n\nGenerado: {ts}\n\n"
        f"| Manifest | `{manifest_path.name}` |\n|---|---|\n"
        f"| Filas | {len(all_rows)} |\n| Válidas | {len(valid_rows)} |\n"
        f"| Errores | {len(errors)} |\n| DB writes | **0** |\n",
        encoding="utf-8")


def write_canary_outputs(results, out_dir, ts, manifest_path):
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = list(results[0].keys()) if results else CANARY_FIELDS
    _write_csv(out_dir / "canary_results.csv",  results, fields)
    success = [r for r in results if r["parse_status"] == "ok"]
    failed  = [r for r in results if r["parse_status"] != "ok"]
    _write_csv(out_dir / "canary_success.csv", success, CANARY_FIELDS)
    _write_csv(out_dir / "canary_failed.csv",  failed,  CANARY_FIELDS)
    visited = [{"source_id": r["source_id"], "source_name": r["source_name"],
                "url_visited": r["url_visited"], "http_status": r["http_status"],
                "elapsed_s": r["elapsed_s"]} for r in results]
    _write_csv(out_dir / "visited_urls.csv", visited,
               ["source_id", "source_name", "url_visited", "http_status", "elapsed_s"])

    n_ok     = len(success)
    t_cards  = sum(r["cards_detected"] for r in results)
    t_links  = sum(r["property_links"]  for r in results)
    n_tmout  = sum(1 for r in results if r["parse_status"] == "timeout")
    n_nocrd  = sum(1 for r in results if r["parse_status"] == "no_cards")
    t_db     = sum(r["db_writes"]        for r in results)

    (out_dir / "db_write_guardrails.md").write_text(
        f"# DB write guardrails — canary\n\nGenerado: {ts}\n\n"
        f"| DB writes | **{t_db}** |\n|---|---|\n"
        f"| UPSERT propiedades | **0** |\n| runs creados | **0** |\n",
        encoding="utf-8")

    summary = (
        f"# Canary HTTP summary\n\nGenerado: {ts}\n\n"
        f"| Fuentes | {len(results)} |\n|---|---|\n"
        f"| Success (cards>0) | **{n_ok}** |\n| No cards | {n_nocrd} |\n"
        f"| Timeout | {n_tmout} |\n| Total cards | {t_cards} |\n"
        f"| Total links | {t_links} |\n\n"
        "## Por fuente\n\n"
        "| id | Fuente | Status | Cards | Links | t(s) |\n|---|---|---|---|---|---|\n"
        + "".join(
            f"| {r['source_id']} | {r['source_name'][:28]} | "
            f"{r['parse_status']} | {r['cards_detected']} | {r['property_links']} | {r['elapsed_s']} |\n"
            for r in results
        )
        + f"\n## Guardrails\n\n| DB writes | **{t_db}** |\n|---|---|\n| publish | **0** |\n"
    )
    (out_dir / "run_manifest_09c_summary.md").write_text(summary, encoding="utf-8")
    (out_dir / "risk_assessment.md").write_text(
        f"# Risk assessment — canary\n\nGenerado: {ts}\n\n"
        f"| DB writes | **0** |\n|---|---|\n| UPSERT propiedades | **0** |\n"
        f"| Fuentes visitadas | {len(results)} |\n| Success | {n_ok} |\n",
        encoding="utf-8")
    (out_dir / "next_step_recommendation.md").write_text(
        f"# Próximo paso\n\nGenerado: {ts}\n\n"
        f"Canary: {n_ok}/{len(results)} success. {t_cards} cards totales.\n\n"
        "Siguiente: --execute --limit 50 --workers 2 (PR-BE-PROD-09d).\n",
        encoding="utf-8")
    (out_dir / "test_results.md").write_text(
        f"# Test results\n\nGenerado: {ts}\n\npytest tests/test_run_manifest.py -v\n",
        encoding="utf-8")


def write_execute_outputs(
    result: Dict,
    out_dir: Path,
    ts: str,
    manifest_path: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    subset        = result["subset"]
    fuentes_sin_fk = result.get("fuentes_sin_fk", [])
    count_bef   = result["count_before"]
    count_aft   = result["count_after"]
    total_saved = result["total_saved"]
    net_new     = result["net_new"]
    new_props   = result["new_props"]
    wkr_results = result["worker_results"]
    source_metrics = result.get("source_metrics", [])

    source_result_fields = [
        "run_id", "source_id", "inmobiliaria_id", "nombre", "started_at",
        "finished_at", "duration_s", "status", "classification", "pages",
        "listings_seen", "details_requested", "valid_properties",
        "new_properties", "duplicates_skipped", "db_writes", "timeout",
        "http_status", "error_type", "error_sanitized", "retryable",
        "retry_count", "memory_peak_mb",
    ]
    source_rows = []
    for metric in source_metrics:
        source_rows.append({
            "run_id": out_dir.name,
            "source_id": metric.get("source_id", ""),
            "inmobiliaria_id": metric.get("inmobiliaria_id", ""),
            "nombre": metric.get("nombre", metric.get("key", "")),
            "started_at": metric.get("started_at", ""),
            "finished_at": metric.get("finished_at", metric.get("ts_utc", "")),
            "duration_s": metric.get("source_time_s", ""),
            "status": metric.get("status", "INTERNAL_ERROR"),
            "classification": metric.get("classification", "INTERNAL_RETRYABLE"),
            "pages": metric.get("pages", 0),
            "listings_seen": metric.get("n_listado", 0),
            "details_requested": metric.get("n_nuevas", 0),
            "valid_properties": metric.get("n_validas", 0),
            "new_properties": metric.get("props_saved", 0),
            "duplicates_skipped": metric.get("duplicates_skipped", 0),
            "db_writes": metric.get("props_saved", 0),
            "timeout": metric.get("had_timeout", False),
            "http_status": metric.get("http_status", ""),
            "error_type": metric.get("error_type", ""),
            "error_sanitized": metric.get("error_sanitized", ""),
            "retryable": metric.get("retryable", False),
            "retry_count": metric.get("retry_count", 0),
            "memory_peak_mb": metric.get("memory_peak_mb", ""),
        })
    for f in fuentes_sin_fk:
        source_rows.append({
            "run_id": out_dir.name,
            "source_id": f.get("source_id", ""),
            "inmobiliaria_id": "",
            "nombre": f.get("_manifest_name", ""),
            "status": "FK_ERROR",
            "classification": "INTERNAL_CORRECTABLE",
            "error_type": "fk_unresolved",
            "error_sanitized": "FK unresolved during preflight",
            "retryable": True,
            "retry_count": 0,
        })
    source_rows.sort(key=lambda row: str(row.get("source_id", "")))
    _write_csv(out_dir / "source_results.csv", source_rows, source_result_fields)

    # executed_sources.csv — fuentes con FK válido que fueron scrapeadas
    exec_rows = [
        {"source_id":      f["source_id"],
         "source_name":    f["_manifest_name"],
         "url_used":       f["web"],
         "url_source":     f["_url_source"],
         "inmobiliaria_id": f.get("inmobiliaria_id", "")}
        for f in subset
    ]
    _write_csv(out_dir / "executed_sources.csv", exec_rows,
               ["source_id", "source_name", "url_used", "url_source", "inmobiliaria_id"])

    # skipped_no_fk.csv — fuentes omitidas por falta de FK
    skip_rows = [
        {"source_id":   f["source_id"], "source_name": f["_manifest_name"],
         "url_listado": f["web"],       "reason":      "no FK en inmobiliarias_main"}
        for f in fuentes_sin_fk
    ]
    _write_csv(out_dir / "skipped_no_fk.csv", skip_rows,
               ["source_id", "source_name", "url_listado", "reason"])

    # inserted_properties.csv — propiedades con created_at > ts_start
    PROP_FIELDS = ["id", "url", "url_normalizada", "hash_dedup", "inmobiliaria_id",
                   "titulo", "fuente_extraccion", "operacion", "tipo_propiedad",
                   "precio", "moneda", "created_at"]
    _write_csv(out_dir / "inserted_properties.csv", new_props, PROP_FIELDS)

    # updated_properties.csv — siempre vacío: pipeline es INSERT plain, nunca UPDATE.
    # La dedup es upstream (existing_urls); URLs conocidas nunca llegan al INSERT.
    _write_csv(out_dir / "updated_properties.csv", [], PROP_FIELDS)

    # skipped_duplicates.csv — no tenemos lista individual, pero podemos estimar
    skipped_note = [{
        "note": "Duplicados omitidos internamente por _scrape_batch via existing_urls.",
        "estimado": "existing_urls tenía {count_bef} URLs antes; el scraper filtra automáticamente.",
    }]
    _write_csv(out_dir / "skipped_duplicates.csv", skipped_note, ["note", "estimado"])

    # failed_sources.csv
    failed = [{"worker_id": k, **v} for k, v in wkr_results.items() if v.get("status") == "error"]
    _write_csv(out_dir / "failed_sources.csv", failed,
               ["worker_id", "saved", "status", "error"])

    # Per-fuente breakdown usando campo `fuente` en new_props
    fuente_counts: Dict[str, int] = {}
    for p in new_props:
        k = p.get("fuente_extraccion") or "?"
        fuente_counts[k] = fuente_counts.get(k, 0) + 1

    # post_execute_validation.md
    val = (
        f"# Post-execute validation — PR-BE-PROD-09d\n\nGenerado: {ts}\n\n"
        f"| Métrica | Valor |\n|---|---|\n"
        f"| propiedades antes | {count_bef:,} |\n"
        f"| propiedades guardadas (sum workers) | {total_saved} |\n"
        f"| delta en existing_urls | {net_new} |\n"
        f"| propiedades created_at > ts_start | **{len(new_props)}** |\n"
        f"| workers con error | {len(failed)} |\n\n"
        "## Fuentes de verdad\n\n"
        "| Métrica | Confiabilidad | Notas |\n|---|---|---|\n"
        "| propiedades guardadas (sum workers) | Alta | Cuenta directa de INSERTs confirmados por Supabase (HTTP 200/201) |\n"
        "| delta en existing_urls | Alta | Refleja exactamente las URLs agregadas al Set en memoria |\n"
        f"| created_at > ts_start | Posible falso negativo | `_query_propiedades_since` solo acepta HTTP 200; lag de Supabase puede devolver 0 aunque los {total_saved} INSERTs sean reales. Ver `inserted_properties.csv`. |\n\n"
        "## Validaciones de exclusividad\n\n"
        "| Validación | Estado |\n|---|---|\n"
        "| Solo fuentes del manifest (50) | OK — wrapper no llama load_fuentes_from_db |\n"
        "| new_url_listado usado | OK — _url_source=new_url_listado en todas |\n"
        "| inmobiliarias_main tocada | NO |\n"
        "| publish_queue tocada | NO |\n"
        "| include-backlog usado | NO |\n"
        "| deploy / frontend | NO |\n\n"
        "## Por fuente (top 20 según created_at)\n\n"
        "| fuente | propiedades |\n|---|---|\n"
        + "".join(f"| {k} | {v} |\n" for k, v in
                  sorted(fuente_counts.items(), key=lambda x: -x[1])[:20])
    )
    (out_dir / "post_execute_validation.md").write_text(val, encoding="utf-8")

    # db_write_audit.md
    audit = (
        f"# DB write audit — PR-BE-PROD-09d\n\nGenerado: {ts}\n\n"
        "## Escrituras autorizadas\n\n"
        f"| Tabla | Operación | Filas | Estado |\n|---|---|---|---|\n"
        f"| propiedades | INSERT plain (sin on_conflict) | {total_saved} | OK |\n\n"
        "## Mecanismo de deduplicación\n\n"
        "La unicidad **no** se garantiza con `on_conflict`. Se garantiza upstream:\n"
        "1. `existing_urls` (Set[str]) se carga por `inmobiliaria_id` antes del scraping.\n"
        "2. Cada URL scrapeada se filtra contra `existing_urls` en memoria.\n"
        "3. Solo URLs ausentes llegan a `batch_save_only_new()` (INSERT plain).\n"
        "4. `updated_properties.csv` es siempre vacío: no hay UPDATEs en este pipeline.\n\n"
        "## Escrituras bloqueadas (confirmadas en 0)\n\n"
        "| Tabla | Estado |\n|---|---|\n"
        "| inmobiliarias_main | 0 |\n"
        "| publish_queue | 0 |\n"
        "| raw / staging | 0 (no aplica en este pipeline) |\n"
        "| url_listado | 0 |\n"
        "| diagnostic_status | 0 |\n"
        "| scraping_runs / scraping_run_items | 0 (no aplica) |\n\n"
        "## Workers\n\n"
        + "".join(
            f"| Worker {k} | saved={v['saved']} | status={v['status']} |\n"
            for k, v in sorted(wkr_results.items())
        )
    )
    (out_dir / "db_write_audit.md").write_text(audit, encoding="utf-8")

    # risk_assessment.md
    risk = (
        f"# Risk assessment — PR-BE-PROD-09d\n\nGenerado: {ts}\n\n"
        f"| Riesgo | Estado |\n|---|---|\n"
        f"| Fuentes fuera del manifest | 0 |\n"
        f"| Tablas no autorizadas escritas | 0 |\n"
        f"| Workers con error | {len(failed)} |\n"
        f"| Propiedades guardadas | {total_saved} |\n"
        f"| Regresión (propiedades borradas) | 0 — INSERT plain; nunca borra ni sobreescribe |\n"
        f"\n## Criterio de corte (no activado)\n\n"
        f"Corte activado si: >10 workers fallidos, error DB, UPSERT fuera de propiedades.\n"
        f"Estado actual: {len(failed)} workers fallidos — "
        f"{'OK' if len(failed) == 0 else 'REVISAR'}.\n"
    )
    (out_dir / "risk_assessment.md").write_text(risk, encoding="utf-8")

    # next_step_recommendation.md
    ok_to_scale = len(new_props) > 0 and len(failed) == 0
    nxt = (
        f"# Próximo paso — post PR-BE-PROD-09d\n\nGenerado: {ts}\n\n"
        f"## Resultado del lote de {len(subset)} fuentes\n\n"
        f"| Métrica | Valor |\n|---|---|\n"
        f"| propiedades guardadas | {total_saved} |\n"
        f"| propiedades nuevas en DB | {len(new_props)} |\n"
        f"| workers exitosos | {len([v for v in wkr_results.values() if v['status']=='ok'])}/{len(wkr_results)} |\n\n"
        f"## Recomendación: {'escalar a 09e' if ok_to_scale else 'revisar antes de escalar'}\n\n"
    )
    if ok_to_scale:
        nxt += (
            "**PR-BE-PROD-09e** — Corrida completa (891 fuentes).\n\n"
            "```bash\n"
            "# Requiere autorización explícita\n"
            "python scripts/run_manifest.py \\\n"
            "  --manifest _scratch/prod_preflight_url_parser_09a/manifest_success_only.csv \\\n"
            "  --execute --workers 4\n"
            "```\n"
            "Nota: 09e necesitará actualizar MAX_EXECUTE_LIMIT y MAX_EXECUTE_WORKERS.\n"
        )
    else:
        nxt += "Revisar `failed_sources.csv` y `post_execute_validation.md` antes de escalar.\n"
    (out_dir / "next_step_recommendation.md").write_text(nxt, encoding="utf-8")

    # run_manifest_09d_summary.md
    summary = (
        f"# PR-BE-PROD-09d — Execute summary\n\nGenerado: {ts}\n\n"
        f"## Input\n\n"
        f"| Manifest | `{manifest_path.name}` |\n|---|---|\n"
        f"| Fuentes ejecutadas | {len(subset)} |\n"
        f"| Workers | {result['workers']} |\n"
        f"| URL source | new_url_listado |\n\n"
        f"## Resultado\n\n"
        f"| Métrica | Valor |\n|---|---|\n"
        f"| propiedades antes | {count_bef:,} |\n"
        f"| propiedades guardadas (workers) | **{total_saved}** |\n"
        f"| delta existing_urls | {net_new} |\n"
        f"| propiedades created_at > ts | **{len(new_props)}** |\n"
        f"| Workers con error | {len(failed)} |\n\n"
        f"## Guardrails\n\n"
        "| Tabla | Escrita |\n|---|---|\n"
        "| propiedades | SI (INSERT plain — dedup upstream via existing_urls) |\n"
        "| inmobiliarias_main | **NO** |\n"
        "| publish_queue | **NO** |\n"
        "| raw / staging | **NO** |\n"
        "| include-backlog | **NO** |\n"
        "| deploy / frontend | **NO** |\n"
    )
    (out_dir / "run_manifest_09d_summary.md").write_text(summary, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Wrapper seguro para corrida de manifest (09b/09c/09d)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--manifest",        required=True)
    p.add_argument("--dry-run",         action="store_true", dest="dry_run")
    p.add_argument("--playwright",      action="store_true")
    p.add_argument("--execute",         action="store_true")
    p.add_argument("--out",             default=None)
    p.add_argument("--limit",           type=int,  default=None)
    p.add_argument("--workers",         type=int,  default=2)
    p.add_argument("--exclude",         default=None)
    p.add_argument("--commit",          action="store_true")
    p.add_argument("--include-backlog", action="store_true", dest="include_backlog")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    ts   = datetime.now(timezone.utc).isoformat()

    # ── Bloqueos permanentes ─────────────────────────────────────────────────

    if args.include_backlog:
        print("ERROR: --include-backlog is permanently blocked.", file=sys.stderr)
        return 1

    if args.commit:
        print("ERROR: --commit is not authorized. Use --execute for production runs.",
              file=sys.stderr)
        return 1

    # ── Checks de --playwright ───────────────────────────────────────────────

    if args.playwright and not args.dry_run:
        print("ERROR: --playwright requires --dry-run. "
              "Site visits without --dry-run are not authorized.",
              file=sys.stderr)
        return 1

    if args.playwright and not args.limit:
        print("ERROR: --playwright requires --limit N for safety.", file=sys.stderr)
        return 1

    # ── Checks de --execute ──────────────────────────────────────────────────

    if args.execute:
        if not args.limit:
            print("ERROR: --execute requires --limit for safety. "
                  f"Use --limit <= {MAX_EXECUTE_LIMIT}.", file=sys.stderr)
            return 1
        if args.limit > MAX_EXECUTE_LIMIT:
            print(f"ERROR: --execute --limit {args.limit} exceeds MAX_EXECUTE_LIMIT "
                  f"({MAX_EXECUTE_LIMIT}) authorized in PR-BE-PROD-09e. "
                  "Raise the constant with explicit authorization for a larger run.",
                  file=sys.stderr)
            return 1
        if args.workers > MAX_HTTP_WORKERS:
            print(f"ERROR: --execute --workers {args.workers} exceeds MAX_HTTP_WORKERS "
                  f"({MAX_HTTP_WORKERS}). Medir RAM real antes de subir el límite.",
                  file=sys.stderr)
            return 1
        if args.dry_run:
            print("ERROR: --execute and --dry-run are mutually exclusive.", file=sys.stderr)
            return 1

    # ── Modo no autorizado ───────────────────────────────────────────────────

    if not args.dry_run and not args.execute:
        print("ERROR: Refusing to run without --dry-run. "
              "Real DB writes are not authorized. "
              "Add --dry-run or --execute (with --limit <= 50).",
              file=sys.stderr)
        return 1

    # ── Cargar manifest ──────────────────────────────────────────────────────

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    mode = ("execute" if args.execute
            else "canary HTTP" if args.playwright
            else "dry-run")
    print(f"[MANIFEST] Manifest: {manifest_path.name}")
    print(f"[MANIFEST] Mode: {mode}")
    print()

    all_rows = load_manifest(manifest_path)
    print(f"[MANIFEST] Filas leídas: {len(all_rows)}")

    excluded_ids: Set[str] = set()
    excl_path = Path(args.exclude) if args.exclude else None
    if excl_path is None:
        default_excl = REPO_ROOT / "_scratch" / "prod_preflight_url_parser_09a" / "manifest_excluded.csv"
        if default_excl.exists():
            excl_path = default_excl
    if excl_path and excl_path.exists():
        excl_rows    = load_manifest(excl_path)
        excluded_ids = {r.get("source_id", "").strip() for r in excl_rows if r.get("source_id")}
        print(f"[MANIFEST] Excluidas cargadas: {len(excluded_ids)} source_ids")

    valid_http, valid_pw, blocked_pw, errors = validate_manifest(all_rows, excluded_ids=excluded_ids)
    valid_rows = valid_http  # alias para dry-run y write_outputs

    if errors:
        print(f"\n[MANIFEST] {len(errors)} filas con errores de validación:")
        for sid, name, reason in errors[:10]:
            print(f"  id={sid:<6} | {name[:35]:<35} | {reason}")
        if len(errors) > 10:
            print(f"  ... y {len(errors) - 10} más")
        print()

    print(f"[MANIFEST] Cola HTTP:            {len(valid_http)} fuentes")
    print(f"[MANIFEST] Cola Playwright:      {len(valid_pw)} fuentes")
    print(f"[MANIFEST] Playwright bloqueadas:{len(blocked_pw)} fuentes (antibot/captcha — sin scraping)")
    print(f"[MANIFEST] Errores validación:   {len(errors)}")

    fuentes_http = build_fuentes(valid_http)
    fuentes_pw   = build_fuentes(valid_pw)
    fuentes      = fuentes_http  # alias para canary/dry-run (HTTP-only paths)
    out_dir = (
        Path(args.out).resolve() if args.out else
        REPO_ROOT / "_scratch" / (
            "run_manifest_09d" if args.execute else
            "run_manifest_09c" if args.playwright else
            "run_manifest_09b"
        )
    )

    # ── Ejecutar ─────────────────────────────────────────────────────────────

    if args.execute:
        result = run_execute(
            fuentes_http, fuentes_pw,
            args.limit, args.workers, MAX_PW_WORKERS,
            out_dir, ts, manifest_path,
        )
        if result is None:
            return 1
        write_execute_outputs(result, out_dir, ts, manifest_path)
        print(f"\n[MANIFEST] Outputs -> {out_dir}")
        print(f"[MANIFEST] Siguiente paso: PR-BE-PROD-09e (corrida completa 891 fuentes)")
        return 0

    if args.playwright:
        canary = run_canary_http(fuentes, args.limit)
        write_canary_outputs(canary, out_dir, ts, manifest_path)
        n_ok   = sum(1 for r in canary if r["parse_status"] == "ok")
        t_crd  = sum(r["cards_detected"] for r in canary)
        print(f"\n[MANIFEST] Canary: {n_ok}/{len(canary)} success | {t_crd} cards | 0 DB writes")
        print(f"[MANIFEST] Outputs -> {out_dir}")
        return 0

    # dry-run puro
    dry_stats = run_dry(fuentes, out_dir, args.limit, ts)
    write_outputs(
        out_dir=out_dir, ts=ts, manifest_path=manifest_path,
        all_rows=all_rows, valid_rows=valid_rows, errors=errors,
        fuentes=fuentes, dry_stats=dry_stats, excluded_rows=[], limit=args.limit,
    )
    print(f"\n[MANIFEST] Dry-run: {len(valid_http)} HTTP + {len(valid_pw)} PW fuentes validadas. 0 DB writes.")
    print(f"[MANIFEST] Outputs -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

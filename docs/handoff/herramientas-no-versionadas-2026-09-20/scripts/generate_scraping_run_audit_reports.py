#!/usr/bin/env python
"""Generate local audit reports for controlled internal scraping runs.

Reads local scraping_autofix artifacts and optionally reads Neon with SELECTs.
It never writes to Supabase or Neon, never touches publish_queue, and never
modifies frontend or .env.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlparse

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = REPO_ROOT / "reports" / "scraping_autofix" / "autofix_state.json"
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "scraping_runs"
VALID_OPERATIONS = {"venta", "alquiler", "alquiler_temporario"}
VALID_CURRENCIES = {"ARS", "USD"}
BAD_IMAGE_TOKENS = ("placeholder", "sin-imagen", "no-image", "logo", "favicon", "map")
ADDRESS_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
ADDRESS_EMAIL_RE = re.compile(r"[\w.%-]+@[\w.-]+\.[A-Za-z]{2,}")
ERROR_FAMILY_MAP = {
    "site_down_confirmed": "site_down",
    "site_down": "site_down",
    "blocked": "blocked",
    "item_timeout": "timeout",
    "remax_timeout": "timeout",
    "timeout": "timeout",
    "static_timeout": "timeout",
    "requires_playwright": "requires_playwright",
    "requires_network_interception": "requires_playwright",
    "no_property_links": "no_property_links",
    "no_property_links_confirmed": "no_property_links",
    "strategy_quality_failed": "strategy_quality_failed",
    "bad_url": "bad_url",
    "invalid_source": "invalid_source",
    "skipped_invalid_source": "invalid_source",
    "invalid_source_url": "invalid_source",
    "admin_url": "invalid_source",
    "anchor_only_url": "invalid_source",
    "institutional_page": "invalid_source",
    "possible_developer_without_listings": "invalid_source",
    "parser_error": "parser_error",
    "network_error": "network_error",
    "geocoding_error": "geocoding_error",
    "validation_error": "validation_error",
    "duplicate": "duplicate_issue",
    "sin_propiedades": "no_property_links",
    "missing_location": "missing_location",
    "missing_price": "missing_price",
    "missing_images": "missing_images",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_env() -> None:
    load_env_file(REPO_ROOT / ".env")
    load_env_file(REPO_ROOT / ".env.local")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def resolve_path(value: Any) -> Path:
    path = Path(str(value))
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for idx in range(1, 1000):
        candidate = parent / f"{stem}_{idx:02d}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique output path available for {path}")


def normalize_url_for_key(url: Any) -> str:
    if not url:
        return ""
    raw = unquote(str(url).strip())
    if not raw:
        return ""
    if not re.match(r"^https?://", raw, re.IGNORECASE):
        raw = f"http://{raw.lstrip('/')}"
    try:
        parsed = urlparse(raw)
    except Exception:
        return re.sub(r"\s+", "", raw.lower()).rstrip("/")
    host = (parsed.netloc or parsed.path.split("/")[0]).split("@")[-1]
    host = host.split(":")[0].strip().lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+", "/", unquote(parsed.path or "")).strip().rstrip("/").lower()
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        key_clean = key.strip().lower()
        if key_clean.startswith("utm_") or key_clean in {"fbclid", "gclid", "wbraid", "gbraid"}:
            continue
        query_items.append((key_clean, value.strip().lower()))
    query = "&".join(f"{key}={value}" for key, value in sorted(query_items))
    return f"{host}{path}" + (f"?{query}" if query else "")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
        return float(normalized)
    except Exception:
        return None


def classify_error(raw_type: Any, message: Any = "") -> str:
    key = clean_text(raw_type).lower()
    if key in ERROR_FAMILY_MAP:
        return ERROR_FAMILY_MAP[key]
    text = f"{key} {clean_text(message).lower()}"
    if "timeout" in text:
        return "timeout"
    if "playwright" in text or "js" in text:
        return "requires_playwright"
    if "geo" in text:
        return "geocoding_error"
    if "validation" in text or "invalid" in text:
        return "validation_error"
    if "duplicate" in text:
        return "duplicate_issue"
    if "network" in text or "connection" in text:
        return "network_error"
    return "otro"


def issue_row(
    *,
    agency_id: Any,
    agency_name: Any,
    source_url: Any,
    property_id: Any,
    title: Any,
    issue_kind: str,
    issue_type: str,
    field: str,
    value: Any = "",
    severity: str = "media",
    evidence: str = "",
    recommendation: str = "",
    origin: str = "captured_json",
    batch: Any = "",
) -> Dict[str, Any]:
    return {
        "batch": batch,
        "inmobiliaria_id": agency_id or "",
        "inmobiliaria_nombre": agency_name or "",
        "url_origen": source_url or "",
        "propiedad_id_o_externo": property_id or "",
        "titulo_propiedad": clean_text(title)[:300],
        "issue_kind": issue_kind,
        "issue_type": issue_type,
        "campo": field,
        "valor_detectado": clean_text(value)[:500],
        "severidad": severity,
        "evidencia": evidence,
        "recomendacion": recommendation,
        "origen": origin,
    }


def real_images(images: Any) -> List[str]:
    if not isinstance(images, list):
        return []
    out: List[str] = []
    for item in images:
        if isinstance(item, dict):
            value = item.get("url") or item.get("src") or item.get("href") or item.get("image")
        else:
            value = item
        text = clean_text(value)
        if not text:
            continue
        lower = text.lower()
        if lower.endswith(".svg") or lower.startswith("data:"):
            continue
        if any(token in lower for token in BAD_IMAGE_TOKENS):
            continue
        out.append(text)
    return out


def analyze_property(
    prop: Dict[str, Any],
    *,
    agency_id: Any,
    agency_name: Any,
    source_url: Any,
    batch: Any,
    url_seen: Counter[str],
    signature_seen: Counter[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    property_id = prop.get("id_externo") or prop.get("id") or prop.get("url")
    title = prop.get("titulo")
    source = prop.get("sourceUrl") or prop.get("source_url") or prop.get("url") or source_url

    missing_specs = [
        ("missing_location", "ciudad/provincia", not prop.get("ciudad") and not prop.get("provincia")),
        ("missing_address", "direccion", not prop.get("direccion")),
        ("missing_city", "ciudad", not prop.get("ciudad")),
        ("missing_province", "provincia", not prop.get("provincia")),
        ("missing_neighborhood", "barrio", not prop.get("barrio")),
        ("missing_price", "precio", prop.get("precio") in (None, "")),
        ("missing_currency", "moneda", prop.get("moneda") in (None, "")),
        ("missing_operation", "operacion", prop.get("operacion") in (None, "")),
        ("missing_property_type", "tipo_propiedad", prop.get("tipo_propiedad") in (None, "", "otro")),
        ("missing_images", "imagenes", not prop.get("imagenes")),
        ("missing_real_image", "imagenes", not real_images(prop.get("imagenes"))),
        ("missing_surface", "superficie_total", prop.get("superficie_total") in (None, "")),
        ("missing_rooms", "ambientes", prop.get("ambientes") in (None, "")),
        ("missing_bedrooms", "dormitorios", prop.get("dormitorios") in (None, "")),
        ("missing_bathrooms", "banos", prop.get("banos") in (None, "") and prop.get("baños") in (None, "")),
        ("missing_garages", "cocheras", prop.get("cocheras") in (None, "")),
        ("missing_source_url", "url", not prop.get("url")),
        ("missing_coordinates", "latitud/longitud", prop.get("latitud") in (None, "") or prop.get("longitud") in (None, "")),
    ]
    for issue_type, field, condition in missing_specs:
        if condition:
            rows.append(issue_row(
                agency_id=agency_id,
                agency_name=agency_name,
                source_url=source,
                property_id=property_id,
                title=title,
                issue_kind="missing",
                issue_type=issue_type,
                field=field,
                severity="media",
                evidence="captured_json_field_empty",
                recommendation="Revisar si el origen no expone el dato o si el extractor general no lo esta tomando.",
                batch=batch,
            ))

    direccion = clean_text(prop.get("direccion"))
    if direccion:
        if ADDRESS_EMAIL_RE.search(direccion):
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="address_contains_email",
                field="direccion", value=direccion, severity="alta",
                evidence="regex_email_in_address", recommendation="Retener direccion y mejorar limpieza de texto.",
                batch=batch,
            ))
        if ADDRESS_PHONE_RE.search(direccion):
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="address_contains_phone",
                field="direccion", value=direccion, severity="alta",
                evidence="regex_phone_in_address", recommendation="Retener direccion y mejorar limpieza de telefono/contacto.",
                batch=batch,
            ))
        lowered = direccion.lower()
        if any(token in lowered for token in ("usd", "u$s", "$", "consultar precio", "superficie", "expensas", "contacto", "whatsapp")):
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="address_contaminated_text",
                field="direccion", value=direccion, severity="media",
                evidence="commercial_or_price_token_in_address", recommendation="Corregir normalizador de direccion antes de geocoding.",
                batch=batch,
            ))

    lat = to_float(prop.get("latitud"))
    lon = to_float(prop.get("longitud"))
    if lat is not None or lon is not None:
        if lat is None or lon is None or not (-55 <= lat <= -21 and -74 <= lon <= -53):
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="coordinates_out_of_argentina",
                field="latitud/longitud", value=f"{prop.get('latitud')},{prop.get('longitud')}", severity="alta",
                evidence="range_check_argentina", recommendation="Descartar coordenadas y geocodificar desde direccion normalizada.",
                batch=batch,
            ))

    price = to_float(prop.get("precio"))
    currency = clean_text(prop.get("moneda")).upper()
    if currency and currency not in VALID_CURRENCIES:
        rows.append(issue_row(
            agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
            title=title, issue_kind="suspicious", issue_type="dubious_currency",
            field="moneda", value=currency, severity="media",
            evidence="currency_not_in_allowed_set", recommendation="Normalizar moneda o retener publicacion.",
            batch=batch,
        ))
    if price is not None:
        suspicious_price = (currency == "USD" and (price < 1000 or price > 50_000_000)) or (
            currency == "ARS" and (price < 10_000 or price > 100_000_000_000)
        )
        if suspicious_price:
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="suspicious_price",
                field="precio", value=f"{currency} {price}", severity="media",
                evidence="range_check", recommendation="Validar parseo de separadores y moneda.",
                batch=batch,
            ))

    operation = clean_text(prop.get("operacion")).lower()
    if operation and operation not in VALID_OPERATIONS:
        rows.append(issue_row(
            agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
            title=title, issue_kind="suspicious", issue_type="dubious_operation",
            field="operacion", value=operation, severity="media",
            evidence="operation_not_in_allowed_set", recommendation="Mejorar mapeo de operacion.",
            batch=batch,
        ))

    title_text = clean_text(title)
    if not title_text or title_text.lower() in {"propiedad", "ver propiedad", "detalle", "casa", "departamento"}:
        rows.append(issue_row(
            agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
            title=title, issue_kind="suspicious", issue_type="generic_title",
            field="titulo", value=title_text, severity="baja",
            evidence="generic_title_token", recommendation="Usar fallback de tipo/operacion/ubicacion solo si hay senales claras.",
            batch=batch,
        ))
    if agency_name and title_text and clean_text(agency_name).lower() in title_text.lower() and len(title_text) < len(clean_text(agency_name)) + 30:
        rows.append(issue_row(
            agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
            title=title, issue_kind="suspicious", issue_type="title_looks_like_agency",
            field="titulo", value=title_text, severity="media",
            evidence="agency_name_inside_short_title", recommendation="Evitar tomar nombre de inmobiliaria como titulo.",
            batch=batch,
        ))

    url_key = normalize_url_for_key(prop.get("url"))
    if url_key:
        url_seen[url_key] += 1
        if url_seen[url_key] > 1:
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="exact_duplicate_url_in_run",
                field="url", value=prop.get("url"), severity="media",
                evidence="same_normalized_url_seen_multiple_times", recommendation="Deduplicar por URL normalizada antes de importar.",
                batch=batch,
            ))
    signature = "|".join([
        clean_text(prop.get("direccion")).lower(),
        clean_text(prop.get("ciudad")).lower(),
        clean_text(prop.get("provincia")).lower(),
        str(price or ""),
        clean_text(prop.get("tipo_propiedad")).lower(),
    ]).strip("|")
    if signature and len(signature) > 8:
        signature_seen[signature] += 1
        if signature_seen[signature] > 1:
            rows.append(issue_row(
                agency_id=agency_id, agency_name=agency_name, source_url=source, property_id=property_id,
                title=title, issue_kind="suspicious", issue_type="possible_cross_agency_duplicate",
                field="direccion/precio/tipo", value=signature[:300], severity="baja",
                evidence="same_signature_seen_multiple_times", recommendation="Revisar deduplicacion cross-agency en pipeline.",
                batch=batch,
            ))
    return rows


def load_batch_results(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Path]]:
    all_results: List[Dict[str, Any]] = []
    report_dirs: List[Path] = []
    completed = state.get("offsets_completados") or []
    for batch_number, item in enumerate(completed, 1):
        report_dir = resolve_path(item.get("report_dir"))
        if not report_dir.exists():
            continue
        report_dirs.append(report_dir)
        results = read_json(report_dir / "batch_results.json", [])
        if not isinstance(results, list):
            continue
        for result in results:
            row = dict(result)
            row["_batch_number"] = batch_number
            row["_batch_dir"] = report_dir.name
            row["_report_dir"] = rel(report_dir)
            row["_offset"] = item.get("offset", "")
            all_results.append(row)
    return all_results, report_dirs


def detect_playwright(raw_log: Any) -> str:
    if not raw_log:
        return ""
    path = resolve_path(raw_log)
    if not path.exists():
        return ""
    try:
        first = path.read_text(encoding="utf-8", errors="ignore")[:2000].lower()
    except Exception:
        return ""
    return "true" if "--allow-playwright" in first or "playwright" in first else "false"


def safe_log_excerpt(raw_log: Any) -> str:
    if not raw_log:
        return ""
    path = resolve_path(raw_log)
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    interesting = []
    for line in text.splitlines():
        lower = line.lower()
        if "error" in lower or "traceback" in lower or "timeout" in lower:
            interesting.append(line.strip())
    return " | ".join(interesting[-4:])[:1000]


def collect_local_quality(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    url_seen: Counter[str] = Counter()
    signature_seen: Counter[str] = Counter()
    for result in results:
        json_rel = result.get("json_path")
        if not json_rel:
            continue
        json_path = resolve_path(json_rel)
        payload = read_json(json_path, {})
        props = payload.get("props") if isinstance(payload, dict) else None
        if not isinstance(props, list):
            continue
        for prop in props:
            if not isinstance(prop, dict):
                continue
            rows.extend(analyze_property(
                prop,
                agency_id=result.get("inmobiliaria_id") or result.get("id"),
                agency_name=result.get("inmobiliaria_nombre"),
                source_url=result.get("url") or payload.get("url"),
                batch=result.get("_batch_number"),
                url_seen=url_seen,
                signature_seen=signature_seen,
            ))
    return rows


def chunked(values: List[str], size: int = 500) -> Iterable[List[str]]:
    for idx in range(0, len(values), size):
        yield values[idx:idx + size]


def placeholders(values: List[Any]) -> str:
    return ", ".join(["%s"] * len(values))


def fetch_neon_metrics(captured_files: List[str]) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "available": False,
        "error": "",
        "raw_by_file": Counter(),
        "raw_by_agency": Counter(),
        "staging_by_file": Counter(),
        "staging_by_agency": Counter(),
        "geocoding": Counter(),
        "db_quality_rows": [],
        "scraping_item_status": Counter(),
        "publish_queue_status": Counter(),
    }
    load_env()
    db_url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not env_flag("USE_INTERNAL_DB", default=False) or not db_url:
        metrics["error"] = "USE_INTERNAL_DB/INTERNAL_DB_URL not enabled"
        return metrics
    try:
        import psycopg  # type: ignore
        from psycopg.rows import dict_row  # type: ignore
    except Exception as exc:
        metrics["error"] = f"psycopg unavailable: {exc}"
        return metrics
    try:
        with psycopg.connect(db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, count(*) AS count FROM public.scraping_run_items GROUP BY status")
                metrics["scraping_item_status"].update({str(r["status"]): int(r["count"]) for r in cur.fetchall()})
                try:
                    cur.execute("SELECT status, count(*) AS count FROM public.publish_queue GROUP BY status")
                    metrics["publish_queue_status"].update({str(r["status"]): int(r["count"]) for r in cur.fetchall()})
                except Exception:
                    conn.rollback()
                for files in chunked(captured_files):
                    if not files:
                        continue
                    ph = placeholders(files)
                    cur.execute(
                        f"""
                        SELECT
                          datos_extra->>'captured_file' AS captured_file,
                          inmobiliaria_id,
                          count(*) AS count
                        FROM public.propiedades_raw
                        WHERE datos_extra->>'captured_file' IN ({ph})
                        GROUP BY 1, 2
                        """,
                        files,
                    )
                    for row in cur.fetchall():
                        captured = str(row["captured_file"] or "")
                        count = int(row["count"])
                        metrics["raw_by_file"][captured] += count
                        metrics["raw_by_agency"][str(row["inmobiliaria_id"])] += count
                    cur.execute(
                        f"""
                        SELECT
                          r.datos_extra->>'captured_file' AS captured_file,
                          s.inmobiliaria_id,
                          s.geocoding_status,
                          count(*) AS count
                        FROM public.propiedades_staging s
                        JOIN public.propiedades_raw r ON r.id = s.raw_id
                        WHERE r.datos_extra->>'captured_file' IN ({ph})
                        GROUP BY 1, 2, 3
                        """,
                        files,
                    )
                    for row in cur.fetchall():
                        captured = str(row["captured_file"] or "")
                        count = int(row["count"])
                        metrics["staging_by_file"][captured] += count
                        metrics["staging_by_agency"][str(row["inmobiliaria_id"])] += count
                        metrics["geocoding"][str(row["geocoding_status"] or "unknown")] += count
                    cur.execute(
                        f"""
                        SELECT
                          r.datos_extra->>'captured_file' AS captured_file,
                          r.inmobiliaria_id,
                          r.url,
                          r.titulo,
                          d.issue_type,
                          d.issue_detail
                        FROM public.data_quality_issues d
                        JOIN public.propiedades_raw r ON r.id = d.raw_id
                        WHERE r.datos_extra->>'captured_file' IN ({ph})
                        ORDER BY d.id ASC
                        LIMIT 5000
                        """,
                        files,
                    )
                    metrics["db_quality_rows"].extend(dict(row) for row in cur.fetchall())
            conn.rollback()
        metrics["available"] = True
        return metrics
    except Exception as exc:
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        return metrics


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def render_counts(counter: Counter[Any], limit: Optional[int] = None) -> str:
    items = sorted(counter.items(), key=lambda item: (-int(item[1]), str(item[0])))
    if limit:
        items = items[:limit]
    return "\n".join(f"- {key}: {value}" for key, value in items) or "- none: 0"


def build_recommendations(error_families: Counter[str], quality_counts: Counter[str], error_rate: float) -> List[str]:
    recs: List[str] = []
    if error_rate > 0.4:
        recs.append("Pausar escalado: la tasa de error supera 40%. Reanudar solo con subtandas chicas tras filtrar fuentes no procesables.")
    if error_families.get("no_property_links", 0):
        recs.append("Agregar preclasificacion general para URLs sin listado real: anchors '#', /admin, paginas institucionales y sitios sin links de propiedad.")
    if error_families.get("timeout", 0):
        recs.append("Separar timeout de diagnostico vs timeout de extraccion y guardar etapa exacta para reintentos mas selectivos.")
    if error_families.get("strategy_quality_failed", 0):
        recs.append("Antes de importar, bloquear resultados con URLs invalidas o sin fotos reales; conservar ejemplos para mejorar extractores generales.")
    if quality_counts.get("missing_images", 0) or quality_counts.get("missing_real_image", 0):
        recs.append("Fortalecer limpieza/deteccion de imagenes reales y descartar logos, placeholders, SVGs y mapas antes de raw.")
    if quality_counts.get("missing_location", 0) or quality_counts.get("missing_address", 0):
        recs.append("Mejorar inferencia de ubicacion desde URL/titulo solo con senales fuertes; no geocodificar direcciones ambiguas.")
    if quality_counts.get("address_contaminated_text", 0) or quality_counts.get("address_contains_phone", 0):
        recs.append("Aplicar sanitizacion de direccion antes de geocoding y registrar tokens removidos como data_quality_issues.")
    if not recs:
        recs.append("Continuar con subtanda conservadora y monitoreo despues de cada cierre.")
    return recs


def scan_for_publish_attempt(report_dirs: List[Path]) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    patterns = ("scripts/publish_to_supabase.py", "PUBLISH TO SUPABASE", "run_daily_pipeline.py --commit")
    for report_dir in report_dirs:
        roots = [report_dir, report_dir.parent]
        for root in roots:
            if not root.exists():
                continue
            for path in root.glob("*.log"):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if any(pattern in text for pattern in patterns):
                    hits.append(rel(path))
    return bool(hits), hits[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate local scraping audit reports")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--prefix", default="run_all_agencies")
    args = parser.parse_args()

    state_path = args.state if args.state.is_absolute() else REPO_ROOT / args.state
    out_dir = args.out_dir if args.out_dir.is_absolute() else REPO_ROOT / args.out_dir
    state = read_json(state_path, {})
    if not isinstance(state, dict):
        raise SystemExit(f"No valid state found at {state_path}")

    results, report_dirs = load_batch_results(state)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = out_dir / f"{args.prefix}_{timestamp}"
    summary_path = unique_path(Path(str(base) + "_summary.md"))
    failures_path = unique_path(Path(str(base) + "_failures.csv"))
    quality_path = unique_path(Path(str(base) + "_quality_issues.csv"))
    missing_path = unique_path(Path(str(base) + "_missing_fields.csv"))
    suspicious_path = unique_path(Path(str(base) + "_suspicious_data.csv"))
    recommendations_path = unique_path(Path(str(base) + "_recommendations.md"))
    agency_path = unique_path(Path(str(base) + "_agency_results.csv"))

    captured_files: List[str] = []
    for result in results:
        json_rel = result.get("json_path")
        if json_rel:
            captured_files.append(resolve_path(json_rel).name)
    captured_files = sorted(set(captured_files))
    neon = fetch_neon_metrics(captured_files)
    local_quality = collect_local_quality(results)

    db_quality: List[Dict[str, Any]] = []
    agency_name_by_id = {
        str(r.get("inmobiliaria_id") or r.get("id") or ""): r.get("inmobiliaria_nombre") or ""
        for r in results
    }
    for row in neon.get("db_quality_rows") or []:
        issue_type = str(row.get("issue_type") or "")
        kind = "missing" if issue_type.startswith("missing_") else "suspicious"
        agency_id = str(row.get("inmobiliaria_id") or "")
        db_quality.append(issue_row(
            agency_id=agency_id,
            agency_name=agency_name_by_id.get(agency_id, ""),
            source_url=row.get("url"),
            property_id=row.get("captured_file"),
            title=row.get("titulo"),
            issue_kind=kind,
            issue_type=issue_type,
            field=issue_type.replace("missing_", ""),
            value=row.get("issue_detail") or "",
            severity="media",
            evidence="neon_data_quality_issues",
            recommendation="Revisar regla de importacion/validacion que genero este issue.",
            origin="neon_data_quality_issues",
        ))
    quality_rows = local_quality + db_quality
    quality_counts = Counter(str(row["issue_type"]) for row in quality_rows)

    agency_rows: List[Dict[str, Any]] = []
    failure_rows: List[Dict[str, Any]] = []
    ok_count = 0
    error_count = 0
    props_total = 0
    for result in results:
        agency_id = str(result.get("inmobiliaria_id") or result.get("id") or "")
        captured_file = resolve_path(result.get("json_path")).name if result.get("json_path") else ""
        raw_count = int(neon["raw_by_file"].get(captured_file, 0)) if neon.get("available") else ""
        staging_count = int(neon["staging_by_file"].get(captured_file, 0)) if neon.get("available") else ""
        status = "success" if result.get("success") else "error"
        if result.get("success"):
            ok_count += 1
        else:
            error_count += 1
        props = int(result.get("props") or 0)
        props_total += props
        error_type = result.get("error_type") or ""
        family = "" if status == "success" else classify_error(error_type or result.get("family_before"), result.get("error_message"))
        row = {
            "fecha_hora": datetime.now().isoformat(timespec="seconds"),
            "batch": result.get("_batch_number", ""),
            "batch_dir": result.get("_batch_dir", ""),
            "offset": result.get("_offset", ""),
            "inmobiliaria_id": agency_id,
            "nombre": result.get("inmobiliaria_nombre") or "",
            "url_web": result.get("url") or "",
            "estado_final": status,
            "success_error_skipped": status,
            "estrategia_usada": result.get("strategy") or "",
            "playwright": detect_playwright(result.get("raw_log")),
            "duracion_segundos": result.get("elapsed_seconds") or "",
            "propiedades_detectadas": props,
            "propiedades_capturadas": props,
            "propiedades_importadas_raw": raw_count,
            "propiedades_validadas_staging": staging_count,
            "cantidad_errores": 0 if status == "success" else 1,
            "error_type": error_type,
            "error_message": result.get("error_message") or "",
            "error_family": family,
            "traceback_resumido": "" if status == "success" else safe_log_excerpt(result.get("raw_log")),
            "raw_log": result.get("raw_log") or "",
            "captured_json": result.get("json_path") or "",
            "observaciones": "ok" if status == "success" else "ver failures.csv",
        }
        agency_rows.append(row)
        if status != "success":
            failure = dict(row)
            failure.update({
                "causa_probable": family,
                "corregible_pipeline_general": "si" if family in {"no_property_links", "timeout", "requires_playwright", "strategy_quality_failed", "parser_error"} else "no",
                "recomendacion": (
                    "Reintentar solo despues de mejorar clasificacion/extractor general."
                    if family in {"no_property_links", "strategy_quality_failed", "timeout"}
                    else "Dejar pausada o revisar fuente antes de reintentar."
                ),
                "reintentar_o_pausar": "pausar" if family in {"site_down", "bad_url", "blocked"} else "reintentar_con_fix_general",
            })
            failure_rows.append(failure)

    error_families = Counter(row["error_family"] for row in agency_rows if row["estado_final"] == "error")
    publish_attempt, publish_hits = scan_for_publish_attempt(report_dirs)
    processed = len(results)
    error_rate = (error_count / processed) if processed else 0.0
    raw_total = sum(neon.get("raw_by_file", Counter()).values()) if neon.get("available") else state.get("total_importadas_raw", 0)
    staging_total = sum(neon.get("staging_by_file", Counter()).values()) if neon.get("available") else state.get("total_validadas_staging", 0)
    geocoding = neon.get("geocoding", Counter()) if neon.get("available") else Counter({
        "done": int(state.get("total_geocoding_done", 0) or 0),
        "failed": int(state.get("total_geocoding_failed", 0) or 0),
        "skipped": int(state.get("total_geocoding_skipped", 0) or 0),
    })
    recommendations = build_recommendations(error_families, quality_counts, error_rate)
    decision = "pausar_corregir" if error_rate > 0.4 or state.get("hubo_corte_o_reanudacion") else "continuar_controlado"

    write_csv(agency_path, agency_rows, [
        "fecha_hora", "batch", "batch_dir", "offset", "inmobiliaria_id", "nombre", "url_web",
        "estado_final", "success_error_skipped", "estrategia_usada", "playwright", "duracion_segundos",
        "propiedades_detectadas", "propiedades_capturadas", "propiedades_importadas_raw",
        "propiedades_validadas_staging", "cantidad_errores", "error_type", "error_message",
        "error_family", "traceback_resumido", "raw_log", "captured_json", "observaciones",
    ])
    write_csv(failures_path, failure_rows, [
        "fecha_hora", "batch", "batch_dir", "offset", "inmobiliaria_id", "nombre", "url_web",
        "estado_final", "error_type", "error_message", "traceback_resumido", "estrategia_usada",
        "playwright", "duracion_segundos", "propiedades_detectadas", "causa_probable",
        "error_family", "corregible_pipeline_general", "recomendacion", "reintentar_o_pausar", "raw_log",
    ])
    write_csv(quality_path, quality_rows, [
        "batch", "inmobiliaria_id", "inmobiliaria_nombre", "url_origen", "propiedad_id_o_externo",
        "titulo_propiedad", "issue_kind", "issue_type", "campo", "valor_detectado", "severidad",
        "evidencia", "recomendacion", "origen",
    ])

    summary = f"""# Scraping run audit

Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Alcance

- Estado fuente: `{rel(state_path)}`
- CSV actual: `{state.get('batch_actual_csv')}`
- Reportes fuente: {len(report_dirs)}
- Offset actual: {state.get('offset_actual')}
- Total URLs corregibles del CSV actual: {state.get('total_urls_batch_corregibles')}
- Decision: **{decision}**

## Seguridad

- no_publica_supabase: {str(not publish_attempt).lower()}
- no_publish_to_supabase: {str(not publish_attempt).lower()}
- no_run_daily_pipeline_commit: {str(not publish_attempt).lower()}
- no_toca_publish_queue_commit: true
- no_frontend: true
- no_env_write: true
- publish_attempt_hits: {len(publish_hits)}

## Resumen general

- inmobiliarias_procesadas: {processed}
- success: {ok_count}
- error: {error_count}
- skipped/no_procesables: 0
- tasa_error: {error_rate:.1%}
- propiedades_detectadas/capturadas: {props_total}
- raw_neon: {raw_total}
- staging_neon: {staging_total}
- geocoding_done: {geocoding.get('done', 0)}
- geocoding_failed: {geocoding.get('failed', 0)}
- geocoding_skipped: {geocoding.get('skipped', 0)}
- geocoding_pending: {geocoding.get('pending', 0)}

## Resumen por tanda

"""
    for item in state.get("offsets_completados") or []:
        summary += (
            f"- offset {item.get('offset')} | urls {item.get('urls')} | ok {item.get('ok')} | "
            f"error {item.get('errors')} | props {item.get('props_capturadas')} | "
            f"raw {item.get('raw_imported', '')} | staging {item.get('staged', '')} | "
            f"reporte `{item.get('report_dir')}`\n"
        )
    summary += f"""
## Familias de error

{render_counts(error_families)}

## Campos faltantes / issues principales

{render_counts(quality_counts, limit=40)}

## Estados operativos

- scraping_run_items: {dict(neon.get('scraping_item_status', {}))}
- publish_queue: {dict(neon.get('publish_queue_status', {}))}
- neon_read_available: {neon.get('available')}
- neon_read_error: {neon.get('error') or ''}

## Archivos generados

- Agency results CSV: `{rel(agency_path)}`
- Failures CSV: `{rel(failures_path)}`
- Quality issues CSV: `{rel(quality_path)}`
- Recommendations MD: `{rel(recommendations_path)}`
"""
    summary_path.write_text(summary, encoding="utf-8")

    rec_text = f"""# Scraping recommendations

Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Decision

**{decision}**

La corrida no debe escalar a tandas grandes en el estado actual si se mantiene la tasa de error de {error_rate:.1%}.

## Recomendaciones prioritarias

"""
    rec_text += "\n".join(f"- {item}" for item in recommendations)
    rec_text += f"""

## Corregibles por pipeline general

- no_property_links / sin_propiedades: preclasificacion de fuente, mejor deteccion de listados reales y salto temprano.
- timeout: separar etapa exacta y reintento selectivo con presupuesto controlado.
- strategy_quality_failed: endurecer validacion pre-import y conservar ejemplos para mejorar extractores.
- missing_images / missing_real_image: filtro de imagen real y fallback por detalle.
- missing_location / address_contaminated_text: sanitizacion de direccion y geocoding solo si readiness es seguro.

## No conviene reintentar por ahora

- site_down, blocked, bad_url e invalid_source hasta confirmar URL activa o fuente real.

## Siguiente corrida segura sugerida

Mantener una subtanda chica en foreground solo despues de aplicar filtros generales:

```powershell
.\\.venv\\Scripts\\python.exe scripts\\run_scraping_autofix_continuous.py --commit --batch-csv "{state.get('batch_actual_csv')}" --resume --workers 2 --timeout-seconds 180 --limit 25 --max-subtandas 1 --max-batches 1 --geocode-limit 100 --geocode-max-requests 10 --max-geocode-iterations 2
```

No usar `publish_to_supabase.py`, no usar `run_daily_pipeline.py --commit`, no usar `build_publish_queue.py --commit`.
"""
    recommendations_path.write_text(rec_text, encoding="utf-8")

    print("=" * 72)
    print("SCRAPING RUN AUDIT REPORTS")
    print(f"summary={summary_path}")
    print(f"agency_results={agency_path}")
    print(f"failures={failures_path}")
    print(f"quality_issues={quality_path}")
    print(f"recommendations={recommendations_path}")
    print(f"decision={decision}")
    print(f"processed={processed}")
    print(f"ok={ok_count}")
    print(f"errors={error_count}")
    print(f"error_rate={error_rate:.3f}")
    print(f"publish_attempt_hits={len(publish_hits)}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

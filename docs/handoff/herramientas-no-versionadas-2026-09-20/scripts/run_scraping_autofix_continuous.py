#!/usr/bin/env python
"""Orquestador reanudable para scraping autofix seguro.

Garantias:
- No modifica .env.
- No publica en Supabase.
- No toca publish_queue.
- No ejecuta publish_to_supabase.py ni run_daily_pipeline.py.
- Usa scraper solo por la ruta segura --test-url + --dump-props-json.
- Persiste estado local para poder reanudar despues de cortes.
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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
REPORT_ROOT = REPO_ROOT / "reports" / "scraping_autofix"
RUN_REPORT_ROOT = REPO_ROOT / "reports" / "scraping_runs"
DATA_ROOT = REPO_ROOT / "data" / "scraping_batches"
STATE_PATH = REPORT_ROOT / "autofix_state.json"
RESUME_PATH = REPORT_ROOT / "autofix_resume.md"
MASTER_PATH = REPORT_ROOT / "master_progress.md"
PROGRESS_MD_PATH = RUN_REPORT_ROOT / "progress_every_2h.md"
PROGRESS_CSV_PATH = RUN_REPORT_ROOT / "progress_every_2h.csv"
PROGRESS_INTERVAL_SECONDS = 2 * 60 * 60
NON_CODE_FAMILIES = {"blocked", "site_down", "site_down_confirmed"}

RE_INT = re.compile(r"([a-zA-Z_]+)[=:]\s*(\d+)")
RE_REPORT_INPUT = re.compile(r"- Input:\s+`([^`]+)`")
RE_REPORT_CAPTURE = re.compile(r"- Capture dir:\s+`([^`]+)`")
RE_REPORT_EXEC = re.compile(r"- Ejecutadas:\s+(\d+)")
RE_REPORT_OK = re.compile(r"- OK:\s+(\d+)")
RE_REPORT_ERROR = re.compile(r"- Error:\s+(\d+)")
RE_REPORT_PROPS = re.compile(r"- Propiedades capturadas:\s+(\d+)")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except Exception:
        return str(path)


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_master(text: str) -> None:
    MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = MASTER_PATH.read_text(encoding="utf-8", errors="ignore") if MASTER_PATH.exists() else "# Scraping autofix master progress\n"
        MASTER_PATH.write_text(current.rstrip() + "\n\n" + text.strip() + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"warning: no pude actualizar master_progress.md: {exc}", file=sys.stderr)


def local_now() -> datetime:
    return datetime.now().astimezone()


def parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()


def format_datetime(value: datetime) -> str:
    offset = value.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return f"{value.strftime('%Y-%m-%d %H:%M:%S')} {offset}".strip()


def format_hours(hours: float) -> str:
    if hours <= 0:
        return "0h 00m"
    total_minutes = int(round(hours * 60))
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def latest_progress_time() -> Optional[datetime]:
    if not PROGRESS_CSV_PATH.exists():
        return None
    try:
        last: Optional[Dict[str, str]] = None
        with PROGRESS_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                last = row
        return parse_datetime(last.get("fecha_hora")) if last else None
    except OSError:
        return None


def progress_metrics(state: Dict[str, Any], stop_reason: str = "") -> Dict[str, Any]:
    now = local_now()
    started = parse_datetime(state.get("fecha_inicio")) or now
    elapsed_hours = max((now - started).total_seconds() / 3600, 0.01)
    total = int(state.get("total_urls_batch_corregibles") or state.get("total_urls_batch") or 0)
    processed = int(state.get("total_urls_procesadas") or 0)
    pending = max(total - processed, 0)
    success = int(state.get("total_ok") or 0)
    error = int(state.get("total_error") or 0)
    skipped = int(state.get("total_skipped") or state.get("total_no_procesables") or 0)
    props = int(state.get("total_props_capturadas") or 0)
    avg_agencies = processed / elapsed_hours
    avg_props = props / elapsed_hours
    last = state.get("ultima_subtanda_completada") or {}
    last_speed = float(last.get("speed_urls_per_hour") or 0)
    eta_hours = pending / avg_agencies if avg_agencies > 0 else 0
    finish = now + timedelta(hours=eta_hours) if eta_hours else None
    error_rate = error / max(processed, 1)
    reliability = "aproximada_baja" if processed < 100 or error_rate > 0.4 else "aproximada"
    derived_stop = stop_reason
    if not derived_stop and not state.get("proceso_en_curso") and pending > 0:
        derived_stop = f"estado={state.get('estado_actual')}; siguiente={state.get('siguiente_accion')}"
    variation = (
        "Puede variar por timeouts, sitios lentos, Playwright, errores de conexion, "
        "URLs malas, tandas con fuentes sin listado real y pausas entre subtandas."
    )
    return {
        "fecha_hora": format_datetime(now),
        "inicio_operativo": format_datetime(started),
        "elapsed_horas": round(elapsed_hours, 2),
        "elapsed_legible": format_hours(elapsed_hours),
        "total_estimadas": total,
        "procesadas": processed,
        "pendientes_estimadas": pending,
        "success": success,
        "error": error,
        "skipped_no_procesables": skipped,
        "props_capturadas": props,
        "promedio_inmobiliarias_hora": round(avg_agencies, 1),
        "promedio_props_hora": round(avg_props, 1),
        "velocidad_ultima_tanda_hora": round(last_speed, 1),
        "eta_horas": round(eta_hours, 1),
        "eta_legible": format_hours(eta_hours),
        "hora_estimada_finalizacion": format_datetime(finish) if finish else "",
        "estimacion_confiable": reliability,
        "motivo_variacion": variation,
        "motivo_freno": derived_stop,
        "ultima_tanda": Path(str(last.get("report_dir") or "")).name if last else "",
        "offset_actual": int(state.get("offset_actual") or 0),
        "recomendacion": (
            "Continuar con subtandas controladas, workers 2, timeout 180s, "
            "y revisar la tasa de error antes de escalar."
        ),
    }


def append_progress_csv(metrics: Dict[str, Any]) -> None:
    RUN_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    fields = [
        "fecha_hora",
        "inicio_operativo",
        "elapsed_horas",
        "total_estimadas",
        "procesadas",
        "pendientes_estimadas",
        "success",
        "error",
        "skipped_no_procesables",
        "props_capturadas",
        "promedio_inmobiliarias_hora",
        "promedio_props_hora",
        "velocidad_ultima_tanda_hora",
        "eta_horas",
        "hora_estimada_finalizacion",
        "estimacion_confiable",
        "motivo_variacion",
        "motivo_freno",
        "ultima_tanda",
        "offset_actual",
        "recomendacion",
    ]
    write_header = not PROGRESS_CSV_PATH.exists() or PROGRESS_CSV_PATH.stat().st_size == 0
    with PROGRESS_CSV_PATH.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(metrics)


def append_progress_markdown(metrics: Dict[str, Any]) -> None:
    RUN_REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    header = "# Progress every 2h - scraping run\n\n"
    if PROGRESS_MD_PATH.exists():
        current = PROGRESS_MD_PATH.read_text(encoding="utf-8", errors="ignore").rstrip()
    else:
        current = (
            header
            + "Este archivo registra avances periodicos de la corrida progresiva de scraping. "
            + "No reemplaza los reportes por tanda; funciona como bitacora de velocidad, ETA y estado de reanudacion."
        )
    section = f"""

## {metrics['fecha_hora']}

### Estado general

- Tiempo total transcurrido: `{metrics['elapsed_legible']}`
- Inmobiliarias/URLs totales estimadas a procesar: `{metrics['total_estimadas']}`
- Inmobiliarias/URLs ya procesadas: `{metrics['procesadas']}`
- Inmobiliarias/URLs pendientes estimadas: `{metrics['pendientes_estimadas']}`
- Success: `{metrics['success']}`
- Error: `{metrics['error']}`
- Skipped/no procesables: `{metrics['skipped_no_procesables']}`
- Propiedades capturadas: `{metrics['props_capturadas']}`
- Ultima tanda: `{metrics['ultima_tanda'] or 'sin_tanda_cerrada'}`
- Offset actual: `{metrics['offset_actual']}`

### Velocidad y ETA

- Promedio de inmobiliarias procesadas por hora: `{metrics['promedio_inmobiliarias_hora']}`
- Promedio de propiedades capturadas por hora: `{metrics['promedio_props_hora']}`
- Velocidad de la ultima tanda: `{metrics['velocidad_ultima_tanda_hora']}` inmobiliarias/hora
- Tiempo estimado restante: `{metrics['eta_legible']}`
- Hora estimada de finalizacion: `{metrics['hora_estimada_finalizacion'] or 'sin estimacion'}`
- Confiabilidad de la estimacion: `{metrics['estimacion_confiable']}`
- Motivo de variacion: {metrics['motivo_variacion']}

### Freno / reanudacion

- Motivo de freno si aplica: {metrics['motivo_freno'] or 'no aplica'}
- Recomendacion: {metrics['recomendacion']}

### Seguridad

- No se publica a Supabase.
- No se ejecuta `publish_to_supabase.py`.
- No se ejecuta `run_daily_pipeline.py --commit`.
- No se toca `publish_queue` con commit.
- No se toca `.env`.
- No se toca `frontend/`.
- No se hace commit.
- No se hace push.
"""
    PROGRESS_MD_PATH.write_text(current + section, encoding="utf-8")


def write_progress_report(state: Dict[str, Any], force: bool = False, stop_reason: str = "") -> None:
    last = latest_progress_time()
    now = local_now()
    due = last is None or (now - last).total_seconds() >= PROGRESS_INTERVAL_SECONDS
    if not force and not due:
        return
    metrics = progress_metrics(state, stop_reason=stop_reason)
    append_progress_csv(metrics)
    append_progress_markdown(metrics)


def csv_rows(path: Path, include_non_code: bool = True) -> List[Dict[str, str]]:
    csv.field_size_limit(1024 * 1024 * 64)
    rows: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        for raw in csv.DictReader(fh):
            url = (raw.get("url") or raw.get("url_listado") or raw.get("web") or "").strip()
            if not url:
                continue
            family = (raw.get("error_type") or "").strip()
            if not include_non_code and family in NON_CODE_FAMILIES:
                continue
            row = dict(raw)
            row["url"] = url
            rows.append(row)
    return rows


def find_url_offset(csv_path: Path, first_url: str) -> Optional[int]:
    target = normalize_url_key(first_url)
    if not target:
        return None
    for idx, row in enumerate(csv_rows(csv_path, include_non_code=False)):
        if normalize_url_key(row.get("url") or "") == target:
            return idx
    return None


def normalize_url_key(url: str) -> str:
    return (url or "").strip().lower().rstrip("/")


def parse_batch_report(report_path: Path) -> Dict[str, Any]:
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    out: Dict[str, Any] = {
        "report_dir": rel(report_path.parent),
        "report_path": rel(report_path),
    }
    for key, regex in [
        ("input", RE_REPORT_INPUT),
        ("capture_dir", RE_REPORT_CAPTURE),
        ("urls", RE_REPORT_EXEC),
        ("ok", RE_REPORT_OK),
        ("errors", RE_REPORT_ERROR),
        ("props_captured", RE_REPORT_PROPS),
    ]:
        match = regex.search(text)
        if match:
            value = match.group(1)
            out[key] = int(value) if value.isdigit() else value
    results_path = report_path.parent / "batch_results.json"
    results = read_json(results_path, [])
    if isinstance(results, list) and results:
        out["first_url"] = results[0].get("url") or ""
        out["last_url"] = results[-1].get("url") or ""
        out["result_count"] = len(results)
        out["ok"] = sum(1 for item in results if item.get("success"))
        out["errors"] = sum(1 for item in results if not item.get("success"))
        out["props_captured"] = sum(int(item.get("props") or 0) for item in results if item.get("success"))
    if out.get("input") and out.get("first_url"):
        csv_path = resolve_path(out["input"])
        if csv_path.exists():
            offset = find_url_offset(csv_path, out["first_url"])
            if offset is not None:
                out["offset"] = offset
    out["completed_report_exists"] = (REPORT_ROOT / f"{report_path.parent.name}_after.md").exists()
    out.update(parse_pipeline_metrics(report_path.parent))
    return out


def parse_pipeline_metrics(report_dir: Path) -> Dict[str, int]:
    metrics = {
        "raw_imported": 0,
        "staged": 0,
        "geo_done": 0,
        "geo_failed": 0,
        "geo_skipped": 0,
    }
    for path in sorted(report_dir.glob("import_commit*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        values = parse_markdown_section_numbers(text, "Resumen") or parse_key_numbers(text)
        metrics["raw_imported"] += values.get("importadas", 0)
    for path in sorted(report_dir.glob("validate_commit*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        values = parse_markdown_section_numbers(text, "Resumen") or parse_key_numbers(text)
        metrics["staged"] += values.get("validadas", values.get("pasaron_a_staging", 0))
    for path in sorted(report_dir.glob("geocode_commit*.md")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        values = parse_markdown_section_numbers(text, "Resultados de esta corrida")
        if not values:
            values = parse_markdown_section_numbers(text, "Resumen") or parse_key_numbers(text)
        metrics["geo_done"] += values.get("done", 0)
        metrics["geo_failed"] += values.get("failed", 0)
        metrics["geo_skipped"] += values.get("skipped", 0)
    return metrics


def completed_subbatches_for_csv(csv_path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    completed: List[Dict[str, Any]] = []
    partial: List[Dict[str, Any]] = []
    for report in sorted(REPORT_ROOT.glob("batch_*/batch_report.md")):
        info = parse_batch_report(report)
        if not info.get("input"):
            continue
        if resolve_path(info["input"]).resolve() != csv_path.resolve():
            continue
        target = completed if info.get("completed_report_exists") else partial
        target.append(info)
    completed.sort(key=lambda item: int(item.get("offset", 0)))
    partial.sort(key=lambda item: int(item.get("offset", 0)))
    return completed, partial


def latest_exported_csv() -> Optional[Path]:
    candidates = sorted(DATA_ROOT.glob("batch_*automation_1000*.csv"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def reconstruct_state(seed_csv: Optional[Path] = None) -> Dict[str, Any]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    csv_path = seed_csv or latest_exported_csv()
    if not csv_path:
        return initial_state(None)
    csv_path = csv_path.resolve()
    all_rows = csv_rows(csv_path, include_non_code=True)
    code_rows = csv_rows(csv_path, include_non_code=False)
    completed, partial = completed_subbatches_for_csv(csv_path)
    completed_offsets: List[Dict[str, Any]] = []
    totals = Counter()
    for item in completed:
        offset = int(item.get("offset", 0))
        urls = int(item.get("urls", item.get("result_count", 0)) or 0)
        completed_offsets.append(
            {
                "offset": offset,
                "limit": urls,
                "urls": urls,
                "ok": int(item.get("ok", 0) or 0),
                "errors": int(item.get("errors", 0) or 0),
                "props_capturadas": int(item.get("props_captured", 0) or 0),
                "report_dir": item.get("report_dir"),
            }
        )
        totals["urls"] += urls
        totals["ok"] += int(item.get("ok", 0) or 0)
        totals["errors"] += int(item.get("errors", 0) or 0)
        totals["props"] += int(item.get("props_captured", 0) or 0)
        totals["raw"] += int(item.get("raw_imported", 0) or 0)
        totals["staged"] += int(item.get("staged", 0) or 0)
        totals["geo_done"] += int(item.get("geo_done", 0) or 0)
        totals["geo_failed"] += int(item.get("geo_failed", 0) or 0)
        totals["geo_skipped"] += int(item.get("geo_skipped", 0) or 0)

    partial_current = partial[-1] if partial else None
    if partial_current and partial_current.get("offset") is not None:
        offset_actual = int(partial_current["offset"])
        estado_actual = "subtanda_parcial_detectada"
        siguiente = "reanudar_subtanda_parcial"
    else:
        offset_actual = next_offset_from_completed(completed_offsets)
        estado_actual = "listo_para_siguiente_subtanda"
        siguiente = "procesar_siguiente_subtanda" if offset_actual < len(code_rows) else "exportar_siguiente_tanda"

    state = initial_state(csv_path)
    state.update(
        {
            "batch_actual_csv": rel(csv_path),
            "batch_numero": infer_batch_number(csv_path),
            "export_offset": infer_export_offset(csv_path),
            "total_urls_batch": len(all_rows),
            "total_urls_batch_corregibles": len(code_rows),
            "offset_actual": offset_actual,
            "offsets_completados": completed_offsets,
            "offsets_pendientes": pending_offsets(offset_actual, len(code_rows), 100),
            "ultima_subtanda_iniciada": subbatch_pointer(partial_current) if partial_current else None,
            "ultima_subtanda_completada": completed_offsets[-1] if completed_offsets else None,
            "estado_actual": estado_actual,
            "total_urls_procesadas": int(totals["urls"]),
            "total_ok": int(totals["ok"]),
            "total_error": int(totals["errors"]),
            "total_props_capturadas": int(totals["props"]),
            "total_importadas_raw": int(totals["raw"]),
            "total_validadas_staging": int(totals["staged"]),
            "total_geocoding_done": int(totals["geo_done"]),
            "total_geocoding_failed": int(totals["geo_failed"]),
            "total_geocoding_skipped": int(totals["geo_skipped"]),
            "proceso_en_curso": bool(partial_current),
            "hubo_corte_o_reanudacion": bool(partial_current),
            "siguiente_accion": siguiente,
            "fecha_ultima_actualizacion": now_iso(),
        }
    )
    if partial_current:
        state["subtanda_parcial"] = subbatch_pointer(partial_current)
    return state


def initial_state(csv_path: Optional[Path]) -> Dict[str, Any]:
    created = now_iso()
    return {
        "batch_actual_csv": rel(csv_path) if csv_path else None,
        "batch_numero": 1,
        "total_urls_batch": 0,
        "total_urls_batch_corregibles": 0,
        "offset_actual": 0,
        "offsets_completados": [],
        "offsets_pendientes": [],
        "ultima_subtanda_iniciada": None,
        "ultima_subtanda_completada": None,
        "estado_actual": "inicializado",
        "total_urls_procesadas": 0,
        "total_ok": 0,
        "total_error": 0,
        "total_props_capturadas": 0,
        "total_importadas_raw": 0,
        "total_validadas_staging": 0,
        "total_geocoding_done": 0,
        "total_geocoding_failed": 0,
        "total_geocoding_skipped": 0,
        "fecha_inicio": created,
        "fecha_ultima_actualizacion": created,
        "proceso_en_curso": False,
        "hubo_corte_o_reanudacion": False,
        "siguiente_accion": "reconstruir_estado",
        "seguridad": safety_flags(),
    }


def safety_flags() -> Dict[str, bool]:
    return {
        "no_toca_env": True,
        "no_borra_datos": True,
        "no_publica_supabase": True,
        "no_toca_publish_queue": True,
        "no_publish_to_supabase": True,
        "no_run_daily_pipeline_commit": True,
        "no_commit_git": True,
        "no_push_git": True,
    }


def infer_batch_number(csv_path: Path) -> int:
    candidates = sorted(DATA_ROOT.glob("batch_*automation_1000*.csv"), key=lambda p: p.stat().st_mtime)
    for idx, item in enumerate(candidates, 1):
        if item.resolve() == csv_path.resolve():
            return idx
    return max(1, len(candidates))


def infer_export_offset(csv_path: Path) -> int:
    match = re.search(r"offset(\d+)", csv_path.name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0


def next_offset_from_completed(completed: List[Dict[str, Any]]) -> int:
    if not completed:
        return 0
    return max(int(item.get("offset", 0)) + int(item.get("urls", 0)) for item in completed)


def pending_offsets(start: int, total: int, limit: int) -> List[Dict[str, int]]:
    out: List[Dict[str, int]] = []
    current = start
    while current < total:
        size = min(limit, total - current)
        out.append({"offset": current, "limit": size})
        current += size
    return out


def subbatch_pointer(info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "offset": int(info.get("offset", 0) or 0),
        "urls": int(info.get("urls", info.get("result_count", 0)) or 0),
        "report_dir": info.get("report_dir"),
        "capture_dir": info.get("capture_dir"),
        "ok": int(info.get("ok", 0) or 0),
        "errors": int(info.get("errors", 0) or 0),
        "props_capturadas": int(info.get("props_captured", 0) or 0),
    }


def write_resume(state: Dict[str, Any]) -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    pending = state.get("offsets_pendientes") or []
    completed = state.get("offsets_completados") or []
    partial = state.get("subtanda_parcial")
    next_command = build_next_command(state)
    text = f"""# Autofix Resume

Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Estado

- CSV actual: `{state.get('batch_actual_csv')}`
- Batch numero: {state.get('batch_numero')}
- Total URLs batch: {state.get('total_urls_batch')}
- Total URLs corregibles: {state.get('total_urls_batch_corregibles')}
- Offset actual: {state.get('offset_actual')}
- Estado actual: {state.get('estado_actual')}
- Proceso en curso: {state.get('proceso_en_curso')}
- Hubo corte/reanudacion: {state.get('hubo_corte_o_reanudacion')}
- Siguiente accion: {state.get('siguiente_accion')}

## Completado

- Subtandas cerradas: {len(completed)}
- URLs procesadas: {state.get('total_urls_procesadas')}
- OK: {state.get('total_ok')}
- Errores: {state.get('total_error')}
- Propiedades capturadas: {state.get('total_props_capturadas')}
- Importadas raw acumuladas: {state.get('total_importadas_raw')}
- Validadas staging acumuladas: {state.get('total_validadas_staging')}
- Geocoding done/failed/skipped acumulado: {state.get('total_geocoding_done')}/{state.get('total_geocoding_failed')}/{state.get('total_geocoding_skipped')}

## Subtanda parcial

{json.dumps(partial, ensure_ascii=False, indent=2) if partial else 'No hay subtanda parcial detectada.'}

## Pendiente

- Subtandas pendientes del batch actual: {len(pending)}
- Proximos offsets: {', '.join(str(item.get('offset')) for item in pending[:10]) or 'none'}
- Estimacion: {len(pending)} subtandas restantes en este CSV corregible; luego exportar siguiente tanda.

## Proximo comando seguro

```powershell
{next_command}
```

## Riesgos / pendientes

- El export read-only puede devolver errores recientes ya trabajados si Supabase no se marca resuelto; se usa offset de exportacion para avanzar pagina.
- Las direcciones ambiguas o contaminadas se marcan skipped; no se inventan coordenadas.
- Importacion y validacion son idempotentes por hash_dedup/duplicados.

## Confirmacion de seguridad

- no .env
- no borrado
- no commit
- no push
- no publicacion Supabase
- no publish_queue
- no publish_to_supabase.py
- no run_daily_pipeline.py --commit
- no cambios destructivos
"""
    RESUME_PATH.write_text(text, encoding="utf-8")


def build_next_command(state: Dict[str, Any]) -> str:
    csv_value = state.get("batch_actual_csv") or ""
    return (
        f".\\.venv\\Scripts\\python.exe scripts\\run_scraping_autofix_continuous.py "
        f"--commit --batch-csv \"{csv_value}\" --resume --workers 2 --timeout-seconds 180"
    )


STALE_LOCK_TIMEOUT_HOURS = 4


def is_pid_alive(pid: int) -> bool:
    """Cross-platform PID liveness check."""
    if not pid:
        return False
    pid = int(pid)
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            return str(pid) in (result.stdout or "")
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ProcessLookupError):
            return False


def check_and_clear_stale_lock(state: Dict[str, Any]) -> bool:
    """If proceso_en_curso=True but the owning PID is dead, clear the flag.

    Returns True when the lock was cleared (stale). The caller should
    save_state() afterwards to persist the change.
    """
    if not state.get("proceso_en_curso"):
        return False
    pid = state.get("proceso_pid")
    if pid and is_pid_alive(int(pid)):
        return False  # Process alive — lock is legitimate
    started_info = state.get("ultima_subtanda_iniciada") or {}
    started_at = parse_datetime(started_info.get("started_at"))
    age_hours = ((local_now() - started_at).total_seconds() / 3600) if started_at else 999
    # Be conservative: if PID exists but very recent (<4h), skip
    if pid and age_hours < STALE_LOCK_TIMEOUT_HOURS:
        return False
    print(
        f"warning: proceso_en_curso=True stale "
        f"(pid={pid or 'ninguno'}, edad={age_hours:.1f}h). Limpiando lock.",
        file=sys.stderr,
    )
    state["proceso_en_curso"] = False
    state["hubo_corte_o_reanudacion"] = True
    state["estado_actual"] = "lock_stale_limpiado"
    state["siguiente_accion"] = "retomar_subtanda_pendiente"
    return True


def save_state(state: Dict[str, Any]) -> None:
    state["fecha_ultima_actualizacion"] = now_iso()
    state["proceso_pid"] = os.getpid()
    state["seguridad"] = safety_flags()
    atomic_write_json(STATE_PATH, state)
    write_resume(state)
    try:
        write_progress_report(state)
    except OSError as exc:
        print(f"warning: no pude actualizar progress_every_2h: {exc}", file=sys.stderr)


def kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, check=False)
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_child(cmd: List[str], log_path: Path, timeout: int, env_extra: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    started = time.time()
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_process_tree(proc)
        stdout, stderr = proc.communicate()
    elapsed = round(time.time() - started, 1)
    text = (
        f"CMD: {' '.join(cmd)}\n"
        f"returncode={proc.returncode}\n"
        f"timed_out={timed_out}\n"
        f"elapsed_seconds={elapsed}\n\n"
        f"=== STDOUT ===\n{stdout or ''}\n\n=== STDERR ===\n{stderr or ''}\n"
    )
    log_path.write_text(text, encoding="utf-8")
    if timed_out and proc.returncode == 0:
        return 124, text
    return int(proc.returncode or 0), text


def parse_key_numbers(text: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip().lstrip("- ")
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        else:
            continue
        key = key.strip()
        raw = value.strip().split()[0] if value.strip() else ""
        if raw.isdigit():
            out[key] = int(raw)
    return out


def parse_markdown_section_numbers(text: str, header: str) -> Dict[str, int]:
    marker = f"## {header}"
    start = text.find(marker)
    if start < 0:
        return {}
    rest = text[start + len(marker):]
    next_header = rest.find("\n## ")
    if next_header >= 0:
        rest = rest[:next_header]
    return parse_key_numbers(rest)


def latest_internal_batch_dir() -> Optional[Path]:
    candidates = sorted(DATA_ROOT.glob("internal_batch_*"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def latest_batch_report_dir() -> Optional[Path]:
    candidates = sorted([p for p in REPORT_ROOT.glob("batch_*") if p.is_dir()], key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def next_sequence_index(report_dir: Path, prefix: str) -> int:
    highest = 0
    for path in report_dir.glob(f"{prefix}_*.md"):
        match = re.search(r"_(\d+)\.md$", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def run_scraping_subbatch(state: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    csv_path = resolve_path(state["batch_actual_csv"])
    offset = int(state["offset_actual"])
    limit = min(args.limit, max(0, int(state.get("total_urls_batch_corregibles", 0)) - offset))
    if limit <= 0:
        state["estado_actual"] = "batch_actual_sin_subtandas_pendientes"
        state["siguiente_accion"] = "exportar_siguiente_tanda"
        save_state(state)
        return {}

    state["proceso_en_curso"] = True
    state["estado_actual"] = "scraping_subtanda"
    state["ultima_subtanda_iniciada"] = {"offset": offset, "limit": limit, "started_at": now_iso()}
    state["siguiente_accion"] = "esperar_scraping"
    save_state(state)

    log_path = REPORT_ROOT / f"autofix_subtanda_{now_stamp()}_scrape.log"
    # No se habilitan flags de Playwright/API globalmente.
    # El batch runner clasifica cada URL por carril y decide per-URL.
    cmd = [
        PYTHON,
        "scripts/run_internal_scraping_batch.py",
        "--input",
        rel(csv_path),
        "--offset",
        str(offset),
        "--limit",
        str(limit),
        "--workers",
        str(args.workers),
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--allow-static-detail",
    ]
    code, text = run_child(cmd, log_path, timeout=args.scraper_timeout)
    if code != 0:
        state["estado_actual"] = "scraping_subtanda_error"
        state["siguiente_accion"] = "reintentar_o_marcar_pendiente_manual"
        state["ultimo_error"] = text[-1000:]
        save_state(state)
        raise RuntimeError(f"Fallo scraping subtanda, ver {log_path}")

    report_dir = latest_batch_report_dir()
    capture_dir = latest_internal_batch_dir()
    if not report_dir or not capture_dir:
        raise RuntimeError("No pude detectar report_dir/capture_dir despues del scraping")
    info = parse_batch_report(report_dir / "batch_report.md")
    state["ultima_subtanda_iniciada"].update(subbatch_pointer(info))
    state["ultima_subtanda_iniciada"]["capture_dir"] = rel(capture_dir / "captured")
    state["estado_actual"] = "scraping_subtanda_completo"
    state["siguiente_accion"] = "importar_capturas"
    save_state(state)
    return {"report_dir": report_dir, "capture_dir": capture_dir / "captured", "info": info}


def import_captures(state: Dict[str, Any], args: argparse.Namespace, capture_dir: Path, report_dir: Path) -> int:
    state["estado_actual"] = "importando_raw"
    state["siguiente_accion"] = "importar_capturas_en_lotes"
    save_state(state)
    env = {"USE_INTERNAL_DB": "true"}
    dry_report = report_dir / "import_dry_run.md"
    batch_csv = state.get("batch_actual_csv")
    cmd = [PYTHON, "scripts/import_captured_props_to_neon.py", "--input-dir", rel(capture_dir)]
    if batch_csv:
        cmd.extend(["--batch-csv", str(batch_csv)])
    cmd.extend(["--report", rel(dry_report), "--dry-run"])
    code, text = run_child(cmd, report_dir / "autofix_import_dry_run.log", timeout=args.step_timeout, env_extra=env)
    if code != 0:
        raise RuntimeError(f"Fallo dry-run import: {text[-1000:]}")
    numbers = parse_key_numbers(text)
    detected = int(numbers.get("propiedades_detectadas", 0))
    importable = int(numbers.get("importables", numbers.get("importable", 0)))
    inserted_total = 0
    if importable <= 0:
        existing = parse_pipeline_metrics(report_dir)
        state["estado_actual"] = "importacion_raw_sin_pendientes"
        state["siguiente_accion"] = "validar_raw"
        save_state(state)
        return int(existing.get("raw_imported", 0))
    if not args.commit:
        return 0
    for offset in range(0, detected, args.import_chunk):
        limit = min(args.import_chunk, detected - offset)
        label = f"{offset:04d}_{offset + limit:04d}"
        report = report_dir / f"import_commit_slice_{label}.md"
        cmd = [
            PYTHON,
            "scripts/import_captured_props_to_neon.py",
            "--input-dir",
            rel(capture_dir),
        ]
        if batch_csv:
            cmd.extend(["--batch-csv", str(batch_csv)])
        cmd.extend([
            "--offset",
            str(offset),
            "--limit",
            str(limit),
            "--report",
            rel(report),
            "--commit",
        ])
        code, text = run_child(cmd, report_dir / f"autofix_import_commit_slice_{label}.log", timeout=args.step_timeout, env_extra=env)
        if code != 0:
            raise RuntimeError(f"Fallo import commit slice {offset}-{offset + limit}: {text[-1000:]}")
        inserted_total += parse_key_numbers(text).get("importadas", 0)
    state["total_importadas_raw"] = int(state.get("total_importadas_raw", 0)) + inserted_total
    state["estado_actual"] = "importacion_raw_completa"
    state["siguiente_accion"] = "validar_raw"
    save_state(state)
    return inserted_total


def validate_raw(state: Dict[str, Any], args: argparse.Namespace, report_dir: Path) -> int:
    state["estado_actual"] = "validando_raw"
    state["siguiente_accion"] = "validar_raw_en_lotes"
    save_state(state)
    env = {"USE_INTERNAL_DB": "true"}
    total = 0
    if not args.commit:
        report = report_dir / "validate_dry_run.md"
        cmd = [PYTHON, "scripts/validate_raw_properties.py", "--source", "captured_json", "--limit", str(args.validate_limit), "--report", rel(report), "--dry-run"]
        code, text = run_child(cmd, report_dir / "autofix_validate_dry_run.log", timeout=args.step_timeout, env_extra=env)
        if code != 0:
            raise RuntimeError(f"Fallo validate dry-run: {text[-1000:]}")
        return 0
    start_idx = next_sequence_index(report_dir, "validate_commit")
    for idx in range(start_idx, start_idx + args.max_validate_iterations):
        label = f"{idx:02d}"
        report = report_dir / f"validate_commit_{label}.md"
        cmd = [PYTHON, "scripts/validate_raw_properties.py", "--source", "captured_json", "--limit", str(args.validate_limit), "--report", rel(report), "--commit"]
        code, text = run_child(cmd, report_dir / f"autofix_validate_commit_{label}.log", timeout=args.step_timeout, env_extra=env)
        if code != 0:
            raise RuntimeError(f"Fallo validate commit {idx}: {text[-1000:]}")
        nums = parse_key_numbers(text)
        read = nums.get("filas_leidas", 0)
        valid = nums.get("validadas", 0)
        total += valid
        if read == 0 or valid == 0:
            break
    existing = parse_pipeline_metrics(report_dir)
    if total == 0 and existing.get("staged"):
        total = int(existing["staged"])
    state["total_validadas_staging"] = int(state.get("total_validadas_staging", 0)) + total
    state["estado_actual"] = "validacion_staging_completa"
    state["siguiente_accion"] = "geocodificar_staging"
    save_state(state)
    return total


def geocode_staging(state: Dict[str, Any], args: argparse.Namespace, report_dir: Path) -> Dict[str, int]:
    state["estado_actual"] = "geocoding_en_curso"
    state["siguiente_accion"] = "geocoding_acotado"
    save_state(state)
    env = {"USE_INTERNAL_DB": "true"}
    totals = Counter()
    if not args.commit:
        report = report_dir / "geocode_dry_run.md"
        cmd = [
            PYTHON,
            "scripts/geocode_staging.py",
            "--source",
            "captured_json",
            "--limit",
            str(args.geocode_limit),
            "--max-requests",
            str(args.geocode_max_requests),
            "--report",
            rel(report),
            "--dry-run",
        ]
        code, text = run_child(cmd, report_dir / "autofix_geocode_dry_run.log", timeout=args.step_timeout, env_extra=env)
        if code != 0:
            raise RuntimeError(f"Fallo geocode dry-run: {text[-1000:]}")
        return dict(totals)
    start_idx = next_sequence_index(report_dir, "geocode_commit")
    for idx in range(start_idx, start_idx + args.max_geocode_iterations):
        label = f"{idx:02d}"
        report = report_dir / f"geocode_commit_{label}.md"
        cmd = [
            PYTHON,
            "scripts/geocode_staging.py",
            "--source",
            "captured_json",
            "--limit",
            str(args.geocode_limit),
            "--max-requests",
            str(args.geocode_max_requests),
            "--report",
            rel(report),
            "--commit",
        ]
        code, text = run_child(cmd, report_dir / f"autofix_geocode_commit_{label}.log", timeout=args.step_timeout, env_extra=env)
        if code != 0:
            raise RuntimeError(f"Fallo geocode commit {idx}: {text[-1000:]}")
        nums = parse_key_numbers(text)
        read = nums.get("filas_leidas", 0)
        totals["done"] += nums.get("done", 0)
        totals["failed"] += nums.get("failed", 0)
        totals["skipped"] += nums.get("skipped", 0)
        if read == 0:
            break
    state["total_geocoding_done"] = int(state.get("total_geocoding_done", 0)) + totals["done"]
    state["total_geocoding_failed"] = int(state.get("total_geocoding_failed", 0)) + totals["failed"]
    state["total_geocoding_skipped"] = int(state.get("total_geocoding_skipped", 0)) + totals["skipped"]
    state["estado_actual"] = "geocoding_completo"
    state["siguiente_accion"] = "cerrar_subtanda"
    save_state(state)
    return dict(totals)


def write_subbatch_reports(state: Dict[str, Any], report_dir: Path, metrics: Dict[str, Any]) -> None:
    name = report_dir.name
    safety = "\n".join(f"- {key}: {value}" for key, value in safety_flags().items())
    families = metrics.get("families") or {}
    family_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(families.items())) or "- none: 0"
    after = f"""# {name} after

- CSV: `{state.get('batch_actual_csv')}`
- Offset: {metrics.get('offset')}
- URLs procesadas: {metrics.get('urls')}
- OK: {metrics.get('ok')}
- Errores: {metrics.get('errors')}
- Propiedades capturadas: {metrics.get('props_captured')}
- Importadas raw: {metrics.get('raw_imported')}
- Validadas staging: {metrics.get('staged')}
- Geocoding done/skipped/failed: {metrics.get('geo_done')}/{metrics.get('geo_skipped')}/{metrics.get('geo_failed')}

## Seguridad

{safety}
"""
    before = f"""# {name} before

- CSV: `{state.get('batch_actual_csv')}`
- Offset: {metrics.get('offset')}
- Workers: 2
- Timeout por URL: 180s
- Ruta: --test-url + --dump-props-json + Neon raw/staging + geocoding acotado.
"""
    fixed = f"""# {name} fixed

- Subtanda cerrada con estado persistente.
- Importacion idempotente por `hash_dedup`.
- Geocoding acotado, sin publicar Supabase.
"""
    remaining = f"""# {name} remaining

## Familias restantes

{family_lines}

## Proxima accion

{state.get('siguiente_accion')}
"""
    errors = f"""# {name} errors

{family_lines}
"""
    (REPORT_ROOT / f"{name}_before.md").write_text(before, encoding="utf-8")
    (REPORT_ROOT / f"{name}_after.md").write_text(after, encoding="utf-8")
    (REPORT_ROOT / f"{name}_fixed.md").write_text(fixed, encoding="utf-8")
    (REPORT_ROOT / f"{name}_remaining.md").write_text(remaining, encoding="utf-8")
    (REPORT_ROOT / f"{name}_errors.md").write_text(errors, encoding="utf-8")
    status_path = REPORT_ROOT / f"status_{now_stamp()}.md"
    status_path.write_text(after + "\n\n" + remaining, encoding="utf-8")


def close_subbatch(state: Dict[str, Any], report_dir: Path, raw_imported: int, staged: int, geo: Dict[str, int]) -> None:
    info = parse_batch_report(report_dir / "batch_report.md")
    pipeline = parse_pipeline_metrics(report_dir)
    raw_imported = int(pipeline.get("raw_imported") or raw_imported or 0)
    staged = int(pipeline.get("staged") or staged or 0)
    geo = {
        "done": int(pipeline.get("geo_done") or geo.get("done", 0) or 0),
        "failed": int(pipeline.get("geo_failed") or geo.get("failed", 0) or 0),
        "skipped": int(pipeline.get("geo_skipped") or geo.get("skipped", 0) or 0),
    }
    offset = int(info.get("offset", state.get("offset_actual", 0)) or 0)
    urls = int(info.get("urls", info.get("result_count", 0)) or 0)
    started_at = (state.get("ultima_subtanda_iniciada") or {}).get("started_at")
    finished_at = now_iso()
    started_dt = parse_datetime(started_at)
    finished_dt = parse_datetime(finished_at) or local_now()
    duration_seconds = max((finished_dt - started_dt).total_seconds(), 0.0) if started_dt else 0.0
    speed_urls_per_hour = (urls / (duration_seconds / 3600)) if duration_seconds > 0 else 0.0
    metrics = {
        "offset": offset,
        "urls": urls,
        "ok": int(info.get("ok", 0) or 0),
        "errors": int(info.get("errors", 0) or 0),
        "props_captured": int(info.get("props_captured", 0) or 0),
        "raw_imported": raw_imported,
        "staged": staged,
        "geo_done": int(geo.get("done", 0)),
        "geo_failed": int(geo.get("failed", 0)),
        "geo_skipped": int(geo.get("skipped", 0)),
        "families": families_from_results(report_dir / "batch_results.json"),
    }
    completed_item = {
        "offset": offset,
        "limit": urls,
        "urls": urls,
        "ok": metrics["ok"],
        "errors": metrics["errors"],
        "props_capturadas": metrics["props_captured"],
        "raw_imported": raw_imported,
        "staged": staged,
        "geo_done": metrics["geo_done"],
        "geo_failed": metrics["geo_failed"],
        "geo_skipped": metrics["geo_skipped"],
        "report_dir": rel(report_dir),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 1),
        "speed_urls_per_hour": round(speed_urls_per_hour, 1),
    }
    state["offsets_completados"].append(completed_item)
    state["ultima_subtanda_completada"] = state["offsets_completados"][-1]
    state["ultima_subtanda_iniciada"] = None
    state.pop("subtanda_parcial", None)
    state["offset_actual"] = offset + urls
    state["offsets_pendientes"] = pending_offsets(
        int(state["offset_actual"]),
        int(state.get("total_urls_batch_corregibles", 0)),
        100,
    )
    state["proceso_en_curso"] = False
    state["estado_actual"] = "subtanda_completada"
    state["siguiente_accion"] = (
        "procesar_siguiente_subtanda"
        if int(state["offset_actual"]) < int(state.get("total_urls_batch_corregibles", 0))
        else "exportar_siguiente_tanda"
    )
    recompute_state_totals(state)
    write_subbatch_reports(state, report_dir, metrics)
    append_master(
        f"""## {datetime.now().strftime('%Y-%m-%d %H:%M')} - {report_dir.name}

- CSV: `{state.get('batch_actual_csv')}`
- Offset cerrado: {offset}
- URLs: {urls}, OK: {metrics['ok']}, errores: {metrics['errors']}, capturadas: {metrics['props_captured']}.
- Raw: {raw_imported}, staging: {staged}, geocoding done/skipped/failed: {metrics['geo_done']}/{metrics['geo_skipped']}/{metrics['geo_failed']}.
- Seguridad: no .env, no borrado, no commit, no push, no Supabase publish, no publish_queue.
"""
    )
    save_state(state)


def recompute_state_totals(state: Dict[str, Any]) -> None:
    totals = Counter()
    for item in state.get("offsets_completados") or []:
        totals["urls"] += int(item.get("urls", 0) or 0)
        totals["ok"] += int(item.get("ok", 0) or 0)
        totals["errors"] += int(item.get("errors", 0) or 0)
        totals["props"] += int(item.get("props_capturadas", 0) or 0)
        pipeline = parse_pipeline_metrics(resolve_path(item["report_dir"])) if item.get("report_dir") else {}
        totals["raw"] += int(item.get("raw_imported", pipeline.get("raw_imported", 0)) or 0)
        totals["staged"] += int(item.get("staged", pipeline.get("staged", 0)) or 0)
        totals["geo_done"] += int(item.get("geo_done", pipeline.get("geo_done", 0)) or 0)
        totals["geo_failed"] += int(item.get("geo_failed", pipeline.get("geo_failed", 0)) or 0)
        totals["geo_skipped"] += int(item.get("geo_skipped", pipeline.get("geo_skipped", 0)) or 0)
    state["total_urls_procesadas"] = int(totals["urls"])
    state["total_ok"] = int(totals["ok"])
    state["total_error"] = int(totals["errors"])
    state["total_props_capturadas"] = int(totals["props"])
    state["total_importadas_raw"] = int(totals["raw"])
    state["total_validadas_staging"] = int(totals["staged"])
    state["total_geocoding_done"] = int(totals["geo_done"])
    state["total_geocoding_failed"] = int(totals["geo_failed"])
    state["total_geocoding_skipped"] = int(totals["geo_skipped"])


def families_from_results(path: Path) -> Dict[str, int]:
    results = read_json(path, [])
    families = Counter()
    if isinstance(results, list):
        for item in results:
            key = "ok" if item.get("success") else (item.get("error_type") or item.get("family_before") or "sin_clasificar")
            families[str(key)] += 1
    return dict(families)


def export_next_batch(state: Dict[str, Any], args: argparse.Namespace) -> Optional[Path]:
    state["estado_actual"] = "exportando_siguiente_tanda"
    state["siguiente_accion"] = "export_read_only_supabase"
    save_state(state)
    offset = int(state.get("export_offset", 0))
    if offset == 0:
        # Si venimos de una tanda ya procesada, avanzar por paginas de 1000
        offset = max(0, (int(state.get("batch_numero", 1)) - 1) * 1000)
    out = DATA_ROOT / f"batch_{now_stamp()}_auto_{int(state.get('batch_numero', 1)) + 1}.csv"
    cmd = [
        PYTHON,
        "scripts/export_scraping_errors.py",
        "--max",
        "1000",
        "--offset",
        str(offset + 1000),
        "--dedup-url",
        "--out",
        rel(out),
    ]
    code, text = run_child(cmd, REPORT_ROOT / f"autofix_export_{now_stamp()}.log", timeout=args.step_timeout)
    if code != 0:
        state["estado_actual"] = "export_error"
        state["ultimo_error"] = text[-1000:]
        save_state(state)
        raise RuntimeError("Fallo export read-only")
    if not out.exists() or not csv_rows(out, include_non_code=True):
        state["estado_actual"] = "sin_mas_tandas_exportadas"
        state["siguiente_accion"] = "generar_reporte_global_final"
        save_state(state)
        return None
    new_state = reconstruct_state(out)
    new_state["fecha_inicio"] = state.get("fecha_inicio") or now_iso()
    new_state["batch_numero"] = int(state.get("batch_numero", 1)) + 1
    new_state["export_offset"] = offset + 1000
    save_state(new_state)
    return out


def process_one_subbatch(state: Dict[str, Any], args: argparse.Namespace) -> None:
    partial = state.get("subtanda_parcial")
    if partial:
        report_dir = resolve_path(partial["report_dir"])
        capture_dir = resolve_path(partial["capture_dir"])
        info = parse_batch_report(report_dir / "batch_report.md")
        state["estado_actual"] = "reanudando_subtanda_parcial"
        state["hubo_corte_o_reanudacion"] = True
        save_state(state)
    else:
        run = run_scraping_subbatch(state, args)
        if not run:
            return
        report_dir = run["report_dir"]
        capture_dir = run["capture_dir"]
        info = run["info"]

    raw_imported = import_captures(state, args, capture_dir, report_dir)
    staged = validate_raw(state, args, report_dir)
    geo = geocode_staging(state, args, report_dir)
    close_subbatch(state, report_dir, raw_imported, staged, geo)


def main() -> int:
    parser = argparse.ArgumentParser(description="Autofix continuo reanudable y seguro")
    parser.add_argument("--batch-csv", type=Path, default=None, help="CSV actual; si falta usa ultimo CSV exportado")
    parser.add_argument("--resume", action="store_true", help="Leer/reconstruir estado y continuar")
    parser.add_argument("--reconstruct-only", action="store_true", help="Solo reconstruye estado y resume markdown")
    parser.add_argument("--dry-run", action="store_true", help="No escribir en Neon ni ejecutar scraping; solo estado/plan")
    parser.add_argument("--commit", action="store_true", help="Ejecutar ruta segura con escrituras solo en Neon interno")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--scraper-timeout", type=int, default=7200)
    parser.add_argument("--step-timeout", type=int, default=1800)
    parser.add_argument("--import-chunk", type=int, default=500)
    parser.add_argument("--validate-limit", type=int, default=1000)
    parser.add_argument("--geocode-limit", type=int, default=1000)
    parser.add_argument("--geocode-max-requests", type=int, default=30)
    parser.add_argument("--max-validate-iterations", type=int, default=20)
    parser.add_argument("--max-geocode-iterations", type=int, default=50)
    parser.add_argument("--max-subtandas", type=int, default=1, help="0 = hasta agotar batch actual")
    parser.add_argument("--max-batches", type=int, default=1, help="0 = continuar exportando hasta agotar")
    args = parser.parse_args()

    if args.workers > 2:
        raise SystemExit("Por seguridad, este orquestador no sube workers por encima de 2.")
    if args.dry_run and args.commit:
        raise SystemExit("Usar --dry-run o --commit, no ambos.")
    if not args.dry_run and not args.commit:
        args.dry_run = True

    state = read_json(STATE_PATH, None) if args.resume else None
    if not isinstance(state, dict) or args.batch_csv:
        state = reconstruct_state(resolve_path(args.batch_csv) if args.batch_csv else None)
    check_and_clear_stale_lock(state)
    save_state(state)

    if args.reconstruct_only or args.dry_run:
        print(f"state={STATE_PATH}")
        print(f"resume={RESUME_PATH}")
        print(f"estado_actual={state.get('estado_actual')}")
        print(f"siguiente_accion={state.get('siguiente_accion')}")
        write_progress_report(
            state,
            force=not PROGRESS_CSV_PATH.exists(),
            stop_reason="dry_run_plan" if args.dry_run else "reconstruct_only",
        )
        return 0

    batches_done = 0
    while True:
        subtandas_done = 0
        while int(state.get("offset_actual", 0)) < int(state.get("total_urls_batch_corregibles", 0)) or state.get("subtanda_parcial"):
            process_one_subbatch(state, args)
            state = read_json(STATE_PATH, state)
            subtandas_done += 1
            if args.max_subtandas and subtandas_done >= args.max_subtandas:
                write_progress_report(state, force=True, stop_reason="limite_subtandas_alcanzado")
                return 0
        batches_done += 1
        final_path = REPORT_ROOT / f"final_batch_{now_stamp()}.md"
        final_path.write_text(render_batch_final(state), encoding="utf-8")
        if args.max_batches and batches_done >= args.max_batches:
            write_progress_report(state, force=True, stop_reason="limite_batches_alcanzado")
            return 0
        next_csv = export_next_batch(state, args)
        if not next_csv:
            global_path = REPORT_ROOT / f"global_final_report_{now_stamp()}.md"
            global_path.write_text(render_global_final(state), encoding="utf-8")
            write_progress_report(state, force=True, stop_reason="sin_mas_tandas_exportadas")
            return 0
        state = read_json(STATE_PATH, reconstruct_state(next_csv))


def render_batch_final(state: Dict[str, Any]) -> str:
    return f"""# Final batch {now_stamp()}

- CSV: `{state.get('batch_actual_csv')}`
- URLs procesadas: {state.get('total_urls_procesadas')}
- OK: {state.get('total_ok')}
- Errores: {state.get('total_error')}
- Propiedades capturadas: {state.get('total_props_capturadas')}
- Raw: {state.get('total_importadas_raw')}
- Staging: {state.get('total_validadas_staging')}
- Geocoding done/failed/skipped: {state.get('total_geocoding_done')}/{state.get('total_geocoding_failed')}/{state.get('total_geocoding_skipped')}

Seguridad: no Supabase publish, no publish_queue, no commit, no push.
"""


def render_global_final(state: Dict[str, Any]) -> str:
    return f"""# Global final report {now_stamp()}

No se exportaron mas tandas corregibles desde la pagina configurada.

- Ultimo CSV: `{state.get('batch_actual_csv')}`
- Total URLs procesadas acumuladas en estado: {state.get('total_urls_procesadas')}
- Total OK: {state.get('total_ok')}
- Total errores: {state.get('total_error')}
- Total raw: {state.get('total_importadas_raw')}
- Total staging: {state.get('total_validadas_staging')}
- Geocoding done/failed/skipped: {state.get('total_geocoding_done')}/{state.get('total_geocoding_failed')}/{state.get('total_geocoding_skipped')}

Restantes esperados: sitios caidos, bloqueados, URL mala, fuente invalida o pendientes de autorizacion.
"""


if __name__ == "__main__":
    raise SystemExit(main())

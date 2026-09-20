#!/usr/bin/env python
"""Genera un reporte detallado de fallos a partir de batch_results.json.

Lee los resultados de una o varias sub-tandas y genera el informe de fallos
detallado que requiere el seguimiento de la corrida controlada, incluyendo:
- Lista completa de fallos individuales con causa probable y recomendaciones
- Agrupacion por familia de error
- Top errores repetidos
- Clasificacion corregible/fix-especifico/no-reintentar
- Resumen general y por tanda

No escribe en Supabase ni en Neon. Solo lee archivos locales.

Uso:
    python scripts/generate_batch_failure_report.py --run-dir reports/scraping_autofix/batch_20260604_1200
    python scripts/generate_batch_failure_report.py --all       # todos los batch_results.json existentes
    python scripts/generate_batch_failure_report.py --all --since 20260604
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = REPO_ROOT / "reports" / "scraping_autofix"
RUNS_ROOT = REPO_ROOT / "reports" / "scraping_runs"

# ---------------------------------------------------------------------------
# Clasificación de familias de error
# ---------------------------------------------------------------------------
FAMILY_META: Dict[str, Dict[str, Any]] = {
    "item_timeout": {
        "causa": "La URL tardó más del timeout configurado en responder o completar el scraping.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Aumentar timeout o habilitar playwright si el sitio usa JS pesado.",
    },
    "timeout": {
        "causa": "Timeout de red o de paso de paginación dentro del scraper.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Reintentar con --allow-playwright o aumentar timeout.",
    },
    "requires_playwright": {
        "causa": "El sitio carga propiedades por JS y no es accesible sin renderizado.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Reintentar con --allow-playwright habilitado.",
    },
    "no_property_links": {
        "causa": "No se encontraron enlaces a propiedades en la URL de listado.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Revisar si la URL de listado es correcta o si el CMS necesita estrategia específica.",
    },
    "no_property_links_confirmed": {
        "causa": "Confirmado: la URL no tiene enlaces de propiedades con ninguna estrategia probada.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Actualizar url_listado en Supabase o marcar la inmobiliaria como inactiva.",
    },
    "strategy_quality_failed": {
        "causa": "La estrategia encontró URLs pero no capturó propiedades con calidad suficiente.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Revisar extractor del CMS detectado. Puede mejorar con ajustes de pipeline.",
    },
    "bad_url": {
        "causa": "La URL de listado es inválida, tiene redirect roto o no responde.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Corregir url_listado en Supabase.",
    },
    "invalid_source": {
        "causa": "La fuente de datos no es compatible con las estrategias disponibles.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Revisar si la inmobiliaria usa un CMS no soportado o cambió su plataforma.",
    },
    "parser_error": {
        "causa": "Error al parsear el HTML o JSON de la respuesta.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Revisar si el sitio cambió su estructura HTML. Puede necesitar actualizar el extractor.",
    },
    "network_error": {
        "causa": "Error de red: conexión rechazada, DNS, o HTTP inesperado.",
        "corregible_pipeline": False,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Reintentar en otro momento. Si persiste, verificar si el sitio sigue activo.",
    },
    "nav_error": {
        "causa": "Error de navegación (redirect roto, SSL, 404, etc.).",
        "corregible_pipeline": False,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Verificar si la URL sigue activa y si el certificado SSL es válido.",
    },
    "site_down": {
        "causa": "El sitio no responde o está caído.",
        "corregible_pipeline": False,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Reintentar en otro momento. No intentar en corridas masivas.",
    },
    "site_down_confirmed": {
        "causa": "Confirmado que el sitio está permanentemente caído o ya no existe.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Marcar la inmobiliaria como inactiva en Supabase.",
    },
    "blocked": {
        "causa": "El sitio bloquea activamente el scraper (Cloudflare, WAF, captcha, etc.).",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Evaluar uso de proxy o ScraperAPI. No procesar en masa por ahora.",
    },
    "sin_propiedades": {
        "causa": "El scraper no encontró propiedades en la URL.",
        "corregible_pipeline": False,
        "fix_especifico": True,
        "reintentar": False,
        "recomendacion": "Verificar si la URL de listado sigue teniendo propiedades activas.",
    },
    "geocoding_error": {
        "causa": "Error al geocodificar la dirección de la propiedad.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": True,
        "recomendacion": "Mejorar normalización de dirección o lógica de geocoding.",
    },
    "validation_error": {
        "causa": "La propiedad no pasó las validaciones de datos mínimos.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": False,
        "recomendacion": "Revisar reglas de validación. La propiedad puede tener datos insuficientes.",
    },
    "missing_location": {
        "causa": "La propiedad no tiene ubicación procesable.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": False,
        "recomendacion": "Mejorar extracción de dirección/barrio/ciudad en el scraper.",
    },
    "missing_price": {
        "causa": "La propiedad no tiene precio.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": False,
        "recomendacion": "Mejorar extracción de precio en el scraper para este CMS.",
    },
    "missing_images": {
        "causa": "La propiedad no tiene imágenes.",
        "corregible_pipeline": True,
        "fix_especifico": False,
        "reintentar": False,
        "recomendacion": "Mejorar extracción de imágenes en el scraper para este CMS.",
    },
}

OTRO_META = {
    "causa": "Error no clasificado. Revisar error_message y raw_log para diagnóstico.",
    "corregible_pipeline": False,
    "fix_especifico": True,
    "reintentar": False,
    "recomendacion": "Revisar el log individual y clasificar manualmente.",
}


def get_family_meta(error_type: Optional[str]) -> Dict[str, Any]:
    if not error_type:
        return OTRO_META
    return FAMILY_META.get(error_type, OTRO_META)


def slugify_family(family: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", (family or "otro").lower()).strip("_") or "otro"


def detect_playwright(raw_log_path: Optional[str]) -> Optional[bool]:
    if not raw_log_path:
        return None
    path = REPO_ROOT / raw_log_path
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return "playwright" in text.lower() or "chromium" in text.lower()
    except Exception:
        return None


def load_results(run_dir: Path) -> Tuple[List[Dict[str, Any]], str]:
    results_path = run_dir / "batch_results.json"
    if not results_path.exists():
        return [], ""
    try:
        data = json.loads(results_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return [], ""
    if not isinstance(data, list):
        return [], ""
    timestamp = run_dir.name.replace("batch_", "")
    return data, timestamp


def classify_item(item: Dict[str, Any], tanda_num: int, tanda_ts: str) -> Dict[str, Any]:
    error_type = item.get("error_type") or item.get("family_before") or ""
    meta = get_family_meta(error_type)
    playwright_used = detect_playwright(item.get("raw_log"))
    return {
        "fecha_hora": tanda_ts,
        "tanda": tanda_num,
        "inmobiliaria_id": item.get("inmobiliaria_id") or "",
        "nombre": item.get("inmobiliaria_nombre") or "",
        "url": item.get("url") or "",
        "estado_final": "success" if item.get("success") else "error",
        "error_type": error_type or "sin_clasificar",
        "error_message": (item.get("error_message") or "")[:300],
        "estrategia": item.get("strategy") or "",
        "playwright": playwright_used,
        "duracion_segundos": item.get("elapsed_seconds"),
        "props_detectadas": item.get("props", 0),
        "causa_probable": meta["causa"],
        "familia": error_type or "sin_clasificar",
        "corregible_pipeline": meta["corregible_pipeline"],
        "fix_especifico": meta["fix_especifico"],
        "reintentar": meta["reintentar"],
        "recomendacion": meta["recomendacion"],
        "raw_log": item.get("raw_log") or "",
    }


def render_report(
    all_results: List[Tuple[int, str, List[Dict[str, Any]]]],
    run_label: str,
    out_path: Path,
) -> None:
    all_items: List[Dict[str, Any]] = []
    tanda_summaries: List[Dict[str, Any]] = []

    for tanda_num, tanda_ts, results in all_results:
        ok = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]
        props = sum(int(r.get("props", 0)) for r in ok)
        tanda_summaries.append({
            "tanda": tanda_num,
            "ts": tanda_ts,
            "total": len(results),
            "ok": len(ok),
            "error": len(failed),
            "props": props,
        })
        for item in failed:
            classified = classify_item(item, tanda_num, tanda_ts)
            all_items.append(classified)

    # Totales
    total_procesadas = sum(s["total"] for s in tanda_summaries)
    total_ok = sum(s["ok"] for s in tanda_summaries)
    total_error = sum(s["error"] for s in tanda_summaries)
    total_props = sum(s["props"] for s in tanda_summaries)

    # Agrupaciones
    by_family: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in all_items:
        by_family[item["familia"]].append(item)
    family_counts = Counter(item["familia"] for item in all_items)
    top_errors = Counter(item["error_message"][:100] for item in all_items if item["error_message"]).most_common(15)

    corregibles = [i for i in all_items if i["corregible_pipeline"]]
    fix_especifico = [i for i in all_items if i["fix_especifico"] and not i["corregible_pipeline"]]
    no_reintentar = [i for i in all_items if not i["reintentar"]]
    reintentables = [i for i in all_items if i["reintentar"]]

    lines = [
        f"# Reporte de fallos - {run_label}",
        "",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## 1. Resumen general",
        "",
        f"- Total inmobiliarias procesadas: {total_procesadas}",
        f"- Success: {total_ok}",
        f"- Error: {total_error}",
        f"- Tasa de error: {total_error/max(total_procesadas,1)*100:.1f}%",
        f"- Propiedades capturadas (OK): {total_props}",
        f"- Tandas procesadas: {len(tanda_summaries)}",
        f"- Fallos clasificados: {len(all_items)}",
        f"  - Corregibles por pipeline: {len(corregibles)}",
        f"  - Requieren fix específico: {len(fix_especifico)}",
        f"  - Reintentables: {len(reintentables)}",
        f"  - No reintentar por ahora: {len(no_reintentar)}",
        "",
        "---",
        "",
        "## 2. Resumen por tanda",
        "",
        "| Tanda | Timestamp | Total | OK | Error | Props OK |",
        "|---|---|---|---|---|---|",
    ]
    for s in tanda_summaries:
        lines.append(
            f"| {s['tanda']} | {s['ts']} | {s['total']} | {s['ok']} | {s['error']} | {s['props']} |"
        )
    lines += [
        "",
        "---",
        "",
        "## 3. Lista completa de inmobiliarias fallidas",
        "",
    ]
    for item in all_items:
        playwright_tag = ""
        if item["playwright"] is True:
            playwright_tag = " [playwright]"
        elif item["playwright"] is False:
            playwright_tag = " [no-playwright]"
        lines.append(
            f"- **Tanda {item['tanda']}** | `{item['inmobiliaria_id']}` | {item['nombre'] or '(sin nombre)'} | "
            f"`{item['error_type']}`{playwright_tag} | {item['url']}"
        )
        if item["error_message"]:
            lines.append(f"  - Mensaje: _{item['error_message']}_")
        lines.append(f"  - Causa: {item['causa_probable']}")
        lines.append(f"  - Rec: {item['recomendacion']}")
    lines += [
        "",
        "---",
        "",
        "## 4. Fallos agrupados por familia",
        "",
    ]
    for family, count in family_counts.most_common():
        meta = get_family_meta(family)
        items_in_family = by_family[family]
        lines += [
            f"### {family} ({count} inmobiliarias)",
            "",
            f"- Causa: {meta['causa']}",
            f"- Corregible por pipeline: {'sí' if meta['corregible_pipeline'] else 'no'}",
            f"- Requiere fix específico: {'sí' if meta['fix_especifico'] else 'no'}",
            f"- Se puede reintentar: {'sí' if meta['reintentar'] else 'no'}",
            f"- Recomendación: {meta['recomendacion']}",
            "",
            "Inmobiliarias:",
        ]
        for item in items_in_family[:30]:
            lines.append(f"  - `{item['inmobiliaria_id']}` | {item['nombre'] or '(sin nombre)'} | {item['url']}")
        if len(items_in_family) > 30:
            lines.append(f"  - ... {len(items_in_family) - 30} más")
        lines.append("")
    lines += [
        "---",
        "",
        "## 5. Top errores más repetidos",
        "",
    ]
    for msg, count in top_errors:
        lines.append(f"- ({count}x) `{msg}`")
    lines += [
        "",
        "---",
        "",
        "## 6. Errores corregibles desde pipeline",
        "",
        "Estas familias pueden mejorar con ajustes de scraper o estrategia, sin cambios manuales por inmobiliaria:",
        "",
    ]
    for family, count in family_counts.most_common():
        if get_family_meta(family)["corregible_pipeline"]:
            lines.append(f"- **{family}** ({count}): {get_family_meta(family)['recomendacion']}")
    lines += [
        "",
        "---",
        "",
        "## 7. Errores que requieren fix específico",
        "",
        "Requieren acción manual por inmobiliaria (corregir URL, marcar inactiva, etc.):",
        "",
    ]
    for item in fix_especifico[:50]:
        lines.append(
            f"- `{item['inmobiliaria_id']}` | {item['nombre'] or '(sin nombre)'} | "
            f"`{item['error_type']}` | {item['url']}"
        )
    if len(fix_especifico) > 50:
        lines.append(f"- ... {len(fix_especifico) - 50} más (ver batch_results.json)")
    lines += [
        "",
        "---",
        "",
        "## 8. Errores que no conviene reintentar por ahora",
        "",
    ]
    no_reintentar_by_family = Counter(i["familia"] for i in no_reintentar)
    for family, count in no_reintentar_by_family.most_common():
        lines.append(f"- **{family}** ({count}): {get_family_meta(family)['recomendacion']}")
    lines += [
        "",
        "---",
        "",
        "## 9. Recomendaciones para la siguiente corrida",
        "",
        "Basadas en los patrones de error de esta corrida:",
        "",
    ]
    if family_counts.get("requires_playwright", 0) > 0:
        lines.append(
            f"- **{family_counts['requires_playwright']} sitios requieren Playwright**: "
            "Ya se incluye `--allow-playwright` en el orquestador. Verificar que Playwright esté instalado."
        )
    if family_counts.get("item_timeout", 0) + family_counts.get("timeout", 0) > 10:
        t_count = family_counts.get("item_timeout", 0) + family_counts.get("timeout", 0)
        lines.append(
            f"- **{t_count} timeouts**: Considerar aumentar `--timeout-seconds` (actualmente 180s). "
            "Los sitios lentos con JS pesado pueden beneficiarse de 240-300s."
        )
    if family_counts.get("blocked", 0) > 0:
        lines.append(
            f"- **{family_counts['blocked']} bloqueados**: No reintentar en masa. "
            "Evaluar soluciones de proxy o ScraperAPI para estos sitios."
        )
    if family_counts.get("site_down", 0) > 0:
        lines.append(
            f"- **{family_counts.get('site_down', 0)} sitios caídos**: "
            "Reintentar en 24-48 horas. Si persiste, marcar como inactivos."
        )
    if total_error / max(total_procesadas, 1) < 0.15:
        lines.append("- **Tasa de error baja** (<15%): Condiciones normales. Continuar con la siguiente tanda.")
    elif total_error / max(total_procesadas, 1) < 0.30:
        lines.append("- **Tasa de error moderada** (15-30%): Revisar familias dominantes antes de continuar.")
    else:
        lines.append(
            "- **Tasa de error alta** (>30%): Frenar y diagnosticar. "
            "Verificar si hay problemas de red o cambios en la mayoría de sitios."
        )
    lines += [
        "",
        "---",
        "",
        "## Confirmación de seguridad",
        "",
        "- no_toca_env: true",
        "- no_borra_datos: true",
        "- no_publica_supabase: true",
        "- no_toca_publish_queue: true",
        "- no_publish_to_supabase: true",
        "- no_run_daily_pipeline_commit: true",
        "- no_commit_git: true",
        "- no_push_git: true",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Reporte guardado: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generar reporte detallado de fallos desde batch_results.json")
    parser.add_argument("--run-dir", type=Path, default=None, help="Directorio de una sub-tanda específica")
    parser.add_argument("--all", action="store_true", help="Procesar todos los batch_results.json existentes")
    parser.add_argument("--since", default=None, help="Solo incluir directorios con timestamp >= YYYYMMDD")
    parser.add_argument("--out", type=Path, default=None, help="Ruta de salida del reporte markdown")
    args = parser.parse_args()

    if not args.run_dir and not args.all:
        raise SystemExit("Especificar --run-dir o --all")

    run_dirs: List[Path] = []
    if args.run_dir:
        run_dirs = [args.run_dir if args.run_dir.is_absolute() else REPO_ROOT / args.run_dir]
    else:
        pattern_dirs = sorted([p for p in REPORT_ROOT.glob("batch_*") if p.is_dir()])
        if args.since:
            pattern_dirs = [p for p in pattern_dirs if p.name.replace("batch_", "") >= args.since]
        run_dirs = pattern_dirs

    all_results: List[Tuple[int, str, List[Dict[str, Any]]]] = []
    for tanda_num, run_dir in enumerate(run_dirs, 1):
        results, ts = load_results(run_dir)
        if results:
            all_results.append((tanda_num, ts, results))

    if not all_results:
        raise SystemExit("No se encontraron batch_results.json con datos.")

    total_fallos = sum(1 for _, _, results in all_results for r in results if not r.get("success"))
    print(f"Sub-tandas encontradas: {len(all_results)}")
    print(f"Total fallos a clasificar: {total_fallos}")

    ts_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.out:
        out_path = args.out if args.out.is_absolute() else REPO_ROOT / args.out
    else:
        since_label = f"_desde_{args.since}" if args.since else ""
        label = run_dirs[-1].name if not args.all else f"all{since_label}"
        out_path = RUNS_ROOT / f"failure_report_{label}_{ts_label}.md"

    run_label = f"{'corrida completa' if args.all else run_dirs[-1].name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    render_report(all_results, run_label, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

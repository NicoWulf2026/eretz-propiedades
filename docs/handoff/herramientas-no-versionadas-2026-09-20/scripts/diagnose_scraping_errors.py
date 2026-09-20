"""Diagnostico de errores de scraping por FAMILIA, en tandas controladas.

Este script NO scrapea por si mismo: orquesta llamadas seguras a
`scraper/scraper_propiedades.py --test-url`, que prueba una URL puntual SIN
consumir la cola productiva y SIN escribir en Supabase ni en Neon. Agrupa las
URLs por familia de error, elige una muestra representativa, corre los tests en
procesos aislados (uno por URL) y genera reportes locales en
`reports/scraping_diagnostics/`.

Garantias de seguridad (por diseno):
  - No toca .env (solo lo lee el subproceso del scraper, como siempre).
  - No consume la cola productiva (usa --test-url).
  - No escribe en Supabase ni en Neon.
  - No corre run_daily_pipeline.py ni el pipeline completo.
  - No publica propiedades.
  - No borra datos.
  - Workers = 1 y ejecucion secuencial.

Entrada:
  CSV local (default: data/scraping_error_samples.csv) con al menos una columna
  de URL. Columnas reconocidas (flexible, case-insensitive):
    url | web | url_listado        -> URL a testear (requerida)
    error_type | error | familia   -> familia de error (opcional)
    inmobiliaria_id | id            -> id de referencia (opcional)
    nombre | inmobiliaria           -> nombre de referencia (opcional)

Salida (en --output-dir/run_<timestamp>/):
    report.json   -> resultados estructurados de toda la tanda
    report.md     -> tabla por familia + resumen
    raw/<slug>.log-> stdout/stderr crudo de cada test
    before_after.md (solo con --compare-with)

Uso tipico:
    # 1) Ver que correria, agrupado por familia, sin ejecutar nada:
    python scripts/diagnose_scraping_errors.py --dry-run --per-family 3 --limit 20

    # 2) Tanda real (sin DB, sin cola, sin publicar):
    python scripts/diagnose_scraping_errors.py --per-family 3 --limit 20 \
        --allow-playwright --timeout-seconds 300

    # 3) Retest + comparacion antes/despues:
    python scripts/diagnose_scraping_errors.py --per-family 3 --limit 20 \
        --allow-playwright --compare-with reports/scraping_diagnostics/run_<ts>
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
from collections import OrderedDict, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Raiz del proyecto (este archivo vive en scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRAPER_PATH = PROJECT_ROOT / "scraper" / "scraper_propiedades.py"
DEFAULT_INPUT = PROJECT_ROOT / "data" / "scraping_error_samples.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "reports" / "scraping_diagnostics"
csv.field_size_limit(sys.maxsize)

# Familias "de codigo" (se atacan con cambios generales en el scraper) vs.
# familias "no-codigo" (antibot / sitio caido), que conviene no testear en masa.
NON_CODE_FAMILIES = {"blocked", "site_down", "site_down_confirmed"}

# Orden de prioridad sugerido para mostrar las familias en el reporte.
FAMILY_PRIORITY = [
    "requires_playwright",
    "wordpress_ajax",
    "webpack_bundle",
    "no_property_links",
    "no_property_links_confirmed",
    "sin_propiedades",
    "timeout",
    "item_timeout",
    "static_timeout",
    "requires_network_interception",
    "strategy_quality_failed",
    "parsing_too_few_vs_expected",
    "save_failed",
    "final_url_domain_mismatch",
    "blocked",
    "site_down",
    "site_down_confirmed",
]

URL_COLS = ("url", "web", "url_listado")
FAMILY_COLS = ("error_type", "error", "familia", "family")
ID_COLS = ("inmobiliaria_id", "id")
NAME_COLS = ("nombre", "inmobiliaria", "name")


def _norm_key(s: str) -> str:
    return (s or "").strip().lower()


def _pick(row: Dict[str, str], candidates) -> str:
    """Devuelve el primer valor no vacio entre columnas candidatas (case-insensitive)."""
    lower = {_norm_key(k): v for k, v in row.items()}
    for c in candidates:
        v = lower.get(c)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _slugify(url: str, idx: int) -> str:
    s = re.sub(r"^https?://", "", url or "")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return f"{idx:03d}_{s[:60] or 'url'}"


def export_samples_from_supabase(
    output_path: Path,
    limit: int,
    status_filter: str,
    timeout_seconds: int = 30,
) -> int:
    """Exporta una muestra de errores desde Supabase a CSV. SOLO LECTURA.

    Reglas de seguridad (estrictas):
      - Unico metodo HTTP: GET (jamas POST/PATCH/DELETE).
      - SIN count=exact ni Prefer: count (no se manda ese header).
      - limit obligatorio y acotado (cap defensivo).
      - No escribe en Supabase ni en Neon. No consume cola. No corre pipeline.
      - Si no puede leer de forma segura, lanza SystemExit SIN escribir el CSV.

    Campos minimos exportados: url (url_listado||web), error_type,
    inmobiliaria_id, nombre (inmobiliaria_nombre), status, id.
    """
    # Cap defensivo: evita consultas pesadas aunque se pida un limit alto.
    if limit <= 0:
        raise SystemExit("--export-limit debe ser > 0")
    if limit > 1000:
        raise SystemExit("--export-limit excede el tope seguro de 1000. Bajalo.")

    try:
        import requests  # import perezoso: el modo offline/dry-run no lo necesita
        from dotenv import load_dotenv
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Faltan dependencias para exportar (requests/python-dotenv): {exc}")

    # Lee credenciales del .env SIN modificarlo.
    load_dotenv(str(PROJECT_ROOT / ".env"))
    supabase_url = (os.environ.get("SUPABASE_URL", "") or "").rstrip("/")
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or os.environ.get("SUPABASE_KEY", "")
    )
    if not supabase_url or not supabase_key:
        raise SystemExit(
            "No se pudo leer SUPABASE_URL / SUPABASE_KEY del entorno (.env). "
            "Exportacion abortada sin tocar nada."
        )

    headers = {  # NOTA: sin 'Prefer: count=...' a proposito (consulta liviana)
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }
    select_cols = "id,inmobiliaria_id,inmobiliaria_nombre,web,url_listado,error_type,status"
    params = {
        "select": select_cols,
        "status": f"eq.{status_filter}",
        "order": "id.desc",
        "limit": str(limit),
    }
    endpoint = f"{supabase_url}/rest/v1/scraping_run_items"

    try:
        resp = requests.get(endpoint, headers=headers, params=params, timeout=timeout_seconds)
    except Exception as exc:
        raise SystemExit(f"Fallo la lectura segura desde Supabase: {exc}. No se escribio nada.")
    if resp.status_code != 200:
        raise SystemExit(
            f"Supabase respondio status={resp.status_code} (esperado 200). "
            f"No se escribio nada. Detalle: {resp.text[:300]}"
        )
    try:
        data = resp.json()
    except Exception as exc:
        raise SystemExit(f"Respuesta no-JSON desde Supabase: {exc}. No se escribio nada.")
    if not isinstance(data, list):
        raise SystemExit(f"Respuesta inesperada desde Supabase (no es lista). No se escribio nada.")
    if not data:
        raise SystemExit(
            f"La consulta status=eq.{status_filter} no devolvio filas. "
            "No se sobrescribe el CSV existente."
        )

    rows_out: List[Dict[str, str]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        url = (row.get("url_listado") or row.get("web") or "").strip()
        if not url:
            continue
        rows_out.append({
            "url": url,
            "error_type": str(row.get("error_type") or "desconocido"),
            "inmobiliaria_id": str(row.get("inmobiliaria_id") or ""),
            "nombre": str(row.get("inmobiliaria_nombre") or ""),
            "status": str(row.get("status") or ""),
            "id": str(row.get("id") or ""),
        })
    if not rows_out:
        raise SystemExit("Ninguna fila tenia URL utilizable (url_listado/web). No se escribio nada.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["url", "error_type", "inmobiliaria_id", "nombre", "status", "id"]
        )
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"[export] {len(rows_out)} fila(s) escritas en {output_path} (solo lectura, sin count).")
    return len(rows_out)


def read_samples(input_path: Path) -> List[Dict[str, str]]:
    """Lee el CSV de muestra. No toca la red ni la DB."""
    if not input_path.exists():
        raise SystemExit(
            f"No existe el archivo de entrada: {input_path}\n"
            "Crealo con columnas: url[,error_type][,inmobiliaria_id][,nombre]\n"
            "Ejemplo de cabecera: url,error_type,inmobiliaria_id,nombre"
        )
    rows: List[Dict[str, str]] = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            url = _pick(raw, URL_COLS)
            if not url:
                continue
            rows.append({
                "url": url,
                "error_type": _pick(raw, FAMILY_COLS) or "desconocido",
                "inmobiliaria_id": _pick(raw, ID_COLS),
                "nombre": _pick(raw, NAME_COLS),
            })
    if not rows:
        raise SystemExit(f"El archivo {input_path} no tiene filas con URL valida.")
    return rows


def group_and_sample(
    rows: List[Dict[str, str]],
    per_family: int,
    limit: int,
    families_filter: Optional[List[str]],
    include_non_code: bool,
) -> "OrderedDict[str, List[Dict[str, str]]]":
    """Agrupa por familia y elige hasta `per_family` por familia, con tope `limit`."""
    by_family: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        fam = _norm_key(r["error_type"]) or "desconocido"
        if families_filter and fam not in families_filter:
            continue
        if not include_non_code and fam in NON_CODE_FAMILIES:
            continue
        by_family[fam].append(r)

    # Orden: prioridad conocida primero, luego alfabetico.
    def fam_sort_key(fam: str):
        try:
            return (0, FAMILY_PRIORITY.index(fam))
        except ValueError:
            return (1, fam)

    ordered = OrderedDict()
    total = 0
    for fam in sorted(by_family.keys(), key=fam_sort_key):
        if total >= limit:
            break
        chosen = by_family[fam][:per_family]
        if total + len(chosen) > limit:
            chosen = chosen[: max(0, limit - total)]
        if chosen:
            ordered[fam] = chosen
            total += len(chosen)
    return ordered


# --- Parseo del stdout de --test-url -------------------------------------------------

RE_STRATEGY = re.compile(r"Estrategia usada:\s*(.+)")
RE_PROPS = re.compile(r"Propiedades detectadas:\s*(\d+)")
RE_ERROR = re.compile(r"TEST URL ERROR \(([^)]+)\):\s*(.+)")
RE_META = re.compile(r"Metadata:\s*(\{.*)")


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def parse_test_output(stdout: str, stderr: str) -> Dict[str, Any]:
    """Extrae datos estructurados del log de --test-url (best-effort).

    El scraper emite sus logs por STDERR (logging), no por STDOUT, asi que
    hay que combinar ambos para no perder estrategia/props/error_final.
    """
    text = ((stdout or "") + "\n" + (stderr or "")).strip()
    res: Dict[str, Any] = {
        "estrategia": None,
        "propiedades": 0,
        "cards": 0,
        "property_links": 0,
        "error_final": None,
        "error_msg": None,
        "clasificacion": None,
    }

    m = RE_STRATEGY.search(text)
    if m:
        res["estrategia"] = m.group(1).strip()
    m = RE_PROPS.search(text)
    if m:
        res["propiedades"] = _safe_int(m.group(1))
    m = RE_ERROR.search(text)
    if m:
        res["error_final"] = m.group(1).strip()
        res["error_msg"] = m.group(2).strip()[:300]

    # Metadata JSON (puede venir truncado a ~3000 chars -> parseo defensivo)
    meta: Dict[str, Any] = {}
    m = RE_META.search(text)
    if m:
        blob = m.group(1).strip()
        try:
            meta = json.loads(blob)
        except Exception:
            meta = {}
    if meta:
        res["clasificacion"] = (
            (meta.get("diagnostico_inicial") or {}).get("classification")
            if isinstance(meta.get("diagnostico_inicial"), dict)
            else meta.get("classification")
        )
        diag = meta.get("playwright_html_render_diagnostics") or {}
        if isinstance(diag, dict):
            res["cards"] = _safe_int(diag.get("cards_count"))
            res["property_links"] = _safe_int(diag.get("property_links_count"))

    # Fallback por regex si el JSON estaba truncado
    if not res["cards"]:
        mm = re.search(r'"cards_count"\s*:\s*(\d+)', text)
        if mm:
            res["cards"] = _safe_int(mm.group(1))
    if not res["property_links"]:
        mm = re.search(r'"property_links_count"\s*:\s*(\d+)', text)
        if mm:
            res["property_links"] = _safe_int(mm.group(1))

    return res


def _safe_relpath(p: Path) -> str:
    """Ruta relativa a PROJECT_ROOT si es posible; si no, ruta absoluta."""
    try:
        return str(p.resolve().relative_to(PROJECT_ROOT))
    except (ValueError, OSError):
        return str(p)


def run_single_test(
    sample: Dict[str, str],
    idx: int,
    raw_dir: Path,
    allow_playwright: bool,
    allow_network: bool,
    timeout_seconds: int,
    allow_visible_api: bool = False,
    allow_static_detail: bool = False,
) -> Dict[str, Any]:
    """Corre UN test aislado via subprocess. No escribe en DB ni cola."""
    url = sample["url"]
    cmd = [sys.executable, str(SCRAPER_PATH), "--test-url", url, "--workers", "1"]
    if allow_playwright:
        cmd.append("--allow-playwright")
    if allow_network:
        cmd.append("--allow-network-interception")
    if allow_visible_api:
        cmd.append("--allow-visible-api")
    if allow_static_detail:
        cmd.append("--allow-static-detail")

    started = time.time()
    timed_out = False
    stdout = stderr = ""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        stdout, stderr = proc.stdout, proc.stderr
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout or "" if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "" if isinstance(exc.stderr, str) else "")
        returncode = -1
    elapsed = round(time.time() - started, 1)

    # Guardar log crudo por URL
    raw_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(url, idx)
    (raw_dir / f"{slug}.log").write_text(
        f"CMD: {' '.join(cmd)}\n\n=== STDOUT ===\n{stdout}\n\n=== STDERR ===\n{stderr}\n",
        encoding="utf-8",
    )

    parsed = parse_test_output(stdout, stderr)
    success = (not timed_out) and parsed["propiedades"] > 0 and parsed["error_final"] is None
    final_error = "item_timeout" if timed_out else parsed["error_final"]

    return {
        "idx": idx,
        "url": url,
        "familia_origen": _norm_key(sample.get("error_type") or "desconocido"),
        "inmobiliaria_id": sample.get("inmobiliaria_id") or None,
        "nombre": sample.get("nombre") or None,
        "estrategia": parsed["estrategia"],
        "clasificacion": parsed["clasificacion"],
        "propiedades": parsed["propiedades"],
        "cards": parsed["cards"],
        "property_links": parsed["property_links"],
        "error_final": final_error,
        "error_msg": "timeout_proceso" if timed_out else parsed["error_msg"],
        "exito": success,
        "elapsed_seconds": elapsed,
        "timed_out": timed_out,
        "used_playwright": allow_playwright,
        "used_network_interception": allow_network,
        "returncode": returncode,
        "raw_log": _safe_relpath(raw_dir / f"{slug}.log"),
    }


def write_reports(run_dir: Path, meta: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    # report.json
    payload = {"meta": meta, "results": results}
    (run_dir / "report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # report.md
    by_fam: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_fam[r["familia_origen"]].append(r)

    lines: List[str] = []
    lines.append(f"# Diagnostico de scraping por familia\n")
    lines.append(f"- Fecha: {meta.get('timestamp')}")
    lines.append(f"- Input: `{meta.get('input')}`")
    lines.append(f"- Tests ejecutados: {len(results)}")
    lines.append(f"- Playwright: {meta.get('allow_playwright')} | Network interception: {meta.get('allow_network_interception')}")
    lines.append(f"- Timeout por test: {meta.get('timeout_seconds')}s\n")

    exitos = sum(1 for r in results if r["exito"])
    lines.append(f"## Resumen global\n")
    lines.append(f"- OK (props > 0): **{exitos}**")
    lines.append(f"- Siguen fallando: **{len(results) - exitos}**\n")

    for fam in sorted(by_fam.keys()):
        items = by_fam[fam]
        ok = sum(1 for r in items if r["exito"])
        lines.append(f"## Familia: `{fam}`  ({ok}/{len(items)} OK)\n")
        lines.append("| URL | resultado | estrategia | props | cards | links | error final | t(s) |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for r in items:
            estado = "OK" if r["exito"] else "FALLO"
            err = r["error_final"] or ("-" if r["exito"] else "fallo_sin_clasificar")
            lines.append(
                f"| {r['url']} | {estado} | {r['estrategia'] or '-'} | {r['propiedades']} | "
                f"{r['cards']} | {r['property_links']} | {err} | {r['elapsed_seconds']} |"
            )
        lines.append("")

    (run_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def write_before_after(run_dir: Path, prev_dir: Path, results: List[Dict[str, Any]]) -> None:
    prev_json = prev_dir / "report.json"
    if not prev_json.exists():
        print(f"[compare] No se encontro {prev_json}; se omite before_after.md")
        return
    try:
        prev = json.loads(prev_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[compare] No se pudo leer run previo: {exc}")
        return

    prev_by_url = {r["url"]: r for r in prev.get("results", [])}
    lines = ["# Comparacion antes / despues\n", f"- Run previo: `{prev_dir}`\n"]
    lines.append("| URL | antes (error/props) | despues (error/props) | cambio |")
    lines.append("|---|---|---|---|")
    mejoraron = empeoraron = igual = 0
    for r in results:
        p = prev_by_url.get(r["url"])
        if not p:
            lines.append(f"| {r['url']} | (nuevo) | {r['error_final'] or 'OK'}/{r['propiedades']} | nuevo |")
            continue
        antes = f"{p.get('error_final') or 'OK'}/{p.get('propiedades', 0)}"
        despues = f"{r['error_final'] or 'OK'}/{r['propiedades']}"
        if (not p.get("exito")) and r["exito"]:
            cambio = "MEJORO"
            mejoraron += 1
        elif p.get("exito") and (not r["exito"]):
            cambio = "EMPEORO"
            empeoraron += 1
        else:
            cambio = "igual"
            igual += 1
        lines.append(f"| {r['url']} | {antes} | {despues} | {cambio} |")
    lines.insert(2, f"- Mejoraron: **{mejoraron}** | Empeoraron: **{empeoraron}** | Igual: **{igual}**\n")
    (run_dir / "before_after.md").write_text("\n".join(lines), encoding="utf-8")


def print_dry_run_plan(grouped, args, total) -> None:
    print("=" * 70)
    print("DRY-RUN: plan de diagnostico (NO se ejecuta ningun test)")
    print("=" * 70)
    print(f"Input            : {args.input}")
    print(f"per-family       : {args.per_family}")
    print(f"limit global     : {args.limit}")
    print(f"allow-playwright : {args.allow_playwright}")
    print(f"allow-network    : {args.allow_network_interception}")
    print(f"timeout/test     : {args.timeout_seconds}s")
    print(f"output-dir       : {args.output_dir}")
    print(f"familias filtro  : {args.families or '(todas de codigo)'}")
    print(f"incluir no-codigo: {args.include_non_code}")
    print("-" * 70)
    if not grouped:
        print("No hay URLs que coincidan con los filtros. Nada para correr.")
        return
    for fam, items in grouped.items():
        marca = " [NO-CODIGO]" if fam in NON_CODE_FAMILIES else ""
        print(f"\nFamilia: {fam}{marca}  -> {len(items)} URL(s)")
        for i, r in enumerate(items, 1):
            ref = r.get("nombre") or r.get("inmobiliaria_id") or "-"
            print(f"   {i}. {r['url']}   (ref: {ref})")
    print("-" * 70)
    print(f"TOTAL a testear si corrieras real: {total} URL(s)")
    cmd = [
        "python", "scripts/diagnose_scraping_errors.py",
        f"--input {args.input}",
        f"--per-family {args.per_family}",
        f"--limit {args.limit}",
        f"--timeout-seconds {args.timeout_seconds}",
    ]
    if args.allow_playwright:
        cmd.append("--allow-playwright")
    if args.allow_network_interception:
        cmd.append("--allow-network-interception")
    if args.allow_visible_api:
        cmd.append("--allow-visible-api")
    if args.allow_static_detail:
        cmd.append("--allow-static-detail")
    print("\nPara correr de verdad, repeti el comando SIN --dry-run:")
    print("   " + " ".join(cmd))
    print("=" * 70)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="Diagnostico seguro de scraping por familia de error (tandas controladas)."
    )
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT),
                        help=f"CSV de muestra (default: {DEFAULT_INPUT})")
    parser.add_argument("--limit", type=int, default=20,
                        help="Tope global de URLs a testear (default: 20)")
    parser.add_argument("--per-family", type=int, default=3,
                        help="Maximo de URLs por familia (default: 3)")
    parser.add_argument("--families", type=str, default=None,
                        help="Filtrar solo estas familias, separadas por coma (ej: requires_playwright,timeout)")
    parser.add_argument("--include-non-code", action="store_true",
                        help="Incluir familias no-codigo (blocked, site_down). Por defecto se excluyen.")
    parser.add_argument("--allow-playwright", action="store_true",
                        help="Pasar --allow-playwright al test (render JS).")
    parser.add_argument("--allow-network-interception", action="store_true",
                        help="Pasar --allow-network-interception al test (captura XHR/fetch).")
    parser.add_argument("--allow-visible-api", action="store_true",
                        help="Pasar --allow-visible-api al test (Fix #1a: consumir endpoints API visibles).")
    parser.add_argument("--allow-static-detail", action="store_true",
                        help="Pasar --allow-static-detail al test (Fix #2: fichas estaticas .php/.html).")
    parser.add_argument("--timeout-seconds", type=int, default=300,
                        help="Timeout duro por test/proceso (default: 300).")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f"Carpeta de reportes (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--compare-with", type=str, default=None,
                        help="Ruta a un run previo (carpeta run_<ts>) para generar before_after.md")
    parser.add_argument("--export-from-supabase", action="store_true",
                        help="Exportar muestra de errores desde Supabase al CSV (--input). SOLO LECTURA, sin count.")
    parser.add_argument("--export-limit", type=int, default=50,
                        help="Tope de filas a exportar desde Supabase (default bajo: 50, cap: 1000).")
    parser.add_argument("--export-status", type=str, default="error",
                        help="Filtro de status para exportar (default: error).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar el plan sin ejecutar ningun test.")
    args = parser.parse_args()

    if not SCRAPER_PATH.exists():
        raise SystemExit(f"No se encontro el scraper en {SCRAPER_PATH}")

    # Paso opcional de exportacion (solo lectura) ANTES de leer la muestra.
    if args.export_from_supabase:
        export_samples_from_supabase(
            Path(args.input),
            limit=args.export_limit,
            status_filter=args.export_status,
        )

    families_filter = None
    if args.families:
        families_filter = [_norm_key(f) for f in args.families.split(",") if f.strip()]

    rows = read_samples(Path(args.input))
    grouped = group_and_sample(
        rows,
        per_family=args.per_family,
        limit=args.limit,
        families_filter=families_filter,
        include_non_code=args.include_non_code,
    )
    flat = [item for items in grouped.values() for item in items]

    if args.dry_run:
        print_dry_run_plan(grouped, args, len(flat))
        return

    # --- Ejecucion real (tests aislados, sin DB / sin cola) ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / f"run_{timestamp}"
    raw_dir = run_dir / "raw"
    print(f"[run] {len(flat)} test(s) -> {run_dir}")

    results: List[Dict[str, Any]] = []
    for i, sample in enumerate(flat, 1):
        print(f"[{i}/{len(flat)}] {sample['url']}  (familia origen: {sample['error_type']})")
        res = run_single_test(
            sample, i, raw_dir,
            allow_playwright=args.allow_playwright,
            allow_network=args.allow_network_interception,
            timeout_seconds=args.timeout_seconds,
            allow_visible_api=args.allow_visible_api,
            allow_static_detail=args.allow_static_detail,
        )
        estado = "OK" if res["exito"] else (res["error_final"] or "fallo")
        print(f"      -> {estado} | props={res['propiedades']} cards={res['cards']} "
              f"links={res['property_links']} t={res['elapsed_seconds']}s")
        results.append(res)

    meta = {
        "timestamp": timestamp,
        "input": args.input,
        "per_family": args.per_family,
        "limit": args.limit,
        "families_filter": families_filter,
        "allow_playwright": args.allow_playwright,
        "allow_network_interception": args.allow_network_interception,
        "allow_visible_api": args.allow_visible_api,
        "allow_static_detail": args.allow_static_detail,
        "timeout_seconds": args.timeout_seconds,
        "total_tests": len(results),
    }
    write_reports(run_dir, meta, results)
    if args.compare_with:
        write_before_after(run_dir, Path(args.compare_with), results)

    exitos = sum(1 for r in results if r["exito"])
    print("-" * 60)
    print(f"Listo. OK={exitos} / {len(results)}.  Reportes en: {run_dir}")
    print(f"  - {run_dir / 'report.json'}")
    print(f"  - {run_dir / 'report.md'}")


if __name__ == "__main__":
    main()

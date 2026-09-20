"""
scripts/prod_preflight_09a.py
PR-BE-PROD-09a — Preflight de corrida productiva URL + parser, sin publish

Lee:  _scratch/combined_url_parser_validation_08/combined_validation_results.csv
Crea: _scratch/prod_preflight_url_parser_09a/  (10 archivos)

GUARDRAILS:
  - 0 DB writes  - 0 raw/staging  - 0 publish  - 0 runs  - 0 push/deploy
  - Solo lectura de archivos locales + inspección de scripts del pipeline
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = REPO_ROOT / "_scratch" / "combined_url_parser_validation_08" / "combined_validation_results.csv"
OUT_DIR   = REPO_ROOT / "_scratch" / "prod_preflight_url_parser_09a"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TS = datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Clasificación por combined_status
# ---------------------------------------------------------------------------

SUCCESS_STATUSES  = {"success_url_only", "success_url_plus_parser"}
PARTIAL_STATUSES  = {"partial_url_only",  "partial_url_plus_parser"}
FAILED_STATUSES   = {"still_failed", "http_error", "error"}
EXCLUDED_ERRORS   = {"still_failed", "http_error", "error"}

# ---------------------------------------------------------------------------
# 1. Leer CSV
# ---------------------------------------------------------------------------

print("[09a] Leyendo combined_validation_results.csv ...")

rows: List[Dict[str, Any]] = []
with open(INPUT_CSV, encoding="utf-8", newline="") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        rows.append(row)

print(f"       {len(rows)} filas cargadas")

# ---------------------------------------------------------------------------
# 2. Clasificar
# ---------------------------------------------------------------------------

manifest_a: List[Dict] = []   # success only
manifest_b_extra: List[Dict] = []   # partial only (extra sobre A)
manifest_c: List[Dict] = []   # excluidas

# Contadores de validaciones
errs_prohibited: List[str] = []
errs_missing_url: List[str] = []
errs_playwright: List[str] = []
errs_failed: List[str] = []
errs_dup: Dict[str, int] = {}

seen_ids: Dict[str, int] = {}

for r in rows:
    sid        = r.get("source_id", "").strip()
    cs         = r.get("combined_status", "").strip()
    url        = (r.get("new_url_listado") or r.get("old_url_listado") or "").strip()
    needs_pw   = r.get("needs_playwright", "False").strip().lower() == "true"
    err_col    = (r.get("error") or "").strip().lower()

    # Deduplicación
    if sid in seen_ids:
        seen_ids[sid] += 1
    else:
        seen_ids[sid] = 1

    # Validaciones de exclusión
    is_prohibited = any(
        domain in url.lower()
        for domain in [
            "facebook.com", "instagram.com", "zonaprop.com", "argenprop.com",
            "properati.com", "mercadolibre.com", "navent.com", "twitter.com",
            "linkedin.com", "youtube.com",
        ]
    )
    is_missing_url = not url
    is_domain_down = err_col in {"http_error", "connection_error"} or cs == "http_error"

    # Clasificar
    if is_prohibited:
        errs_prohibited.append(sid)
        manifest_c.append(r)
    elif is_missing_url:
        errs_missing_url.append(sid)
        manifest_c.append(r)
    elif cs in SUCCESS_STATUSES:
        if needs_pw:
            errs_playwright.append(sid)
            manifest_c.append(r)
        else:
            manifest_a.append(r)
    elif cs in PARTIAL_STATUSES:
        if needs_pw:
            errs_playwright.append(sid)
            manifest_c.append(r)
        else:
            manifest_b_extra.append(r)
    else:
        errs_failed.append(sid)
        manifest_c.append(r)

manifest_b = manifest_a + manifest_b_extra
dups = {k: v for k, v in seen_ids.items() if v > 1}

# ---------------------------------------------------------------------------
# 3. Totales
# ---------------------------------------------------------------------------

total_a         = len(manifest_a)
total_b         = len(manifest_b)
total_b_extra   = len(manifest_b_extra)
total_c         = len(manifest_c)
total_checked   = len(rows)

# Desgloses dentro de A y B
def count_by_field(lst, field, value):
    return sum(1 for r in lst if r.get(field, "").strip() == value)

a_url_only      = count_by_field(manifest_a, "combined_status", "success_url_only")
a_url_parser    = count_by_field(manifest_a, "combined_status", "success_url_plus_parser")
b_partial_only  = count_by_field(manifest_b_extra, "combined_status", "partial_url_only")
b_partial_parser= count_by_field(manifest_b_extra, "combined_status", "partial_url_plus_parser")

# Propiedades en manifests
total_links_a   = sum(int(r.get("property_links") or 0) for r in manifest_a)
total_links_b   = sum(int(r.get("property_links") or 0) for r in manifest_b)

# Yields estimados
total_yield_a   = sum(int(r.get("estimated_yield") or 0) for r in manifest_a)
total_yield_b   = sum(int(r.get("estimated_yield") or 0) for r in manifest_b)

print(f"       Manifest A (success only):        {total_a}")
print(f"       Manifest B (success + partial):   {total_b}")
print(f"       Manifest C (excluidas):           {total_c}")
print(f"       Duplicados: {len(dups)}")
print(f"       Fuentes prohibidas detectadas: {len(errs_prohibited)}")
print(f"       Missing URL: {len(errs_missing_url)}")
print(f"       Playwright candidates excluidos: {len(errs_playwright)}")


# ---------------------------------------------------------------------------
# Helpers de escritura CSV
# ---------------------------------------------------------------------------

FIELDNAMES = [
    "source_id", "source_name", "old_url_listado", "new_url_listado",
    "url_status", "parser_status", "parser_family", "combined_status",
    "is_parser_recovered", "property_links", "old_cards", "new_cards",
    "estimated_yield", "detail_category", "detail_score",
    "detail_title", "detail_price", "needs_playwright", "error",
]

def write_csv(path: Path, data: List[Dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


# ---------------------------------------------------------------------------
# 4. CSV: Manifest A
# ---------------------------------------------------------------------------

path_ma = OUT_DIR / "manifest_success_only.csv"
write_csv(path_ma, manifest_a)
print(f"[09a] {path_ma.name} -> {total_a} filas")

# ---------------------------------------------------------------------------
# 5. CSV: Manifest B
# ---------------------------------------------------------------------------

path_mb = OUT_DIR / "manifest_success_plus_partial.csv"
write_csv(path_mb, manifest_b)
print(f"[09a] {path_mb.name} -> {total_b} filas")

# ---------------------------------------------------------------------------
# 6. CSV: Manifest C (excluidas)
# ---------------------------------------------------------------------------

path_mc = OUT_DIR / "manifest_excluded.csv"
write_csv(path_mc, manifest_c)
print(f"[09a] {path_mc.name} -> {total_c} filas")

# ---------------------------------------------------------------------------
# 7. proposed_commands.md
# ---------------------------------------------------------------------------

proposed_commands = f"""# Comandos propuestos — PR-BE-PROD-09a

> Generado: {TS}
> Estado: PROPUESTOS — NO ejecutar sin autorización explícita del usuario

## Contexto: arquitectura actual del pipeline

El entry point productivo actual es `scraper/run.py`.

### Limitación crítica

`run.py` actualmente **NO soporta filtrado por source_id ni por manifest**.
Carga TODAS las fuentes desde `inmobiliarias_scraping` por dominio.

**Se requiere un script wrapper** (`scripts/run_manifest.py`) antes de
poder ejecutar una corrida acotada a los manifests A/B.

---

## Opción 1 — Dry-run completo (sin manifest filter, sin writes)

```bash
cd scraper
python run.py --dry-run --skip-specialized --workers 2
```

**Qué hace:** visita todas las fuentes, imprime lo que guardaría, NO escribe DB.
**Riesgo:** corre sobre TODAS las fuentes, no solo las 892/953 del manifest.
**Recomendación:** NO usar todavía — esperar wrapper.

---

## Opción 2 — Dry-run con wrapper de manifest (RECOMENDADO)

```bash
# Paso 1: crear wrapper (ver pipeline_write_path_analysis.md para spec)
# Paso 2: ejecutar dry-run acotado al manifest A
cd scraper
python ../scripts/run_manifest.py \\
  --manifest ../_scratch/prod_preflight_url_parser_09a/manifest_success_only.csv \\
  --dry-run \\
  --workers 2 \\
  --skip-specialized
```

**Qué hace:**
1. Lee el manifest CSV (source_id + new_url_listado)
2. Carga solo esas {total_a} fuentes (no el universo completo)
3. Corre el scraper en modo dry-run (0 writes)
4. Imprime links encontrados por fuente

---

## Opción 3 — Corrida productiva real (manifest A, sin publish)

```bash
cd scraper
python ../scripts/run_manifest.py \\
  --manifest ../_scratch/prod_preflight_url_parser_09a/manifest_success_only.csv \\
  --workers 4 \\
  --skip-specialized
```

**ADVERTENCIA:** Esta opción escribe en `propiedades` (tabla productiva).
**NO ejecutar hasta tener wrapper validado y autorización explícita.**

---

## Flags que NO existen en run.py actual

| Flag | Estado | Alternativa |
|---|---|---|
| `--source-id` | NO existe | Usar wrapper de manifest |
| `--manifest` | NO existe | Usar wrapper de manifest |
| `--include-new` | NO existe | No necesario en run.py |
| `--include-backlog` | NO existe | No usar |
| `--no-publish` | NO existe | No hay publish separado |
| `--source-view` | NO existe | No usar |

---

## Paso inmediato recomendado

1. Crear `scripts/run_manifest.py` (ver spec en pipeline_write_path_analysis.md)
2. Validar con `--dry-run` sobre Manifest A (10-20 fuentes de prueba)
3. Revisar output
4. Si OK → solicitar autorización para corrida real
"""

(OUT_DIR / "proposed_commands.md").write_text(proposed_commands, encoding="utf-8")
print("[09a] proposed_commands.md -> OK")

# ---------------------------------------------------------------------------
# 8. pipeline_write_path_analysis.md
# ---------------------------------------------------------------------------

write_path = f"""# Análisis de ruta de escritura del pipeline — PR-BE-PROD-09a

> Generado: {TS}

## Pipeline activo: scraper/run.py

### Fuente de fuentes (LECTURA)

| Tabla | Operación | Columnas leídas |
|---|---|---|
| `inmobiliarias_scraping` | SELECT | `nombre`, `web`, `ciudad` |

`load_fuentes_from_db()` carga TODAS las filas con `web != null`.
Filtra portales prohibidos y duplicados por dominio.
**No filtra por source_id ni url_listado.**

### Propiedades existentes (LECTURA)

| Tabla | Operación | Columnas leídas |
|---|---|---|
| `propiedades` | SELECT | `url` |

`supabase.get_all_existing_urls()` carga hasta 100,000 URLs para dedup en memoria.

### Escritura de propiedades nuevas (WRITE)

| Tabla | Operación | Columnas escritas | Conflicto |
|---|---|---|---|
| `propiedades` | UPSERT (POST) | todos los campos de Propiedad | `on_conflict=url` |

Método: `SupabaseClient.batch_save_only_new()` → POST a `/rest/v1/propiedades?on_conflict=url`
Chunk size: 20 por request. Retry: 3 intentos.

### Tablas NO tocadas por run.py

| Tabla | Estado |
|---|---|
| `inmobiliarias_main` | NO tocada |
| `url_listado` (columna) | NO tocada |
| `diagnostic_status` | NO tocada |
| `scraping_readiness` | NO tocada |
| `exclude_from_scraping` | NO tocada |
| `publish_queue` | NO existe en este pipeline |
| `raw` (internal_scraping) | NO tocada (pipeline viejo) |
| `staging` (internal_scraping) | NO tocada (pipeline viejo) |
| `scraping_runs` | NO existe en este pipeline |
| `scraping_run_items` | NO existe en este pipeline |

### ¿Existe publish separado?

**No.** En `run.py`, escribir a `propiedades` ES el publish.
No hay pipeline de staging → publish.
La tabla `propiedades` es la tabla pública.

**Esto significa:** si se corre `run.py` sin `--dry-run`, los datos
van directamente a producción (tabla `propiedades`).

---

## Limitación: run.py no soporta filtrado por manifest

`run.py` carga fuentes desde `inmobiliarias_scraping.web`, que contiene
la URL base del sitio, NO necesariamente el `url_listado` actualizado.

Las 1,057 fuentes del manifest tienen su `url_listado` actualizado en
`inmobiliarias_main.url_listado` (por PR-BE-URL-06), pero `run.py`
lee `inmobiliarias_scraping.web` (URL base del sitio, no de listado).

**Para correr solo las fuentes del manifest y con el url_listado correcto,
se necesita un wrapper.**

---

## Spec del wrapper: scripts/run_manifest.py

### Interfaz propuesta

```
python scripts/run_manifest.py \\
  --manifest PATH_CSV \\
  [--dry-run] \\
  [--workers N] \\
  [--skip-specialized] \\
  [--limit N]            # max fuentes a procesar (para tests)
```

### Lógica propuesta

```python
# 1. Leer manifest CSV
#    Columnas: source_id, source_name, new_url_listado, combined_status, ...
manifest = read_csv(args.manifest)

# 2. Construir lista de fuentes para el scraper
fuentes = []
for row in manifest:
    fuentes.append({{
        "key": slugify(row["source_name"]),
        "web": row["new_url_listado"],   # URL correcta (post-06d fix)
        "ciudad": "",                    # desconocida en este contexto
        "operacion": None,               # detectada por parser
        "tipo_cms": "tokko",
    }})

# 3. Pasar fuentes directamente a run._scrape_batch()
#    (evitar load_fuentes_from_db() — no queremos el universo completo)
run.run_from_fuentes(fuentes, dry_run=args.dry_run, workers=args.workers)
```

### Cambios necesarios en run.py

Extraer `run_from_fuentes(fuentes, dry_run, workers)` como función pública:

```python
def run_from_fuentes(
    fuentes: List[Dict],
    workers: int = DEFAULT_WORKERS,
    dry_run: bool = False,
    skip_specialized: bool = True,
) -> None:
    session = SessionFactory.make()
    supabase = SupabaseClient(session, ...)
    existing_urls = supabase.get_all_existing_urls()
    lock = threading.Lock()
    batches = _split_batches(fuentes, workers)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        ...
```

**Esfuerzo estimado:** ~50 líneas. Refactor mínimo, sin cambiar lógica de scraping.

---

## Alternativa más simple: filtro inline (sin wrapper)

Modificar `load_fuentes_from_db()` para aceptar un set de URLs permitidas:

```python
allowed_urls = set(load_manifest_urls(args.manifest))
fuentes = [f for f in load_fuentes_from_db(session) if f["web"] in allowed_urls]
```

**Problema:** `inmobiliarias_scraping.web` puede diferir del `url_listado`
actualizado. Matching por URL exacta puede fallar si hay trailing slashes
o variaciones de http/https.

**Recomendación:** usar matching por dominio normalizado como backup.
"""

(OUT_DIR / "pipeline_write_path_analysis.md").write_text(write_path, encoding="utf-8")
print("[09a] pipeline_write_path_analysis.md -> OK")

# ---------------------------------------------------------------------------
# 9. no_publish_guardrails.md
# ---------------------------------------------------------------------------

no_pub = f"""# Guardrails de no-publish — PR-BE-PROD-09a

> Generado: {TS}

## Arquitectura: no existe publish separado en run.py

En el pipeline actual (`scraper/run.py`), NO hay una fase de publish
separada. Escribir a `propiedades` ES el acto de publicar.

Esto implica que **el único guardrail de no-publish es `--dry-run`**.

---

## Mecanismo de dry-run (activo en run.py)

```python
# run.py línea 369-380
if nuevas_final and not dry_run:
    saved = supabase.batch_save_only_new([p.to_payload() for p in nuevas_final])
    ...
elif nuevas_final and dry_run:
    for p in nuevas_final[:3]:
        logger.info(f"  [DRY] {{p.titulo[:60]}} | {{p.url}}")
    total += len(nuevas_final)
```

Con `--dry-run`:
- NO se llama `batch_save_only_new()`
- NO se hace POST a Supabase
- Se imprime por consola lo que SE GUARDARÍA (hasta 3 ejemplos por fuente)
- El contador `total` refleja cuántas se habrían guardado

---

## Garantías de no-publish en este preflight (09a)

| Acción | Estado | Mecanismo |
|---|---|---|
| POST a `propiedades` | BLOQUEADO | No ejecutamos run.py |
| UPSERT a `propiedades` | BLOQUEADO | No ejecutamos run.py |
| Escritura a `raw` | NO APLICA | run.py no usa raw |
| Escritura a `staging` | NO APLICA | run.py no usa staging |
| `publish_queue` | NO APLICA | No existe en run.py |
| Scraping de sitios web | BLOQUEADO | No ejecutamos run.py |
| DB writes de cualquier tipo | **0** | Solo leemos CSVs locales |

---

## Protocolo para fase productiva (09b — cuando se autorice)

### Secuencia recomendada

1. **Crear wrapper** `scripts/run_manifest.py` (sin ejecutar corrida)
2. **Dry-run sobre 5 fuentes** de prueba del manifest A para validar
   que el parser con los dos fixes funciona end-to-end
3. **Revisar output** del dry-run con el usuario
4. **Autorización explícita** del usuario para corrida real
5. **Corrida real por lotes** (50-100 fuentes primero, no las 892 de golpe)
6. **Validar tabla propiedades** después de cada lote
7. **Escalar** si los lotes iniciales pasan QA

### Flags de contención en corrida real

```bash
python scripts/run_manifest.py \\
  --manifest manifest_success_only.csv \\
  --workers 2              # no saturar con 4+ workers desde el arranque
  --skip-specialized       # no correr APL/Raffin/etc. hasta validar genéricas
  --limit 50               # limitar a 50 fuentes en el primer lote
```

---

## Riesgo residual: propiedades ya en DB

`batch_save_only_new()` usa `on_conflict=url` → upsert, no insert puro.
Si una URL ya existe en `propiedades`, el UPSERT puede actualizar sus datos.
Esto no es un "nuevo publish" pero sí modifica datos existentes.

**Mitigación:** el lock en `_scrape_batch` y el check `url not in existing_urls`
deberían prevenir la mayoría de duplicados. Aun así, el upsert puede
actualizar campos como `scraped_at` o precios que cambiaron.

**Recomendación:** documentar este comportamiento antes de la corrida real.
"""

(OUT_DIR / "no_publish_guardrails.md").write_text(no_pub, encoding="utf-8")
print("[09a] no_publish_guardrails.md -> OK")

# ---------------------------------------------------------------------------
# 10. validation_plan.md
# ---------------------------------------------------------------------------

val_plan = f"""# Plan de validación post-corrida — PR-BE-PROD-09a

> Generado: {TS}
> Esta validación aplica DESPUÉS de que se autorice y ejecute la corrida real

## Métricas baseline (pre-corrida, del manifest A)

| Métrica | Valor |
|---|---|
| Fuentes en Manifest A | {total_a} |
| Fuentes en Manifest B | {total_b} |
| Property links detectados (validación 07d/08) | {total_links_a:,} (solo A) |
| Estimated yield total (A) | {total_yield_a:,} |
| Parser recovered (08) | 93 |
| True regressions (08) | 0 |

## Validaciones post-corrida

### 1. Conteo de propiedades nuevas

```sql
-- Cuántas propiedades se guardaron en la última corrida
SELECT COUNT(*) FROM propiedades
WHERE scraped_at > '<timestamp_inicio_corrida>'
```

**Esperado:** entre 1,000 y 14,920 propiedades nuevas (según dedup con existentes)

### 2. Fuentes que aportaron propiedades

```sql
SELECT fuente, COUNT(*) as n
FROM propiedades
WHERE scraped_at > '<timestamp_inicio_corrida>'
GROUP BY fuente
ORDER BY n DESC
LIMIT 50
```

**Esperado:** la mayoría de las {total_a} fuentes del manifest con n > 0

### 3. Calidad de datos

```sql
SELECT
  COUNT(*) FILTER (WHERE titulo IS NULL OR titulo = 'Sin título') as sin_titulo,
  COUNT(*) FILTER (WHERE precio IS NULL) as sin_precio,
  COUNT(*) FILTER (WHERE operacion IS NULL) as sin_operacion,
  COUNT(*) FILTER (WHERE tipo_propiedad = 'otro') as tipo_otro,
  COUNT(*) as total
FROM propiedades
WHERE scraped_at > '<timestamp_inicio_corrida>'
```

**Esperado:** < 10% sin precio, < 5% sin operacion

### 4. Regressions: fuentes que antes tenían propiedades y ahora no

```sql
-- Fuentes con propiedades antes de la corrida
-- (requiere snapshot pre-corrida de fuentes con n > 0)
-- Comparar contra conteo post-corrida por fuente
```

**Esperado:** 0 regressions (validado en 07d con 221 fuentes)

### 5. URLs duplicadas

```sql
SELECT url, COUNT(*) as n
FROM propiedades
GROUP BY url
HAVING COUNT(*) > 1
ORDER BY n DESC
LIMIT 20
```

**Esperado:** 0 duplicados (el upsert on_conflict=url previene esto)

---

## Métricas a monitorear en la corrida

Del output de `run.py` en consola:

| Log pattern | Qué mide |
|---|---|
| `[W0][key] X URLs en Y páginas de listado` | Links detectados por fuente |
| `[W0][key] X fichas nuevas a scrapear` | Fichas nuevas (no en DB) |
| `[W0][key] Guardadas: X` | Propiedades efectivamente escritas |
| `SCRAPING COMPLETO ... Guardadas Fase 1: X` | Total al final |
| `ERROR` o `Timeout` | Fallos individuales |

---

## Criterio de éxito

| Condición | Criterio |
|---|---|
| Propiedades nuevas guardadas | > 1,000 |
| Tasa de error por fuente | < 10% |
| Regressions (fuentes que tenían y no aportaron) | 0 |
| Duplicados en DB | 0 |
| Datos con título y precio | > 85% |
"""

(OUT_DIR / "validation_plan.md").write_text(val_plan, encoding="utf-8")
print("[09a] validation_plan.md -> OK")

# ---------------------------------------------------------------------------
# 11. risk_assessment.md
# ---------------------------------------------------------------------------

risk = f"""# Risk assessment — PR-BE-PROD-09a

> Generado: {TS}

## Riesgos técnicos

### Riesgo 1 — run.py no filtra por manifest — ALTO (requiere mitigación)

`run.py` no tiene mecanismo de filtrado por source_id ni por URL de listado.
Si se corre sin wrapper, procesará TODAS las fuentes de `inmobiliarias_scraping`,
no solo las {total_a} del manifest A.

**Mitigación:** crear wrapper `scripts/run_manifest.py` ANTES de correr.
**Estado:** pendiente de implementación.

### Riesgo 2 — propiedades escribe directamente a producción — MEDIO

No existe staging en este pipeline. `propiedades` es la tabla pública.
Un run con error masivo podría escribir datos basura en producción.

**Mitigación:**
- Correr dry-run primero
- Usar `--limit 50` en el primer lote real
- Revisar output antes de escalar

### Riesgo 3 — upsert puede actualizar propiedades existentes — BAJO

`on_conflict=url` hace upsert, no insert puro. Propiedades con la misma
URL podrían tener campos actualizados (precio, scraped_at).

**Mitigación:** este comportamiento es esperado y deseable (actualiza datos stale).
No requiere acción adicional.

### Riesgo 4 — 20 fuentes still_failed con needs_playwright en manifest A — 0

Las fuentes con `needs_playwright=True` fueron excluidas del manifest A y B.
Están en manifest C (excluidas).

**Verificación:** {len(errs_playwright)} fuentes con needs_playwright detectadas y excluidas.

### Riesgo 5 — Fuentes prohibidas en manifest — 0

Se verificaron {len(errs_prohibited)} fuentes prohibidas.
Ninguna quedó en manifest A ni B.

### Riesgo 6 — Fuentes sin url_listado — {len(errs_missing_url)}

{len(errs_missing_url)} fuentes sin URL detectadas y excluidas al manifest C.

### Riesgo 7 — Duplicados por source_id — {len(dups)}

{f"Duplicados detectados: {list(dups.items())[:10]}" if dups else "0 duplicados. OK."}

### Riesgo 8 — Timeouts de sitios durante corrida — BAJO

Los timeouts están configurados por `SCRAPER_TIMEOUT_MULTIPLIER`.
Por default 1.0x. Para la primera corrida se puede dejar el default.
Los fallos individuales no detienen el batch.

---

## Resumen de riesgos

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Sin filtrado por manifest | ALTO | Crear wrapper antes de correr |
| Escribe directo a prod | MEDIO | Dry-run primero, lotes de 50 |
| Upsert actualiza existentes | BAJO | Esperado y deseable |
| Playwright en manifest | 0 | Excluidas correctamente |
| Fuentes prohibidas | 0 | Excluidas correctamente |
| Missing URL | {len(errs_missing_url)} | Excluidas correctamente |
| Duplicados | {len(dups)} | {"Revisar" if dups else "OK"} |

---

## Evaluación final de este preflight (09a)

| Dimensión | Estado |
|---|---|
| DB writes en 09a | **0** |
| raw/staging writes | **0** |
| publish | **0** |
| scraping productivo | **0** |
| runs creados | **0** |
| push/deploy/frontend | **0** |
| Manifest A generado | **{total_a} fuentes** |
| Manifest B generado | **{total_b} fuentes** |
| Manifest C (excluidas) | **{total_c} fuentes** |
| Validaciones de exclusión | **OK** |
| **Veredicto preflight** | **LISTO para próximo paso (crear wrapper)** |
"""

(OUT_DIR / "risk_assessment.md").write_text(risk, encoding="utf-8")
print("[09a] risk_assessment.md -> OK")

# ---------------------------------------------------------------------------
# 12. next_step_recommendation.md
# ---------------------------------------------------------------------------

next_step = f"""# Próximo paso recomendado — post PR-BE-PROD-09a

> Generado: {TS}

## Resumen del preflight

| Métrica | Valor |
|---|---|
| Fuentes Manifest A (success) | **{total_a}** |
| Fuentes Manifest B (success + partial) | **{total_b}** |
| Fuentes excluidas | **{total_c}** |
| Property links en Manifest A | **{total_links_a:,}** |
| Property links en Manifest B | **{total_links_b:,}** |
| Estimated yield en Manifest A | **{total_yield_a:,}** |
| Fuentes playwright excluidas | **{len(errs_playwright)}** |
| Fuentes prohibidas excluidas | **{len(errs_prohibited)}** |
| Fuentes missing URL excluidas | **{len(errs_missing_url)}** |
| Duplicados | **{len(dups)}** |

## Recomendación: Manifest A vs Manifest B

**Recomendación: comenzar con Manifest A (solo success, {total_a} fuentes)**

Razones:
- Las {total_b_extra} fuentes partial tienen entre 1-8 links detectados,
  no garantizan fichas navegables. Mayor riesgo de datos incompletos.
- Las {total_a} fuentes success tienen validación de detalle en 07d (97 OK).
- Si Manifest A funciona bien, escalar a B es trivial.
- Menor blast radius en el primer lote.

## Próximos pasos secuenciales

### PR-BE-PROD-09b — Crear wrapper de manifest (INMEDIATO)

Crear `scripts/run_manifest.py` que:
1. Acepta `--manifest CSV_PATH`
2. Carga solo las fuentes del manifest (no el universo completo)
3. Usa la columna `new_url_listado` como URL de scraping
4. Integra con `run._scrape_batch()` existente
5. Soporta `--dry-run`, `--workers`, `--limit`

**Esfuerzo:** ~80 líneas de Python. Sin cambiar playwright_scraper.py.
**Riesgo:** bajo (solo orquestación, no cambia lógica de scraping)

### PR-BE-PROD-09c — Dry-run sobre 10 fuentes del manifest A

```bash
python scripts/run_manifest.py \\
  --manifest _scratch/prod_preflight_url_parser_09a/manifest_success_only.csv \\
  --dry-run --workers 1 --limit 10
```

Validar: ¿el scraper encuentra links con el url_listado correcto?
¿Los dos fixes (URL + parser) están activos en el run?

### PR-BE-PROD-09d — Corrida real primer lote (50 fuentes, con autorización)

Solo después de validar 09c.
```bash
python scripts/run_manifest.py \\
  --manifest _scratch/prod_preflight_url_parser_09a/manifest_success_only.csv \\
  --workers 2 --limit 50
```

### PR-BE-PROD-09e — Corrida real completa (892 fuentes, con autorización)

Solo después de validar 09d.

---

## Alternativa: PR-BE-PW-06 antes de corrida productiva

Si se prefiere no avanzar con la corrida genérica todavía, la alternativa
es abordar las 20 fuentes needs_playwright (y las 123 SPAs CMS unknown)
en PR-BE-PW-06 para maximizar la cobertura antes del lote productivo.

**Trade-off:**
- Corrida ahora: impacto inmediato en {total_a} fuentes, pero 20 quedan fuera
- PW-06 primero: +20 fuentes pero ~2-3 semanas de trabajo adicional

---

## Guardrails confirmados en 09a

DB writes: **0** | raw/staging: **0** | publish: **0** |
runs productivos: **0** | push/deploy/frontend: **0** |
Manifests: **solo en _scratch/**
"""

(OUT_DIR / "next_step_recommendation.md").write_text(next_step, encoding="utf-8")
print("[09a] next_step_recommendation.md -> OK")

# ---------------------------------------------------------------------------
# 13. prod_preflight_summary.md (archivo 1, generado al final con todos los datos)
# ---------------------------------------------------------------------------

# Desglose de excluidas por razón
c_still_failed    = count_by_field(manifest_c, "combined_status", "still_failed")
c_http_error      = count_by_field(manifest_c, "combined_status", "http_error")
c_error           = count_by_field(manifest_c, "combined_status", "error")
c_playwright      = len(errs_playwright)
c_missing_url     = len(errs_missing_url)
c_prohibited      = len(errs_prohibited)

summary = f"""# PR-BE-PROD-09a — Preflight de corrida productiva URL + parser

Generado: {TS}

## Inputs

| Archivo | Filas |
|---|---|
| `combined_validation_results.csv` | {total_checked} |

## Manifests generados

### Manifest A — Success only (RECOMENDADO para primer lote)

| Estado | n |
|---|---|
| `success_url_only` | {a_url_only} |
| `success_url_plus_parser` | {a_url_parser} |
| **TOTAL Manifest A** | **{total_a}** |

- Property links detectados: **{total_links_a:,}**
- Estimated yield total: **{total_yield_a:,}**

### Manifest B — Success + partial

| Estado | n |
|---|---|
| Fuentes de Manifest A | {total_a} |
| `partial_url_only` (adicional) | {b_partial_only} |
| `partial_url_plus_parser` (adicional) | {b_partial_parser} |
| **TOTAL Manifest B** | **{total_b}** |

- Property links detectados: **{total_links_b:,}**
- Estimated yield total: **{total_yield_b:,}**

### Manifest C — Excluidas

| Razón | n |
|---|---|
| `still_failed` | {c_still_failed} |
| `http_error` / `error` | {c_http_error + c_error} |
| needs_playwright (excluidos de A/B) | {c_playwright} |
| missing url_listado | {c_missing_url} |
| fuente prohibida | {c_prohibited} |
| **TOTAL Manifest C** | **{total_c}** |

## Análisis del pipeline

### Pipeline activo: scraper/run.py

| Dimensión | Estado |
|---|---|
| Entry point | `scraper/run.py` |
| Fuentes leídas desde | `inmobiliarias_scraping.web` |
| Escribe en | `propiedades` (upsert on_conflict=url) |
| Publish separado | **NO EXISTE** — escribir = publicar |
| Filtrado por manifest | **NO SOPORTADO** — requiere wrapper |
| Flag `--dry-run` | SÍ disponible |
| Flag `--include-backlog` | NO existe |
| Flag `--source-id` | NO existe |

### ¿Hace falta crear wrapper?

**SÍ.** Para correr solo las fuentes del manifest (y con el `url_listado`
correcto post-06d), se necesita `scripts/run_manifest.py`.

Sin wrapper, `run.py` ignoraría el manifest y correría sobre todo el universo.

## Validaciones de exclusión

| Validación | Resultado |
|---|---|
| Fuentes prohibidas en Manifest A | **0** |
| Fuentes prohibidas en Manifest B | **0** |
| Missing URL en Manifest A | **0** |
| Missing URL en Manifest B | **0** |
| needs_playwright en Manifest A | **0** |
| needs_playwright en Manifest B | **0** |
| still_failed en Manifest A | **0** |
| still_failed en Manifest B | **0** |
| Duplicados por source_id | **{len(dups)}** |
| Todos los outputs en _scratch/ | **SI** |
| DB writes en 09a | **0** |
| raw/staging writes en 09a | **0** |
| publish en 09a | **0** |
| scraping productivo en 09a | **0** |
| runs en 09a | **0** |
| push/deploy/frontend en 09a | **0** |

## Recomendación

**Comenzar con Manifest A ({total_a} fuentes)**, no con B.
**Próximo paso: crear `scripts/run_manifest.py`** (PR-BE-PROD-09b).

## Guardrails confirmados

DB writes: **0** | UPDATE: **0** | publish: **0** |
scraping productivo: **0** | runs: **0** | push/deploy/frontend: **0** |
columnas de clasificación: **no tocadas** | `--include-backlog`: **no usado**
"""

(OUT_DIR / "prod_preflight_summary.md").write_text(summary, encoding="utf-8")
print("[09a] prod_preflight_summary.md -> OK")

# ---------------------------------------------------------------------------
# Resumen final
# ---------------------------------------------------------------------------

print()
print("=" * 60)
print("PR-BE-PROD-09a completado")
print(f"  Manifest A (success):        {total_a:>4} fuentes")
print(f"  Manifest B (success+partial):{total_b:>4} fuentes")
print(f"  Manifest C (excluidas):      {total_c:>4} fuentes")
print(f"  Property links (A):          {total_links_a:>7,}")
print(f"  Property links (B):          {total_links_b:>7,}")
print(f"  Estimated yield (A):         {total_yield_a:>7,}")
print(f"  Duplicados:                  {len(dups):>4}")
print(f"  Playwright excluidos:        {len(errs_playwright):>4}")
print(f"  Prohibidas excluidas:        {len(errs_prohibited):>4}")
print(f"  Missing URL excluidas:       {len(errs_missing_url):>4}")
print(f"  DB writes:                   0")
print(f"  publish/runs/push/deploy:    0")
print(f"  Outputs:                     {OUT_DIR}")
print("=" * 60)

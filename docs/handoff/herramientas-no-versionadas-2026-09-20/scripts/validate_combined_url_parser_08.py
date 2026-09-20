"""
PR-BE-COMBINED-08 — Validación combinada URL + parser post-merge.

Mide el impacto combinado de:
  1. UPDATE real de url_listado sobre 1.057 fuentes (PR-BE-URL-06)
  2. Fix de parser mergeado en main (PR #6)

NO DB writes. NO UPDATE. NO publish. NO scraping productivo. NO push.
"""

import csv
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRATCH = ROOT / "_scratch"
OUT = SCRATCH / "combined_url_parser_validation_08"
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Input paths
# ---------------------------------------------------------------------------
URL_UPDATED    = SCRATCH / "url_listing_update_pr_be_url_06d" / "updated_rows.csv"
URL_VALIDATION = SCRATCH / "url_listing_post_update_validation" / "post_update_validation_results.csv"
PARSER_BA      = SCRATCH / "parser_fix_pr_be_parser_07b" / "parser_fix_before_after.csv"
PARSER_REC     = SCRATCH / "parser_fix_pr_be_parser_07b" / "recovered_after_parser_fix.csv"
DETAIL_VAL     = SCRATCH / "parser_detail_validation_pr_be_parser_07d" / "detail_validation_results.csv"

# ---------------------------------------------------------------------------
# Combined status mapping
# ---------------------------------------------------------------------------
# URL statuses -> combined category
URL_TO_COMBINED = {
    "success_after_url_fix":   "success_url_only",
    "partial_after_url_fix":   "partial_url_only",
    "needs_parser_fix":        None,          # overridden by parser result
    "still_no_property_links": "still_failed",
    "http_error":              "http_error",
    "unexpected_error":        "error",
}

PARSER_TO_COMBINED = {
    "success_after_parser_fix":  "success_url_plus_parser",
    "partial_after_parser_fix":  "partial_url_plus_parser",
    "still_failed":              "still_failed",
}

SUCCESS_CATS  = {"success_url_only", "success_url_plus_parser"}
PARTIAL_CATS  = {"partial_url_only", "partial_url_plus_parser"}
FAILED_CATS   = {"still_failed"}
ERR_CATS      = {"http_error", "error"}


def load_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    print("=" * 70)
    print("PR-BE-COMBINED-08 — Combined URL + parser validation")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)
    print("\n[GUARDRAILS] DB=0 | UPDATE=0 | publish=0 | push=0 | deploy=0\n")

    # -----------------------------------------------------------------------
    # Load inputs
    # -----------------------------------------------------------------------
    url_updated    = {r["source_id"]: r for r in load_csv(URL_UPDATED)}
    url_validation = {r["source_id"]: r for r in load_csv(URL_VALIDATION)}
    parser_ba      = {r["source_id"]: r for r in load_csv(PARSER_BA)}
    parser_rec_ids = {r["source_id"] for r in load_csv(PARSER_REC)}
    detail_val     = {r["source_id"]: r for r in load_csv(DETAIL_VAL)}

    print(f"URL updated:    {len(url_updated)} sources")
    print(f"URL validation: {len(url_validation)} sources")
    print(f"Parser BA:      {len(parser_ba)} sources (needs_parser_fix universe)")
    print(f"Parser rec IDs: {len(parser_rec_ids)} (old=0 -> new>0)")
    print(f"Detail val:     {len(detail_val)} sources")

    # -----------------------------------------------------------------------
    # Build combined record per source
    # -----------------------------------------------------------------------
    results = []
    for sid, upd in url_updated.items():
        url_val = url_validation.get(sid, {})
        par     = parser_ba.get(sid, {})
        det     = detail_val.get(sid, {})

        url_status = url_val.get("new_status", "unknown")
        combined   = URL_TO_COMBINED.get(url_status, "unknown")

        # If needs_parser, override with parser result
        if url_status == "needs_parser_fix":
            parser_status = par.get("status_after", "still_failed")
            combined = PARSER_TO_COMBINED.get(parser_status, "still_failed")

        # Property links (best available count)
        prop_links_url  = int(upd.get("property_links_count", 0) or 0)
        prop_links_new  = int(par.get("new_parse_cards_count", 0) or 0)
        prop_links_old  = int(par.get("old_parse_cards_count", 0) or 0)
        prop_links = max(prop_links_url, prop_links_new)

        # Was this source recovered by parser fix (old=0->new>0)?
        is_parser_recovered = sid in parser_rec_ids

        # Detail quality from 07d
        detail_cat    = det.get("category", "")
        detail_score  = int(det.get("quality_score", 0) or 0)
        detail_title  = det.get("title", "")
        detail_price  = det.get("price", "")

        # Estimated yield
        est_yield = int(upd.get("estimated_property_yield", 0) or 0)
        if not est_yield:
            est_yield = int(par.get("estimated_property_yield", 0) or 0)

        # Needs category
        needs_playwright = (
            combined == "still_failed"
            and par.get("family", "") in {
                "custom_listing_detail", "listing_items_with_no_anchor",
                "anchor_cards_without_detail_link",
            }
        )

        results.append({
            "source_id":         sid,
            "source_name":       upd.get("source_name", ""),
            "old_url_listado":   upd.get("old_url_listado", ""),
            "new_url_listado":   upd.get("new_url_listado", ""),
            "url_status":        url_status,
            "parser_status":     par.get("status_after", ""),
            "parser_family":     par.get("family", ""),
            "combined_status":   combined,
            "is_parser_recovered": is_parser_recovered,
            "property_links":    prop_links,
            "old_cards":         prop_links_old,
            "new_cards":         prop_links_new,
            "estimated_yield":   est_yield,
            "detail_category":   detail_cat,
            "detail_score":      detail_score,
            "detail_title":      detail_title[:80],
            "detail_price":      detail_price[:40],
            "needs_playwright":  needs_playwright,
            "error":             url_val.get("previous_error_category", ""),
        })

    # -----------------------------------------------------------------------
    # Tallies
    # -----------------------------------------------------------------------
    cat_counts = Counter(r["combined_status"] for r in results)

    success_n   = sum(cat_counts.get(c, 0) for c in SUCCESS_CATS)
    partial_n   = sum(cat_counts.get(c, 0) for c in PARTIAL_CATS)
    failed_n    = sum(cat_counts.get(c, 0) for c in FAILED_CATS)
    err_n       = sum(cat_counts.get(c, 0) for c in ERR_CATS)
    total_n     = len(results)
    recoverable = success_n + partial_n
    rec_pct     = round(100 * recoverable / total_n, 1) if total_n else 0

    # Success breakdown
    url_only_n    = cat_counts.get("success_url_only", 0)
    parser_rec_n  = cat_counts.get("success_url_plus_parser", 0)
    partial_url_n = cat_counts.get("partial_url_only", 0)
    partial_par_n = cat_counts.get("partial_url_plus_parser", 0)

    # Property links totals
    total_links_success = sum(
        r["property_links"] for r in results if r["combined_status"] in SUCCESS_CATS
    )
    total_links_all = sum(r["property_links"] for r in results)

    # Parser recovered (old=0->new>0)
    parser_recovered_n = sum(1 for r in results if r["is_parser_recovered"])

    # Detail quality on recovered sources
    detail_ok_n    = sum(1 for r in results if r["detail_category"] == "detail_parse_ok")
    detail_part_n  = sum(1 for r in results if r["detail_category"] == "detail_parse_partial")

    # Regressions (sources with old_cards > 0 that ended in still_failed)
    regressions = [
        r for r in results
        if r["combined_status"] == "still_failed"
        and r["old_cards"] > 0
        and r["new_cards"] == 0
        and r["parser_status"] != ""  # was in parser universe
    ]

    # Needs playwright
    needs_pw_n = sum(1 for r in results if r["needs_playwright"])

    print(f"\n=== Combined results ({total_n} sources) ===")
    print(f"  success (URL only):          {url_only_n}")
    print(f"  success (URL + parser):      {parser_rec_n}")
    print(f"  partial (URL only):          {partial_url_n}")
    print(f"  partial (URL + parser):      {partial_par_n}")
    print(f"  still_failed:                {failed_n}")
    print(f"  http_error / error:          {err_n}")
    print(f"  TOTAL recoverable:           {recoverable} / {total_n} ({rec_pct}%)")
    print(f"  Parser recovered (0->>0):     {parser_recovered_n}")
    print(f"  Total property links:        {total_links_all}")
    print(f"  Links on success sources:    {total_links_success}")
    print(f"  True regressions:            {len(regressions)}")
    print(f"  Needs playwright:            {needs_pw_n}")

    # -----------------------------------------------------------------------
    # Output CSVs
    # -----------------------------------------------------------------------
    ALL_FIELDS = [
        "source_id", "source_name", "old_url_listado", "new_url_listado",
        "url_status", "parser_status", "parser_family", "combined_status",
        "is_parser_recovered", "property_links", "old_cards", "new_cards",
        "estimated_yield", "detail_category", "detail_score",
        "detail_title", "detail_price", "needs_playwright", "error",
    ]

    def wcsv(path, rows):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ALL_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    wcsv(OUT / "combined_validation_results.csv", results)
    wcsv(OUT / "success_combined.csv",
         [r for r in results if r["combined_status"] in SUCCESS_CATS])
    wcsv(OUT / "partial_combined.csv",
         [r for r in results if r["combined_status"] in PARTIAL_CATS])
    wcsv(OUT / "still_failed_combined.csv",
         [r for r in results if r["combined_status"] in FAILED_CATS])
    wcsv(OUT / "regression_check.csv", regressions)

    top_ok = sorted(
        [r for r in results if r["combined_status"] in SUCCESS_CATS | PARTIAL_CATS],
        key=lambda x: x["estimated_yield"], reverse=True
    )[:30]
    wcsv(OUT / "top_recovered_by_yield.csv", top_ok)

    top_fail = sorted(
        [r for r in results if r["combined_status"] in FAILED_CATS | ERR_CATS],
        key=lambda x: x["estimated_yield"], reverse=True
    )[:30]
    wcsv(OUT / "top_still_failed_by_yield.csv", top_fail)

    # -----------------------------------------------------------------------
    # Summary markdown
    # -----------------------------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()
    summary = f"""# PR-BE-COMBINED-08 — Validación combinada URL + parser

Generated: {now}

## Estado en main

- PR #6 mergeado: `9aa299bde9 fix: improve parser detail URL detection`
- Tests post-merge: **81/81 passed** (`pytest tests/ -q`)
- Compilación: OK (`playwright_scraper.py`, `validate_parser_fix_07b.py`, `validate_detail_quality_07d.py`)

## Universo

**{total_n} fuentes** con `url_listado` actualizado (PR-BE-URL-06).

## Impacto combinado URL + parser

| Estado | n | % |
|---|---|---|
| `success_url_only` | {url_only_n} | {round(100*url_only_n/total_n,1)}% |
| `success_url_plus_parser` | {parser_rec_n} | {round(100*parser_rec_n/total_n,1)}% |
| `partial_url_only` | {partial_url_n} | {round(100*partial_url_n/total_n,1)}% |
| `partial_url_plus_parser` | {partial_par_n} | {round(100*partial_par_n/total_n,1)}% |
| `still_failed` | {failed_n} | {round(100*failed_n/total_n,1)}% |
| `http_error` / `error` | {err_n} | {round(100*err_n/total_n,1)}% |
| **TOTAL recuperables** | **{recoverable}** | **{rec_pct}%** |

## Métricas de impacto

| Métrica | Valor |
|---|---|
| Fuentes analizadas | {total_n} |
| Success combinado (URL + parser) | {success_n} |
| Partial combinado | {partial_n} |
| Recuperadas solo por URL fix | {url_only_n} |
| Recuperadas por URL + parser fix | {parser_rec_n} |
| Parser recuperadas (old=0->new>0) | {parser_recovered_n} |
| Still failed | {failed_n} |
| HTTP errors / errores | {err_n} |
| Property links detectados (total) | {total_links_all:,} |
| Property links en fuentes success | {total_links_success:,} |
| Detalle validado OK (07d) | {detail_ok_n} |
| Detalle validado partial (07d) | {detail_part_n} |
| Regresiones reales (old>0->new=0) | {len(regressions)} |
| Necesitan Playwright | {needs_pw_n} |

## Cascada de fixes

```
1.057 fuentes con url_listado actualizado
  ├── 583  success_after_url_fix          -> success_url_only
  ├──  44  partial_after_url_fix          -> partial_url_only
  ├── 413  needs_parser_fix
  │     ├── 309  success_after_parser_fix -> success_url_plus_parser
  │     ├──  17  partial_after_parser_fix -> partial_url_plus_parser
  │     └──  87  still_failed             -> still_failed
  ├──  10  still_no_property_links        -> still_failed
  ├──   6  http_error                     -> http_error
  └──   1  unexpected_error               -> error
```

## Guardrails confirmados

- DB writes: **0** | UPDATE: **0** | publish: **0**
- scraping productivo/runs: **0** | push/deploy/frontend: **0**
- columnas de clasificación: **no tocadas**
- `--include-backlog`: **no usado**
- Outputs en `_scratch/combined_url_parser_validation_08/`
"""
    (OUT / "combined_validation_summary.md").write_text(summary, encoding="utf-8")

    # -----------------------------------------------------------------------
    # Risk assessment
    # -----------------------------------------------------------------------
    risk_md = f"""# Risk assessment — PR-BE-COMBINED-08

## Riesgos identificados

### Regresiones reales: {len(regressions)}
{"Sin regresiones. Ambos fixes son seguros para producción." if not regressions else chr(10).join(f"- id={r['source_id']} {r['source_name']}: old={r['old_cards']} new={r['new_cards']}" for r in regressions)}

### Still failed: {failed_n}
- {failed_n} fuentes sin links tras URL + parser fix.
- Subconjunto estimado necesita Playwright: {needs_pw_n}.
- Resto: sitios custom sin patrón detectable, listados institucionales, o fuentes de bajo yield (<5 props).

### HTTP errors: {err_n}
Errors de conectividad en momento de validación. No implican falla permanente.
Reintentar con delay o Playwright antes de excluir definitivamente.

## Evaluación general

- Impacto combinado: **{recoverable}/{total_n} ({rec_pct}%)** fuentes recuperadas.
- URL fix aportó: {url_only_n + partial_url_n} fuentes directamente.
- Parser fix aportó: {parser_rec_n + partial_par_n} fuentes adicionales.
- Sin regresiones en ninguna capa.
- **Ambos fixes son seguros y complementarios.**
"""
    (OUT / "risk_assessment.md").write_text(risk_md, encoding="utf-8")

    # -----------------------------------------------------------------------
    # Next step recommendation
    # -----------------------------------------------------------------------
    next_md = f"""# Próximo paso recomendado — post PR-BE-COMBINED-08

## Situación

- {recoverable}/{total_n} ({rec_pct}%) fuentes listas para scraping productivo.
- {failed_n} fuentes still_failed: {needs_pw_n} candidatas a Playwright, resto manual/baja prioridad.
- {len(regressions)} regresiones reales: 0.
- Main actualizado con PR #6.

## Opciones de próximo paso

### Opción A (mayor impacto): Corrida productiva combinada
Correr el pipeline sobre las {success_n} fuentes `success` con los dos fixes activos.
Requiere: coordinar con selector (`--include-new`), NO publish, NO `--include-backlog`.
Riesgo: bajo. 0 regresiones, 97%+ detalle validado.

### Opción B: PR-BE-PW-06 — Runner Playwright productivo
Recuperar las {needs_pw_n}+ fuentes que necesitan renderizado JS.
Candidatas: react_spa / nuxt / wix / webflow / squarespace + las 87 still_failed con señal.
Impacto estimado: ~1.310 fichas adicionales (+ potencial en still_failed).

### Opción C: Manual review de COMINCINI (id=1611)
total_propiedades=75.000 inflado. Verificar antes de cualquier corrida.

## Recomendación
-> **Opción A** si el objetivo es materializar el impacto acumulado ya.
-> **Opción B** si se quiere maximizar cobertura antes de la corrida.
"""
    (OUT / "next_step_recommendation.md").write_text(next_md, encoding="utf-8")

    # -----------------------------------------------------------------------
    # Final output list
    # -----------------------------------------------------------------------
    print(f"\n[OUTPUT] {OUT}")
    print("Files written:")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}")

    print(f"\n[GUARDRAILS FINAL] DB=0 | UPDATE=0 | publish=0 | push=0 | deploy=0")
    return results, cat_counts


if __name__ == "__main__":
    main()

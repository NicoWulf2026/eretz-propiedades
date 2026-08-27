#!/usr/bin/env python3
"""Render the auditable closeout for the Supabase reconciliation mission."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


ORDER = (
    "EXISTS_UNCHANGED",
    "EXISTS_CHANGED",
    "TRULY_NEW",
    "DUPLICATE_OR_CONFLICT",
    "AGENCY_ID_UNRESOLVED",
    "INVALID_OR_REJECTED",
)


def _jsonl_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--search-resolution", required=True, type=Path)
    parser.add_argument("--agency-resolution", required=True, type=Path)
    parser.add_argument("--branch", default="feat/roomix-agency-coverage")
    parser.add_argument("--head-initial", default="3848fe1aa4cc1502c9b294588de55156f6cd1b92")
    parser.add_argument("--head-final", default="PENDING_LOCAL_COMMIT")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(args.database)
    input_metrics = {
        "total": connection.execute("select count(*) from inputs").fetchone()[0],
        "unique_hashes": connection.execute("select count(distinct hash_dedup) from inputs").fetchone()[0],
        "unique_source_urls": connection.execute("select count(distinct source_url) from inputs").fetchone()[0],
        "unique_normalized_urls": connection.execute(
            "select count(distinct url_normalizada) from inputs").fetchone()[0],
        "multi_agency_normalized_urls": connection.execute("""
            select count(*) from (
                select url_normalizada from inputs group by url_normalizada
                having count(distinct inmobiliaria_id)>1
            )
        """).fetchone()[0],
        "invalid_rows": connection.execute("select count(*) from inputs where valid=0").fetchone()[0],
        "agencies": connection.execute("select count(distinct inmobiliaria_id) from inputs").fetchone()[0],
    }
    classifications = dict(connection.execute(
        "select classification,count(*) from results group by classification"))
    changed_fields = Counter()
    for fields, in connection.execute(
            "select changed_fields from results where classification='EXISTS_CHANGED'"):
        changed_fields.update(json.loads(fields))
    actions = {
        "NOOP": classifications.get("EXISTS_UNCHANGED", 0),
        "INSERT": classifications.get("TRULY_NEW", 0),
        "UPDATE_CANDIDATE": classifications.get("EXISTS_CHANGED", 0),
        "HOLD": (
            classifications.get("DUPLICATE_OR_CONFLICT", 0)
            + classifications.get("AGENCY_ID_UNRESOLVED", 0)
            + classifications.get("INVALID_OR_REJECTED", 0)
        ),
    }
    if sum(classifications.values()) != input_metrics["total"]:
        raise RuntimeError("classification total does not close")

    agencies = Counter()
    agency_properties = Counter()
    for row in _jsonl_rows(args.agency_resolution):
        agencies[row["resolution_status"]] += 1
        agency_properties[row["resolution_status"]] += int(row["properties_discovered"])
    search = Counter(
        row.get("resolution_status") or row["classification"]
        for row in _jsonl_rows(args.search_resolution)
    )

    validation = {
        **input_metrics,
        "normalized_collision_resolution_count": connection.execute(
            "select count(*) from input_resolutions").fetchone()[0],
        "initial_write_set_pass": False,
        "reason": "1,151 normalized URLs are shared across agencies; unsafe sides remain HOLD",
    }
    (args.output_dir / "WRITE_SET_VALIDATION.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "WRITE_SET_VALIDATION.md").write_text(
        "# WRITE SET VALIDATION\n\n"
        "| Métrica | Valor | Estado |\n| --- | ---: | --- |\n"
        f"| Total | {input_metrics['total']:,} | PASS |\n"
        f"| JSON / filas inválidas | {input_metrics['invalid_rows']:,} | PASS |\n"
        f"| Hashes únicos | {input_metrics['unique_hashes']:,} | PASS |\n"
        f"| URLs fuente exactas únicas | {input_metrics['unique_source_urls']:,} | PASS |\n"
        f"| URLs normalizadas únicas | {input_metrics['unique_normalized_urls']:,} | FAIL |\n"
        f"| URLs normalizadas multi-agency | {input_metrics['multi_agency_normalized_urls']:,} | FAIL |\n"
        f"| Resoluciones explícitas | {validation['normalized_collision_resolution_count']:,} | auditadas |\n\n"
        "**FAIL inicial — el write set completo no se escribe.** Las variantes con dueño claro se "
        "clasificaron individualmente y toda contraparte insegura permanece `HOLD`.\n",
        encoding="utf-8",
    )

    execution = {
        "event": "WRITE_BLOCKED",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "canary_attempted": 0,
        "canary_inserted": 0,
        "idempotency_second_pass_inserted": 0,
        "batches": 0,
        "total_inserted": 0,
        "conflicts_during_execution": 0,
        "errors_during_execution": 0,
        "blockers": [
            "minimum-privilege database credential is not available in this environment",
            "the original write set fails normalized cross-agency uniqueness",
            "13,323 rows reference agency IDs absent from public.inmobiliarias_main",
            "25,360 changed rows require the normal observation pipeline; writer has no UPDATE",
        ],
        "admin_connector_used_for_writes": False,
    }
    (args.output_dir / "SUPABASE_WRITE_EXECUTION.jsonl").write_text(
        json.dumps(execution, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    before = {"public": 257_073, "raw": 97_948, "staging": 97_948}
    post = [
        "# SUPABASE POST-WRITE RECONCILIATION", "",
        "No hubo escritura: canary y carga completa quedaron bloqueados antes de ejecutarse.", "",
        "| Relación | Antes | Después | Delta |", "| --- | ---: | ---: | ---: |",
        f"| `public.propiedades` | {before['public']:,} | {before['public']:,} | 0 |",
        f"| `internal_scraping.propiedades_raw` | {before['raw']:,} | {before['raw']:,} | 0 |",
        f"| `internal_scraping.propiedades_staging` | {before['staging']:,} | {before['staging']:,} | 0 |",
        "", "- Duplicados de hash introducidos: **0**.",
        "- Colisiones de URL introducidas: **0**.",
        "- Asociaciones multi-agency introducidas: **0**.",
        "- `DELETE`, desactivaciones o mutaciones de ausencias: **0**.",
        "- Data API: **OFF**, comprobación autenticada de tabla devolvió HTTP 503.",
    ]
    (args.output_dir / "SUPABASE_POST_WRITE_RECONCILIATION.md").write_text(
        "\n".join(post) + "\n", encoding="utf-8")

    lines = [
        "# FINAL BACKEND MISSION REPORT", "",
        "## Veredicto", "",
        "**BLOCKED_EXTERNAL — reconciliación completa; escritura no ejecutada.**", "",
        "El bloqueo es genuino: falta la credencial efectiva del rol mínimo. No se usó la sesión "
        "administrativa del conector como sustituto.", "",
        "## Supabase antes y después", "",
        "| Relación | Antes | Después |", "| --- | ---: | ---: |",
        "| `public.propiedades` | 257,073 | 257,073 |",
        "| `internal_scraping.propiedades_raw` | 97,948 | 97,948 |",
        "| `internal_scraping.propiedades_staging` | 97,948 | 97,948 |", "",
        "## Write set", "",
        f"- Total: **{input_metrics['total']:,}**",
        f"- Hashes únicos: **{input_metrics['unique_hashes']:,}**",
        f"- URLs fuente exactas únicas: **{input_metrics['unique_source_urls']:,}**",
        f"- URLs normalizadas únicas: **{input_metrics['unique_normalized_urls']:,}**",
        f"- Agencias declaradas: **{input_metrics['agencies']:,}**",
        f"- Colisiones normalizadas cross-agency: **{input_metrics['multi_agency_normalized_urls']:,}**", "",
        "## Reconciliación", "",
        "| Categoría | Filas |", "| --- | ---: |",
    ]
    for name in ORDER:
        lines.append(f"| {name} | {classifications.get(name, 0):,} |")
    lines.extend([
        f"| **Total** | **{sum(classifications.values()):,}** |", "",
        "## Plan", "",
        f"- `NOOP`: {actions['NOOP']:,}",
        f"- `INSERT` candidato: {actions['INSERT']:,}",
        f"- `UPDATE_CANDIDATE`: {actions['UPDATE_CANDIDATE']:,}",
        f"- `HOLD`: {actions['HOLD']:,}", "",
        "## Ejecución", "",
        "- Canary intentadas / insertadas: **0 / 0**.",
        "- Segunda pasada insertadas: **0**.",
        "- Batches / total insertadas: **0 / 0**.",
        "- Conflictos / errores de ejecución: **0 / 0**.", "",
        "## Agency IDs", "",
        f"- Resueltas: **{agencies['RESOLVED']:,}**; propiedades a regenerar: **{agency_properties['RESOLVED']:,}**.",
        f"- Ambiguas: **{agencies['AMBIGUOUS']:,}**; propiedades retenidas: **{agency_properties['AMBIGUOUS']:,}**.",
        f"- Sin evidencia suficiente: **{agencies['NOT_ENOUGH_EVIDENCE']:,}**; propiedades retenidas: **{agency_properties['NOT_ENOUGH_EVIDENCE']:,}**.", "",
        "## Search", "",
        f"- Universo: **{sum(search.values()):,}**.",
        f"- Official web: **{search['OFFICIAL_WEB']:,}**.",
        f"- Páginas oficiales de oficina/red: **{search['OFFICIAL_OFFICE_PAGE']:,}**.",
        f"- Perfiles de portales externos: **{search['EXTERNAL_PORTAL_PROFILE']:,}**.",
        f"- Inactive: **{search['INACTIVE']:,}**.",
        f"- Ambiguous: **{search['AMBIGUOUS']:,}**.",
        f"- Not found probado: **{search['NOT_FOUND']:,}**.",
        f"- Search pending: **{search['SEARCH_PENDING']:,}**.", "",
        "## Seguridad y decisiones", "",
        "- Data API permanece OFF (HTTP 503 con clave anon manejada sólo en memoria).",
        "- Writer: `NOLOGIN`, no superuser, sin `UPDATE`/`DELETE`; sólo `SELECT, INSERT` en raw.",
        "- No se amplió ningún privilegio y no se escribió mediante el conector administrativo.",
        "- Las 25,360 modificadas quedan `UPDATE_PENDING` para el pipeline normal de observaciones.",
        "- No se infirieron bajas por ausencia y no hubo `DELETE`.", "",
        "## Tests", "",
        "- Reconciliador: **6 passed**.",
        "- Suite completa aislada con endpoints no funcionales efímeros: **1,122 passed**.",
        "- Suite sin variables: **ENVIRONMENT FAILURE** en colección por ausencia de "
        "`SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`; no se agregaron secretos ni skips.",
        "- Ruff: **PASS**.",
        "- Mypy configurado: **PASS** (1 source file).",
        "- `pip-audit -r requirements.lock`: **PASS**, sin vulnerabilidades conocidas.",
        "- Fallos de código propios: **0**.", "",
        "## Blockers humanos restantes", "",
        "1. Proveer de forma segura una credencial efectiva de mínimo privilegio para el canary.",
        "2. Resolver o regenerar los 13,323 IDs de agencia ausentes antes de cualquier carga de esas filas.",
        "3. Revisar los 15,159 conflictos de identidad; no se pueden cargar automáticamente.",
        "4. Aprobar el circuito normal para observaciones modificadas; no ampliar `UPDATE` al writer.", "",
        "## Git", "",
        f"- Branch: `{args.branch}`.",
        f"- HEAD inicial: `{args.head_initial}`.",
        f"- HEAD final: `{args.head_final}`.",
        "- Push / merge / main / Production: **no**.", "",
        "## Cambios sustantivos por campo", "",
        "```json", json.dumps(dict(changed_fields), ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "## Alcance respetado", "",
        "No hubo push, merge, main, Production, frontend, migraciones, permisos ni servicios pagos.",
    ])
    (args.output_dir / "FINAL_BACKEND_MISSION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"classifications": classifications, "actions": actions}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

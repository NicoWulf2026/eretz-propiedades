#!/usr/bin/env python
"""PR-BE-DATA-01 — Propuesta de limpieza del universo de inmobiliarias.

SOLO PROPUESTA. NO escribe DB. NO publica. NO scrapea. Genera archivos locales
revisables con la accion recomendada para cada una de las 7.004 inmobiliarias,
combinando el censo HTTP + la pasada Playwright.

--commit NO esta implementado en este PR (queda bloqueado con error explicito).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
from collections import Counter
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEF_HTTP = REPO_ROOT / "_scratch" / "full_source_diagnostic_7004" / "diagnostic_results.jsonl"
DEF_PW = REPO_ROOT / "_scratch" / "full_source_diagnostic_7004_playwright_pass" / "playwright_results.jsonl"


def load_env(p):
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(p):
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            out[r["source_id"]] = r
        except Exception:
            continue
    return out


def db_sitio_activo():
    """Read-only: {id: sitio_activo}. Si no hay DB, devuelve {} (no bloquea)."""
    load_env(REPO_ROOT / ".env")
    load_env(REPO_ROOT / ".env.local")
    url = os.getenv("INTERNAL_DB_URL", "").strip()
    if not url:
        return {}
    try:
        import psycopg
        conn = psycopg.connect(url, connect_timeout=30)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        cur.execute("SELECT id, sitio_activo FROM public.inmobiliarias_main")
        d = {r[0]: r[1] for r in cur.fetchall()}
        conn.close()
        return d
    except Exception as e:
        print(f"[warn] no se pudo leer sitio_activo (read-only): {str(e)[:120]}")
        return {}


ACTION_FAMILY = {
    "keep_ready_to_scrape": "ready",
    "reincorporate_misclassified_ready": "ready",
    "exclude_missing_url": "cleanup",
    "exclude_domain_down": "cleanup",
    "exclude_prohibited_source": "cleanup",
    "needs_cms_strategy_fix": "cms_strategy",
    "needs_parser_fix": "parser",
    "needs_listing_url_fix": "url",
    "needs_playwright_runner": "playwright",
    "needs_quality_fix": "quality",
    "manual_review": "manual",
}


def yint(v):
    try:
        return int(v or 0)
    except Exception:
        return 0


def decide(h, pw, sitio_activo):
    """Devuelve (action, reason, db_change, requires_db_write_later, risk)."""
    st = h.get("final_status")
    if h.get("is_prohibited_source"):
        return ("exclude_prohibited_source", "fuente prohibida por regla de ERETZ (zonaprop/argenprop/portal)",
                "set sitio_activo=false; marcar excluida", True, "ninguno")
    if st == "missing_url":
        return ("exclude_missing_url", "sin web ni url_listado",
                "set sitio_activo=false", True, "bajo")
    if st in ("dns_error", "domain_down"):
        return ("exclude_domain_down", "dominio no resuelve / conexion fallida",
                "set sitio_activo=false", True, "bajo")
    if st == "success":
        if sitio_activo is False:
            return ("reincorporate_misclassified_ready", "marcada no-scrapeable en DB pero scrapea OK",
                    "set sitio_activo=true", True, "bajo")
        return ("keep_ready_to_scrape", "scrapea OK por HTTP", "ninguno (ya activa)", False, "ninguno")
    if st == "success_low_quality":
        return ("needs_quality_fix", "scrapea pero faltan campos clave",
                "ninguno (fix de parser/normalizacion)", False, "bajo")
    # las que pasaron por Playwright (requires_playwright / antibot / forbidden / captcha)
    if pw is not None:
        pst = pw.get("playwright_final_status")
        if pst in ("playwright_success", "playwright_success_low_quality"):
            return ("needs_playwright_runner", "recuperada con Playwright (SPA/JS)",
                    "ninguno (requiere runner Playwright productivo)", False, "medio")
        if pst in ("playwright_no_property_links", "playwright_zero_properties", "playwright_parser_error"):
            return ("needs_parser_fix", "renderiza con JS pero no expone fichas parseables",
                    "ninguno (fix de selectores por familia)", False, "medio")
        if pst == "playwright_true_antibot":
            return ("manual_review", "antibot real confirmado con Playwright",
                    "ninguno (revision manual)", False, "alto")
        return ("manual_review", f"playwright {pst}", "ninguno", False, "medio")
    # problemas HTTP que NO pasaron por Playwright
    if st == "cms_unknown":
        return ("needs_cms_strategy_fix", "cms desconocido + sin links",
                "update cms_detectado/estrategia_scraping (despues)", True, "medio")
    if st in ("no_property_links", "parser_error"):
        return ("needs_parser_fix", "carga pero el selector no encuentra links/fichas",
                "ninguno (fix de parser por familia)", False, "medio")
    if st in ("bad_listing_url", "not_found", "ssl_error"):
        return ("needs_listing_url_fix", "URL de listado mala (404/ssl/bad)",
                "update url_listado (despues)", True, "medio")
    if st in ("timeout", "server_error", "rate_limited", "forbidden"):
        return ("manual_review", f"transitorio/infra: {st}", "ninguno (retry/manual)", False, "bajo")
    return ("manual_review", f"sin clasificar: {st}", "ninguno", False, "bajo")


def priority_of(action, yield_):
    if action in ("keep_ready_to_scrape", "reincorporate_misclassified_ready"):
        return "ready"
    if action in ("exclude_missing_url", "exclude_domain_down", "exclude_prohibited_source"):
        return "low"
    if yield_ >= 1000:
        return "high"
    if yield_ >= 200:
        return "medium"
    return "low"


TABLE = "public.inmobiliarias_main"

# Subgrupos conservadores de fix_sitio_activo (sitio_activo=true pero NO ready).
# SOLO confirmed_down es candidato real a sitio_activo=false.
def sitio_activo_subgroup(r):
    st = r.get("http_final_status")
    act = r.get("recommended_action")
    if st in ("dns_error", "domain_down"):
        return "sitio_activo_false_positive_confirmed_down"
    if st == "missing_url":
        return "sitio_activo_true_but_missing_url"
    if act == "needs_cms_strategy_fix":
        return "sitio_activo_true_but_needs_cms_strategy"
    if act == "needs_parser_fix":
        return "sitio_activo_true_but_needs_parser"
    if act == "needs_listing_url_fix":
        return "sitio_activo_true_but_needs_listing_url"
    if act == "needs_playwright_runner":
        return "sitio_activo_true_but_needs_playwright"
    return "sitio_activo_true_manual_review"


def db_action_for(r):
    """Devuelve (update_type, target_column, proposed_value, confidence, risk, requires_manual, reason, sql_preview)."""
    sid = r["source_id"]
    sa = r.get("current_sitio_activo")
    st = r.get("http_final_status")
    act = r.get("recommended_action")
    if act == "exclude_prohibited_source":
        return ("set_diagnostic_status", "diagnostic_status (FUTURA)", "excluded_prohibited", "alta", "ninguno", False,
                "fuente prohibida; la web puede estar viva -> NO marcar sitio_activo=false; excluir por columna nueva o filtro de selector",
                f"-- requiere columna nueva: UPDATE {TABLE} SET diagnostic_status='excluded_prohibited' WHERE id={sid};")
    if st in ("dns_error", "domain_down") and sa is True:
        return ("set_sitio_activo_false", "sitio_activo", False, "alta", "bajo", False,
                f"web no responde (censo={st}) y sitio_activo=true -> falso positivo real",
                f"UPDATE {TABLE} SET sitio_activo=false WHERE id={sid}; -- censo={st}")
    if act == "reincorporate_misclassified_ready" and sa is False:
        return ("set_sitio_activo_true", "sitio_activo", True, "alta", "bajo", False,
                "scrapea OK (censo=success) pero sitio_activo=false -> reincorporar",
                f"UPDATE {TABLE} SET sitio_activo=true WHERE id={sid}; -- censo=success")
    if act == "exclude_missing_url":
        return ("set_diagnostic_status", "diagnostic_status (FUTURA)", "no_url", "media", "ninguno", True,
                "sin URL: no se puede confirmar si la web esta caida -> NO tocar sitio_activo; marcar estado y conseguir URL",
                f"-- requiere columna nueva: UPDATE {TABLE} SET diagnostic_status='no_url' WHERE id={sid};")
    if act in ("needs_cms_strategy_fix", "needs_parser_fix", "needs_listing_url_fix", "needs_playwright_runner", "needs_quality_fix"):
        return ("set_diagnostic_status", "diagnostic_status (FUTURA)", act.replace("needs_", "").replace("_fix", ""),
                "media", "ninguno", False,
                "web viva, requiere fix -> NO tocar sitio_activo; marcar estado diagnostico",
                f"-- requiere columna nueva: UPDATE {TABLE} SET diagnostic_status='{act}' WHERE id={sid};")
    if act == "keep_ready_to_scrape":
        return ("no_db_change", "-", None, "alta", "ninguno", False, "ya ready y activa", "-- sin cambio")
    return ("no_db_change_manual", "diagnostic_status (FUTURA)", "manual_review", "baja", "ninguno", True,
            f"transitorio/sin clasificar ({st}) -> revisar manual antes de cualquier cambio",
            f"-- revisar manual: id={sid} status={st}")


def write_db_dry_run(rows, db_out):
    db_out.mkdir(parents=True, exist_ok=True)
    actions = []
    subgroups = Counter()
    for r in rows:
        ut, col, pv, conf, risk, manual, reason, sqlp = db_action_for(r)
        sg = None
        if r.get("current_sitio_activo") is True and r.get("recommended_action_family") not in ("ready",):
            sg = sitio_activo_subgroup(r)
            subgroups[sg] += 1
        actions.append({
            "source_id": r["source_id"], "source_name": r["source_name"],
            "current_sitio_activo": r.get("current_sitio_activo"),
            "current_sitio_activo_reason": f"DB={r.get('current_sitio_activo')} vs censo={r.get('http_final_status')}",
            "recommended_action": r["recommended_action"], "recommended_db_update_type": ut,
            "target_column": col, "current_value": r.get("current_sitio_activo"), "proposed_value": pv,
            "confidence": conf, "risk": risk, "requires_manual_review": manual, "reason": reason,
            "sql_preview": sqlp, "sitio_activo_subgroup": sg,
        })
    acols = ["source_id", "source_name", "current_sitio_activo", "current_sitio_activo_reason",
             "recommended_action", "recommended_db_update_type", "target_column", "current_value",
             "proposed_value", "confidence", "risk", "requires_manual_review", "reason", "sql_preview"]
    with (db_out / "db_dry_run_actions.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=acols, extrasaction="ignore"); w.writeheader()
        for a in actions:
            w.writerow(a)
    with (db_out / "sitio_activo_subgroups.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["source_id", "source_name", "http_final_status", "subgroup"])
        for r in rows:
            if r.get("current_sitio_activo") is True and r.get("recommended_action_family") not in ("ready",):
                w.writerow([r["source_id"], r["source_name"], r.get("http_final_status"), sitio_activo_subgroup(r)])
    with (db_out / "manual_review_before_db.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["source_id", "source_name", "http_final_status", "recommended_action", "reason"])
        for a in actions:
            if a["requires_manual_review"]:
                w.writerow([a["source_id"], a["source_name"], "", a["recommended_action"], a["reason"]])

    def ids(pred):
        return [r["source_id"] for r in rows if pred(r)]

    HEADER = "-- ====== DRY RUN — NO EJECUTAR ======\n-- Generado por apply_universe_cleanup.py --db-dry-run. NINGUN cambio fue aplicado a la DB.\n"
    MIGRATION = ("-- (FUTURO, requiere autorizacion) columna de estado diagnostico para NO sobrecargar\n"
                 "-- sitio_activo (=web responde) ni estrategia_scraping (=como scrapear):\n"
                 f"-- ALTER TABLE {TABLE} ADD COLUMN diagnostic_status text;\n"
                 f"-- COMMENT ON COLUMN {TABLE}.diagnostic_status IS 'estado del censo diagnostico (ready/needs_*/excluded_*/down/no_url/manual)';\n\n")

    def batched_update(setclause, id_list, note):
        if not id_list:
            return f"-- (0 filas) {note}\n"
        chunks = [id_list[i:i + 500] for i in range(0, len(id_list), 500)]
        out = [f"-- {note}: {len(id_list)} filas"]
        for ch in chunks:
            out.append(f"UPDATE {TABLE} SET {setclause} WHERE id IN ({','.join(str(x) for x in ch)});")
        return "\n".join(out) + "\n"

    down_ids = ids(lambda r: r.get("http_final_status") in ("dns_error", "domain_down") and r.get("current_sitio_activo") is True)
    reinc_ids = ids(lambda r: r.get("recommended_action") == "reincorporate_misclassified_ready" and r.get("current_sitio_activo") is False)
    prohib_ids = ids(lambda r: r.get("recommended_action") == "exclude_prohibited_source")
    nourl_ids = ids(lambda r: r.get("recommended_action") == "exclude_missing_url")

    (db_out / "candidate_domain_down.sql").write_text(
        HEADER + "-- SEGURO: web NO responde (dns_error/domain_down) y sitio_activo=true -> sitio_activo=false.\n"
        "-- NO incluye timeout/server_error/ssl (la web SI responde).\n" +
        batched_update("sitio_activo=false", down_ids, "confirmed_down -> sitio_activo=false"), encoding="utf-8")
    (db_out / "candidate_reincorporate_misclassified.sql").write_text(
        HEADER + "-- SEGURO: scrapean OK pero estaban sitio_activo=false -> sitio_activo=true.\n" +
        batched_update("sitio_activo=true", reinc_ids, "reincorporate -> sitio_activo=true"), encoding="utf-8")
    (db_out / "candidate_exclude_prohibited.sql").write_text(
        HEADER + "-- Prohibidas: la web puede estar VIVA -> NO marcar sitio_activo=false.\n"
        "-- Excluir por columna nueva diagnostic_status o por filtro del selector de scraping.\n" + MIGRATION +
        batched_update("diagnostic_status='excluded_prohibited'", prohib_ids, "prohibidas (requiere columna nueva)"), encoding="utf-8")
    (db_out / "candidate_missing_url.sql").write_text(
        HEADER + "-- Sin URL: NO se puede confirmar caida -> NO tocar sitio_activo. Marcar estado y conseguir URL.\n" + MIGRATION +
        batched_update("diagnostic_status='no_url'", nourl_ids, "sin_url (requiere columna nueva)"), encoding="utf-8")
    (db_out / "db_dry_run_actions.sql").write_text(
        HEADER + MIGRATION +
        "-- ===== CAMBIOS SEGUROS (sitio_activo, reversibles) =====\n" +
        batched_update("sitio_activo=false", down_ids, "A) confirmed_down -> false") + "\n" +
        batched_update("sitio_activo=true", reinc_ids, "B) reincorporate -> true") +
        "\n-- ===== REQUIEREN COLUMNA NUEVA diagnostic_status (no ejecutables hoy) =====\n" +
        batched_update("diagnostic_status='excluded_prohibited'", prohib_ids, "C) prohibidas") + "\n" +
        batched_update("diagnostic_status='no_url'", nourl_ids, "D) sin_url") + "\n"
        "-- needs_cms/parser/listing/playwright/quality: marcar diagnostic_status, NUNCA sitio_activo=false.\n",
        encoding="utf-8")

    # summary
    ut_counts = Counter(a["recommended_db_update_type"] for a in actions)
    L = [f"# PR-BE-DATA-01b — DB dry-run conservador (NO ejecutado)", f"_generado: {now_iso()}_", "",
         "## Q1. ¿Columna para excluir de scraping sin tocar sitio_activo?",
         "**No existe** una columna dedicada. Solo `sitio_activo` (bool), `activa` (bool, todo true) y "
         "`estrategia_scraping` (text), que ya está **sobrecargada** con estados que NO son estrategias "
         "(`dominio_caido` 482, `sin_estrategia` 271, `sin_url` 121).",
         "", "## Q2. Recomendación de columna nueva",
         "**Sí**: agregar `diagnostic_status text` (enum: ready/needs_cms/needs_parser/needs_url/needs_playwright/"
         "excluded_prohibited/down/no_url/manual). Separa 'web responde' (sitio_activo) de 'estado del censo'. "
         "Requiere migración futura (DDL preview en los .sql).",
         "", "## Conteos por tipo de cambio DB propuesto"]
    for k, v in ut_counts.most_common():
        L.append(f"- `{k}`: {v}")
    L += ["", "## Subgrupos de sitio_activo (true pero no-ready)"]
    for k, v in subgroups.most_common():
        L.append(f"- `{k}`: {v}")
    L += ["", "## Q3-Q7 respuestas",
          f"- **Q5. Realmente a sitio_activo=false:** SOLO **{len(down_ids)}** (confirmed_down con sitio_activo=true). NO los 4.469.",
          f"- **Q6. Solo necesitan fix (NO marcar inactivas):** ~{subgroups.get('sitio_activo_true_but_needs_cms_strategy',0)+subgroups.get('sitio_activo_true_but_needs_parser',0)+subgroups.get('sitio_activo_true_but_needs_listing_url',0)+subgroups.get('sitio_activo_true_but_needs_playwright',0)+subgroups.get('sitio_activo_true_manual_review',0)+subgroups.get('sitio_activo_true_but_missing_url',0)} (web viva).",
          "- **Q3. Cambios seguros:** sitio_activo=false en confirmed_down; sitio_activo=true en reincorporar. Reversibles, bajo riesgo.",
          "- **Q4. Cambios riesgosos:** marcar sitio_activo=false a needs_* / missing_url / prohibidas (rompería 'web viva'); evitar.",
          f"- **Q7. Universo listo sin tocar sitio_activo masivamente:** filtrar la corrida por el SELECTOR (success/links>0) o por `diagnostic_status` futura; el universo ready (~2.138) no depende de marcar 4.469 inactivas.",
          "- **Q8. Backup previo (futuro commit):** `pg_dump`/COPY de `inmobiliarias_main` (o `CREATE TABLE backup_inmobiliarias_main_YYYYMMDD AS SELECT *`) antes de cualquier UPDATE.",
          "- **Q9. Comando --commit futuro (NO ejecutar):** `apply_universe_cleanup.py --db-commit --only set_sitio_activo_false --batch 500 --backup-first` (gated, por lotes, con backup). Hoy bloqueado.",
          "", "## Cero DB writes en este paso. Nada aplicado."]
    (db_out / "db_dry_run_summary.md").write_text("\n".join(L), encoding="utf-8")
    print(f"[db-dry-run] LISTO en {db_out}")
    print(f"[db-dry-run] sitio_activo=false candidatos (confirmed_down): {len(down_ids)} | reincorporar: {len(reinc_ids)} | prohibidas: {len(prohib_ids)} | sin_url: {len(nourl_ids)}")
    print("[db-dry-run] tipos de cambio:", dict(ut_counts.most_common()))
    print("[db-dry-run] subgrupos sitio_activo:", dict(subgroups.most_common()))


def load_proposal_rows(p):
    rows = []
    for line in pathlib.Path(p).read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description="PR-BE-DATA-01 — propuesta de limpieza de universo (SOLO PROPUESTA, no DB)")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--db-dry-run", action="store_true", help="Genera SQL/propuesta Con-DB conservadora (NO ejecuta)")
    ap.add_argument("--db-commit", action="store_true")
    ap.add_argument("--proposal-input", default=str(REPO_ROOT / "_scratch" / "universe_cleanup_proposal" / "universe_cleanup_proposal.jsonl"))
    ap.add_argument("--db-out", default=str(REPO_ROOT / "_scratch" / "universe_cleanup_db_dry_run"))
    ap.add_argument("--input-http", default=str(DEF_HTTP))
    ap.add_argument("--input-playwright", default=str(DEF_PW))
    ap.add_argument("--out", default=str(REPO_ROOT / "_scratch" / "universe_cleanup_proposal"))
    args = ap.parse_args()

    if args.commit or args.db_commit:
        raise SystemExit("--commit is not implemented in this PR")

    if args.db_dry_run:
        rows = load_proposal_rows(args.proposal_input)
        if not rows:
            raise SystemExit(f"No se pudo leer la propuesta base: {args.proposal_input} (corré primero --dry-run)")
        print(f"[db-dry-run] propuesta base: {len(rows)} filas")
        write_db_dry_run(rows, pathlib.Path(args.db_out))
        return

    http = read_jsonl(pathlib.Path(args.input_http))
    pw = read_jsonl(pathlib.Path(args.input_playwright))
    if not http:
        raise SystemExit(f"No se pudo leer input HTTP: {args.input_http}")
    sitio = db_sitio_activo()
    print(f"[cleanup] http={len(http)} playwright={len(pw)} sitio_activo_db={len(sitio)}")

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for sid, h in http.items():
        pwr = pw.get(sid)
        sa = sitio.get(sid, None)
        action, reason, db_change, req_db, risk = decide(h, pwr, sa)
        yld = yint(h.get("expected_property_yield"))
        row = {
            "source_id": sid,
            "source_name": h.get("source_name"),
            "province": h.get("province"),
            "city": h.get("city"),
            "website_url": h.get("website_url"),
            "listing_url": h.get("listing_url"),
            "http_final_status": h.get("final_status"),
            "playwright_final_status": (pwr.get("playwright_final_status") if pwr else None),
            "current_sitio_activo": sa,
            "current_cms_detectado": h.get("cms_current_db"),
            "current_estrategia_scraping": h.get("strategy_current_db"),
            "recommended_action": action,
            "recommended_action_family": ACTION_FAMILY[action],
            "recommended_db_change": db_change,
            "requires_db_write_later": req_db,
            "reason": reason,
            "priority": priority_of(action, yld),
            "estimated_impact": yld,
            "risk": risk,
            "needs_manual_review": action == "manual_review",
            "notes": ("strategy_seems_wrong" if h.get("strategy_seems_wrong") else "")
                     + (";listing_url_missing" if h.get("listing_url_is_missing") else ""),
        }
        rows.append(row)

    cols = ["source_id", "source_name", "province", "city", "website_url", "listing_url",
            "http_final_status", "playwright_final_status", "current_sitio_activo",
            "current_cms_detectado", "current_estrategia_scraping", "recommended_action",
            "recommended_action_family", "recommended_db_change", "requires_db_write_later",
            "reason", "priority", "estimated_impact", "risk", "needs_manual_review", "notes"]

    # principal CSV + JSONL
    with (out_dir / "universe_cleanup_proposal.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with (out_dir / "universe_cleanup_proposal.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def sub(name, pred):
        rs = [r for r in rows if pred(r)]
        with (out_dir / name).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in sorted(rs, key=lambda x: x["estimated_impact"], reverse=True):
                w.writerow(r)
        return len(rs)

    n = {}
    n["ready_now"] = sub("ready_now.csv", lambda r: r["recommended_action"] == "keep_ready_to_scrape")
    n["exclude_no_url"] = sub("exclude_no_url.csv", lambda r: r["recommended_action"] == "exclude_missing_url")
    n["exclude_domain_down"] = sub("exclude_domain_down.csv", lambda r: r["recommended_action"] == "exclude_domain_down")
    n["exclude_prohibited"] = sub("exclude_prohibited.csv", lambda r: r["recommended_action"] == "exclude_prohibited_source")
    # fix_sitio_activo: activa en DB pero NO ready (debe pasar a false)
    n["fix_sitio_activo"] = sub("fix_sitio_activo.csv", lambda r: r["current_sitio_activo"] is True
                                and r["recommended_action_family"] not in ("ready",))
    n["reincorporate"] = sub("reincorporate_misclassified.csv", lambda r: r["recommended_action"] == "reincorporate_misclassified_ready")
    n["needs_cms"] = sub("needs_cms_strategy_fix.csv", lambda r: r["recommended_action"] == "needs_cms_strategy_fix")
    n["needs_parser"] = sub("needs_parser_fix.csv", lambda r: r["recommended_action"] == "needs_parser_fix")
    n["needs_listing"] = sub("needs_listing_url_fix.csv", lambda r: r["recommended_action"] == "needs_listing_url_fix")
    n["needs_playwright"] = sub("needs_playwright_runner.csv", lambda r: r["recommended_action"] == "needs_playwright_runner")
    n["manual_review"] = sub("manual_review.csv", lambda r: r["recommended_action"] == "manual_review")

    # summary.md
    bycat = Counter(r["recommended_action"] for r in rows)
    byfam = Counter(r["recommended_action_family"] for r in rows)

    def top(pred, k=20):
        rs = sorted([r for r in rows if pred(r)], key=lambda x: x["estimated_impact"], reverse=True)[:k]
        return [f"  - id={r['source_id']} y={r['estimated_impact']} {str(r['source_name'])[:28]} [{r['http_final_status']}]" for r in rs]

    L = [f"# PR-BE-DATA-01 — Propuesta de limpieza de universo", f"_generado: {now_iso()}_  ·  total: **{len(rows)}**", ""]
    L.append("## Conteos por accion")
    for a, c in bycat.most_common():
        L.append(f"- `{a}`: {c}")
    L.append("\n## Conteos por familia")
    for a, c in byfam.most_common():
        L.append(f"- {a}: {c}")
    L += ["", f"1. total analizadas: {len(rows)}",
          f"2. ready now (keep): {n['ready_now']}",
          f"3. excluir sin URL: {n['exclude_no_url']}",
          f"4. excluir dominio caido: {n['exclude_domain_down']}",
          f"5. prohibidas: {n['exclude_prohibited']}",
          f"6. sitio_activo falso positivo (activa pero no-ready): {n['fix_sitio_activo']}",
          f"7. reincorporar mal clasificadas: {n['reincorporate']}",
          f"8. necesitan CMS/estrategia: {n['needs_cms']}",
          f"9. necesitan parser: {n['needs_parser']}",
          f"10. necesitan URL/listing: {n['needs_listing']}",
          f"11. necesitan Playwright runner: {n['needs_playwright']}",
          f"    manual_review: {n['manual_review']}"]
    L.append("\n## 12. Top 20 ready now por impacto")
    L += top(lambda r: r["recommended_action"] == "keep_ready_to_scrape")
    L.append("\n## 13. Top 20 para reincorporar")
    L += top(lambda r: r["recommended_action"] == "reincorporate_misclassified_ready")
    L.append("\n## 14. Top 20 para excluir (prohibidas/sin-url/caidas)")
    L += top(lambda r: r["recommended_action_family"] == "cleanup")
    L.append("\n## 15. Top 20 manual review")
    L += top(lambda r: r["recommended_action"] == "manual_review")
    L += ["", "## 16. Riesgos",
          "- Cambios CON-DB (sitio_activo, cms, estrategia, url_listado) NO ejecutados aca; requieren PR aparte con backup + dry-run.",
          "- `estimated_impact` viene del registro (total_propiedades), puede estar inflado/sparse.",
          "", "## 17. Cambios DB necesarios DESPUES (en fase Con-DB)",
          f"- set sitio_activo=false: ~{n['exclude_no_url']+n['exclude_domain_down']+n['exclude_prohibited']+n['fix_sitio_activo']} (excluidas + falsos positivos)",
          f"- set sitio_activo=true (reincorporar): {n['reincorporate']}",
          f"- update cms_detectado/estrategia_scraping: {n['needs_cms']}",
          f"- update url_listado: {n['needs_listing']}",
          "", "## 18. Siguiente paso",
          "Revisar manualmente esta propuesta (sobre todo fix_sitio_activo y reincorporate). Con tu OK, preparar la fase Con-DB (UPDATE gated, backup previo, dry-run)."]
    (out_dir / "summary.md").write_text("\n".join(L), encoding="utf-8")

    # validaciones de consistencia
    print("\n=== VALIDACIONES ===")
    ids = [r["source_id"] for r in rows]
    print(f"1. prohibidas en ready_now: {sum(1 for r in rows if r['recommended_action']=='keep_ready_to_scrape' and r.get('http_final_status')=='prohibited_source_skipped')}")
    print(f"2. duplicados source_id: {len(ids)-len(set(ids))}")
    print(f"3. filas sin accion: {sum(1 for r in rows if not r['recommended_action'])}")
    print(f"4. total representadas: {len(rows)} (input http={len(http)})")
    print(f"5. suma por accion == total: {sum(bycat.values())==len(rows)}")
    print(f"[cleanup] LISTO. archivos en {out_dir}")
    print("[cleanup] conteos:", dict(bycat.most_common()))


if __name__ == "__main__":
    main()

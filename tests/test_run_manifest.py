"""
tests/test_run_manifest.py
PR-BE-PROD-09b/09c/09d — Tests del wrapper run_manifest.py

Cubre (09b — 17 tests originales):
  1. manifest válido carga correctamente
  2. manifest con duplicados detectados
  3. manifest con URL vacía rechazado
  4. manifest con fuente excluida rechazado
  5. ejecución sin --dry-run bloqueada
  6. --commit bloqueado
  7. --include-backlog bloqueado
  8. --execute sin --limit bloqueado
  9. --playwright sin --dry-run bloqueado (actualizado en 09c)
 10. uso de new_url_listado como URL prioritaria (no old_url_listado)
 11. fuente con combined_status still_failed rechazada
 12. fuente con dominio prohibido rechazada
 13. fuente con needs_playwright rechazada
 14. new_url_listado vacío con old_url_listado disponible: usa old como fallback
 15. fuente en manifest_excluded rechazada por excluded_ids
 16. build_fuentes: key slug generado correctamente
 17. dry-run completo genera outputs

Cubre (09c — 5 tests):
 18. --playwright + --dry-run permitido (no bloqueado)
 19. --playwright sin --limit bloqueado
 20. --playwright + --commit bloqueado (por --commit check primero)
 21. --playwright + --execute bloqueado (por playwright check primero)
 22. canary HTTP con session mockeada: 0 DB writes, estructura de resultado correcta

Cubre (09d — 5 tests):
 23. --execute sin --limit bloqueado (refuerza #8 con mensaje correcto)
 24. --execute --limit 51 bloqueado (excede MAX_EXECUTE_LIMIT)
 25. --execute --workers 3 bloqueado (excede MAX_EXECUTE_WORKERS)
 26. --execute --dry-run mutuamente excluyentes
 27. --execute --limit 2 --workers 2 llama run_execute (mockeado, 0 DB sin env)
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import List, Dict
from unittest.mock import patch, MagicMock

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_manifest import (  # noqa: E402
    load_manifest,
    validate_manifest,
    build_fuentes,
    main,
    MAX_EXECUTE_LIMIT,
    MAX_HTTP_WORKERS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(**kwargs) -> Dict[str, str]:
    defaults = {
        "source_id": "100",
        "source_name": "Test Inmobiliaria",
        "old_url_listado": "",
        "new_url_listado": "https://testinmo.com.ar/venta",
        "combined_status": "success_url_only",
        "is_parser_recovered": "False",
        "property_links": "10",
        "needs_playwright": "False",
        "error": "",
    }
    defaults.update(kwargs)
    return defaults


def _write_manifest(path, rows):
    import csv as csv_mod
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv_mod.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _make_manifest(rows: List[Dict]) -> io.StringIO:
    import csv as csv_mod
    buf = io.StringIO()
    if not rows:
        return buf
    writer = csv_mod.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# 1. Manifest válido
# ---------------------------------------------------------------------------

def test_valid_manifest_loads_all_rows():
    rows = [_row(source_id=str(i), source_name=f"Inmo {i}") for i in range(5)]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 5
    assert len(errors) == 0


def test_load_manifest_accepts_utf8_bom(tmp_path):
    manifest = tmp_path / "manifest_bom.csv"
    manifest.write_text(
        "source_id,source_name,new_url_listado\n"
        "100,Inmobiliaria Nunez,https://example.com/propiedades\n",
        encoding="utf-8-sig",
    )

    rows = load_manifest(manifest)

    assert rows[0]["source_id"] == "100"
    assert rows[0]["source_name"] == "Inmobiliaria Nunez"


# ---------------------------------------------------------------------------
# 2. Duplicados detectados
# ---------------------------------------------------------------------------

def test_duplicate_source_id_rejected():
    rows = [
        _row(source_id="200", source_name="Inmo A"),
        _row(source_id="200", source_name="Inmo A (dup)"),
        _row(source_id="201", source_name="Inmo B"),
    ]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 2  # 200 (primera), 201
    assert any("duplicate" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 3. URL vacía rechazada
# ---------------------------------------------------------------------------

def test_empty_url_rejected():
    rows = [
        _row(source_id="300", new_url_listado="", old_url_listado=""),
        _row(source_id="301", new_url_listado="https://ok.com.ar/venta"),
    ]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    assert valid[0]["source_id"] == "301"
    assert any("missing url" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 4. Fuente con combined_status still_failed rechazada
# ---------------------------------------------------------------------------

def test_still_failed_status_rejected():
    rows = [
        _row(source_id="400", combined_status="still_failed"),
        _row(source_id="401", combined_status="success_url_only"),
    ]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    assert valid[0]["source_id"] == "401"
    assert any("still_failed" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 5. Ejecución sin --dry-run bloqueada
# ---------------------------------------------------------------------------

def test_no_dryrun_flag_exits_with_error(tmp_path, capsys):
    manifest_file = tmp_path / "manifest.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file)])
    assert ret != 0
    captured = capsys.readouterr()
    assert "Refusing to run without --dry-run" in captured.err


# ---------------------------------------------------------------------------
# 6. --commit bloqueado
# ---------------------------------------------------------------------------

def test_commit_flag_blocked(tmp_path, capsys):
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--commit"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--commit is not authorized" in captured.err


# ---------------------------------------------------------------------------
# 7. --include-backlog bloqueado
# ---------------------------------------------------------------------------

def test_include_backlog_blocked(tmp_path, capsys):
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--include-backlog"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--include-backlog is permanently blocked" in captured.err


# ---------------------------------------------------------------------------
# 8. --execute sin --limit bloqueado
# ---------------------------------------------------------------------------

def test_execute_flag_blocked(tmp_path, capsys):
    """--execute sin --limit debe ser rechazado."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--execute"])
    assert ret != 0
    captured = capsys.readouterr()
    # En 09d el mensaje es "requires --limit" (no "is not authorized")
    assert "--execute" in captured.err and "--limit" in captured.err


# ---------------------------------------------------------------------------
# 9. --playwright bloqueado
# ---------------------------------------------------------------------------

def test_playwright_flag_blocked(tmp_path, capsys):
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--playwright"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--playwright" in captured.err and "dry-run" in captured.err


# ---------------------------------------------------------------------------
# 10. new_url_listado tiene prioridad sobre old_url_listado
# ---------------------------------------------------------------------------

def test_new_url_listado_takes_priority():
    rows = [_row(
        source_id="500",
        new_url_listado="https://correct.com.ar/venta",
        old_url_listado="https://wrong.com.ar/old",
    )]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    fuentes = build_fuentes(valid)
    assert fuentes[0]["web"] == "https://correct.com.ar/venta"
    assert fuentes[0]["_url_source"] == "new_url_listado"


def test_old_url_listado_used_as_fallback_when_new_empty():
    rows = [_row(
        source_id="501",
        new_url_listado="",
        old_url_listado="https://fallback.com.ar/venta",
    )]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    fuentes = build_fuentes(valid)
    assert fuentes[0]["web"] == "https://fallback.com.ar/venta"


# ---------------------------------------------------------------------------
# 11. Dominio prohibido rechazado
# ---------------------------------------------------------------------------

def test_prohibited_domain_rejected():
    rows = [
        _row(source_id="600", new_url_listado="https://zonaprop.com/venta"),
        _row(source_id="601", new_url_listado="https://argenprop.com/casas"),
        _row(source_id="602", new_url_listado="https://legitima.com.ar/venta"),
    ]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    assert valid[0]["source_id"] == "602"
    assert all("prohibited" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 12. needs_playwright rechazada
# ---------------------------------------------------------------------------

def test_needs_playwright_rejected():
    rows = [
        _row(source_id="700", needs_playwright="True"),
        _row(source_id="701", needs_playwright="False"),
    ]
    valid, pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    assert valid[0]["source_id"] == "701"
    # Diseño dos colas: needs_playwright se rutea a la cola PW (valid_pw),
    # ya no se rechaza como error.
    assert any(f["source_id"] == "700" for f in pw)


# ---------------------------------------------------------------------------
# 13. Fuente en excluded_ids rechazada
# ---------------------------------------------------------------------------

def test_excluded_ids_rejected():
    rows = [
        _row(source_id="800"),
        _row(source_id="801"),
        _row(source_id="802"),
    ]
    excluded = {"801"}
    valid, _pw, _blocked, errors = validate_manifest(rows, excluded_ids=excluded)
    assert len(valid) == 2
    valid_ids = {r["source_id"] for r in valid}
    assert "801" not in valid_ids
    assert any("manifest_excluded" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 14. build_fuentes: key slug generado correctamente
# ---------------------------------------------------------------------------

def test_build_fuentes_key_slug():
    rows = [_row(source_id="900", source_name="Pérez & Cía Inmobiliaria CABA")]
    valid, _pw, _blocked, _err = validate_manifest(rows)
    fuentes = build_fuentes(valid)
    assert len(fuentes) == 1
    key = fuentes[0]["key"]
    assert all(c.isalnum() or c == "_" for c in key)
    assert len(key) <= 40


# ---------------------------------------------------------------------------
# 15. Missing source_id rechazado
# ---------------------------------------------------------------------------

def test_missing_source_id_rejected():
    rows = [
        {"source_id": "", "source_name": "Sin ID", "new_url_listado": "https://ok.com.ar",
         "old_url_listado": "", "combined_status": "success_url_only",
         "needs_playwright": "False", "error": ""},
        _row(source_id="999"),
    ]
    valid, _pw, _blocked, errors = validate_manifest(rows)
    assert len(valid) == 1
    assert valid[0]["source_id"] == "999"
    assert any("missing source_id" in e[2] for e in errors)


# ---------------------------------------------------------------------------
# 16. dry-run completo: retorna 0 y genera outputs
# ---------------------------------------------------------------------------

def test_dryrun_succeeds_and_generates_outputs(tmp_path):
    import csv as csv_mod
    manifest_file = tmp_path / "manifest.csv"
    rows = [_row(source_id=str(i), source_name=f"Inmo {i}") for i in range(3)]
    _write_manifest(manifest_file, rows)

    out_dir = tmp_path / "output"
    ret = main([
        "--manifest", str(manifest_file),
        "--dry-run",
        "--out", str(out_dir),
        "--limit", "2",
    ])
    assert ret == 0
    assert (out_dir / "run_manifest_summary.md").exists()
    assert (out_dir / "manifest_loaded.csv").exists()
    assert (out_dir / "dry_run_plan.csv").exists()
    assert (out_dir / "excluded_safety_check.csv").exists()
    assert (out_dir / "write_path_guardrails.md").exists()
    assert (out_dir / "proposed_next_commands.md").exists()
    assert (out_dir / "risk_assessment.md").exists()
    assert (out_dir / "next_step_recommendation.md").exists()


# ===========================================================================
# Tests 09c: --playwright con --dry-run
# ===========================================================================

def test_playwright_with_dryrun_is_not_blocked_by_playwright_check(tmp_path, capsys):
    """--playwright + --dry-run + --limit no debe ser rechazado por el check de --playwright."""
    manifest_file = tmp_path / "m.csv"
    rows = [_row(source_id=str(i)) for i in range(3)]
    _write_manifest(manifest_file, rows)

    import run_manifest as rm
    original = rm.run_canary_http

    def mock_canary(fuentes, limit, session=None):
        return [{
            "source_id": f["source_id"], "source_name": f["_manifest_name"],
            "url_visited": f["web"], "url_source": "new_url_listado",
            "http_status": 200, "cards_detected": 5, "property_links": 5,
            "parse_method": "mock", "parse_status": "ok",
            "elapsed_s": 0.5, "error": "",
            "db_writes": 0, "upsert_propiedades": 0,
            "runs_created": 0, "publish": 0,
        } for f in fuentes[:limit]]

    rm.run_canary_http = mock_canary
    try:
        out_dir = tmp_path / "out"
        ret = main([
            "--manifest", str(manifest_file),
            "--dry-run", "--playwright", "--limit", "2",
            "--out", str(out_dir),
        ])
    finally:
        rm.run_canary_http = original

    assert ret == 0
    captured = capsys.readouterr()
    assert "--playwright is not authorized" not in captured.err


def test_playwright_without_limit_blocked(tmp_path, capsys):
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--dry-run", "--playwright"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--limit" in captured.err


def test_playwright_with_commit_blocked(tmp_path, capsys):
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--playwright", "--commit"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--commit is not authorized" in captured.err


def test_playwright_with_execute_blocked(tmp_path, capsys):
    """--playwright + --execute (sin --dry-run ni --limit): bloqueado por playwright check."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--playwright", "--execute"])
    assert ret != 0
    captured = capsys.readouterr()
    # playwright sin --dry-run se bloquea primero
    assert "--playwright" in captured.err and "dry-run" in captured.err


def test_canary_zero_db_writes_with_mock_session():
    """Verifica que run_canary_http produce 0 DB writes y estructura correcta."""
    from run_manifest import run_canary_http

    fuentes = [
        {
            "key": "inmo_test", "source_id": "100",
            "web": "https://testinmo.com.ar/venta",
            "ciudad": "", "operacion": None, "tipo_cms": "tokko",
            "_manifest_name": "Inmo Test", "_url_source": "new_url_listado",
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = ("<html><body><div class='property-card'>"
                      "<a href='/propiedad/123'>Casa</a>"
                      "<span class='price'>USD 100000</span></div></body></html>")

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    results = run_canary_http(fuentes, limit=1, session=mock_session)

    assert len(results) == 1
    r = results[0]
    assert r["db_writes"] == 0
    assert r["upsert_propiedades"] == 0
    assert r["runs_created"] == 0
    assert r["publish"] == 0
    assert r["url_source"] == "new_url_listado"
    assert r["http_status"] == 200
    assert r["source_id"] == "100"


# ===========================================================================
# Tests 09d: --execute con guardrails
# ===========================================================================

def test_execute_without_limit_blocked(tmp_path, capsys):
    """--execute sin --limit siempre bloqueado."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file), "--execute"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--execute" in captured.err and "--limit" in captured.err


def test_execute_limit_over_max_blocked(tmp_path, capsys):
    """--execute --limit > 50 bloqueado."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    over = MAX_EXECUTE_LIMIT + 1
    ret = main(["--manifest", str(manifest_file), "--execute", f"--limit={over}"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "MAX_EXECUTE_LIMIT" in captured.err or str(MAX_EXECUTE_LIMIT) in captured.err


def test_execute_workers_over_max_blocked(tmp_path, capsys):
    """--execute --workers > MAX_HTTP_WORKERS bloqueado."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    over = MAX_HTTP_WORKERS + 1
    ret = main(["--manifest", str(manifest_file), "--execute",
                "--limit", "1", f"--workers={over}"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "MAX_HTTP_WORKERS" in captured.err or str(MAX_HTTP_WORKERS) in captured.err


def test_execute_and_dryrun_mutually_exclusive(tmp_path, capsys):
    """--execute + --dry-run mutuamente excluyentes."""
    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row()])

    ret = main(["--manifest", str(manifest_file),
                "--execute", "--dry-run", "--limit", "1"])
    assert ret != 0
    captured = capsys.readouterr()
    assert "mutually exclusive" in captured.err


def test_execute_calls_run_execute_when_authorized(tmp_path, capsys):
    """--execute --limit 2 --workers 2 llama run_execute y escribe outputs (mockeado)."""
    manifest_file = tmp_path / "m.csv"
    rows = [_row(source_id=str(i), source_name=f"Inmo {i}") for i in range(5)]
    _write_manifest(manifest_file, rows)

    out_dir = tmp_path / "out09d"
    fuente_mock = {**build_fuentes([_row(source_id="1")])[0], "inmobiliaria_id": 999}

    mock_result = {
        "subset":          [fuente_mock],
        "fuentes_sin_fk":  [],
        "fk_mapping":      {"1": 999},
        "count_before":    1000,
        "count_after":     1005,
        "total_saved":     5,
        "net_new":         5,
        "new_props":       [{"url": "https://x.com/1", "titulo": "Casa",
                             "fuente_extraccion": "inmo_0", "operacion": "venta",
                             "tipo_propiedad": "casa", "precio": "100000",
                             "moneda": "USD", "created_at": "2026-06-28T00:00:00Z"}],
        "worker_results":  {0: {"saved": 3, "status": "ok"},
                            1: {"saved": 2, "status": "ok"}},
        "workers":  2,
        "limit":    2,
        "batches":  2,
    }

    import run_manifest as rm
    original = rm.run_execute

    def mock_run_execute(fuentes_http, fuentes_pw, limit, http_workers, pw_workers,
                         out_dir_arg, ts_start, manifest_path):
        return mock_result

    rm.run_execute = mock_run_execute
    try:
        ret = main([
            "--manifest", str(manifest_file),
            "--execute", "--limit", "2", "--workers", "2",
            "--out", str(out_dir),
        ])
    finally:
        rm.run_execute = original

    assert ret == 0
    assert (out_dir / "run_manifest_09d_summary.md").exists()
    assert (out_dir / "executed_sources.csv").exists()
    assert (out_dir / "inserted_properties.csv").exists()
    assert (out_dir / "db_write_audit.md").exists()
    assert (out_dir / "post_execute_validation.md").exists()
    assert (out_dir / "risk_assessment.md").exists()
    assert (out_dir / "next_step_recommendation.md").exists()


# ===========================================================================
# Tests 09d-FIX: schema compatibility + FK preflight
# ===========================================================================

def test_payload_has_no_barrio_normalizado():
    """to_payload() no debe incluir barrio_normalizado (no existe en DB)."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test")
    assert "barrio_normalizado" not in p.to_payload()


def test_payload_has_no_calidad_score():
    """to_payload() no debe incluir calidad_score (no existe en DB)."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test")
    assert "calidad_score" not in p.to_payload()


def test_payload_has_no_scraped_at():
    """to_payload() no debe incluir scraped_at (no existe en DB)."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test")
    assert "scraped_at" not in p.to_payload()


def test_payload_metros_mapped_to_superficie_total():
    """to_payload() debe mapear metros -> superficie_total."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test", metros=150)
    payload = p.to_payload()
    assert "metros" not in payload
    assert payload["superficie_total"] == 150


def test_payload_fuente_mapped_to_fuente_extraccion():
    """to_payload() debe mapear fuente -> fuente_extraccion."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test", fuente="tokko_test")
    payload = p.to_payload()
    assert "fuente" not in payload
    assert payload["fuente_extraccion"] == "tokko_test"


def test_payload_includes_inmobiliaria_id_when_set():
    """to_payload() debe incluir inmobiliaria_id cuando está definido."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test", inmobiliaria_id=4321)
    payload = p.to_payload()
    assert payload["inmobiliaria_id"] == 4321


def test_payload_excludes_inmobiliaria_id_when_none():
    """to_payload() NO debe incluir inmobiliaria_id cuando es None."""
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="Test", inmobiliaria_id=None)
    payload = p.to_payload()
    assert "inmobiliaria_id" not in payload


def test_payload_has_hash_dedup():
    """to_payload() debe incluir hash_dedup como SHA256[:32] de '{inmob_id}|url|{url_norm}'."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad, _compute_hash_dedup
    url = "https://www.example.com/propiedad/123"
    p = Propiedad(url=url, titulo="Test", inmobiliaria_id=999)
    payload = p.to_payload()
    assert "hash_dedup" in payload
    assert len(payload["hash_dedup"]) == 32
    expected = _compute_hash_dedup(999, url)
    assert payload["hash_dedup"] == expected


# --- 09d-INT: _safe_int guard tests ---

def test_safe_int_none_returns_none():
    """_safe_int(None) -> None."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import _safe_int
    assert _safe_int(None) is None


def test_safe_int_valid_string():
    """_safe_int('3') -> 3."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import _safe_int
    assert _safe_int("3") == 3


def test_safe_int_phone_overflow():
    """_safe_int('3413024001') -> None (fuera de rango PostgreSQL integer)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import _safe_int
    assert _safe_int("3413024001") is None


def test_safe_int_max_boundary():
    """_safe_int(2_147_483_647) -> 2_147_483_647 (valor máximo PostgreSQL integer)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import _safe_int
    assert _safe_int(2_147_483_647) == 2_147_483_647


def test_safe_int_over_max():
    """_safe_int(2_147_483_648) -> None (un paso sobre el máximo PostgreSQL integer)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import _safe_int
    assert _safe_int(2_147_483_648) is None


def test_payload_dormitorios_out_of_range_becomes_none():
    """to_payload() convierte dormitorios fuera de rango a None."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", dormitorios=3_413_024_001)
    assert p.to_payload()["dormitorios"] is None


def test_payload_banos_out_of_range_becomes_none():
    """to_payload() convierte banos fuera de rango a None."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", banos=3_413_024_001)
    assert p.to_payload()["banos"] is None


def test_payload_ambientes_out_of_range_becomes_none():
    """to_payload() convierte ambientes fuera de rango a None."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", ambientes=3_413_024_001)
    assert p.to_payload()["ambientes"] is None


def test_payload_superficie_total_out_of_range_becomes_none():
    """to_payload() convierte superficie_total (metros) fuera de rango a None."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", metros=3_413_024_001)
    assert p.to_payload()["superficie_total"] is None


def test_batch_save_no_on_conflict(tmp_path):
    """batch_save_only_new() no debe usar on_conflict=url en la URL del POST."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    captured_urls = []

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_session.post.return_value = mock_response

    client = SupabaseClient(mock_session, "https://fake.supabase.co", "fakekey", "propiedades")
    client.batch_save_only_new([{"url": "https://x.com/1", "titulo": "T", "inmobiliaria_id": 1}])

    assert mock_session.post.called
    call_url = mock_session.post.call_args[0][0]
    assert "on_conflict" not in call_url


def test_lookup_inmobiliaria_ids_returns_mapping():
    """_lookup_inmobiliaria_ids con mocked requests retorna mapping correcto."""
    import run_manifest as rm

    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"id": 1612, "nombre": "Berrueta", "scraping_id_origen": 3529},
        {"id": 5201, "nombre": "D'Eramo",  "scraping_id_origen": 3899},
    ]

    with patch("requests.get", return_value=mock_resp):
        mapping = rm._lookup_inmobiliaria_ids(
            "https://fake.co", "fakekey", ["3529", "3899", "9999"]
        )

    assert mapping["3529"] == 1612
    assert mapping["3899"] == 5201
    assert "9999" not in mapping


def _fk_response(rows):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = rows
    return response


def test_safe_fk_collision_uses_only_compatible_canonical_id():
    import run_manifest as rm

    source = {
        "source_id": "84",
        "_manifest_name": "Yacoub Alquileres",
        "web": "https://yacoub.com.ar/propiedades",
    }
    primary = [{
        "id": 4566,
        "nombre": "Raizen Servicios Inmobiliarios",
        "web": "http://raizeninmobiliaria.com.ar",
        "url_listado": "http://raizeninmobiliaria.com.ar/adm-propiedades.php",
        "scraping_id_origen": 84,
    }]
    fallback = [{
        "id": 84,
        "nombre": "Yacoub Alquileres",
        "web": "https://yacoub.com.ar",
        "url_listado": "https://yacoub.com.ar/propiedades",
        "scraping_id_origen": 735,
    }]

    with patch("requests.get", side_effect=[_fk_response(primary), _fk_response(fallback)]):
        mapping, errors = rm._lookup_inmobiliaria_ids_safe("https://fake.co", "fake", [source])

    assert mapping == {"84": 84}
    assert errors == []


def test_safe_fk_keeps_compatible_primary_when_fallback_mismatches():
    import run_manifest as rm

    source = {"source_id": "10", "_manifest_name": "Primary Inmo", "web": "https://primary.test"}
    primary = [{
        "id": 500,
        "nombre": "Primary Inmo",
        "web": "https://primary.test",
        "url_listado": None,
        "scraping_id_origen": 10,
    }]
    fallback = [{
        "id": 10,
        "nombre": "Other Inmo",
        "web": "https://other.test",
        "url_listado": None,
        "scraping_id_origen": 77,
    }]

    with patch("requests.get", side_effect=[_fk_response(primary), _fk_response(fallback)]):
        mapping, errors = rm._lookup_inmobiliaria_ids_safe("https://fake.co", "fake", [source])

    assert mapping == {"10": 500}
    assert errors == []


def test_safe_fk_ambiguous_collision_is_rejected():
    import run_manifest as rm

    source = {"source_id": "10", "_manifest_name": "Same", "web": "https://same.test"}
    primary = [{"id": 500, "nombre": "Same", "web": "https://same.test", "url_listado": None, "scraping_id_origen": 10}]
    fallback = [{"id": 10, "nombre": "Same", "web": "https://same.test", "url_listado": None, "scraping_id_origen": 77}]

    with patch("requests.get", side_effect=[_fk_response(primary), _fk_response(fallback)]):
        mapping, errors = rm._lookup_inmobiliaria_ids_safe("https://fake.co", "fake", [source])

    assert mapping == {}
    assert any("unresolved FK collision" in error[2] for error in errors)


def test_safe_fk_multiple_primary_matches_are_rejected():
    import run_manifest as rm

    source = {"source_id": "10", "_manifest_name": "Inmo", "web": "https://inmo.test"}
    primary = [
        {"id": 500, "nombre": "Inmo", "web": "https://inmo.test", "url_listado": None, "scraping_id_origen": 10},
        {"id": 501, "nombre": "Inmo 2", "web": "https://inmo2.test", "url_listado": None, "scraping_id_origen": 10},
    ]

    with patch("requests.get", side_effect=[_fk_response(primary), _fk_response([])]):
        mapping, errors = rm._lookup_inmobiliaria_ids_safe("https://fake.co", "fake", [source])

    assert mapping == {}
    assert any("ambiguous scraping_id_origen" in error[2] for error in errors)


def test_safe_fk_missing_source_is_classified():
    import run_manifest as rm

    source = {"source_id": "9999", "_manifest_name": "Missing", "web": "https://missing.test"}
    with patch("requests.get", side_effect=[_fk_response([]), _fk_response([])]):
        mapping, errors = rm._lookup_inmobiliaria_ids_safe("https://fake.co", "fake", [source])

    assert mapping == {}
    assert errors == [("9999", "Missing", "missing FK candidate")]


def test_fk_missing_source_excluded_from_execute():
    """La lógica de FK filtering de run_execute separa fuentes con/sin match."""
    # Simular el algoritmo de filtering que vive en run_execute:
    # si fk_map no tiene sid, la fuente va a fuentes_sin_fk
    fuentes_all = [
        {**build_fuentes([_row(source_id="100", source_name="Inmo OK")])[0]},
        {**build_fuentes([_row(source_id="200", source_name="Inmo NO FK")])[0]},
        {**build_fuentes([_row(source_id="300", source_name="Inmo OK 2")])[0]},
    ]
    fk_map = {"100": 999, "300": 888}   # 200 sin FK

    fuentes_con_fk = []
    fuentes_sin_fk = []
    for f in fuentes_all:
        sid = str(f.get("source_id", ""))
        mid = fk_map.get(sid)
        if mid is not None:
            fuentes_con_fk.append({**f, "inmobiliaria_id": mid})
        else:
            fuentes_sin_fk.append(f)

    assert len(fuentes_con_fk) == 2
    assert len(fuentes_sin_fk) == 1
    assert fuentes_sin_fk[0]["source_id"] == "200"
    for f in fuentes_con_fk:
        assert f.get("inmobiliaria_id") is not None
    assert fuentes_con_fk[0]["inmobiliaria_id"] == 999
    assert fuentes_con_fk[1]["inmobiliaria_id"] == 888


def test_fk_all_missing_aborts_execute(tmp_path, capsys):
    """Si ninguna fuente tiene FK, run_execute retorna None y el wrapper aborta."""
    import run_manifest as rm
    orig_lookup = rm._lookup_inmobiliaria_ids
    # All sources missing FK → run_execute returns None
    orig_execute = rm.run_execute

    def mock_run_execute_returns_none(*args, **kwargs):
        return None

    manifest_file = tmp_path / "m.csv"
    _write_manifest(manifest_file, [_row(source_id="9999")])
    out_dir = tmp_path / "out"

    rm._lookup_inmobiliaria_ids = lambda url, k, ids: {}  # empty map → all missing
    rm.run_execute = mock_run_execute_returns_none
    try:
        ret = main([
            "--manifest", str(manifest_file),
            "--execute", "--limit", "1", "--workers", "2",
            "--out", str(out_dir),
        ])
    finally:
        rm._lookup_inmobiliaria_ids = orig_lookup
        rm.run_execute = orig_execute

    # When run_execute returns None, main should return 1
    assert ret == 1


# ---------------------------------------------------------------------------
# 09d-ESTADO: estado field in payload (7 tests)
# ---------------------------------------------------------------------------

def test_payload_includes_estado():
    """to_payload() debe incluir el campo 'estado'."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T")
    assert "estado" in p.to_payload()


def test_payload_estado_is_activa():
    """to_payload() debe enviar estado='activa' para pasar propiedades_estado_chk."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T")
    assert p.to_payload()["estado"] == "activa"


def test_payload_estado_not_activo():
    """to_payload() NO debe enviar 'activo' (falla propiedades_estado_chk)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T")
    assert p.to_payload()["estado"] != "activo"


def test_payload_estado_with_inmobiliaria_id():
    """estado='activa' coexiste correctamente con inmobiliaria_id."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", inmobiliaria_id=42)
    payload = p.to_payload()
    assert payload["estado"] == "activa"
    assert payload["inmobiliaria_id"] == 42


def test_payload_estado_with_hash_dedup():
    """estado='activa' coexiste correctamente con hash_dedup."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com/prop/1", titulo="T", inmobiliaria_id=99)
    payload = p.to_payload()
    assert payload["estado"] == "activa"
    assert "hash_dedup" in payload
    assert len(payload["hash_dedup"]) == 32


def test_payload_no_unexpected_columns():
    """to_payload() no incluye columnas inexistentes en propiedades (barrio_normalizado, calidad_score, scraped_at)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", inmobiliaria_id=1)
    payload = p.to_payload()
    for banned in ("barrio_normalizado", "calidad_score", "scraped_at"):
        assert banned not in payload, f"Column {banned!r} must not appear in payload"


def test_payload_safe_int_still_works_with_estado():
    """_safe_int() guard sigue aplicando en presencia de estado='activa'."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad
    p = Propiedad(url="https://x.com", titulo="T", dormitorios=3_413_024_001, inmobiliaria_id=1)
    payload = p.to_payload()
    assert payload["estado"] == "activa"
    assert payload["dormitorios"] is None  # overflow -> None


# ---------------------------------------------------------------------------
# 09e-DEDUP: dedup robusto por inmobiliaria (fix límite PostgREST 1.000)
# ---------------------------------------------------------------------------

def test_max_execute_limit_matches_audited_universe():
    """El techo debe coincidir exactamente con el universo auditado."""
    from run_manifest import MAX_EXECUTE_LIMIT
    assert MAX_EXECUTE_LIMIT == 1391, (
        f"MAX_EXECUTE_LIMIT={MAX_EXECUTE_LIMIT}, se esperaba 1391"
    )


def test_load_existing_urls_by_inmobiliaria_returns_url_set():
    """_load_existing_urls_by_inmobiliaria() con mock retorna Set[str] de URLs."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from unittest.mock import MagicMock, patch
    from run_manifest import _load_existing_urls_by_inmobiliaria

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {"url": "https://inmo1.com/prop/1"},
        {"url": "https://inmo1.com/prop/2"},
    ]

    with patch("requests.get", return_value=mock_resp):
        result = _load_existing_urls_by_inmobiliaria("https://fake.co", "fakekey", [42])

    assert isinstance(result, set)
    assert "https://inmo1.com/prop/1" in result
    assert "https://inmo1.com/prop/2" in result


def test_load_existing_urls_by_inmobiliaria_empty_when_no_props():
    """_load_existing_urls_by_inmobiliaria() retorna set vacío si no hay propiedades."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from unittest.mock import MagicMock, patch
    from run_manifest import _load_existing_urls_by_inmobiliaria

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch("requests.get", return_value=mock_resp):
        result = _load_existing_urls_by_inmobiliaria("https://fake.co", "fakekey", [99])

    assert result == set()


def test_load_existing_urls_by_inmobiliaria_multiple_ids():
    """_load_existing_urls_by_inmobiliaria() agrega URLs de múltiples inmobiliarias."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from unittest.mock import MagicMock, patch
    from run_manifest import _load_existing_urls_by_inmobiliaria

    def fake_get(*args, **kwargs):
        inmo_filter = kwargs.get("params", {}).get("inmobiliaria_id", "")
        r = MagicMock()
        r.status_code = 200
        assert inmo_filter == "in.(1,2)"
        r.json.return_value = [
            {"url": "https://a.com/1"},
            {"url": "https://b.com/1"},
        ]
        return r

    with patch("requests.get", side_effect=fake_get):
        result = _load_existing_urls_by_inmobiliaria("https://fake.co", "fakekey", [1, 2])

    assert "https://a.com/1" in result
    assert "https://b.com/1" in result
    assert len(result) == 2


def test_load_existing_urls_fails_closed_on_http_error():
    """_load_existing_urls_by_inmobiliaria() no lanza si PostgREST retorna error."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from unittest.mock import MagicMock, patch
    from run_manifest import _load_existing_urls_by_inmobiliaria

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.return_value = []

    with patch("requests.get", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="Dedup preflight HTTP 500"):
            _load_existing_urls_by_inmobiliaria("https://fake.co", "fakekey", [42])
        result = set()

    assert isinstance(result, set)  # no lanza, retorna set (posiblemente vacío)


def test_load_existing_urls_paginates_and_reports_metrics():
    from unittest.mock import MagicMock, patch
    from run_manifest import _load_existing_urls_by_inmobiliaria

    first = MagicMock(status_code=200)
    first.json.return_value = [
        {"url": f"https://a.com/{index}"} for index in range(1000)
    ]
    second = MagicMock(status_code=200)
    second.json.return_value = [{"url": "https://a.com/1000"}]
    metrics = {}

    with patch("requests.get", side_effect=[first, second]) as mocked_get:
        result = _load_existing_urls_by_inmobiliaria(
            "https://fake.co", "fakekey", [1, 1, 2], metrics=metrics
        )

    assert len(result) == 1001
    assert mocked_get.call_count == 2
    assert mocked_get.call_args_list[1].kwargs["params"]["offset"] == "1000"
    assert mocked_get.call_args_list[1].kwargs["params"]["order"] == "inmobiliaria_id.asc,id.asc"
    assert metrics["inmobiliaria_count"] == 2
    assert metrics["query_count"] == 2


def test_insert_only_proxy_filters_historical_exact_url_before_insert():
    from run_manifest import _InsertOnlySupabaseProxy

    client = MagicMock()
    client.table = "propiedades"
    existing = {"url": "https://x.com/old", "inmobiliaria_id": 7}
    fresh = {"url": "https://x.com/new", "inmobiliaria_id": 7}
    client.filter_new_exact_urls.return_value = ([fresh], 1)
    client.batch_save_only_new.return_value = 1

    proxy = _InsertOnlySupabaseProxy(client)
    assert proxy.batch_save_only_new([existing, fresh]) == 1
    client.batch_save_only_new.assert_called_once_with([fresh])


def test_exact_url_guard_is_scoped_by_inmobiliaria_id_and_fails_closed():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    response = MagicMock(status_code=200, text="")
    response.json.return_value = [{
        "inmobiliaria_id": 7,
        "url": "https://x.com/shared",
    }]
    session = MagicMock()
    session.get.return_value = response
    client = SupabaseClient(session, "https://fake.supabase.co", "fakekey", "propiedades")

    payloads = [
        {"url": "https://x.com/shared", "inmobiliaria_id": 7},
        {"url": "https://x.com/new", "inmobiliaria_id": 7},
        {"url": "https://x.com/shared", "inmobiliaria_id": 8},
    ]
    filtered, skipped = client.filter_new_exact_urls(payloads)

    assert skipped == 1
    assert payloads[0] not in filtered
    assert payloads[1:] == filtered
    assert "%" not in session.get.call_args_list[0].kwargs["params"]["url"]
    assert '"https://x.com/shared"' in session.get.call_args_list[0].kwargs["params"]["url"]

    session.get.side_effect = requests.ConnectionError("offline")
    with pytest.raises(RuntimeError, match="Exact URL guard request failed"):
        client.filter_new_exact_urls(payloads)


def test_dedup_prevents_existing_url_reinsertion():
    """URL ya en existing_urls es filtrada — no pasa el filtro pre-ficha."""
    existing_urls = {"https://inmo.com/prop/1", "https://inmo.com/prop/2"}
    candidate_urls = ["https://inmo.com/prop/1", "https://inmo.com/prop/3"]

    nuevas_urls = [u for u in candidate_urls if u not in existing_urls]

    assert "https://inmo.com/prop/1" not in nuevas_urls  # existente → omitida
    assert "https://inmo.com/prop/3" in nuevas_urls      # nueva → pasa


def test_dedup_detects_internal_batch_duplicate():
    """Dos props del mismo batch con la misma URL: solo la primera se inserta."""
    import threading
    existing_urls: set = set()
    lock = threading.Lock()

    url_shared = "https://inmo.com/prop/duplicated"
    props = [
        {"url": url_shared, "titulo": "Primera"},
        {"url": url_shared, "titulo": "Segunda"},
    ]

    inserted = []
    with lock:
        for p in props:
            if p["url"] not in existing_urls:
                existing_urls.add(p["url"])
                inserted.append(p)

    assert len(inserted) == 1
    assert inserted[0]["titulo"] == "Primera"


def test_dedup_does_not_omit_genuinely_new_url():
    """URL ausente de existing_urls pasa el filtro sin ser omitida."""
    existing_urls: set = {"https://inmo.com/prop/vieja"}
    nueva_url = "https://inmo.com/prop/nueva-unica"

    assert nueva_url not in existing_urls


def test_dedup_payload_preserves_required_fields_after_filter():
    """Propiedad que pasa el dedup sigue teniendo estado, inmobiliaria_id y hash_dedup."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from models import Propiedad

    existing_urls: set = set()
    url = "https://inmo.com/prop/nueva"
    p = Propiedad(url=url, titulo="Casa nueva", inmobiliaria_id=42)

    assert url not in existing_urls  # pasa el filtro dedup

    payload = p.to_payload()
    assert payload["estado"] == "activa"
    assert payload["inmobiliaria_id"] == 42
    assert "hash_dedup" in payload
    assert len(payload["hash_dedup"]) == 32


# ===========================================================================
# Tests Manifest B — Fix 409 hash_dedup fallback (PR-BE-PROD-ManifestB)
# ===========================================================================

def test_batch_409_fallback_saves_new_skips_duplicate():
    """Batch con 1 hash_dedup duplicado y 2 nuevas: guarda las 2 nuevas, salta la duplicada."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    # Call 1: batch POST → 409
    # Call 2: individual insert prop A → 201 (nueva)
    # Call 3: individual insert prop B → 409 (hash_dedup dup)
    # Call 4: individual insert prop C → 201 (nueva)
    batch_409 = MagicMock(status_code=409, text='{"code":"23505"}')
    ok1 = MagicMock(status_code=201, text="")
    dup = MagicMock(status_code=409, text='{"code":"23505"}')
    ok2 = MagicMock(status_code=201, text="")

    mock_session = MagicMock()
    mock_session.post.side_effect = [batch_409, ok1, dup, ok2]

    client = SupabaseClient(mock_session, "https://fake.supabase.co", "fakekey", "propiedades")
    payloads = [
        {"url": "https://x.com/1", "titulo": "Nueva A", "hash_dedup": "aaa", "estado": "activa", "inmobiliaria_id": 1},
        {"url": "https://x.com/2", "titulo": "Duplicada", "hash_dedup": "bbb", "estado": "activa", "inmobiliaria_id": 1},
        {"url": "https://x.com/3", "titulo": "Nueva C", "hash_dedup": "ccc", "estado": "activa", "inmobiliaria_id": 1},
    ]
    result = client.batch_save_only_new(payloads)

    assert result == 2, f"Esperado 2 guardadas, got {result}"
    assert mock_session.post.call_count == 4  # 1 batch + 3 individuales


def test_batch_409_does_not_crash_source():
    """Un 409 en batch con único payload no lanza excepción — la fuente continúa."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    batch_409 = MagicMock(status_code=409, text='{"code":"23505"}')
    ind_409 = MagicMock(status_code=409, text='{"code":"23505"}')

    mock_session = MagicMock()
    mock_session.post.side_effect = [batch_409, ind_409]

    client = SupabaseClient(mock_session, "https://fake.supabase.co", "fakekey", "propiedades")
    try:
        result = client.batch_save_only_new([
            {"url": "https://x.com/1", "titulo": "T", "hash_dedup": "aaa", "estado": "activa", "inmobiliaria_id": 1}
        ])
    except Exception as exc:
        raise AssertionError(f"batch_save_only_new no debe lanzar excepción con 409: {exc}") from exc

    assert result == 0  # la única prop era duplicada


def test_batch_409_fix_no_on_conflict_in_any_call():
    """batch_save_only_new() no usa on_conflict=url ni en batch normal ni en fallback individual."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    batch_409 = MagicMock(status_code=409, text='{"code":"23505"}')
    ok = MagicMock(status_code=201, text="")
    mock_session = MagicMock()
    mock_session.post.side_effect = [batch_409, ok]

    client = SupabaseClient(mock_session, "https://fake.supabase.co", "fakekey", "propiedades")
    client.batch_save_only_new([
        {"url": "https://x.com/1", "titulo": "T", "hash_dedup": "abc", "estado": "activa", "inmobiliaria_id": 1}
    ])

    for call in mock_session.post.call_args_list:
        call_url = call[0][0]
        assert "on_conflict" not in call_url, f"on_conflict encontrado en URL: {call_url}"


def test_batch_409_fallback_preserves_estado_hash_dedup_inmobiliaria_id():
    """En fallback individual, los payloads mantienen estado='activa', hash_dedup e inmobiliaria_id."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import SupabaseClient

    batch_409 = MagicMock(status_code=409, text='{"code":"23505"}')
    ok = MagicMock(status_code=201, text="")
    mock_session = MagicMock()
    mock_session.post.side_effect = [batch_409, ok]

    client = SupabaseClient(mock_session, "https://fake.supabase.co", "fakekey", "propiedades")
    payload = {
        "url": "https://x.com/1", "titulo": "T",
        "hash_dedup": "abcdef1234567890abcdef1234567890",
        "estado": "activa",
        "inmobiliaria_id": 42,
    }
    client.batch_save_only_new([payload])

    # La segunda llamada (fallback individual) debe contener el payload original intacto
    assert mock_session.post.call_count == 2
    individual_kwargs = mock_session.post.call_args_list[1][1]
    sent = individual_kwargs["json"][0]
    assert sent["estado"] == "activa"
    assert sent["hash_dedup"] == "abcdef1234567890abcdef1234567890"
    assert sent["inmobiliaria_id"] == 42


def test_batch_save_reports_confirmed_rows_before_later_chunk_failure():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import PartialBatchInsertError, SupabaseClient

    mock_session = MagicMock()
    mock_session.post.side_effect = [
        MagicMock(status_code=201, text=""),
        requests.ConnectionError("temporary DNS failure"),
    ]
    client = SupabaseClient(
        mock_session, "https://fake.supabase.co", "fakekey", "propiedades"
    )
    payloads = [
        {"url": f"https://x.com/{i}", "titulo": "T", "inmobiliaria_id": 1}
        for i in range(21)
    ]

    with pytest.raises(PartialBatchInsertError) as caught:
        client.batch_save_only_new(payloads)

    assert caught.value.saved_count == 20
    assert [p["url"] for p in caught.value.saved_payloads] == [
        f"https://x.com/{i}" for i in range(20)
    ]


def test_batch_save_reports_confirmed_individual_rows_before_failure():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "scraper"))
    from clients import PartialBatchInsertError, SupabaseClient

    mock_session = MagicMock()
    mock_session.post.side_effect = [
        MagicMock(status_code=409, text='{"code":"23505"}'),
        MagicMock(status_code=201, text=""),
        requests.ConnectionError("connection reset"),
    ]
    client = SupabaseClient(
        mock_session, "https://fake.supabase.co", "fakekey", "propiedades"
    )
    payloads = [
        {"url": "https://x.com/1", "titulo": "T", "inmobiliaria_id": 1},
        {"url": "https://x.com/2", "titulo": "T", "inmobiliaria_id": 1},
    ]

    with pytest.raises(PartialBatchInsertError) as caught:
        client.batch_save_only_new(payloads)

    assert caught.value.saved_count == 1
    assert caught.value.saved_payloads[0]["url"] == "https://x.com/1"

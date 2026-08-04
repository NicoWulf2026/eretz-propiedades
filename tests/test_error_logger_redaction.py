"""Tests Fase A-bis del logger de errores: redacción de secretos y robustez.

Ejecutable sin pytest:  python tests/test_error_logger_redaction.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scraper.error_logger import redact, log_error, _jsonl_path  # noqa: E402


# --- Secretos FALSOS de prueba (no son reales) ---
FAKE_PASS = "SuperSecret123FAKE"
FAKE_JWT = "eyJhbGciFAKE.eyJzdWIiFAKE.signatureFAKE"
FAKE_CONN = f"postgresql://admin:{FAKE_PASS}@db.proj.supabase.co:5432/postgres"
FAKE_BEARER = f"Authorization: Bearer {FAKE_JWT}"
FAKE_QS = f"https://x.supabase.co/rest/v1/t?apikey={FAKE_JWT}&token=abc123&password={FAKE_PASS}"


def test_redact_connection_string():
    out = redact(FAKE_CONN)
    assert FAKE_PASS not in out, out
    assert "admin" not in out, out
    assert "<redacted>" in out, out


def test_redact_querystring():
    out = redact(FAKE_QS)
    assert FAKE_PASS not in out, out
    assert "abc123" not in out, out
    assert "<redacted>" in out, out


def test_redact_jwt():
    out = redact(f"key={FAKE_JWT}")
    assert FAKE_JWT not in out, out
    assert "redacted" in out, out


def test_redact_bearer():
    out = redact(FAKE_BEARER)
    assert FAKE_JWT not in out, out
    assert "Bearer" in out and "<redacted>" in out, out


def test_log_error_db_none_creates_jsonl():
    rid = 999999  # run_id de prueba aislado
    p = _jsonl_path(rid)
    if p.exists():
        p.unlink()
    log_error(fase="publish", error_type="test", severidad="warning",
              mensaje=f"fallo con {FAKE_CONN}", run_id=rid, db_url=None)
    assert p.exists(), "JSONL no creado con db_url=None"
    content = p.read_text(encoding="utf-8")
    rec = json.loads(content.strip().splitlines()[-1])
    assert FAKE_PASS not in content, "password FALSO presente en JSONL"
    assert rec["fase"] == "publish"


def test_log_error_broken_db_no_raise():
    # db_url que apunta a un host inexistente: _write_table debe fallar silenciosamente.
    try:
        log_error(fase="publish", error_type="test", severidad="warning",
                  mensaje="x", run_id=999998,
                  db_url="postgresql://u:p@nonexistent.invalid:5432/db")
    except Exception as e:  # pragma: no cover
        raise AssertionError(f"log_error NO debe lanzar excepción: {e}")


def test_log_error_exploding_object_no_raise():
    class Boom:
        def __str__(self): raise RuntimeError("boom")
    try:
        log_error(fase="publish", error_type="test", mensaje=Boom(), run_id=999997)
    except Exception as e:  # pragma: no cover
        raise AssertionError(f"log_error NO debe romper ni con objetos que explotan: {e}")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    jsonl_for_grep = None
    for t in tests:
        try:
            t()
            if t.__name__ == "test_log_error_db_none_creates_jsonl":
                jsonl_for_grep = _jsonl_path(999999)
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{'TODOS OK' if failed == 0 else str(failed)+' FALLARON'}")
    if jsonl_for_grep:
        print(f"JSONL_FOR_GREP={jsonl_for_grep}")
    sys.exit(1 if failed else 0)

"""Tests Fase B.1 — robustez de publish: clasificador, retry, reclaim.

Con mocks: NO toca red, NI Supabase, NI producción.
Ejecutable sin pytest:  python tests/test_publish_robustez.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.publish_to_supabase as P  # noqa: E402

# Silenciar el logger en los tests (no escribir JSONL/tabla).
P._log_error = lambda **k: None


# --- is_transient_error: conservador con 4xx permanentes ---
def test_permanent_4xx_no_transient():
    for code in ("400", "401", "403", "404", "409", "422"):
        assert P.is_transient_error(Exception(f"HTTP {code} error")) is False, code


def test_429_is_transient():
    assert P.is_transient_error(Exception("HTTP 429 Too Many Requests")) is True


def test_5xx_is_transient():
    for code in ("500", "502", "503", "504"):
        assert P.is_transient_error(Exception(f"server {code}")) is True, code


def test_network_errors_transient():
    assert P.is_transient_error(ConnectionResetError("reset")) is True
    assert P.is_transient_error(TimeoutError("x")) is True
    assert P.is_transient_error(Exception("Read timed out")) is True
    assert P.is_transient_error(Exception("Connection aborted")) is True


# --- publish_with_retry ---
def test_retry_recovers_after_1():
    calls = {"n": 0}
    def fake(db, prop):
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("HTTP 503")
        return (1, 1)
    P.publish_one = fake
    t, n, reint = P.publish_with_retry(None, {}, max_retries=3, base_delay=0)
    assert (t, n) == (1, 1) and reint == 1 and calls["n"] == 2


def test_retry_recovers_after_2():
    calls = {"n": 0}
    def fake(db, prop):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("timeout")
        return (2, 0)
    P.publish_one = fake
    t, n, reint = P.publish_with_retry(None, {}, max_retries=3, base_delay=0)
    assert reint == 2 and calls["n"] == 3


def test_permanent_no_retry():
    calls = {"n": 0}
    def fake(db, prop):
        calls["n"] += 1
        raise Exception("HTTP 400 Bad Request")
    P.publish_one = fake
    raised = False
    try:
        P.publish_with_retry(None, {}, max_retries=3, base_delay=0)
    except Exception:
        raised = True
    assert raised and calls["n"] == 1  # error permanente: NO reintenta


def test_transient_exhausts_then_raises():
    calls = {"n": 0}
    def fake(db, prop):
        calls["n"] += 1
        raise Exception("HTTP 503")
    P.publish_one = fake
    raised = False
    try:
        P.publish_with_retry(None, {}, max_retries=2, base_delay=0)
    except Exception:
        raised = True
    assert raised and calls["n"] == 3  # 1 inicial + 2 retries, luego re-lanza


# --- reclaim_stale_publishing: incrementa attempts ---
def test_reclaim_increments_attempts():
    class FakeCur:
        def __init__(self):
            self.sql = None
            self.params = None
        def execute(self, sql, params):
            self.sql = sql
            self.params = params
        def fetchall(self):
            return [{"id": 1}, {"id": 2}]
    cur = FakeCur()
    n = P.reclaim_stale_publishing(cur, older_than_minutes=30, max_attempts=5)
    assert n == 2
    assert "attempts = attempts + 1" in cur.sql      # incrementa attempts
    assert "status = 'publishing'" in cur.sql
    assert cur.params == [30, 5]


def test_reclaim_none():
    class FakeCur:
        def execute(self, sql, params): pass
        def fetchall(self): return []
    assert P.reclaim_stale_publishing(FakeCur(), 30, 5) == 0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:  # error inesperado
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'TODOS OK' if failed == 0 else str(failed) + ' FALLARON'}")
    sys.exit(1 if failed else 0)

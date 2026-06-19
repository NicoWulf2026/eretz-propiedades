"""Tests del scope por run de build_publish_queue (Fase B — ajuste build_queue).

Con mocks: NO toca Supabase, NI red, NI producción.
Ejecutable sin pytest:  python tests/test_build_queue_run_scope.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import scripts.build_publish_queue as B  # noqa: E402


class FakeCur:
    """Cursor mock que captura el SQL ejecutado y devuelve filas predefinidas."""
    def __init__(self, rows=None, one=None):
        self.sqls = []
        self.params = []
        self._rows = rows or []
        self._one = one
    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.params.append(params)
    def fetchall(self):
        return self._rows
    def fetchone(self):
        return self._one


# --- determine_selection_mode (pura) ---
def test_default_sin_flags_es_run_latest():
    assert B.determine_selection_mode(None, False, None) == ("run_latest", None)

def test_run_id_es_modo_run():
    assert B.determine_selection_mode(None, False, 14) == ("run", 14)

def test_include_backlog_es_modo_backlog():
    assert B.determine_selection_mode(None, True, None) == ("backlog", None)

def test_ids_file_tiene_prioridad():
    assert B.determine_selection_mode([1, 2], False, 14) == ("ids_file", None)


# --- latest_finished_run_id usa status='finished' ---
def test_latest_finished_run_id_filtra_finished():
    cur = FakeCur(one={"n": 14})
    rid = B.latest_finished_run_id(cur)
    assert rid == 14
    assert "status = 'finished'" in cur.sqls[0]
    assert "scraping_runs" in cur.sqls[0]

def test_latest_finished_run_id_none_si_no_hay():
    assert B.latest_finished_run_id(FakeCur(one={"n": None})) is None


# --- fetch_staging_rows_by_run acota por run ---
def test_fetch_by_run_filtra_run():
    cur = FakeCur(rows=[{"id": 1}])
    B.fetch_staging_rows_by_run(cur, 14, 100)
    sql = cur.sqls[0]
    assert "scraping_run_id = %s" in sql
    assert "propiedades_raw" in sql and "scraping_run_items" in sql
    assert cur.params[0] == [14, 100]


# --- count_staging_backlog: COUNT solo cuando se llama (dry-run con --show-backlog-count) ---
def test_count_backlog_sql():
    cur = FakeCur(one={"n": 49338})
    n = B.count_staging_backlog(cur)
    assert n == 49338
    assert "COUNT(*)" in cur.sqls[0] and "status = 'staging'" in cur.sqls[0]


# --- Reglas de incompletos INTACTAS: classify_row NO rechaza por campos faltantes ---
def test_incompleto_no_rechaza():
    # Prop sin título, sin precio, sin ciudad/provincia, sin coords: debe encolar.
    row = {
        "id": 1, "inmobiliaria_id": 5, "hash_dedup": "abc",
        "url": "https://x.com/p/1", "url_normalizada": "x.com/p/1",
        "operacion": "consultar",          # operacion desconocida -> consultar, válida
        "precio": None,                    # sin precio: NO bloquea
        "validation_score": 0,             # score bajo con min_score=0: NO bloquea
        "geocoding_status": "pending",     # pending con allow_pending_geo: NO bloquea
        "status": "staging",
    }
    result, priority = B.classify_row(
        row, existing_queue_ids=set(), min_score=0, allow_pending_geo=True
    )
    assert result == "queued", f"incompleto NO debe rechazarse, got {result}"


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
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{'TODOS OK' if failed == 0 else str(failed) + ' FALLARON'}")
    sys.exit(1 if failed else 0)

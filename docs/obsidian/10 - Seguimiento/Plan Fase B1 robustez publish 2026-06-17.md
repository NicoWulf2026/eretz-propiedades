# Plan Fase B.1 — Robustez de publish_to_supabase (2026-06-17)

**Decisión elegida: Modelo B — Robusto.** Pendiente de revisión/aprobación del diff
exacto **antes de implementar**. NO implementado. NO push.

Ver también: [[Auditoria completa y rebranding ERETZ 2026-06-17]] · [[11 - Pendientes]]

Alcance: claim atómico por fila + commit por fila + retry transitorio + reclaim de
`publishing` stale + logging vía `error_logger.py`. Idempotencia intacta. Sin tocar
reglas de negocio, frontend, Neon, scraper monolítico, validate_raw.

---

## 1. Archivos a tocar
- `scripts/publish_to_supabase.py` — nuevas funciones + reescritura del loop de `main`.
- `tests/test_publish_robustez.py` — **nuevo**, con mocks (no toca red ni producción).
- **No** se toca schema (la tabla `internal_scraping.error_log` ya existe de A-bis).

## 2. Flujo nuevo (Modelo B)
```
preflight: reclaim_stale_publishing(older_than_minutes=30) + commit
loop (hasta --limit / --max-supabase-writes):
  fila = claim_one_pending(cur)         # UPDATE→publishing, FOR UPDATE SKIP LOCKED
  commit                                # estado publishing PERSISTIDO por fila
  if fila is None: break
  validar staging (reglas de negocio SIN cambios)
  try:
     total,nuevas,reint = publish_with_retry(db, prop)   # REST idempotente + backoff
     mark_queue_done + mark_staging_published
     commit                            # done PERSISTIDO por fila
  except permanente/agotado:
     mark_queue_failed (error_message, attempts) + commit
dry-run: NO reclama ni marca; usa SELECT de solo lectura; nunca escribe.
```

## 3. Diff exacto propuesto

### 3.1 Imports
```diff
 import argparse
 import os
+import random
 import re
 import sys
 import time
```

### 3.2 Nuevas funciones (insertar antes de `main`)
```python
# Marcadores de error transitorio (reintentable).
_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504",
    "timeout", "timed out", "connection reset", "connectionreset",
    "max retries", "remotedisconnected", "connection aborted",
    "temporarily unavailable", "10054", "read timed out",
)

def is_transient_error(exc: Any) -> bool:
    """True si el error es transitorio (vale la pena reintentar)."""
    try:
        import requests
        if isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout,
                            requests.exceptions.ChunkedEncodingError)):
            return True
    except Exception:
        pass
    msg = str(exc or "").lower()
    # 4xx no-429 = permanente (no reintentar)
    if any(c in msg for c in ("400", "401", "403", "404", "409", "422")) and "429" not in msg:
        return False
    return any(m in msg for m in _TRANSIENT_MARKERS)


def publish_with_retry(db, prop, *, max_retries=3, base_delay=1.0, max_delay=30.0,
                       queue_id=None, run_id=None, worker=None):
    """Publica con retry para transitorios. Devuelve (total, nuevas, reintentos).
    Re-lanza si el error es permanente o se agotan los retries (caller marca failed).
    Idempotente: save_propiedades hace upsert por url_normalizada."""
    attempt = 0
    while True:
        try:
            total, nuevas = publish_one(db, prop)
            if attempt > 0:
                _log_error(fase="publish", error_type="transient_recovered",
                           severidad="warning", recuperable=True, reintentos=attempt,
                           accion_tomada="retry", estado_final="done",
                           afecto_publicacion=True, propiedad_id=queue_id,
                           run_id=run_id, worker=worker, db_url=_ABIS_DB_URL,
                           mensaje=f"recuperado tras {attempt} reintento(s)")
            return total, nuevas, attempt
        except Exception as exc:
            transient = is_transient_error(exc)
            if not transient or attempt >= max_retries:
                _log_error(fase="publish",
                           error_type=("transient_exhausted" if transient else "permanent_error"),
                           severidad="warning", recuperable=False, reintentos=attempt,
                           accion_tomada="give_up", estado_final="failed",
                           afecto_publicacion=False, propiedad_id=queue_id,
                           run_id=run_id, worker=worker, mensaje=str(exc), db_url=_ABIS_DB_URL)
                raise
            attempt += 1
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, delay * 0.25)  # jitter
            _log_error(fase="publish", error_type="transient_retry",
                       severidad="warning", recuperable=True, reintentos=attempt,
                       accion_tomada=f"retry_in_{delay:.1f}s", estado_final="retrying",
                       afecto_publicacion=False, propiedad_id=queue_id,
                       run_id=run_id, worker=worker, mensaje=str(exc), db_url=_ABIS_DB_URL)
            time.sleep(delay)


def reclaim_stale_publishing(cur, older_than_minutes: int = 30, max_attempts: int = 5):
    """Devuelve a 'pending' las filas 'publishing' viejas (proceso anterior cortado).
    Respeta tope de attempts. Registra el reclaim. NO commitea (el caller commitea)."""
    cur.execute(
        """
        UPDATE publish_queue
        SET status = 'pending'
        WHERE status = 'publishing'
          AND COALESCE(last_attempt_at, queued_at) < now() - make_interval(mins => %s)
          AND attempts < %s
        RETURNING id
        """,
        [older_than_minutes, max_attempts],
    )
    rows = cur.fetchall()
    n = len(rows)
    if n:
        _log_error(fase="publish", error_type="reclaim_stale_publishing",
                   severidad="warning", recuperable=True, accion_tomada="reset_to_pending",
                   estado_final="pending", afecto_publicacion=False, db_url=_ABIS_DB_URL,
                   mensaje=f"reclamadas {n} filas publishing > {older_than_minutes}min")
    return n


def claim_one_pending(cur, staging_ids_filter=None):
    """Reclama UNA fila pending de forma atómica y la marca publishing.
    FOR UPDATE SKIP LOCKED garantiza que dos workers no reclamen la misma fila.
    Retorna dict de la fila o None. NO commitea (el caller commitea)."""
    extra = "AND staging_id = ANY(%(sids)s)" if staging_ids_filter else ""
    cur.execute(
        f"""
        UPDATE publish_queue
        SET status = 'publishing', last_attempt_at = now()
        WHERE id = (
            SELECT id FROM publish_queue
            WHERE status = 'pending' {extra}
            ORDER BY priority ASC, queued_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING id, staging_id, propiedad_supabase_id, action, priority, attempts, status
        """,
        {"sids": staging_ids_filter} if staging_ids_filter else {},
    )
    row = cur.fetchone()
    return dict(row) if row else None
```

### 3.3 Reescritura del loop en `main` (commit mode)
- **Antes:** `mark_queue_publishing(TODAS)` → loop → `conn.commit()` único al final.
- **Después (commit mode):**
  ```python
  with connect_internal_db(db_url) as conn:
      with conn.cursor() as cur:
          reclaim_stale_publishing(cur, older_than_minutes=args.reclaim_minutes)
      conn.commit()
      while published_ok + deactivated_ok + failed < args.limit and writes_used < args.max_supabase_writes:
          with conn.cursor() as cur:
              fila = claim_one_pending(cur, staging_ids_filter)
          conn.commit()                      # publishing persistido por fila
          if fila is None:
              break
          # ... validar + publish_with_retry + mark_done/mark_failed ...
          conn.commit()                      # done/failed persistido por fila
  ```
- **dry-run:** sin cambios — usa `fetch_queue_rows(commit=False)` (SELECT solo lectura),
  imprime "DRY-RUN would publish", `conn.rollback()`. No reclama ni marca.

### 3.4 Nuevos args (con defaults seguros)
```diff
+parser.add_argument("--max-retries", type=int, default=3)
+parser.add_argument("--reclaim-minutes", type=int, default=30)
```

## 4. Tests nuevos (`tests/test_publish_robustez.py`, con mocks, sin red)
- `is_transient_error`: 429, 500/502/503/504, timeout, ConnectionReset → True; 400/404/validation → False.
- retry recupera tras 1 y tras 2 fallos transitorios (mock `publish_one` que falla N veces y luego OK).
- error permanente (400) → no reintenta (1 sola llamada).
- transitorio que agota `max_retries` → re-lanza → caller marca failed.
- `reclaim_stale_publishing`: marca pending solo las publishing viejas con attempts<max.
- logger registra retry/recuperación/failed sin romper (mock `_log_error`).
- dry-run sigue sin escribir (smoke test).

## 5. Riesgos
- **ALTO**: escribe producción. Mitigación: dry-run + tests con mocks + prueba real chica (`--limit 10`) + rollback git.
- Backoff mal calibrado → tandas largas. Mitigación: `max_delay=30s`, `max_retries=3`.
- Commit por fila = más round-trips a Postgres (latencia). Mitigación: aceptable; el cuello real es el REST a Supabase, no el commit local.
- `make_interval` requiere PG ≥ 9.4 (Supabase es 17 → OK).

## 6. Validaciones (antes de aplicar, ya con el diff)
```
python -m py_compile scripts/publish_to_supabase.py scraper/error_logger.py tests/test_publish_robustez.py
python tests/test_publish_robustez.py            # suite con mocks
python tests/test_error_logger_redaction.py      # sigue 7/7
python scripts/publish_to_supabase.py --limit 5 --dry-run   # comportamiento intacto
```

## 7. Prueba real chica (NO ejecutar todavía)
```
# requiere cola con pending; hoy pending=0, habría que encolar unas pocas primero
python scripts/publish_to_supabase.py --limit 10 --max-supabase-writes 10 --commit
# verificar: failed=0, publishing=0, pending bajó, public.propiedades consistente,
#            error_log sin entradas inesperadas
```

## 8. Rollback
- Todo en rama `chore/fase-a-eretz-higiene` (o rama nueva de B.1), **sin push**.
- `git checkout scripts/publish_to_supabase.py` revierte el script.
- Idempotente: revertir y re-correr es seguro (upsert por url_normalizada).
- `error_log` solo acumula (no se revierte; es histórico).

## Estado
**Modelo B — Robusto, pendiente de diff exacto y aprobación antes de implementar.**
Este documento ES el diff exacto propuesto. Falta tu OK para crear los archivos.

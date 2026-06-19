"""Logger de errores del pipeline ERETZ Propiedades.

Diseño (Fase A-bis):
  - JSONL append-only por corrida: SIEMPRE primero (fuente durable; sobrevive cortes).
  - tabla internal_scraping.error_log: best-effort, SOLO si se pasa `db_url`.
  - Conexión a la tabla: EFÍMERA y autocommit (NO comparte transacción con el caller).
    Un fallo al insertar en la tabla nunca rompe ni ensucia la transacción del publish.
  - log_error() NUNCA lanza excepción: no puede tumbar scraping, publish ni drain.
  - Redacción obligatoria de secretos antes de escribir a archivo o tabla.

Severidades: critical | warning | soft | incomplete | prohibited_source
  - incomplete  -> propiedad con dato faltante (NO es error crítico ni hard reject).
  - soft        -> data_quality issue (missing_images, etc.).
  - warning     -> error recuperable / transitorio.
  - critical    -> error no recuperable.
  - prohibited_source -> Zonaprop/Argenprop detectados (NO se scrapean).
"""

from __future__ import annotations

import datetime
import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_MAX_FIELD = 4000  # nunca loguear respuestas/HTML gigantes

# ---------------------------------------------------------------------------
# Redacción obligatoria de secretos
# ---------------------------------------------------------------------------
_REDACTIONS = [
    # connection strings: postgresql://user:password@host/db  -> ://<redacted>@
    (re.compile(r"(://)[^@/\s]+(@)"), r"\1<redacted>\2"),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"), r"\1<redacted>"),
    # JWT (anon key / service_role key): eyJ....<...>.<...>
    (re.compile(r"eyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]+"), "<redacted_jwt>"),
    # tokens tipo sk-...
    (re.compile(r"sk-[A-Za-z0-9]{8,}"), "<redacted_token>"),
    # querystrings sensibles: ?apikey=... &token=... &password=... &access_token=... &key=...
    (re.compile(r"(?i)([?&](?:apikey|api_key|access_token|token|password|passwd|key|secret)=)[^&\s#]+"),
     r"\1<redacted>"),
    # pares clave=valor sensibles: service_role=..., password: ..., bearer ...
    (re.compile(r"(?i)\b(service_role|api[_-]?key|password|passwd|secret|token)\b\s*[=:]\s*\S+"),
     r"\1=<redacted>"),
]


def redact(text: Optional[Any]) -> Optional[str]:
    """Redacta secretos y trunca. Devuelve None si la entrada es None."""
    if text is None:
        return None
    s = str(text)
    for rx, repl in _REDACTIONS:
        s = rx.sub(repl, s)
    if len(s) > _MAX_FIELD:
        s = s[:_MAX_FIELD] + "...[truncated]"
    return s


# ---------------------------------------------------------------------------
# Destino 1: JSONL append-only por corrida
# ---------------------------------------------------------------------------
def _jsonl_path(run_id: Optional[int]) -> Path:
    d = _REPO / "logs"
    d.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d")
    return d / f"errors_run{run_id if run_id is not None else 'NA'}_{ts}.jsonl"


def _write_jsonl(rec: dict, run_id: Optional[int]) -> None:
    try:
        line = json.dumps(rec, ensure_ascii=False)
        with _LOCK, open(_jsonl_path(run_id), "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except Exception:
        # El logger jamás debe romper el proceso por un fallo de archivo.
        pass


# ---------------------------------------------------------------------------
# Destino 2: tabla internal_scraping.error_log (best-effort, conexión efímera)
# ---------------------------------------------------------------------------
_INSERT_SQL = """
INSERT INTO internal_scraping.error_log
  (run_id, inmobiliaria_id, inmobiliaria_nombre, source_url, fase, error_type,
   mensaje, detalle, severidad, recuperable, reintentos, accion_tomada, estado_final,
   worker, afecto_publicacion, requiere_revision_manual, propiedad_id, raw_id, queue_id)
VALUES
  (%(run_id)s, %(inmobiliaria_id)s, %(inmobiliaria_nombre)s, %(source_url)s, %(fase)s,
   %(error_type)s, %(mensaje)s, %(detalle)s, %(severidad)s, %(recuperable)s, %(reintentos)s,
   %(accion_tomada)s, %(estado_final)s, %(worker)s, %(afecto_publicacion)s,
   %(requiere_revision_manual)s, %(propiedad_id)s, %(raw_id)s, %(queue_id)s)
"""


def _write_table(rec: dict, db_url: str) -> None:
    """Inserta en error_log usando una conexión EFÍMERA autocommit, aislada del caller.

    Si la DB falla, no rompe nada: el JSONL ya quedó escrito. La conexión propia
    garantiza que un error aquí no haga rollback ni ensucie la transacción del publish.
    """
    conn = None
    try:
        import psycopg  # import diferido: el logger no exige psycopg para el JSONL
        conn = psycopg.connect(db_url, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(_INSERT_SQL, rec)
    except Exception:
        # DB caída / insert inválido -> solo queda el JSONL. Nunca propagar.
        pass
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------
def log_error(
    *,
    fase: str,
    error_type: str,
    severidad: str = "warning",
    mensaje: Optional[str] = None,
    detalle: Optional[str] = None,
    run_id: Optional[int] = None,
    inmobiliaria_id: Optional[int] = None,
    inmobiliaria_nombre: Optional[str] = None,
    source_url: Optional[str] = None,
    recuperable: Optional[bool] = None,
    reintentos: int = 0,
    accion_tomada: Optional[str] = None,
    estado_final: Optional[str] = None,
    worker: Optional[str] = None,
    afecto_publicacion: Optional[bool] = None,
    requiere_revision_manual: bool = False,
    propiedad_id: Optional[int] = None,
    raw_id: Optional[int] = None,
    queue_id: Optional[int] = None,
    db_url: Optional[str] = None,
) -> None:
    """Registra un error en JSONL (siempre) y en tabla (best-effort si hay db_url).

    NUNCA lanza excepción. Todos los textos pasan por redact() antes de persistir.
    Cuándo se escribe cada destino:
      - JSONL: SIEMPRE (primero). Es la fuente durable.
      - tabla error_log: solo si `db_url` no es None, con conexión efímera propia.
    """
    try:
        rec = {
            "ocurrido_en": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "run_id": run_id,
            "inmobiliaria_id": inmobiliaria_id,
            "inmobiliaria_nombre": redact(inmobiliaria_nombre),
            "source_url": redact(source_url),
            "fase": fase,
            "error_type": error_type,
            "mensaje": redact(mensaje),
            "detalle": redact(detalle),
            "severidad": severidad,
            "recuperable": recuperable,
            "reintentos": reintentos,
            "accion_tomada": accion_tomada,
            "estado_final": estado_final,
            "worker": worker,
            "afecto_publicacion": afecto_publicacion,
            "requiere_revision_manual": requiere_revision_manual,
            "propiedad_id": propiedad_id,
            "raw_id": raw_id,
            "queue_id": queue_id,
        }
    except Exception:
        return  # construir el registro nunca debe romper

    # 1) JSONL SIEMPRE primero (durable)
    _write_jsonl(rec, run_id)

    # 2) tabla best-effort, solo si hay db_url (conexión propia, aislada)
    if db_url:
        _write_table(rec, db_url)

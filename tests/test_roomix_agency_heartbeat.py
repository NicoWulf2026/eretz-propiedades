"""Tests del heartbeat remoto del crawler Roomix Agency Coverage.

Ejecutable sin pytest:  python tests/test_roomix_agency_heartbeat.py

Cubre lo exigido por la misión de observabilidad:
  - serialización del heartbeat
  - completion_pct correcto
  - real_estate_entities = INMOBILIARIA + OFICINA_FRANQUICIA
  - un fallo/timeout de Supabase NO mata ni frena el crawler
  - no se filtran secretos ni datos comerciales de la propiedad
  - estado COMPLETED
  - reanudación desde checkpoint (no reinicia contadores)
  - ETA razonable por throughput reciente
  - detección de heartbeat stale
  - throttling: NO se escribe una vez por ficha
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scraper.roomix_agency_heartbeat import (  # noqa: E402
    CrawlHeartbeat,
    is_stalled,
    sanitize_ref,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    VALID_STATUSES,
)

# --- Secretos FALSOS de prueba (no son reales) ---
FAKE_PASS = "SuperSecret123FAKE"
FAKE_DB_URL = f"postgresql://eretz_preview_ro:{FAKE_PASS}@db.proj.supabase.co:5432/postgres"
FAKE_TOKEN = "abc123FAKE"


class Clock:
    """Reloj inyectable para tests deterministas."""

    def __init__(self, t: float = 1_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _hb(tmp: Path, clock: Clock, **kw) -> CrawlHeartbeat:
    kw.setdefault("run_id", "roomix-test")
    kw.setdefault("jsonl_path", tmp / "hb.jsonl")
    kw.setdefault("time_fn", clock)
    kw.setdefault("sample_interval_seconds", 0)
    return CrawlHeartbeat(**kw)


def _lines(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# --------------------------------------------------------------------------
# Serialización
# --------------------------------------------------------------------------
def test_heartbeat_serializa_a_jsonl_valido():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock(), total_listings=168563, crawler_version="1.4.2",
                 matcher_version="m7")
        hb.start(processed_listings=18120)
        recs = _lines(tmp / "hb.jsonl")
        assert len(recs) == 1, recs
        r = recs[0]
        assert r["run_id"] == "roomix-test"
        assert r["status"] == STATUS_RUNNING
        assert r["processed_listings"] == 18120
        assert r["crawler_version"] == "1.4.2"
        assert r["matcher_version"] == "m7"
        assert "started_at" in r and "last_heartbeat_at" in r
        json.dumps(r)  # debe ser serializable sin ayuda


def test_status_invalido_se_ignora():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock())
        hb.update(status="BANANA", processed_listings=5)
        assert hb.snapshot()["status"] in VALID_STATUSES
        assert hb.snapshot()["status"] == STATUS_RUNNING


# --------------------------------------------------------------------------
# Métricas derivadas
# --------------------------------------------------------------------------
def test_completion_pct_correcto():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock(), total_listings=200)
        hb.update(processed_listings=50)
        assert hb.snapshot()["completion_pct"] == 25.0


def test_completion_pct_none_sin_total():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock())
        hb.update(processed_listings=50)
        assert hb.snapshot()["completion_pct"] is None


def test_completion_pct_no_supera_100():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock(), total_listings=100)
        hb.update(processed_listings=140)  # delta final puede exceder el snapshot
        assert hb.snapshot()["completion_pct"] == 100.0


def test_real_estate_entities_es_inmobiliaria_mas_oficina():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock())
        hb.update(inmobiliarias=3073, oficinas_franquicia=263,
                  agentes=1064, developers=40, unknown=285, garbage=7)
        snap = hb.snapshot()
        assert snap["real_estate_entities"] == 3073 + 263 == 3336
        # agentes/developers/unknown/garbage NO inflan el padrón objetivo
        for f in ("agentes", "developers", "unknown", "garbage"):
            assert snap[f] > 0
        assert snap["real_estate_entities"] < sum(
            snap[f] for f in ("inmobiliarias", "oficinas_franquicia", "agentes",
                              "developers", "unknown", "garbage"))


# --------------------------------------------------------------------------
# Robustez: Supabase caído nunca frena el crawl
# --------------------------------------------------------------------------
def test_timeout_de_supabase_no_mata_el_crawler():
    class _BoomPsycopg:
        @staticmethod
        def connect(*a, **k):
            raise TimeoutError("simulated supabase timeout")

    saved = sys.modules.get("psycopg")
    sys.modules["psycopg"] = _BoomPsycopg  # type: ignore[assignment]
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            hb = _hb(tmp, Clock(), db_url=FAKE_DB_URL, total_listings=1000)
            hb.start(processed_listings=10)      # no debe lanzar
            hb.update(processed_listings=20, force=True)
            recs = _lines(tmp / "hb.jsonl")
            # el JSONL local (fuente durable) siguió escribiéndose igual
            assert len(recs) == 2, recs
            assert recs[-1]["processed_listings"] == 20
    finally:
        if saved is not None:
            sys.modules["psycopg"] = saved
        else:
            sys.modules.pop("psycopg", None)


def test_jsonl_ilegible_no_mata_el_crawler():
    with tempfile.TemporaryDirectory() as d:
        # ruta inválida: el directorio es en realidad un archivo
        bad = Path(d) / "archivo"
        bad.write_text("x", encoding="utf-8")
        hb = CrawlHeartbeat(run_id="r", jsonl_path=bad / "sub" / "hb.jsonl",
                            time_fn=Clock())
        hb.start(processed_listings=1)  # no debe lanzar


# --------------------------------------------------------------------------
# Seguridad: sin secretos, sin datos comerciales
# --------------------------------------------------------------------------
def test_no_filtra_db_url_ni_secretos():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock(), db_url=FAKE_DB_URL)
        hb.start(processed_listings=1,
                 last_listing_ref=f"https://roomix.com/ficha/123?token={FAKE_TOKEN}")
        blob = (tmp / "hb.jsonl").read_text(encoding="utf-8")
        assert FAKE_PASS not in blob, blob
        assert FAKE_TOKEN not in blob, blob
        assert "postgresql://" not in blob, blob
        assert json.dumps(hb.snapshot()).find(FAKE_PASS) == -1


def test_descarta_datos_comerciales_de_la_propiedad():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock())
        hb.update(processed_listings=1, precio=350000, descripcion="Depto 3 amb",
                  fotos=["a.jpg"], amenities=["pileta"])
        snap = hb.snapshot()
        for prohibido in ("precio", "descripcion", "fotos", "amenities"):
            assert prohibido not in snap, snap


def test_sanitize_ref_quita_querystring_y_fragment():
    out = sanitize_ref(f"https://roomix.com/f/1?token={FAKE_TOKEN}#foto3")
    assert FAKE_TOKEN not in out
    assert out == "https://roomix.com/f/1"


# --------------------------------------------------------------------------
# Estados
# --------------------------------------------------------------------------
def test_completed_status_se_emite():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock(), total_listings=100)
        hb.start(processed_listings=100)
        hb.mark_completed(processed_listings=100)
        recs = _lines(tmp / "hb.jsonl")
        assert recs[-1]["status"] == STATUS_COMPLETED
        assert recs[-1]["completion_pct"] == 100.0


def test_failed_status_se_emite():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock())
        hb.start(processed_listings=5)
        hb.mark_failed()
        assert _lines(tmp / "hb.jsonl")[-1]["status"] == STATUS_FAILED


def test_cambio_de_estado_fuerza_escritura():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        hb = _hb(tmp, Clock(), min_interval_seconds=99999, min_listings_delta=99999)
        hb.start(processed_listings=1)
        n0 = len(_lines(tmp / "hb.jsonl"))
        hb.set_status("PAUSED")
        assert len(_lines(tmp / "hb.jsonl")) == n0 + 1


# --------------------------------------------------------------------------
# Reanudación
# --------------------------------------------------------------------------
def test_resume_no_reinicia_contadores():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        # Segunda instancia del MISMO run: reanuda desde el checkpoint local.
        hb = _hb(tmp, Clock(), run_id="roomix-2026-08", total_listings=168563)
        hb.start(processed_listings=18120, last_checkpoint="ck-18120")
        snap = hb.snapshot()
        assert snap["processed_listings"] == 18120, "no debe arrancar de cero"
        assert snap["last_checkpoint"] == "ck-18120"
        assert snap["status"] == STATUS_RUNNING
        assert snap["run_id"] == "roomix-2026-08", "mismo run_id => upsert idempotente"


# --------------------------------------------------------------------------
# ETA
# --------------------------------------------------------------------------
def test_eta_razonable_por_throughput_reciente():
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        hb = _hb(Path(d), clock, total_listings=1000)
        hb.update(processed_listings=0)
        clock.advance(100)
        hb.update(processed_listings=100)      # 1 ficha/segundo
        eta = hb.snapshot()["eta_seconds"]
        assert eta is not None
        assert 850 <= eta <= 950, eta          # ~900 restantes a 1/s


def test_eta_none_sin_muestras_suficientes():
    with tempfile.TemporaryDirectory() as d:
        hb = _hb(Path(d), Clock(), total_listings=1000)
        hb.update(processed_listings=10)
        assert hb.snapshot()["eta_seconds"] is None


def test_eta_none_sin_total_conocido():
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        hb = _hb(Path(d), clock)
        hb.update(processed_listings=0)
        clock.advance(100)
        hb.update(processed_listings=100)
        assert hb.snapshot()["eta_seconds"] is None


def test_eta_cero_al_completar():
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        hb = _hb(Path(d), clock, total_listings=100)
        hb.update(processed_listings=0)
        clock.advance(50)
        hb.update(processed_listings=100)
        assert hb.snapshot()["eta_seconds"] == 0


def test_eta_usa_ventana_reciente_no_promedio_historico():
    """Si el crawler se acelera, el ETA debe reflejar el ritmo NUEVO."""
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        hb = _hb(Path(d), clock, total_listings=10_000, eta_window_seconds=100)
        hb.update(processed_listings=0)
        clock.advance(1000)
        hb.update(processed_listings=100)      # tramo lento: 0.1/s
        clock.advance(50)
        hb.update(processed_listings=600)      # tramo rápido: 10/s
        clock.advance(50)
        hb.update(processed_listings=1100)     # sigue a 10/s
        eta = hb.snapshot()["eta_seconds"]
        # A ritmo histórico (~1.1/s) el ETA sería ~8000s; con ventana reciente ~890s.
        assert eta is not None
        assert eta < 2000, f"el ETA quedó anclado al promedio histórico: {eta}"


# --------------------------------------------------------------------------
# Stall detection (lado lectura)
# --------------------------------------------------------------------------
def test_stale_heartbeat_detection():
    import datetime
    now = datetime.datetime(2026, 8, 18, 12, 0, tzinfo=datetime.timezone.utc)
    now_ts = now.timestamp()
    viejo = (now - datetime.timedelta(minutes=45)).isoformat()
    reciente = (now - datetime.timedelta(minutes=5)).isoformat()

    assert is_stalled(viejo, "RUNNING", now=now_ts) is True
    assert is_stalled(reciente, "RUNNING", now=now_ts) is False
    # un COMPLETED viejo no es un stall
    assert is_stalled(viejo, "COMPLETED", now=now_ts) is False
    assert is_stalled(viejo, "PAUSED", now=now_ts) is False
    assert is_stalled(viejo, "FAILED", now=now_ts) is False
    # datos ilegibles -> no inventar un stall
    assert is_stalled("no-es-fecha", "RUNNING", now=now_ts) is False
    assert is_stalled(None, "RUNNING", now=now_ts) is False


# --------------------------------------------------------------------------
# Throttling: el monitor no puede castigar al crawler
# --------------------------------------------------------------------------
def test_no_escribe_una_vez_por_ficha():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        clock = Clock()
        hb = _hb(tmp, clock, total_listings=1_000_000,
                 min_interval_seconds=300, min_listings_delta=250)
        hb.start(processed_listings=0)
        for i in range(1, 200):            # 199 fichas, <250 y <300s
            clock.advance(1)
            hb.update(processed_listings=i)
        assert len(_lines(tmp / "hb.jsonl")) == 1, "escribió más de un heartbeat"


def test_flush_por_intervalo_de_tiempo():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        clock = Clock()
        hb = _hb(tmp, clock, min_interval_seconds=300, min_listings_delta=999999)
        hb.start(processed_listings=0)
        clock.advance(301)
        hb.update(processed_listings=3)
        assert len(_lines(tmp / "hb.jsonl")) == 2


def test_flush_por_delta_de_listings():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        clock = Clock()
        hb = _hb(tmp, clock, min_interval_seconds=999999, min_listings_delta=250)
        hb.start(processed_listings=0)
        hb.update(processed_listings=249)
        assert len(_lines(tmp / "hb.jsonl")) == 1
        hb.update(processed_listings=250)
        assert len(_lines(tmp / "hb.jsonl")) == 2


# --------------------------------------------------------------------------
# Runner standalone
# --------------------------------------------------------------------------
if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    fallos = 0
    for nombre, fn in fns:
        try:
            fn()
            print(f"  PASS  {nombre}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"  FAIL  {nombre}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - fallos}/{len(fns)} tests OK")
    sys.exit(1 if fallos else 0)

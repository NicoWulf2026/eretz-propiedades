"""Tests para scripts/create_retry_run_from_error_items.py (logica pura, sin DB)."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.create_retry_run_from_error_items import (  # noqa: E402
    ALLOWED_ERROR_TYPES,
    PROHIBITED_CMS,
    build_retry_item_payload,
    parse_error_types,
    select_candidates,
    skip_reason_for_row,
)


def _row(**over):
    base = {
        "id": 111,
        "scraping_run_id": 21,
        "inmobiliaria_id": 696,
        "inmobiliaria_nombre": "Alianza Real Estate",
        "ciudad": "Cordoba",
        "provincia": "Cordoba",
        "web": "http://alianzarealestate.com.ar",
        "url_listado": "http://alianzarealestate.com.ar/propiedades",
        "cms_detectado": "custom",
        "error_type": "timeout",
    }
    base.update(over)
    return base


# 1. Copia correcta de campos error -> nuevo item pending
def test_build_payload_copia_campos():
    p = build_retry_item_payload(999, _row(), notes="retry b", created_at_iso="2026-06-23T00:00:00Z")
    assert p["scraping_run_id"] == 999
    assert p["status"] == "pending"
    assert p["inmobiliaria_id"] == 696
    assert p["inmobiliaria_nombre"] == "Alianza Real Estate"
    assert p["ciudad"] == "Cordoba"
    assert p["provincia"] == "Cordoba"
    assert p["web"] == "http://alianzarealestate.com.ar"
    assert p["url_listado"] == "http://alianzarealestate.com.ar/propiedades"
    assert p["cms_detectado"] == "custom"
    md = p["metadata"]
    assert md["created_from"] == "create_retry_run_from_error_items"
    assert md["retry_of_run_id"] == 21
    assert md["original_run_item_id"] == 111
    assert md["original_error_type"] == "timeout"
    assert md["notes"] == "retry b"


# 2. Allowlist acepta los 3 tipos
@pytest.mark.parametrize("et", ["timeout", "item_timeout", "static_timeout"])
def test_allowlist_acepta(et):
    assert skip_reason_for_row(_row(error_type=et), sorted(ALLOWED_ERROR_TYPES)) is None
    assert parse_error_types(et) == [et]


# 3. Rechaza requires_playwright / site_down / skipped_invalid_source
@pytest.mark.parametrize("et", ["requires_playwright", "site_down_confirmed", "skipped_invalid_source",
                                 "no_property_links", "sin_propiedades"])
def test_rechaza_no_permitidos(et):
    reason = skip_reason_for_row(_row(error_type=et), sorted(ALLOWED_ERROR_TYPES))
    assert reason is not None and ("rechazado" in reason or "no_permitido" in reason)
    with pytest.raises(SystemExit):
        parse_error_types(et)


# 4. Skip si falta web o url_listado
def test_skip_sin_web():
    assert skip_reason_for_row(_row(web=None), sorted(ALLOWED_ERROR_TYPES)) == "sin_web"
    assert skip_reason_for_row(_row(web="  "), sorted(ALLOWED_ERROR_TYPES)) == "sin_web"


def test_skip_sin_url_listado():
    assert skip_reason_for_row(_row(url_listado=None), sorted(ALLOWED_ERROR_TYPES)) == "sin_url_listado"


# 5. Skip si CMS es zonaprop / argenprop
@pytest.mark.parametrize("cms", sorted(PROHIBITED_CMS))
def test_skip_cms_prohibido(cms):
    reason = skip_reason_for_row(_row(cms_detectado=cms.upper()), sorted(ALLOWED_ERROR_TYPES))
    assert reason == f"cms_prohibido:{cms}"


# 6. Dedup: no crea si ya hay pending
def test_dedup_pending_existente():
    rows = [_row(inmobiliaria_id=696)]
    to_create, skips = select_candidates(rows, sorted(ALLOWED_ERROR_TYPES), existing_pending_ids={696}, limit=5)
    assert to_create == []
    assert any(s["reason"] == "ya_tiene_pending" for s in skips)


def test_dedup_duplicado_en_lote():
    rows = [_row(id=1, inmobiliaria_id=696), _row(id=2, inmobiliaria_id=696)]
    to_create, skips = select_candidates(rows, sorted(ALLOWED_ERROR_TYPES), existing_pending_ids=set(), limit=5)
    assert len(to_create) == 1
    assert any(s["reason"] == "duplicado_en_lote" for s in skips)


# 7. (dry-run no escribe) — cubierto a nivel de logica: select_candidates es puro y
#    main() hace rollback en dry-run. Verificamos que el filtrado no muta las filas.
def test_select_no_muta_filas():
    rows = [_row()]
    snapshot = dict(rows[0])
    select_candidates(rows, sorted(ALLOWED_ERROR_TYPES), existing_pending_ids=set(), limit=5)
    assert rows[0] == snapshot


# 8. ids-file / limit: respeta el limite
def test_respeta_limit():
    rows = [_row(id=i, inmobiliaria_id=1000 + i) for i in range(10)]
    to_create, _ = select_candidates(rows, sorted(ALLOWED_ERROR_TYPES), existing_pending_ids=set(), limit=3)
    assert len(to_create) == 3


# Extra: parse_error_types coma-separado y default
def test_parse_error_types_default_y_coma():
    assert parse_error_types(None) == sorted(ALLOWED_ERROR_TYPES)
    assert parse_error_types("timeout,item_timeout") == sorted({"timeout", "item_timeout"})
    with pytest.raises(SystemExit):
        parse_error_types("timeout,requires_playwright")

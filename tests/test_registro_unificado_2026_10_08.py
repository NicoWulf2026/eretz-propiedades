"""El registro unificado da a cada agencia un estado excluyente y su proxima accion (mision 08-10)."""
from __future__ import annotations

from scripts.registro_unificado import ACCION, estado_canonico


def _ident(status="READY", url="https://a.com.ar"):
    return {"identity_status": status, "official_url": url}


def _reg(resolucion="RESOLVED", web_kind="OFFICIAL_WEB"):
    return {"resolution": {"resolution_status": resolucion}, "platform": {"web_kind": web_kind}}


def test_el_primer_estado_que_aplica_manda():
    # Conflicto le gana a todo: certificar una identidad ambigua no la vuelve de nadie.
    assert estado_canonico(_ident(), _reg("AMBIGUOUS"), {"status": "CERTIFIED_COMPLETE"},
                           set(), set(), "x") == "IDENTIDAD_CONFLICTIVA"
    assert estado_canonico(_ident("BLOCKED_EXTERNAL"), _reg(), None, set(), set(), "x") == "SIN_WEB_PROPIA"
    assert estado_canonico(_ident(), _reg(), None, {"x"}, set(), "x") == "SIN_WEB_PROPIA"
    assert estado_canonico(_ident("IDENTITY_PENDING", None), _reg(), None, set(), set(), "x") == "SIN_WEB"
    assert estado_canonico(_ident("IDENTITY_PENDING"), _reg(), None, set(), set(), "x") == "WEB_SIN_VERIFICAR"


def test_las_listas_se_reparten_por_su_cierre_vigente():
    ok = _ident(), _reg()
    assert estado_canonico(*ok, None, set(), set(), "x") == "LISTA_PARA_SCRAPEAR"
    assert estado_canonico(*ok, {"status": "CERTIFIED_BEST_AVAILABLE"}, set(), set(), "x") == "CERTIFICADA"
    assert estado_canonico(*ok, {"status": "NEEDS_FIX"}, set(), set(), "x") == "NEEDS_FIX"
    assert estado_canonico(*ok, {"status": "IDENTITY_PENDING"}, set(), set(), "x") == "NEEDS_FIX"
    assert estado_canonico(*ok, {"status": "BLOCKED_EXTERNAL"}, set(), set(), "x") == "BLOCKED_EXTERNAL"
    assert estado_canonico(*ok, {"status": "NO_INVENTORY_CONFIRMED"}, set(), set(),
                           "x") == "SIN_INVENTARIO_CONFIRMADO"


def test_todo_estado_tiene_proxima_accion():
    for estado in ("IDENTIDAD_CONFLICTIVA", "SIN_WEB_PROPIA", "SIN_WEB", "WEB_SIN_VERIFICAR", "LISTA_PARA_SCRAPEAR",
                   "NEEDS_FIX", "BLOCKED_EXTERNAL", "SIN_INVENTARIO_CONFIRMADO", "CERTIFICADA",
                   "MAIN_SIN_DATOS_LOCALES", "MAIN_CON_HOST_SIN_IDENTIDAD"):
        assert ACCION[estado]

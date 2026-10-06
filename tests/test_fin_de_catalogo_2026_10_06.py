"""COMPLETE exige prueba positiva de que el catalogo termina donde termino la enumeracion.

Medido el 06-10 contra la fuente (barrido `scripts/baseline_del_sprint.py`): de 614 COMPLETE,
17 venian de UNA pagina HTML sin total declarado. `cipollone` certificaba los 12 destacados de
la portada mientras /catalogo/VENTA publica otras fichas (ids 23-42); `constant` 24 de una
pagina con 7 fichas mas enlazadas en el propio sitio. Lo leido se publica igual: lo que cambia
es que no se afirma COMPLETE sin prueba.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ), str(RAIZ / "scripts")]

from agency_certifier import certification_status  # noqa: E402

COMP = {"same_url_set": True, "idempotent": True, "identity_collisions": 0}


def _run(**k):
    base = {"estado": "OK", "detalles_fallidos": 0, "enumeracion_agotada": True,
            "enumeradas": 12, "paginas": 1}
    return dict(base, **k)


def _enum():
    return {"enumerated": 12, "pages_observed": 1}


def test_MUERDE_una_pagina_html_sin_total_no_es_complete() -> None:
    r = _run(variante="LISTADO_HTML")
    status, razones = certification_status(r, r, COMP, _enum(), {})
    assert status == "CERTIFIED_BEST_AVAILABLE"
    assert "NO_POSITIVE_END_OF_CATALOG_EVIDENCE" in razones


def test_MUERDE_wordpress_html_de_una_pagina_tampoco() -> None:
    r = _run(variante="WORDPRESS_HTML", enumeradas=24)
    assert certification_status(r, r, COMP, _enum(), {})[0] == "CERTIFIED_BEST_AVAILABLE"


def test_con_total_declarado_que_coincide_sigue_complete() -> None:
    r = _run(variante="LISTADO_HTML", total_declarado=12)
    assert certification_status(r, r, COMP, _enum(), {})[0] == "CERTIFIED_COMPLETE"


def test_con_paginacion_seguida_sigue_complete() -> None:
    r = _run(variante="LISTADO_HTML", paginas=3, enumeradas=40)
    assert certification_status(r, r, COMP, {"enumerated": 40, "pages_observed": 3}, {})[0] \
        == "CERTIFIED_COMPLETE"


def test_las_variantes_con_fin_propio_no_cambian() -> None:
    # Sitemap y APIs enumeran el catalogo entero por construccion.
    for variante in ("SITEMAP", "XINTEL_API", "WORDPRESS_REST", "TFW_ESTANDAR"):
        r = _run(variante=variante)
        assert certification_status(r, r, COMP, _enum(), {})[0] == "CERTIFIED_COMPLETE", variante


def test_un_defecto_sigue_mandando_sobre_la_falta_de_prueba() -> None:
    r = _run(variante="LISTADO_HTML", detalles_fallidos=2)
    assert certification_status(r, r, COMP, _enum(), {})[0] == "NEEDS_FIX"

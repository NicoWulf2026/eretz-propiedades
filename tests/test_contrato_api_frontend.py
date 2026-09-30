"""El fixture de contrato del frontend sale de la API real y no puede quedar viejo."""
from __future__ import annotations

from scripts import exportar_contrato_api as C


def test_el_contrato_versionado_coincide_con_la_api():
    actual = C.SALIDA.read_text(encoding="utf-8")
    assert actual == C.serializar(C.capturar()), (
        "la API v2 cambio y frontend/src/test/api-v2-contrato-real.json no: correr "
        "python scripts/exportar_contrato_api.py y revisar el diff (el frontend lo valida)")

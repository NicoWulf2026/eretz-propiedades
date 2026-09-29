"""Una web «oficial» que es un portal multi-agencia no certifica inventario.

`kerlin bienes raices` figuraba READY/OFFICIAL_WEB con
`muchaspropiedades.com.ar/inmobiliarias.php`: un portal de San Nicolas con
decenas de inmobiliarias. La corrida del 27-09 enumero 96 fichas ajenas. No
llegaron a la snapshot (0 filas servidas desde hosts de portal en la v4j), pero
una recertificacion que pasara las certificaria como propias.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))


def _registro(url: str) -> dict:
    return {"resolution": {"resolution_status": "RESOLVED", "eretz_id": 1},
            "live": {"validation_status": "VALIDATED"},
            "source": {"official_url": url}, "platform": {"web_kind": "OFFICIAL_WEB"},
            "directory": {}, "verificada": {}}


def test_el_portal_de_san_nicolas_es_portal() -> None:
    from agency_web_discovery import es_portal
    assert es_portal("https://muchaspropiedades.com.ar/inmobiliarias.php")


def test_no_se_certifica_una_agencia_cuya_web_es_el_portal(tmp_path) -> None:
    import agency_certifier as AC
    catalogo = {"roomix:kerlin": _registro("https://muchaspropiedades.com.ar/inmobiliarias.php")}
    resultado = AC.certify("roomix:kerlin", catalogo, tmp_path, tmp_path / "x.db")
    assert resultado["status"] not in ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "NEEDS_FIX")

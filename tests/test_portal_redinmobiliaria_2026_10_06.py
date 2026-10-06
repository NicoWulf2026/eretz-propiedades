"""Una ficha de una red multi-agencia no es la web oficial de una inmobiliaria.

`fabiana bert propiedades` figuraba READY/OFFICIAL_WEB con
`redinmobiliaria.ar/site/properties/544003/...`, una ficha suya dentro de Red
Inmobiliaria. El catalogo `/site/properties/sale` es de la red: muestreado el
06-10, cada ficha trae el contacto de otra inmobiliaria (moyanopropiedades,
solohogareselegidos, luconiaprop). El worker llevaba 3 h y 1.648 fichas vistas
atribuyendolas a una sola agencia.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

FICHA = "https://redinmobiliaria.ar/site/properties/544003/venta-de-parcela-en-rawson-bs-as"


def _registro(url: str) -> dict:
    return {"resolution": {"resolution_status": "RESOLVED", "eretz_id": 1},
            "live": {"validation_status": "VALIDATED"},
            "source": {"official_url": url}, "platform": {"web_kind": "OFFICIAL_WEB"},
            "directory": {}, "verificada": {}}


def test_MUERDE_la_red_inmobiliaria_es_portal() -> None:
    from agency_web_discovery import es_portal
    assert es_portal(FICHA)
    assert es_portal("https://www.redinmobiliaria.ar/site/properties/sale")


def test_una_inmobiliaria_con_red_en_el_nombre_no_es_portal() -> None:
    # Comparacion por nombre registrable entero: `sinergiaredinmobiliaria` es otra cosa.
    from agency_web_discovery import es_portal
    assert not es_portal("https://www.sinergiaredinmobiliaria.com.ar")


def test_no_se_certifica_una_agencia_cuya_web_es_una_ficha_de_la_red(tmp_path) -> None:
    import agency_certifier as AC
    catalogo = {"roomix:fabiana bert propiedades": _registro(FICHA)}
    resultado = AC.certify("roomix:fabiana bert propiedades", catalogo, tmp_path,
                           tmp_path / "x.db")
    assert resultado["status"] not in ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
                                       "NEEDS_FIX")

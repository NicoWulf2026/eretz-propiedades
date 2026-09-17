# -*- coding: utf-8 -*-
"""El id estable de 178 propiedades no puede ser el mismo 35 veces.

`baron inmobiliaria` tiene el id `300` en 36 propiedades distintas. El
extractor lo sacó de *"Oslo al 300"*, el número de calle del slug. En el mismo
registro conviven `ids_unicos: 35`, `enumeradas: 178` y
`identity_collisions: 0`.

Esto no rompe el inventario —`enumerated` cuenta urls y RUN1/RUN2 compara por
url— pero sí rompe la señal, y es el §39 exacto: un campo que afirma más de lo
que verifica. El riesgo vive aguas abajo, en dedupe y lifecycle, que usarían el
id colapsado como clave.

El detector no arregla el extractor. Sólo hace visible lo que el campo de al
lado ya probaba.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import colision_de_ids_estables as detector  # noqa: E402


def resultado(ids: int, urls: int, estado: str = "NEEDS_FIX",
              collisions: int = 0, agencia: str = "baron inmobiliaria") -> dict:
    # El id de agencia va como parámetro porque el detector se queda con el
    # ÚLTIMO resultado de cada agencia: dos fixtures con el mismo nombre se
    # pisan y el test mediría otra cosa.
    return {
        "canonical_agency_id": f"roomix:{agencia}",
        "agency_name": agencia.title(),
        "status": estado,
        "run1": {"ids_unicos": ids, "enumeradas": urls},
        "comparison": {"identity_collisions": collisions},
        "connector_strategy": "generic/html_catalog",
        "official_url": "https://www.baroninmobiliaria.com.ar",
    }


def marcadas(resultados: list[dict], monkeypatch) -> list[dict]:
    monkeypatch.setattr(detector, "_jsonl", lambda ruta: iter(resultados))
    return detector.desde_los_resultados()


def test_MUERDE_el_caso_real_de_baron_queda_marcado(monkeypatch):
    filas = marcadas([resultado(35, 178)], monkeypatch)
    assert len(filas) == 1
    assert filas[0]["urls_por_id"] == 5.09
    # Lo que hace al hallazgo: el sistema dice que no pasa nada.
    assert filas[0]["identity_collisions_declarado"] == 0


def test_una_agencia_sana_no_se_marca(monkeypatch):
    """Un id por url es lo normal y no puede generar ruido.

    416 agencias pasan por acá. Un detector que marque a las sanas se apaga
    solo, porque nadie mira una lista de 400 avisos.
    """
    assert marcadas([resultado(178, 178)], monkeypatch) == []


def test_mas_ids_que_urls_tampoco_se_marca(monkeypatch):
    """Puede pasar entre corridas y no es esta colisión."""
    assert marcadas([resultado(200, 178)], monkeypatch) == []


def test_un_catalogo_diminuto_no_alcanza_para_opinar(monkeypatch):
    """Con 4 urls, que dos compartan id puede ser una repetición de la fuente.

    Acusar ahí sería inventar un defecto a partir de ruido.
    """
    assert marcadas([resultado(2, 4)], monkeypatch) == []
    assert marcadas([resultado(3, 6)], monkeypatch) != []


def test_el_estado_terminal_no_protege_de_la_marca(monkeypatch):
    """Diez de las afectadas están CERTIFIED_COMPLETE.

    Que una agencia haya cerrado bien no es motivo para no mirarle los ids:
    justamente las terminales son las que siguen hacia dedupe y publicación.
    """
    filas = marcadas([resultado(51, 108, "CERTIFIED_COMPLETE")], monkeypatch)
    assert len(filas) == 1 and filas[0]["status"] == "CERTIFIED_COMPLETE"


def test_se_ordena_por_gravedad(monkeypatch):
    """Primero el que más colapsa, que es donde conviene mirar."""
    filas = marcadas([resultado(100, 110, agencia="una"),
                      resultado(35, 178, agencia="baron inmobiliaria"),
                      resultado(50, 108, agencia="otra")], monkeypatch)
    assert [f["ids_unicos"] for f in filas] == [35, 50, 100]

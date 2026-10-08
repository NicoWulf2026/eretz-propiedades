"""Lo que la preingestion tiene como AGENCY_ID_UNRESOLVED de la MISMA agencia no es "ya conocido".

08-10, auditoria de cobertura: 21.189 filas certificadas en 290 agencias no llegaban a la snapshot
(`brick` COMPLETE 551/551 -> 26 servidas). La preingestion del 03-09 tiene esas URLs como
`AGENCY_ID_UNRESOLVED / CANONICAL_AGENCY_NOT_RESOLVED` (de cuando la agencia no estaba resuelta): no se
sirven. `decidir` las daba por conocidas (`url_ya_en_preingestion`, `numero_de_url_ya_visto`) y descartaba
la fila certificada: el inventario no llegaba nunca. Solo ese caso se libera: si la URL esta en otro estado
(reclamada por otra agencia, rechazada por calidad, duplicada) sigue bloqueando.
"""
from __future__ import annotations

import json
import sqlite3

from scripts.snapshot_certificadas import conocidas_de, decidir

AG = "roomix:uno"
OTRA = "roomix:otra"


def _pre(filas):
    db = sqlite3.connect(":memory:")
    db.execute("create table rows (row_json text, canonical_id text, status text, "
               "hash_dedup text, url_normalized text)")
    for canonical, status, h, url, fila in filas:
        db.execute("insert into rows values (?,?,?,?,?)", (json.dumps(fila), canonical, status, h, url))
    return conocidas_de(db)


def _fila(h, url, aviso):
    return {"hash_dedup": h, "source_url": url, "source_listing_id": aviso, "inmobiliaria_id": 7,
            "canonical_agency_id": AG, "titulo": f"Casa {aviso}", "precio": 100000, "moneda": "USD"}


def _cert():
    return {"canonical_agency_id": AG, "status": "CERTIFIED_COMPLETE", "checked_at": "2026-10-08T10:00:00"}


def _no_resuelta(canonical, h, url, aviso):
    return (canonical, "AGENCY_ID_UNRESOLVED", h, url,
            {"source_url": "https://" + url, "source_listing_id": aviso, "titulo": "otra cosa", "precio": 5})


def test_MUERDE_la_url_no_resuelta_de_la_misma_agencia_se_suma():
    pre = _pre([_no_resuelta(AG, "h-vieja", "a.com/property/casa-linda", "")])
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/property/casa-linda", "casa-linda")])], pre)
    assert [f["hash_dedup"] for f in d.nuevas] == ["h-nueva"]


def test_MUERDE_el_numero_de_un_aviso_no_resuelto_no_bloquea():
    pre = _pre([_no_resuelta(AG, "h-vieja", "a.com/p/7779042-viejo", "7779042")])
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/p/7779042-nuevo", "x")])], pre)
    assert [f["hash_dedup"] for f in d.nuevas] == ["h-nueva"]


def test_url_no_resuelta_de_OTRA_agencia_sigue_bloqueando():
    pre = _pre([_no_resuelta(OTRA, "h-otra", "a.com/property/casa-linda", "")])
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/property/casa-linda", "casa-linda")])], pre)
    assert d.nuevas == [] and d.motivos["url_ya_en_preingestion"] == 1


def test_url_no_resuelta_que_ademas_esta_en_otro_estado_sigue_bloqueando():
    pre = _pre([_no_resuelta(AG, "h-vieja", "a.com/property/casa-linda", ""),
                (AG, "DUPLICATE_OR_CONFLICT", "h-dup", "a.com/property/casa-linda",
                 {"source_url": "https://a.com/property/casa-linda"})])
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/property/casa-linda", "casa-linda")])], pre)
    assert d.nuevas == []


def test_url_candidata_sigue_siendo_ya_conocida():
    pre = _pre([(AG, "CANDIDATE", "h-vieja", "a.com/property/casa-linda",
                 {"source_url": "https://a.com/property/casa-linda", "titulo": "x"})])
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/property/casa-linda", "casa-linda")])], pre)
    assert d.nuevas == [] and d.motivos["url_ya_en_preingestion"] == 1


def test_el_hash_no_resuelto_de_la_misma_agencia_no_es_ya_en_preingestion():
    pre = _pre([_no_resuelta(AG, "h-igual", "a.com/property/casa-linda", "")])
    d = decidir([(_cert(), [_fila("h-igual", "https://a.com/property/casa-linda", "casa-linda")])], pre)
    assert [f["hash_dedup"] for f in d.nuevas] == ["h-igual"]

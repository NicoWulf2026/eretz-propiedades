"""La candidata no pierde filas SERVIDAS sin un motivo de politica (P1/P8).

2026-10-01: la candidata perdia 100 filas servidas de agencias que habian
retrocedido a NEEDS_FIX (casamia, d amato, pennacchio...); la compuerta P2
freno el despliegue. `--servida` las conserva tal cual.
"""
from __future__ import annotations

import sqlite3

from scripts.api_snapshot import _servidas_a_conservar


def _origen(tmp_path, hashes):
    con = sqlite3.connect(tmp_path / "origen.sqlite3")
    con.execute("create table rows (hash_dedup text, status text, row_json text)")
    con.executemany("insert into rows values (?, 'CANDIDATE', '{}')", [(h,) for h in hashes])
    return con


def _servida(tmp_path, ids):
    ruta = tmp_path / "servida.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table propiedades (id text, agency_id text, titulo text)")
    con.executemany("insert into propiedades values (?, 'roomix:x', 't')", [(i,) for i in ids])
    con.commit(); con.close()
    return ruta


def test_conserva_solo_lo_servido_que_la_candidata_perderia(tmp_path):
    origen = _origen(tmp_path, ["a", "b"])
    servida = _servida(tmp_path, ["a", "b", "c", "d", "e"])
    nuevas = [{"hash_dedup": "c"}]          # vuelve por un paquete certificado
    retirar = {"d"}                         # retiro con motivo de politica: se retira
    conservadas = _servidas_a_conservar(origen, servida, nuevas, retirar)
    assert [f["id"] for f in conservadas] == ["e"]
    assert conservadas[0]["agency_id"] == "roomix:x"


def test_sin_servida_no_conserva_nada(tmp_path):
    origen = _origen(tmp_path, [])
    assert _servidas_a_conservar(origen, None, [], set()) == []
    assert _servidas_a_conservar(origen, tmp_path / "no.sqlite3", [], set()) == []


def test_listadas_en_paquetes_lee_todos_los_estados(tmp_path):
    """Un REMOVED verificado se aplica si la ficha no figura en NINGUN paquete actual
    (pennacchio, 2026-10-01: 6 soft-404 verificados volvian a servirse)."""
    import json
    from scripts.api_snapshot import _listadas_en_paquetes
    for carpeta, hashes in (("a", ["h1", "h2"]), ("b", ["h3"])):
        (tmp_path / carpeta).mkdir()
        (tmp_path / carpeta / "properties_run2.jsonl").write_text(
            "\n".join(json.dumps({"hash_dedup": h}) for h in hashes), encoding="utf-8")
    assert _listadas_en_paquetes(tmp_path) == {"h1", "h2", "h3"}

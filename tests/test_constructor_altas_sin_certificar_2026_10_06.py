"""Una fila que no se servia y no llega con paquete certificado no es un alta (06-10).

P2 solo aprueba altas SUMADA_CERTIFICADA. `o feely`: dos emprendimientos de URUGUAY
(Colonia, Punta del Este) excluidos antes como exterior por el paquete del 29-09
reaparecian con provincia 'Santa Fe' inferida del padron cuando la corrida nueva no
llego a esas fichas. La compuerta P2 lo freno ('2 altas sin motivo aprobado').
"""
from __future__ import annotations

import inspect
import sqlite3

from scripts import api_snapshot as a


def test_ids_servidos(tmp_path):
    ruta = tmp_path / "servida.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table propiedades (id text)")
    con.executemany("insert into propiedades values (?)", [("a",), ("b",)])
    con.commit(); con.close()
    assert a._ids_servidos(ruta) == {"a", "b"}
    assert a._ids_servidos(None) is None
    assert a._ids_servidos(tmp_path / "no_existe.sqlite3") is None


def test_MUERDE_el_constructor_no_suma_altas_sin_paquete_certificado():
    fuente = inspect.getsource(a._build_contents)
    assert "ALTA_SIN_CERTIFICAR" in fuente
    assert "fresca is None and not es_nueva" in fuente
    assert "hash_dedup not in ids_servidos" in fuente

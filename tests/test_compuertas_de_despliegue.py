"""Politica P2: despliegue automatico de la snapshot local solo si pasan todas."""
from __future__ import annotations

import json
import sqlite3

from scripts.compuertas_de_despliegue import (compuerta_datos, compuerta_inventario,
                                              compuerta_qa, compuerta_regresion)


def test_bajas_y_altas_con_motivo_aprobado_pasan():
    cambios = {"a": "EXTERIOR_ARGENTINA_ONLY", "b": "RETIRO_MUERTE_VERIFICADA",
               "c": "NO_ES_FICHA_CATEGORIA", "n": "SUMADA_CERTIFICADA"}
    assert compuerta_inventario({"a", "b", "c"}, {"n"}, cambios) == []


def test_MUERDE_un_retiro_por_ausencia_sin_muerte_verificada_no_se_despliega_solo():
    cambios = {"a": "RETIRO_AUSENTE_DE_INVENTARIO_COMPLETO"}
    assert compuerta_inventario({"a"}, set(), cambios)


def test_MUERDE_una_baja_o_alta_sin_motivo_no_se_despliega():
    assert compuerta_inventario({"x"}, set(), {})
    assert compuerta_inventario(set(), {"y"}, {})
    assert compuerta_inventario(set(), set(), None)


def _qa(tmp_path, **cambios):
    casos = [{"case": c, "status": 200, "median_ms": 50} for c in
             ("explorer", "combined", "price_asc", "price_desc", "window_end", "empty",
              "map_small", "map_large_combined", "detail", "agency", "batch_100", "batch_missing")]
    casos += [{"case": "window_rejected", "status": 400, "median_ms": 5},
              {"case": "invalid_sort", "status": 422, "median_ms": 5}]
    qa = {"cases": casos, "conflicting_map_points": 0, **cambios}
    (tmp_path / "API_BENCHMARK.json").write_text(json.dumps(qa), encoding="utf-8")


def test_qa_completa_pasa_y_un_conflicto_en_el_mapa_no(tmp_path):
    _qa(tmp_path)
    assert compuerta_qa(tmp_path) == []
    _qa(tmp_path, conflicting_map_points=3)
    assert compuerta_qa(tmp_path)


def test_MUERDE_un_caso_con_otro_estado_frena(tmp_path):
    _qa(tmp_path)
    qa = json.loads((tmp_path / "API_BENCHMARK.json").read_text(encoding="utf-8"))
    qa["cases"][0]["status"] = 500
    (tmp_path / "API_BENCHMARK.json").write_text(json.dumps(qa), encoding="utf-8")
    assert compuerta_qa(tmp_path)


def _snapshot(ruta, filas):
    con = sqlite3.connect(ruta)
    con.execute("create table propiedades (id text, agency_id text, source_url text, latitud real, "
                "longitud real, precio real, moneda text, operacion text)")
    con.executemany("insert into propiedades values (?,?,?,?,?,?,?,?)", filas)
    con.commit()
    con.close()


def test_exterior_y_precio_simbolico_frenan(tmp_path):
    ruta = tmp_path / "s.sqlite3"
    _snapshot(ruta, [("a", "x", "https://a.com/p/1", -34.9, -56.16, 100000, "USD", "venta")])
    assert any("fuera del pais" in f for f in compuerta_datos(ruta, set()))
    ruta2 = tmp_path / "s2.sqlite3"
    _snapshot(ruta2, [("a", "x", "https://a.com/p/1", -34.6, -58.4, 1, "USD", "venta")])
    assert any("simbolicos" in f for f in compuerta_datos(ruta2, set()))


def test_regression_gate_con_pendientes_frena(tmp_path):
    (tmp_path / "_regresion").mkdir()
    (tmp_path / "_regresion" / "GATE_x.json").write_text(json.dumps({"pendientes_de_revision": 3}))
    assert compuerta_regresion(tmp_path)
    (tmp_path / "_regresion" / "GATE_x.json").write_text(json.dumps({"pendientes_de_revision": 0}))
    assert compuerta_regresion(tmp_path) == []

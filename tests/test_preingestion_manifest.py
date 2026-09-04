"""La base vigente se declara en un solo lugar y no se puede retroceder."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import preingestion_manifest as manifiesto
from scripts.agency_rollout_preflight import base_de_datos_vigente


def _manifiesto(tmp_path, vigente: str, historica: str) -> Path:
    ruta = tmp_path / "ERETZ_DATA_MANIFEST.json"
    ruta.write_text(json.dumps({
        "preingestion": {
            "canonica": {"ruta": vigente, "fecha": "2026-09-03",
                         "candidatas": 58427, "estado": "VIGENTE"},
            "historicas": [{"ruta": historica, "fecha": "2026-08-27",
                            "candidatas": 45404, "estado": "HISTORICA",
                            "proposito": "evidencia del delta D-014"}],
        }}, ensure_ascii=False), encoding="utf-8")
    return ruta


def test_la_vigente_sale_del_manifiesto(tmp_path, monkeypatch):
    """La ruta escrita a mano en dos `argparse` distintos fue justamente cómo
    el certificador terminó apuntando a la base del 27 de agosto sin que nadie
    lo notara. Una ruta a mano envejece en silencio."""
    nueva = tmp_path / "nueva.sqlite3"
    nueva.touch()
    monkeypatch.setattr(manifiesto, "MANIFIESTO",
                        _manifiesto(tmp_path, str(nueva), str(tmp_path / "vieja.sqlite3")))
    manifiesto._manifiesto.cache_clear()
    assert manifiesto.base_canonica() == nueva


def test_el_preflight_se_niega_a_arrancar_con_una_snapshot_vencida(tmp_path,
                                                                   monkeypatch):
    """Una snapshot histórica puede seguir existiendo como evidencia, pero
    jamás ser el default operativo de un runner."""
    nueva, vieja = tmp_path / "nueva.sqlite3", tmp_path / "vieja.sqlite3"
    nueva.touch(); vieja.touch()
    monkeypatch.setattr(manifiesto, "MANIFIESTO",
                        _manifiesto(tmp_path, str(nueva), str(vieja)))
    manifiesto._manifiesto.cache_clear()

    ok, detalle = base_de_datos_vigente(str(vieja))
    assert ok is False
    assert "HISTORICA" in detalle and "2026-08-27" in detalle

    ok, detalle = base_de_datos_vigente(str(nueva))
    assert ok is True
    assert "58427" in detalle


def test_una_base_sin_declarar_tampoco_pasa(tmp_path, monkeypatch):
    """Sin declararla no se puede auditar después con qué datos se decidió."""
    nueva = tmp_path / "nueva.sqlite3"; nueva.touch()
    monkeypatch.setattr(manifiesto, "MANIFIESTO",
                        _manifiesto(tmp_path, str(nueva), str(tmp_path / "v.sqlite3")))
    manifiesto._manifiesto.cache_clear()
    ok, detalle = base_de_datos_vigente(str(tmp_path / "cualquiera.sqlite3"))
    assert ok is False
    assert "no esta declarada" in detalle


def test_sin_manifiesto_se_cae_hacia_la_vigente_y_no_hacia_la_vieja(tmp_path,
                                                                    monkeypatch):
    """Ante la ausencia del manifiesto conviene fallar apuntando a lo vigente:
    revivir en silencio una snapshot vencida es el error que esto previene."""
    monkeypatch.setattr(manifiesto, "MANIFIESTO", tmp_path / "no_existe.json")
    manifiesto._manifiesto.cache_clear()
    assert manifiesto.base_canonica() == manifiesto.RESPALDO
    assert "20260903" in str(manifiesto.RESPALDO)


def test_el_manifiesto_real_declara_la_base_del_3_de_septiembre():
    """Contra el archivo de verdad, no contra un fixture."""
    manifiesto._manifiesto.cache_clear()
    canonica = manifiesto.base_canonica()
    assert "20260903" in str(canonica)
    dato = manifiesto.describir(canonica)
    assert dato.get("estado") == "VIGENTE"
    assert dato.get("candidatas") == 58427
    # Y la del 27 de agosto sigue existiendo, declarada como evidencia.
    historicas = manifiesto.historicas()
    assert any("20260827" in str(h) for h in historicas)

"""El replay re-extrae desde el almacen sin tocar la red y clasifica cada diferencia (mision 08-10)."""
from __future__ import annotations

import json

import pytest

from connectors.base import ErrorPermanente
from scripts.almacen_de_paginas import AlmacenDePaginas
from scripts.replay_desde_almacen import DescargadorDelAlmacen, comparar, indice_de


def test_el_descargador_del_almacen_nunca_sale_a_la_red(tmp_path):
    alm = AlmacenDePaginas(tmp_path)
    alm.contexto = {"canonical_agency_id": "roomix:a"}
    alm.guardar("https://a.com.ar/p/1", "<html>uno</html>")
    d = DescargadorDelAlmacen(alm, indice_de(tmp_path, "roomix:a"))
    assert d.bajar("https://a.com.ar/p/1") == "<html>uno</html>"
    with pytest.raises(ErrorPermanente):
        d.bajar("https://a.com.ar/p/2")
    assert d.faltantes == ["https://a.com.ar/p/2"] and d.pedidos == 0


def test_el_indice_se_queda_con_la_ultima_descarga_de_esa_agencia(tmp_path):
    (tmp_path / "indice").mkdir()
    filas = [{"url": "u", "sha256": "viejo", "bajada_en": "2026-10-08T10:00:00", "canonical_agency_id": "roomix:a"},
             {"url": "u", "sha256": "nuevo", "bajada_en": "2026-10-08T12:00:00", "canonical_agency_id": "roomix:a"},
             {"url": "u", "sha256": "ajeno", "bajada_en": "2026-10-08T13:00:00", "canonical_agency_id": "roomix:b"}]
    (tmp_path / "indice" / "2026-10-08.w0.jsonl").write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
    assert indice_de(tmp_path, "roomix:a") == {"u": "nuevo"}


def test_comparar_distingue_recuperado_perdido_y_cambiado():
    viejas = [{"source_url": "u", "precio": None, "ciudad": "Rosario", "dormitorios": 3, "banos": 1.0}]
    nuevas = {"u": {"precio": 100.0, "ciudad": None, "dormitorios": 2, "banos": 1}}
    r = comparar(viejas, nuevas)["por_campo"]
    assert r["precio"] == {"recuperado": 1} and r["ciudad"] == {"perdido": 1}
    assert r["dormitorios"] == {"cambiado": 1} and r["banos"] == {"igual": 1}

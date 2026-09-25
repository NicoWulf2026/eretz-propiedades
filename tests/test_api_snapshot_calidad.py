"""La snapshot aplica la misma regla que el runner al texto del sitio.

La v4 del 2026-09-24 traia 4.813 filas en 61 agencias con la descripcion
institucional del sitio: agencias todavia no recertificadas con el codigo que
la descarta. La snapshot no espera a la recertificacion.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

ESLOGAN = "Silvina Hill Propiedades es una inmobiliaria de la ciudad de Tucuman, con 20 anos."


def _correr(tmp_path, monkeypatch, filas):
    origen = tmp_path / "pre.sqlite3"
    con = sqlite3.connect(origen)
    con.execute("create table rows (row_json text, canonical_id text, "
                "hash_dedup text, status text)")
    for i, (agencia, titulo, descripcion, *resto) in enumerate(filas):
        fila = {"hash_dedup": f"h{i:03d}", "canonical_agency_id": agencia,
                "source_url": f"https://a.com/{i}", "titulo": titulo,
                "descripcion": descripcion, "tipo_propiedad": (resto or [None])[0]}
        con.execute("insert into rows values (?,?,?,?)",
                    (json.dumps(fila), agencia, f"h{i:03d}", "CANDIDATE"))
    con.commit()
    con.close()
    salida = tmp_path / "out"
    salida.mkdir()
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("", encoding="utf-8")

    from scripts import api_snapshot
    monkeypatch.setattr(sys, "argv", [
        "snap", "--db", str(origen), "--gate", str(vacio),
        "--cobertura", str(vacio), "--salida", str(salida)])
    monkeypatch.setattr(api_snapshot, "exigir_base_vigente", lambda r: Path(r))
    monkeypatch.setattr(api_snapshot, "mas_frescas", lambda root: {})
    monkeypatch.setattr(api_snapshot, "agencias_con_web_ajena", lambda root: set())
    assert api_snapshot.main() == 0
    resumen = json.loads((salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(salida / "ERETZ_API_SNAPSHOT.sqlite3")
    docs = {i: (t, d, tp) for i, t, d, tp in con.execute(
        "select id, titulo, descripcion, tipo_propiedad from propiedades")}
    return resumen, docs


def test_MUERDE_el_texto_del_sitio_repetido_no_llega_a_la_snapshot(tmp_path, monkeypatch):
    filas = [("roomix:silvina", f"Casa {i}", ESLOGAN) for i in range(9)]
    filas += [("roomix:silvina", "Depto propio", "Departamento de dos ambientes al frente, luminoso.")]
    resumen, docs = _correr(tmp_path, monkeypatch, filas)
    assert [docs[f"h{i:03d}"][1] for i in range(9)] == [None] * 9
    assert docs["h009"][1].startswith("Departamento de dos ambientes")
    assert resumen["descripciones_del_sitio_descartadas"] == 9


def test_sin_titulo_la_descripcion_se_conserva_para_no_dejar_la_fila_sin_texto(tmp_path, monkeypatch):
    filas = [("roomix:silvina", None, ESLOGAN) for _ in range(8)]
    _, docs = _correr(tmp_path, monkeypatch, filas)
    assert all(d == ESLOGAN for _, d, _ in docs.values())


def test_pocas_fichas_no_alcanzan_para_juzgar(tmp_path, monkeypatch):
    filas = [("roomix:chica", f"Casa {i}", ESLOGAN) for i in range(5)]
    _, docs = _correr(tmp_path, monkeypatch, filas)
    assert all(d == ESLOGAN for _, d, _ in docs.values())


def test_MUERDE_una_cochera_que_es_lo_que_trae_la_propiedad_no_es_su_tipo(tmp_path, monkeypatch):
    filas = [("roomix:a", "Dúplex de 6 amb. con cochera y patio", "Texto propio uno largo suficiente", "cochera"),
             ("roomix:a", "4 AMBIENTES CON COCHERA Y TERRAZA", "Texto propio dos largo suficiente", "cochera"),
             ("roomix:a", "Cochera cubierta en venta", "Texto propio tres largo suficiente", "cochera")]
    resumen, docs = _correr(tmp_path, monkeypatch, filas)
    assert [docs[f"h00{i}"][2] for i in range(3)] == ["casa", None, "cochera"]
    assert resumen["tipos_cochera_por_accesorio_corregidos"] == 2

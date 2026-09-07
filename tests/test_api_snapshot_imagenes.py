"""Una imagen compartida por muchas fichas no es la foto de ninguna."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.api_snapshot import FICHAS_PARA_SER_COMPARTIDA


def _base(tmp_path, filas):
    ruta = tmp_path / "pre.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table rows (row_json text, canonical_id text, "
                "hash_dedup text, status text)")
    for i, (agencia, imagenes) in enumerate(filas):
        fila = {"hash_dedup": f"h{i}", "canonical_agency_id": agencia,
                "source_url": f"https://a.com/{i}", "titulo": "Casa",
                "imagenes": imagenes}
        con.execute("insert into rows values (?,?,?,?)",
                    (json.dumps(fila), agencia, f"h{i}", "CANDIDATE"))
    con.commit()
    con.close()
    return ruta


def _correr(tmp_path, filas, monkeypatch):
    db = _base(tmp_path, filas)
    salida = tmp_path / "out"
    salida.mkdir()
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("", encoding="utf-8")

    from scripts import api_snapshot
    monkeypatch.setattr(sys, "argv", [
        "snap", "--db", str(db), "--gate", str(vacio),
        "--cobertura", str(vacio), "--salida", str(salida)])
    monkeypatch.setattr(api_snapshot, "exigir_base_vigente", lambda r: Path(r))
    assert api_snapshot.main() == 0
    resumen = json.loads(
        (salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(salida / "ERETZ_API_SNAPSHOT.sqlite3")
    con.row_factory = sqlite3.Row
    docs = {f["id"]: json.loads(f["documento"])
            for f in con.execute("select id, documento from propiedades")}
    con.close()
    return resumen, docs


def test_un_avatar_repetido_no_es_la_foto_de_nadie(tmp_path, monkeypatch):
    """`user-4.png` está en 58 de 360 fichas de una agencia: el connector sólo
    descarta las que aparecen en la MITAD del catálogo y eso deja pasar mucho."""
    compartida = "https://a.com/user-4.png"
    filas = [("roomix:alfa", [compartida, f"https://a.com/{i}.jpg"])
             for i in range(FICHAS_PARA_SER_COMPARTIDA)]
    resumen, docs = _correr(tmp_path, filas, monkeypatch)

    assert resumen["imagenes_compartidas_descartadas"] == FICHAS_PARA_SER_COMPARTIDA
    for doc in docs.values():
        assert compartida not in doc["imagenes"]
        assert len(doc["imagenes"]) == 1


def test_una_foto_que_se_repite_poco_se_conserva(tmp_path, monkeypatch):
    """Un emprendimiento con unidades que comparten un render es legítimo: el
    umbral no puede castigarlo."""
    compartida = "https://a.com/render.jpg"
    filas = [("roomix:alfa", [compartida])
             for _ in range(FICHAS_PARA_SER_COMPARTIDA - 1)]
    resumen, docs = _correr(tmp_path, filas, monkeypatch)

    assert resumen["imagenes_compartidas_descartadas"] == 0
    for doc in docs.values():
        assert doc["imagenes"] == [compartida]


def test_el_umbral_es_por_agencia(tmp_path, monkeypatch):
    """La misma URL en agencias distintas no dice nada: son sitios distintos y
    el conteo de una no puede castigar a la otra."""
    compartida = "https://cdn.com/generica.jpg"
    filas = [(f"roomix:ag{i}", [compartida])
             for i in range(FICHAS_PARA_SER_COMPARTIDA + 2)]
    resumen, docs = _correr(tmp_path, filas, monkeypatch)

    assert resumen["imagenes_compartidas_descartadas"] == 0


def test_quedarse_sin_fotos_no_borra_la_propiedad(tmp_path, monkeypatch):
    """Se queda sin fotos, no sin propiedad: lo que tenía no era suyo."""
    compartida = "https://a.com/footer.png"
    filas = [("roomix:alfa", [compartida])
             for _ in range(FICHAS_PARA_SER_COMPARTIDA)]
    resumen, docs = _correr(tmp_path, filas, monkeypatch)

    assert resumen["propiedades"] == FICHAS_PARA_SER_COMPARTIDA
    assert resumen["fichas_que_quedaron_sin_foto_propia"] == FICHAS_PARA_SER_COMPARTIDA
    for doc in docs.values():
        assert doc["imagenes"] == []
        assert doc["id"] and doc["source_url"]

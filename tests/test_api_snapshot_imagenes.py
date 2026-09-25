"""Repetition prompts review; only independent page-asset evidence excludes."""
from __future__ import annotations

import json
import sqlite3
import sys
import pytest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from scripts.api_snapshot import FICHAS_PARA_SER_COMPARTIDA  # noqa: E402


def _base(tmp_path, filas, values=None):
    ruta = tmp_path / "pre.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table rows (row_json text, canonical_id text, "
                "hash_dedup text, status text)")
    for i, (agencia, imagenes) in enumerate(filas):
        fila = {"hash_dedup": f"h{i}", "canonical_agency_id": agencia,
                "source_url": f"https://a.com/{i}", "titulo": "Casa",
                "imagenes": imagenes}
        fila.update(values or {})
        con.execute("insert into rows values (?,?,?,?)",
                    (json.dumps(fila), agencia, f"h{i}", "CANDIDATE"))
    con.commit()
    con.close()
    return ruta


def _correr(tmp_path, filas, monkeypatch, values=None, fresh=None, gate=None):
    db = _base(tmp_path, filas, values)
    salida = tmp_path / "out"
    salida.mkdir()
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("", encoding="utf-8")
    gate_path = tmp_path / 'gate.jsonl'
    gate_path.write_text(''.join(json.dumps(dict(hash_dedup=h, alcances=scopes)) + '\n'
                                for h, scopes in (gate or {}).items()), encoding='utf-8')

    from scripts import api_snapshot
    monkeypatch.setattr(sys, "argv", [
        "snap", "--db", str(db), "--gate", str(gate_path),
        "--cobertura", str(vacio), "--salida", str(salida)])
    monkeypatch.setattr(api_snapshot, "exigir_base_vigente", lambda r: Path(r))
    monkeypatch.setattr(api_snapshot, 'mas_frescas', lambda root, **_: fresh or {})
    monkeypatch.setattr(api_snapshot, 'agencias_con_web_ajena', lambda root, **_: set())
    assert api_snapshot.main() == 0
    resumen = json.loads(
        (salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(salida / "ERETZ_API_SNAPSHOT.sqlite3")
    con.row_factory = sqlite3.Row
    docs = {f["id"]: json.loads(f["documento"])
            for f in con.execute("select id, documento from propiedades")}
    con.close()
    return resumen, docs


def test_snapshot_recalculates_scopes_after_current_offer_merge(tmp_path, monkeypatch):
    summary, docs = _correr(tmp_path, [('roomix:alfa', [])], monkeypatch,
                           values={'precio': 99000, 'moneda': 'USD', 'operacion': 'venta'},
                           fresh={'h0': {'precio': None, 'moneda': None, 'operacion': None}},
                           gate={'h0': ['FICHA', 'LISTADO', 'FILTRO_PRECIO', 'FILTRO_OPERACION']})
    assert summary['propiedades'] == 1
    assert docs['h0']['precio'] is None and docs['h0']['moneda'] is None
    assert docs['h0']['operacion'] is None
    assert docs['h0']['alcances'] == ['FICHA', 'LISTADO']


def test_snapshot_builder_cannot_delete_its_own_source(tmp_path, monkeypatch):
    from scripts import api_snapshot
    source = tmp_path / 'ERETZ_API_SNAPSHOT.sqlite3'
    source.write_bytes(b'irreplaceable source fixture')
    monkeypatch.setattr(sys, 'argv', ['snap', '--db', str(source), '--salida', str(tmp_path), '--replace-derived'])
    with pytest.raises(SystemExit):
        api_snapshot.main()
    assert source.read_bytes() == b'irreplaceable source fixture'


def test_snapshot_builder_refuses_implicit_replacement(tmp_path, monkeypatch):
    from scripts import api_snapshot
    output = tmp_path / 'ERETZ_API_SNAPSHOT.sqlite3'
    output.write_bytes(b'previous snapshot')
    monkeypatch.setattr(sys, 'argv', ['snap', '--db', str(tmp_path / 'different.sqlite3'), '--salida', str(tmp_path)])
    with pytest.raises(SystemExit):
        api_snapshot.main()
    assert output.read_bytes() == b'previous snapshot'


def test_snapshot_connection_failure_cleans_only_its_owned_build(tmp_path):
    from scripts.api_snapshot import _snapshot_connections
    temporary = tmp_path / 'own.building.sqlite3'
    with pytest.raises(sqlite3.OperationalError):
        with _snapshot_connections(tmp_path / 'nonexistent-source.sqlite3', temporary):
            pytest.fail('missing readonly source cannot open')
    assert not temporary.exists()
    assert not (tmp_path / 'nonexistent-source.sqlite3').exists()


def test_snapshot_cannot_clean_a_foreign_preexisting_temporary(tmp_path):
    from scripts.api_snapshot import _snapshot_connections
    temporary = tmp_path / 'foreign.building.sqlite3'
    temporary.write_bytes(b'foreign work')
    with pytest.raises(FileExistsError):
        with _snapshot_connections(tmp_path / 'source.sqlite3', temporary):
            pytest.fail('exclusive ownership cannot be acquired')
    assert temporary.read_bytes() == b'foreign work'


def test_snapshot_failure_closes_both_connections_and_removes_owned_build(tmp_path):
    from scripts.api_snapshot import _snapshot_connections
    source = _base(tmp_path, [('agency', [])])
    original = source.read_bytes()
    temporary = tmp_path / 'own.building.sqlite3'
    with pytest.raises(RuntimeError, match='fixture failure'):
        with _snapshot_connections(source, temporary) as (origin, derived):
            raise RuntimeError('fixture failure')
    for connection in (origin, derived):
        with pytest.raises(sqlite3.ProgrammingError, match='closed database'):
            connection.execute('select 1')
    assert not temporary.exists()
    assert source.read_bytes() == original


def test_failed_snapshot_build_preserves_the_served_artifact(tmp_path, monkeypatch):
    from scripts import api_snapshot
    db = _base(tmp_path, [('agency', [])])
    output = tmp_path / 'ERETZ_API_SNAPSHOT.sqlite3'
    output.write_bytes(b'previous snapshot')
    monkeypatch.setattr(sys, 'argv', ['snap', '--db', str(db), '--salida', str(tmp_path), '--replace-derived'])
    monkeypatch.setattr(api_snapshot, 'exigir_base_vigente', lambda path: Path(path))
    monkeypatch.setattr(api_snapshot, '_leer_jsonl', lambda *args: {})
    monkeypatch.setattr(api_snapshot, 'mas_frescas', lambda root, **_: {})
    monkeypatch.setattr(api_snapshot, 'agencias_con_web_ajena', lambda root, **_: set())
    def failed(*args):
        raise RuntimeError('intentional fixture failure')
    monkeypatch.setattr(api_snapshot, 'fila_de_api', failed)
    with pytest.raises(RuntimeError, match='intentional fixture failure'):
        api_snapshot.main()
    assert output.read_bytes() == b'previous snapshot'
    assert not list(tmp_path.glob('ERETZ_API_SNAPSHOT.sqlite3.building.*'))


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


def test_many_units_can_share_a_real_building_render(tmp_path, monkeypatch):
    render = 'https://agency.test/building/render.jpg'
    rows = [('roomix:alfa', [render]) for _ in range(12)]
    summary, docs = _correr(tmp_path, rows, monkeypatch)
    assert summary['imagenes_compartidas_descartadas'] == 0
    assert summary['imagenes_repetidas_sin_evidencia_de_descarte'] == 12
    assert all(doc['imagenes'] == [render] for doc in docs.values())


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

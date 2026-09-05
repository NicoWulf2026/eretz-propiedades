"""Qué distingue a los miembros de un grupo duplicado."""
from __future__ import annotations

import json
import sqlite3

from scripts.property_duplicate_evidence import (campos_que_difieren,
                                                 normalizado)


def _ficha(**cambios):
    base = {"titulo": "PH en Venta", "descripcion": "Muy lindo",
            "precio": 140000.0, "moneda": "USD", "operacion": "venta",
            "tipo_propiedad": "ph", "direccion": "Tissera esquina Los Cedros",
            "barrio": "La Calera", "ciudad": None, "provincia": "Cordoba",
            "ambientes": 7, "dormitorios": 3, "banos": 2,
            "superficie_total": None, "superficie_cubierta": 158.0,
            "latitud": -31.36261, "longitud": -64.34613}
    base.update(cambios)
    return base


def test_una_mayuscula_no_hace_distinta_a_una_direccion():
    """`Tissera Esquina Los Cedros` y `Tissera esquina Los Cedros` son la misma
    dirección. Comparándolas crudas, el grupo salía como "pueden ser dos
    unidades distintas" cuando lo único que cambiaba era una mayúscula."""
    assert (normalizado("direccion", "Tissera Esquina Los Cedros")
            == normalizado("direccion", "tissera  esquina los cedros"))
    assert (normalizado("barrio", "Córdoba") == normalizado("barrio", "CORDOBA"))


def test_los_numeros_no_se_normalizan():
    """Un piso distinto SÍ distingue. `Chacra del Norte 1` y `Chacra del Norte
    2` no pueden colapsar en la misma dirección."""
    assert (normalizado("direccion", "Chacra del Norte 1")
            != normalizado("direccion", "Chacra del Norte 2"))


def test_el_precio_no_se_toca_al_normalizar():
    """Normalizar es para texto libre. Un número no tiene ortografía."""
    assert normalizado("precio", 140000.0) == 140000.0
    assert normalizado("latitud", -31.36261) == -31.36261
    assert normalizado("direccion", None) is None


def test_dos_fichas_iguales_salvo_la_mayuscula_no_difieren_en_direccion():
    difieren = campos_que_difieren([
        _ficha(direccion="Tissera Esquina Los Cedros"),
        _ficha(direccion="Tissera esquina Los Cedros"),
    ])
    assert difieren == []


def test_un_bano_de_diferencia_no_convierte_una_propiedad_en_dos():
    """El caso medido: misma dirección, mismo precio, misma superficie
    cubierta, y `banos` 2 contra 1. Es un dato mal cargado, no dos unidades."""
    difieren = campos_que_difieren([
        _ficha(direccion="Tissera Esquina Los Cedros", banos=2),
        _ficha(direccion="Tissera esquina Los Cedros", banos=1),
    ])
    assert difieren == ["banos"]


def test_el_id_de_la_url_nunca_entra_en_la_comparacion():
    """Es justamente lo que sabemos que difiere: comparar la URL haría que
    todos los grupos difirieran siempre y la evidencia no diría nada."""
    from scripts.property_duplicate_evidence import VISIBLES
    assert "source_url" not in VISIBLES
    assert "hash_dedup" not in VISIBLES


def test_no_elige_ganador_ni_escribe_en_ninguna_base(tmp_path, monkeypatch, capsys):
    """Cuál se muestra define quién se lleva el clic: es una decisión de
    producto y este script sólo junta la evidencia para tomarla."""
    db = tmp_path / "p.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (row_json text, canonical_id text, "
                     "hash_dedup text, status text)")
    for h, cambios in (("h1", {}), ("h2", {"banos": 1})):
        fila = dict(_ficha(**cambios), source_url=f"https://alfa.com.ar/p/{h}",
                    hash_dedup=h, canonical_agency_id="roomix:alfa")
        conexion.execute("insert into rows values (?,?,?,?)",
                         (json.dumps(fila), "roomix:alfa", h, "CANDIDATE"))
    conexion.commit()
    conexion.close()

    grupos = tmp_path / "grupos.jsonl"
    grupos.write_text(json.dumps({
        "grupo_id": "g1", "alcance": "MISMA_INMOBILIARIA",
        "miembros": [{"hash_dedup": "h1"}, {"hash_dedup": "h2"}],
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    salida = tmp_path / "out"
    salida.mkdir()

    import sys
    from scripts import property_duplicate_evidence as evidencia
    monkeypatch.setattr(sys, "argv", [
        "evidencia", "--db", str(db), "--grupos", str(grupos),
        "--salida", str(salida)])
    assert evidencia.main() == 0

    resumen = json.loads((salida / "PROPERTY_DUPLICATE_EVIDENCE_SUMMARY.json")
                         .read_text(encoding="utf-8"))
    assert resumen["ganadores_elegidos"] == 0
    assert resumen["database_writes"] == 0
    assert resumen["por_clase"] == {"MISMO_INMUEBLE_DATOS_INCONSISTENTES": 1}

    fila = json.loads((salida / "PROPERTY_DUPLICATE_EVIDENCE.jsonl")
                      .read_text(encoding="utf-8").strip())
    assert fila["ganador_elegido"] is None
    assert fila["campos_que_difieren"] == ["banos"]


def test_un_grupo_al_que_le_falta_una_fila_no_se_clasifica(tmp_path, monkeypatch):
    """Sin las dos filas completas no se puede afirmar nada del grupo, y
    afirmarlo igual sería inventar la evidencia que este script existe para
    juntar."""
    db = tmp_path / "p.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (row_json text, canonical_id text, "
                     "hash_dedup text, status text)")
    fila = dict(_ficha(), source_url="https://alfa.com.ar/p/h1",
                hash_dedup="h1", canonical_agency_id="roomix:alfa")
    conexion.execute("insert into rows values (?,?,?,?)",
                     (json.dumps(fila), "roomix:alfa", "h1", "CANDIDATE"))
    conexion.commit()
    conexion.close()

    grupos = tmp_path / "grupos.jsonl"
    grupos.write_text(json.dumps({
        "grupo_id": "g1", "alcance": "MISMA_INMOBILIARIA",
        "miembros": [{"hash_dedup": "h1"}, {"hash_dedup": "ausente"}],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    salida = tmp_path / "out"
    salida.mkdir()

    import sys
    from scripts import property_duplicate_evidence as evidencia
    monkeypatch.setattr(sys, "argv", [
        "evidencia", "--db", str(db), "--grupos", str(grupos),
        "--salida", str(salida)])
    assert evidencia.main() == 0

    resumen = json.loads((salida / "PROPERTY_DUPLICATE_EVIDENCE_SUMMARY.json")
                         .read_text(encoding="utf-8"))
    assert resumen["grupos_analizados"] == 0
    assert resumen["grupos_sin_filas_completas"] == 1

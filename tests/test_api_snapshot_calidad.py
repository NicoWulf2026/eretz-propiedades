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


def _correr(tmp_path, monkeypatch, filas, frescas=None):
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
    llamadas = []
    monkeypatch.setattr(api_snapshot, "mas_frescas",
                        lambda root, **k: llamadas.append(k) or (frescas or {}))
    monkeypatch.setattr(api_snapshot, "agencias_con_web_ajena", lambda root, **_: set())
    assert api_snapshot.main() == 0
    resumen = json.loads((salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").read_text(encoding="utf-8"))
    con = sqlite3.connect(salida / "ERETZ_API_SNAPSHOT.sqlite3")
    docs = {i: (t, d, tp) for i, t, d, tp in con.execute(
        "select id, titulo, descripcion, tipo_propiedad from propiedades")}
    assert llamadas == [{"parciales": True}]
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


def test_MUERDE_las_entidades_html_no_llegan_al_texto_servido(tmp_path, monkeypatch):
    filas = [("roomix:cip", "Venta de lote en Carpinter&iacute;a &#8211; Inmobiliaria CIP",
              "&lt;p&gt;Departamento de 2 Amb.&amp;nbsp; en PH&lt;/p&gt;\nCon patio y cochera."),
             ("roomix:cip", "Casa 3 < 4 dormitorios", "Texto sin entidades, largo y normal.")]
    resumen, docs = _correr(tmp_path, monkeypatch, filas)
    assert docs["h000"][0] == "Venta de lote en Carpintería – Inmobiliaria CIP"
    assert docs["h000"][1] == "Departamento de 2 Amb. en PH\nCon patio y cochera."
    assert docs["h001"][0] == "Casa 3 < 4 dormitorios"
    assert resumen["textos_con_entidades_limpiados"] == 2


def test_MUERDE_la_snapshot_toma_los_campos_extraidos_de_un_cierre_parcial(tmp_path, monkeypatch):
    """`blanco`: NEEDS_FIX por precio, moneda y ciudad; sus titulos reales si."""
    frescas = {"h000": {"hash_dedup": "h000", "titulo": "Casa en Pilar",
                        "_campos_confiables": ["titulo"]}}
    resumen, docs = _correr(tmp_path, monkeypatch,
                            [("roomix:blanco", "Blanco Propiedades", "Texto propio largo uno")],
                            frescas)
    assert docs["h000"][0] == "Casa en Pilar"
    assert resumen["filas_con_frescura_parcial"] == 1


def test_MUERDE_el_nombre_de_la_agencia_repetido_como_titulo_no_se_sirve(tmp_path, monkeypatch):
    """La v4 del 25-09 servia 1.980 titulos que son el nombre de la agencia
    (`patagonica` 320, `meta` «Meta Inmobiliaria | Propiedades en Tucuman»)."""
    filas = [("roomix:meta inmobiliaria", "Meta Inmobiliaria | Propiedades en Tucumán",
              f"Departamento {i} de dos ambientes al frente.") for i in range(9)]
    filas += [("roomix:meta inmobiliaria", "Casa en Yerba Buena", "Casa con pileta y quincho.")]
    resumen, docs = _correr(tmp_path, monkeypatch, filas)
    assert [docs[f"h{i:03d}"][0] for i in range(9)] == [None] * 9
    assert docs["h009"][0] == "Casa en Yerba Buena"
    assert resumen["titulos_del_sitio_descartados"] == 9


def test_un_titulo_propio_con_el_nombre_de_la_agencia_se_conserva(tmp_path, monkeypatch):
    filas = [("roomix:blanco propiedades", f"Blanco Propiedades - Casa {i} en Pilar",
              f"Texto propio {i} de la ficha.") for i in range(9)]
    _, docs = _correr(tmp_path, monkeypatch, filas)
    assert all(t.startswith("Blanco Propiedades - Casa") for t, _, _ in docs.values())


def test_un_titulo_repetido_que_no_es_la_agencia_se_conserva(tmp_path, monkeypatch):
    """`pozzobon`: «casa» en 7 de 8 fichas es un titulo pobre, no del sitio."""
    filas = [("roomix:pozzobon", "Casa", f"Texto propio {i} de la ficha.") for i in range(9)]
    _, docs = _correr(tmp_path, monkeypatch, filas)
    assert all(t == "Casa" for t, _, _ in docs.values())


def test_sin_descripcion_el_titulo_del_sitio_se_conserva(tmp_path, monkeypatch):
    filas = [("roomix:meta inmobiliaria", "Meta Inmobiliaria", None) for _ in range(9)]
    _, docs = _correr(tmp_path, monkeypatch, filas)
    assert all(t == "Meta Inmobiliaria" for t, _, _ in docs.values())

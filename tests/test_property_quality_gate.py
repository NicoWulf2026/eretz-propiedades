"""El quality gate: de dónde sale el diagnóstico de un campo ausente."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts.property_quality_gate import GATE_VERSION, cobertura_por_agencia


def _paquete(tmp_path: Path, agencia: str, campos: dict) -> Path:
    carpeta = tmp_path / agencia.replace(":", "_").replace(" ", "_")
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "certification.json").write_text(json.dumps(
        {"canonical_agency_id": agencia, "field_coverage": campos},
        ensure_ascii=False), encoding="utf-8")
    return carpeta


def test_haberlo_extraido_prueba_que_la_fuente_lo_publica(tmp_path):
    """La señal de origen falla hacia el "no lo publica", y eso exonera al parser.

    `alpha inmobiliaria` figura con `source_provided: 0` en `descripcion` y con
    las 127 descripciones extraídas. Leyendo sólo la señal, cualquier ficha
    suya sin descripción salía como `SOURCE_NOT_PROVIDED` —"no hay nada que
    arreglar"— sobre un campo que la fuente evidentemente publica.

    Eran 128 de 290 exoneraciones, el 44 %.
    """
    _paquete(tmp_path, "roomix:alpha", {
        "descripcion": {"source_provided": 0, "normalized_present": 127},
    })
    cobertura = cobertura_por_agencia(tmp_path)

    assert cobertura["roomix:alpha"]["descripcion"] is True


def test_un_campo_que_nunca_se_extrajo_ni_se_vio_sigue_exonerado(tmp_path):
    """La corrección no puede convertir todo en defecto nuestro.

    Si la fuente no lo publicaba y nunca se extrajo, `SOURCE_NOT_PROVIDED` es
    la verdad y no hay nada que arreglar.
    """
    _paquete(tmp_path, "roomix:beta", {
        "barrio": {"source_provided": 0, "normalized_present": 0},
    })
    cobertura = cobertura_por_agencia(tmp_path)

    assert cobertura["roomix:beta"]["barrio"] is False


def test_sin_paquete_no_se_inventa_diagnostico(tmp_path):
    """Sin certificación no se sabe, y decirlo es parte del contrato."""
    assert cobertura_por_agencia(tmp_path) == {}
    assert cobertura_por_agencia(tmp_path / "no-existe") == {}


def test_un_paquete_ilegible_no_tumba_el_gate(tmp_path):
    """Un JSON roto es una agencia sin diagnóstico, no una corrida caída."""
    roto = tmp_path / "roto"
    roto.mkdir()
    (roto / "certification.json").write_text("{no es json", encoding="utf-8")
    _paquete(tmp_path, "roomix:sana", {
        "precio": {"source_provided": 10, "normalized_present": 10}})

    cobertura = cobertura_por_agencia(tmp_path)
    assert cobertura == {"roomix:sana": {"precio": True}}


def test_un_paquete_sin_field_coverage_no_deja_agencia_fantasma(tmp_path):
    """153 de 200 paquetes no tienen `field_coverage` —son los que no
    encontraron inventario—. Registrarlos con un diccionario vacío haría creer
    que esa agencia tiene diagnóstico y que ningún campo se publica."""
    _paquete(tmp_path, "roomix:vacia", {})
    assert "roomix:vacia" not in cobertura_por_agencia(tmp_path)


def test_el_gate_no_escribe_en_ninguna_base(tmp_path, monkeypatch, capsys):
    """La barrera de autorización: el gate es una lectura y un artefacto."""
    db = tmp_path / "p.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (row_json text, canonical_id text, "
                     "hash_dedup text, status text)")
    fila = {"source_url": "https://alfa.com.ar/p/1", "hash_dedup": "h1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "operacion": "venta", "tipo_propiedad": "casa",
            "precio": 100000.0, "moneda": "USD", "ciudad": "Rosario"}
    conexion.execute("insert into rows values (?,?,?,?)",
                     (json.dumps(fila), "roomix:alfa", "h1", "CANDIDATE"))
    conexion.commit()
    conexion.close()
    solo_lectura = db.stat().st_mtime

    salida = tmp_path / "out"
    salida.mkdir()
    paquetes = tmp_path / "paquetes"
    paquetes.mkdir()

    import sys
    from scripts import property_quality_gate as gate
    monkeypatch.setattr(sys, "argv", [
        "gate", "--db", str(db), "--paquetes", str(paquetes),
        "--salida", str(salida)])
    assert gate.main() == 0

    resumen = json.loads(
        (salida / "PROPERTY_QUALITY_GATE_SUMMARY.json").read_text(encoding="utf-8"))
    assert resumen["database_writes"] == 0
    assert resumen["propiedades_evaluadas"] == 1
    assert db.stat().st_mtime == solo_lectura

    filas = [json.loads(l) for l in
             (salida / "PROPERTY_QUALITY_GATE.jsonl").read_text(
                 encoding="utf-8").splitlines()]
    assert len(filas) == 1
    # Una fila por propiedad, no un agregado: un número resumido no se puede
    # discutir, una fila sí.
    assert filas[0]["hash_dedup"] == "h1"
    assert filas[0]["gate_version"] == GATE_VERSION
    assert filas[0]["origen_del_diagnostico"] == "sin_paquete_de_certificacion"
    # Sin ciudad no hay filtro por ciudad, pero la propiedad existe igual.
    assert "FICHA" in filas[0]["alcances"] and "LISTADO" in filas[0]["alcances"]
    assert "MAPA" not in filas[0]["alcances"]


def test_la_base_por_defecto_es_la_canonica_del_manifiesto():
    """Una snapshot vieja clavada en el default ya hizo que el certificador
    midiera contra un universo al que le faltaban 13.023 candidatas. El default
    no puede ser una ruta escrita a mano."""
    fuente = Path("scripts/property_quality_gate.py").read_text(encoding="utf-8")
    assert 'default=str(base_canonica())' in fuente
    assert "PREINGESTION_REBUILD_20260903" not in fuente


def test_solo_entran_las_propuestas_de_ciudad_aptas(tmp_path):
    """Las 6.890 retenidas —entre ellas `Villa del Parque`, barrio de CABA
    propuesto como localidad de Río Negro— no entran ni siquiera en la
    proyección. Proyectar sobre datos que no se van a escribir sería prometer
    un filtro que no va a existir."""
    from scripts.property_quality_gate import ciudades_propuestas

    auditoria = tmp_path / "audit.jsonl"
    auditoria.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in (
        {"hash_dedup": "buena", "apta_para_escritura": True,
         "propuesto": {"ciudad": "Morón", "provincia": "Buenos Aires"}},
        {"hash_dedup": "dudosa", "apta_para_escritura": False,
         "propuesto": {"ciudad": "Villa del Parque", "provincia": "Río Negro"}},
    )) + "\n", encoding="utf-8")

    propuestas = ciudades_propuestas(auditoria)
    assert set(propuestas) == {"buena"}
    assert ciudades_propuestas(tmp_path / "no-existe.jsonl") == {}


def test_la_localidad_sale_de_la_cobertura_y_no_del_campo_crudo(tmp_path, monkeypatch):
    """`FILTRO_CIUDAD: 5.965` no era cobertura de localidad: era "hay texto en
    el campo ciudad". Un barrio contaba igual que una localidad censal."""
    salida = _corrida(tmp_path, monkeypatch, ciudad="Villa del Parque",
                      nivel="PROVINCIA", valor="Buenos Aires")
    resumen = json.loads(
        (salida / "PROPERTY_QUALITY_GATE_SUMMARY.json").read_text(encoding="utf-8"))
    # Hay texto de ciudad, pero no hay localidad demostrada.
    assert "FILTRO_LOCALIDAD" not in resumen["por_alcance"]
    assert resumen["por_alcance"]["AREA_BUSQUEDA"] == 1
    assert resumen["database_writes"] == 0
    # Y la propiedad existe igual: la regla que no se negocia.
    assert resumen["publicables"] == resumen["propiedades_evaluadas"] == 1


def test_el_municipio_da_area_y_nunca_localidad(tmp_path, monkeypatch):
    """La decisión: un municipio puede servir para descubrir una propiedad,
    pero no puede fingir ser una localidad.

    El nivel lo decide la cobertura, que ya aplicó la geometría oficial y la
    regla de conflicto. El gate NO recalcula geografía: dos lugares decidiendo
    lo mismo producen dos verdades, y tarde o temprano difieren.
    """
    salida = _corrida(tmp_path, monkeypatch, ciudad=None,
                      nivel="MUNICIPIO", valor="La Calera")
    resumen = json.loads(
        (salida / "PROPERTY_QUALITY_GATE_SUMMARY.json").read_text(encoding="utf-8"))
    assert resumen["area_de_busqueda_por_nivel"] == {"MUNICIPIO": 1}
    assert resumen["por_alcance"]["AREA_BUSQUEDA"] == 1
    assert "FILTRO_LOCALIDAD" not in resumen["por_alcance"]
    assert resumen["database_writes"] == 0


def test_un_conflicto_geografico_se_cuenta_y_no_borra_la_propiedad(tmp_path, monkeypatch):
    """La coordenada y la fuente se contradicen en 3.859 propiedades. No se
    elige ninguna: se declara el conflicto y queda contado."""
    salida = _corrida(tmp_path, monkeypatch, ciudad=None,
                      nivel="PROVINCIA", valor="Cordoba",
                      estado="GEO_CONFLICT")
    resumen = json.loads(
        (salida / "PROPERTY_QUALITY_GATE_SUMMARY.json").read_text(encoding="utf-8"))
    assert resumen["propiedades_en_conflicto_geografico"] == 1
    assert resumen["publicables"] == 1


def _corrida(tmp_path, monkeypatch, *, ciudad, nivel, valor, estado=None):
    """Una propiedad y su cobertura: el gate de punta a punta."""
    db = tmp_path / "p.sqlite3"
    conexion = sqlite3.connect(db)
    conexion.execute("create table rows (row_json text, canonical_id text, "
                     "hash_dedup text, status text)")
    fila = {"source_url": "https://alfa.com.ar/p/1", "hash_dedup": "h1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "operacion": "venta", "tipo_propiedad": "casa",
            "precio": 100000.0, "moneda": "USD", "ciudad": ciudad}
    conexion.execute("insert into rows values (?,?,?,?)",
                     (json.dumps(fila), "roomix:alfa", "h1", "CANDIDATE"))
    conexion.commit()
    conexion.close()

    cobertura = tmp_path / "cobertura.jsonl"
    cobertura.write_text(json.dumps({
        "hash_dedup": "h1", "localidad_canonica": None,
        "estado_geografico": estado,
        "area_busqueda": {"nivel": nivel, "nombre": valor}},
        ensure_ascii=False) + "\n", encoding="utf-8")

    salida = tmp_path / "out"
    salida.mkdir()
    paquetes = tmp_path / "paquetes"
    paquetes.mkdir()
    vacio = tmp_path / "vacio.jsonl"
    vacio.write_text("", encoding="utf-8")

    import sys
    from scripts import property_quality_gate as gate
    monkeypatch.setattr(sys, "argv", [
        "gate", "--db", str(db), "--paquetes", str(paquetes),
        "--salida", str(salida), "--auditoria-de-ciudad", str(vacio),
        "--cobertura-geografica", str(cobertura)])
    assert gate.main() == 0
    return salida


def test_una_cobertura_parcial_no_alcanza_para_culparnos(tmp_path):
    """`alderinmobiliaria` no publica superficie en ninguna de las cinco fichas
    que abrí, y 147 propiedades suyas figuraban como defecto nuestro porque
    otras sí la publican.

    La señal es POR AGENCIA: cuando la fuente lo publica en algunas fichas y en
    otras no, el agregado no dice de cuál se trata ésta. El estado honesto es
    "no sabemos".
    """
    from scripts.property_quality_gate import cobertura_por_agencia

    _paquete(tmp_path, "roomix:parcial", {
        "superficie_total": {"source_provided": 30, "normalized_present": 30,
                             "normalized_total": 100},
    })
    assert cobertura_por_agencia(tmp_path)["roomix:parcial"]["superficie_total"] is None


def test_una_cobertura_alta_si_alcanza(tmp_path):
    """Si la fuente lo publica en la enorme mayoría, que falte en una es
    nuestro."""
    from scripts.property_quality_gate import cobertura_por_agencia

    _paquete(tmp_path, "roomix:alta", {
        "precio": {"source_provided": 95, "normalized_present": 95,
                   "normalized_total": 100}})
    assert cobertura_por_agencia(tmp_path)["roomix:alta"]["precio"] is True


def test_ninguna_la_publica_sigue_siendo_no_provisto(tmp_path):
    from scripts.property_quality_gate import cobertura_por_agencia

    _paquete(tmp_path, "roomix:cero", {
        "barrio": {"source_provided": 0, "normalized_present": 0,
                   "normalized_total": 100}})
    assert cobertura_por_agencia(tmp_path)["roomix:cero"]["barrio"] is False


def test_no_saber_se_traduce_a_ausente_sin_diagnostico():
    """`None` no es una tercera categoría inventada: es el valor que el
    contrato ya interpreta como AUSENTE_SIN_DIAGNOSTICO."""
    from scripts.property_contract import AUSENTE_SIN_DIAGNOSTICO, estado_de_campo

    assert estado_de_campo({}, "superficie_total", None) == AUSENTE_SIN_DIAGNOSTICO

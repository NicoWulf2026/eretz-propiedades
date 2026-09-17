# -*- coding: utf-8 -*-
"""El índice derivado: qué garantiza y qué no puede romper.

El JSONL es el registro append-only que produce la certificación; esto es su
índice. La distinción importa porque define qué es recuperable: si el índice se
corrompe se borra y se reconstruye, y si el JSONL se corrompe se perdió trabajo.

La unicidad es el punto delicado. `(agency_id, source_url)` y `fingerprint` sí
lo son —medido sobre las 22.097 reales—, pero `(agency_id, source_listing_id)`
**no**: `baron inmobiliaria` tiene el id `300` en 36 propiedades distintas. Un
índice único sobre el listing_id revienta la carga, que es justamente como se
descubrió la colisión.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from indice_de_propiedades import TOPE_VALOR, construir  # noqa: E402


def propiedad(url: str, listing: str, fp: str, precio: str = "100000") -> dict:
    return {
        "run_id": "2026-09-16T00:00:00",
        "agency_id": "roomix:baron inmobiliaria",
        "source_url": url,
        "source_listing_id": listing,
        "connector": "generico",
        "strategy": "generic/html_catalog",
        "strategy_fingerprint": "abc123",
        "agency_status": "NEEDS_FIX",
        "imagenes": 3,
        "fingerprint": fp,
        "scraped_at": "2026-09-16T00:01:00",
        "campos": {
            "precio": {"valor": precio, "estado": "PROVIDED_EXTRACTED"},
            "titulo": {"valor": "Casa en venta", "estado": "PROVIDED_EXTRACTED"},
            "barrio": {"valor": None, "estado": "SOURCE_NOT_PROVIDED"},
        },
    }


def escribir(tmp_path: Path, filas: list[dict]) -> Path:
    origen = tmp_path / "propiedades.jsonl"
    origen.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                              for f in filas), encoding="utf-8")
    return origen


def test_MUERDE_el_listing_id_repetido_no_impide_construir(tmp_path):
    """El caso real de `baron`: 36 propiedades con el id `300`.

    Si el índice exigiera unicidad sobre `(agency_id, source_listing_id)`, la
    carga reventaría y el artefacto quedaría sin construir. Esto no es una
    tolerancia laxa: las 36 son propiedades distintas, con urls distintas, y
    perderlas sería peor que registrar un id repetido.
    """
    filas = [propiedad(f"https://x.com/casa-{i}-al-300-7eb{i:03x}", "300", f"fp{i}")
             for i in range(36)]
    destino = tmp_path / "indice.sqlite3"
    resumen = construir(escribir(tmp_path, filas), destino)
    assert resumen["propiedades"] == 36
    assert resumen["duplicados_descartados"] == 0

    conexion = sqlite3.connect(destino)
    repetidos = conexion.execute(
        "SELECT count(*) FROM propiedad WHERE source_listing_id = '300'"
    ).fetchone()[0]
    assert repetidos == 36
    conexion.close()


def test_la_misma_url_dos_veces_se_descarta_una(tmp_path):
    """`(agency_id, source_url)` sí es la clave, y el índice la respeta.

    Dos filas con la misma url son la misma propiedad vista dos veces, no dos
    propiedades. Insertar las dos rompería el índice único y, peor, contaría
    inventario de más.
    """
    filas = [propiedad("https://x.com/casa-1", "1", "fpA"),
             propiedad("https://x.com/casa-1", "1", "fpB", precio="999")]
    resumen = construir(escribir(tmp_path, filas), tmp_path / "i.sqlite3")
    assert resumen["propiedades"] == 1
    assert resumen["duplicados_descartados"] == 1


def test_los_campos_quedan_consultables_por_estado(tmp_path):
    """La consulta que el Regression Gate V2 hace: campo y estado (§56)."""
    destino = tmp_path / "i.sqlite3"
    construir(escribir(tmp_path, [propiedad("https://x.com/a", "1", "fp1")]),
              destino)
    conexion = sqlite3.connect(destino)
    filas = dict(conexion.execute(
        "SELECT campo, estado FROM campo ORDER BY campo").fetchall())
    assert filas["precio"] == "PROVIDED_EXTRACTED"
    assert filas["barrio"] == "SOURCE_NOT_PROVIDED"
    conexion.close()


def test_un_valor_enorme_se_recorta_y_no_infla_el_indice(tmp_path):
    """Una descripción de 8 KB no aporta a una comparación campo a campo.

    El valor entero vive en el JSONL, que para eso es el registro.
    """
    fila = propiedad("https://x.com/a", "1", "fp1")
    fila["campos"]["descripcion"] = {"valor": "x" * 9000,
                                     "estado": "PROVIDED_EXTRACTED"}
    destino = tmp_path / "i.sqlite3"
    construir(escribir(tmp_path, [fila]), destino)
    conexion = sqlite3.connect(destino)
    guardado = conexion.execute(
        "SELECT valor FROM campo WHERE campo = 'descripcion'").fetchone()[0]
    assert len(guardado) == TOPE_VALOR
    conexion.close()


def test_un_json_roto_en_el_medio_no_tumba_la_construccion(tmp_path):
    """El JSONL puede quedar con una línea a medias tras una caída.

    El índice tiene que poder reconstruirse igual: si una línea rota impidiera
    indexar, una caída a mitad de escritura dejaría el artefacto inservible
    hasta que alguien editara el archivo a mano.
    """
    origen = tmp_path / "p.jsonl"
    bueno = json.dumps(propiedad("https://x.com/a", "1", "fp1"),
                       ensure_ascii=False)
    otro = json.dumps(propiedad("https://x.com/b", "2", "fp2"),
                      ensure_ascii=False)
    origen.write_text(f"{bueno}\n{{roto\n{otro}\n", encoding="utf-8")
    resumen = construir(origen, tmp_path / "i.sqlite3")
    assert resumen["propiedades"] == 2


def test_el_indice_se_reemplaza_entero_y_no_a_medias(tmp_path):
    """Se construye en un temporal y se renombra.

    Si fallara a mitad escribiendo sobre el destino, quedaría un índice
    incompleto que parece completo, que es peor que no tener ninguno.
    """
    destino = tmp_path / "i.sqlite3"
    construir(escribir(tmp_path, [propiedad("https://x.com/a", "1", "fp1")]),
              destino)
    construir(escribir(tmp_path, [propiedad("https://x.com/b", "2", "fp2"),
                                  propiedad("https://x.com/c", "3", "fp3")]),
              destino)
    conexion = sqlite3.connect(destino)
    assert conexion.execute("SELECT count(*) FROM propiedad").fetchone()[0] == 2
    conexion.close()
    assert not destino.with_suffix(".sqlite3.tmp").exists()

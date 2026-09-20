# -*- coding: utf-8 -*-
"""Una huella que no ve el dato que uso es una huella que miente.

Pendiente #4 de Codex, detectado y no corregido:

    Code fingerprint schema 5 no captura versión de INPUT GeoRef
    efectivamente usado. Geografia cachea y carga provincias/
    localidades_censales; cambios de referencia pueden dejar code hash igual.
    Capturar input realmente usado por ambos runs.

Es un agujero real. `connectors/geografia.py` decide la ciudad y la provincia
de cada propiedad leyendo `provincias.json` y `localidades_censales.json`. Si
el snapshot de GeoRef cambia —y cambia: es una descarga con fecha— la
extracción cambia y **la huella no se entera**. Las certificaciones quedan
vigentes describiendo un resultado que hoy no se reproduciría.

El propio módulo de geografía ya está en la huella (`shared/geografia`), lo
cual demuestra que el criterio está aceptado: cambiar lo que decide la ciudad
invalida. Lo que faltaba era que el criterio alcanzara al **dato**, no sólo al
código.

Se capturan los dos recursos que `Geografia._cargar` lee de verdad —no los
seis del manifiesto—, que es lo que Codex pidió: «input realmente usado».
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.agency_fingerprints import huella_del_input_geografico  # noqa: E402


def manifiesto(tmp_path: Path, provincias="aaa", localidades="bbb") -> Path:
    (tmp_path / "MANIFEST.json").write_text(json.dumps({
        "fuente": "georef", "descargado": "2026-09-01",
        "recursos": {
            "provincias": {"sha256": provincias},
            "departamentos": {"sha256": "no-se-usa"},
            "localidades-censales": {"sha256": localidades},
            "asentamientos": {"sha256": "tampoco"},
        }}), encoding="utf-8")
    return tmp_path


def test_el_input_tiene_huella_propia(tmp_path):
    valor = huella_del_input_geografico(manifiesto(tmp_path))
    assert isinstance(valor, bytes) and valor


def test_MUERDE_cambiar_las_localidades_cambia_la_huella(tmp_path):
    """El caso que motiva todo esto.

    Un snapshot nuevo de localidades cambia qué ciudad se resuelve para miles
    de propiedades. Si la huella no se mueve, las certificaciones viejas
    quedan «vigentes» describiendo algo que ya no pasaría.
    """
    antes = huella_del_input_geografico(manifiesto(tmp_path, localidades="b1"))
    despues = huella_del_input_geografico(manifiesto(tmp_path, localidades="b2"))
    assert antes != despues


def test_MUERDE_cambiar_las_provincias_tambien(tmp_path):
    antes = huella_del_input_geografico(manifiesto(tmp_path, provincias="p1"))
    despues = huella_del_input_geografico(manifiesto(tmp_path, provincias="p2"))
    assert antes != despues


def test_MUERDE_un_recurso_que_NO_se_usa_no_mueve_la_huella(tmp_path):
    """«Input realmente usado», que es lo que pidió Codex.

    `Geografia._cargar` lee dos archivos: `provincias.json` y
    `localidades_censales.json`. Los otros cuatro del manifiesto no los abre
    nadie, y hacerlos parte de la huella significaría recertificar 261
    agencias por un archivo que no cambió nada de lo extraído.
    """
    antes = huella_del_input_geografico(manifiesto(tmp_path))
    (tmp_path / "MANIFEST.json").write_text(json.dumps({
        "recursos": {"provincias": {"sha256": "aaa"},
                     "departamentos": {"sha256": "CAMBIADO"},
                     "localidades-censales": {"sha256": "bbb"}}}),
        encoding="utf-8")
    assert huella_del_input_geografico(tmp_path) == antes


def test_MUERDE_sin_manifiesto_la_huella_dice_que_no_sabe(tmp_path):
    """Y no se parece a la de un manifiesto presente.

    Dos máquinas, una con la referencia y otra sin ella, no producen el mismo
    resultado geográfico. Que produzcan la misma huella sería la falsedad
    exacta que esto viene a cerrar: silencio donde hay diferencia.
    """
    sin = huella_del_input_geografico(tmp_path)
    con = huella_del_input_geografico(manifiesto(tmp_path))
    assert sin != con
    assert b"sin-manifiesto" in sin


def test_un_manifiesto_ilegible_tampoco_se_confunde_con_uno_bueno(tmp_path):
    (tmp_path / "MANIFEST.json").write_text("{roto", encoding="utf-8")
    ilegible = huella_del_input_geografico(tmp_path)
    assert ilegible != huella_del_input_geografico(manifiesto(tmp_path))


def test_el_componente_entra_en_la_huella_de_estrategia():
    """No alcanza con calcularlo: tiene que estar en los componentes.

    Es el error que el propio repositorio ya cometió con `generic/common`,
    donde una lista blanca dejaba doce métodos afuera en silencio.
    """
    from scripts.agency_fingerprints import fingerprint_components
    componentes = fingerprint_components("generico", "generic/html_catalog")
    assert "shared/geo_input" in componentes

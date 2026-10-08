"""El almacen guarda cada pagina bajada sin cambiar lo que devuelve el descargador ni poder romperlo."""
from __future__ import annotations

import json

import pytest

from scripts.almacen_de_paginas import AlmacenDePaginas, enganchar


class _Falso:
    def __init__(self, cuerpos):
        self.cuerpos = cuerpos

    def bajar(self, url):
        valor = self.cuerpos[url]
        if isinstance(valor, Exception):
            raise valor
        return valor


def test_guarda_lo_bajado_y_devuelve_lo_mismo(tmp_path):
    clase = type("D", (_Falso,), {})
    alm = AlmacenDePaginas(tmp_path, worker="w1")
    alm.contexto = {"canonical_agency_id": "roomix:a"}
    enganchar(clase, alm)
    d = clase({"https://a.com.ar/p/1": "<html>ficha uno</html>", "https://a.com.ar/p/2": "<html>ficha uno</html>"})
    assert d.bajar("https://a.com.ar/p/1") == "<html>ficha uno</html>"
    assert d.bajar("https://a.com.ar/p/2") == "<html>ficha uno</html>"
    # mismo contenido, un solo blob; dos lineas de indice
    assert alm.guardadas == 1 and alm.repetidas == 1
    indice = list((tmp_path / "indice").glob("*.w1.jsonl"))
    filas = [json.loads(l) for l in indice[0].read_text(encoding="utf-8").splitlines()]
    assert [f["url"] for f in filas] == ["https://a.com.ar/p/1", "https://a.com.ar/p/2"]
    assert filas[0]["canonical_agency_id"] == "roomix:a"
    assert alm.leer(filas[0]["sha256"]) == "<html>ficha uno</html>"


def test_los_errores_de_red_se_propagan_igual(tmp_path):
    clase = type("D", (_Falso,), {})
    enganchar(clase, AlmacenDePaginas(tmp_path))
    with pytest.raises(TimeoutError):
        clase({"u": TimeoutError("x")}).bajar("u")


def test_un_almacen_roto_no_rompe_la_descarga(tmp_path):
    archivo = tmp_path / "no_es_carpeta"
    archivo.write_text("x", encoding="utf-8")
    clase = type("D", (_Falso,), {})
    alm = AlmacenDePaginas(archivo)          # raiz imposible: no se puede crear nada adentro
    enganchar(clase, alm)
    assert clase({"u": "<html>ok</html>"}).bajar("u") == "<html>ok</html>"
    assert alm.errores == 1


def test_enganchar_dos_veces_no_guarda_dos_veces(tmp_path):
    clase = type("D", (_Falso,), {})
    alm = AlmacenDePaginas(tmp_path)
    enganchar(clase, alm)
    enganchar(clase, alm)
    clase({"u": "<html>x</html>"}).bajar("u")
    assert alm.guardadas == 1 and alm.repetidas == 0

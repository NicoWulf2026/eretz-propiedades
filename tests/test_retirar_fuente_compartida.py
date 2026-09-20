# -*- coding: utf-8 -*-
"""Retirar una url que no es de nadie, de todas las capas que la tengan.

`https://cir.org.ar/socios` figura como fuente de **diez** agencias. Es la
lista de socios de un colegio inmobiliario: no es la web de ninguna de ellas.

Lo que hace peligroso a este arreglo no es lo que quita sino dónde: de las 23
agencias, 4 resuelven por `platform.domain` y 12 por `verificada.official_url`.
Retirar una sola capa deja aparecer la de abajo **con la misma url**, y el
trabajo queda inerte. Ya pasó: cinco correcciones de fuente que di por
aplicadas no hacían nada porque edité la capa 2 mientras la capa 1 ganaba.

Medido en el dry-run: la url está en 6 filas del directorio de plataformas, 3
del registro de fuentes, 6 de la resolución y **18 de las verificadas**.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from retirar_fuente_compartida import normalizar, retirar_en  # noqa: E402

URL = "https://cir.org.ar/socios"


def escribir(ruta: Path, filas: list[dict]) -> None:
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n"
                            for f in filas), encoding="utf-8")


def leer(ruta: Path) -> list[dict]:
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def test_MUERDE_la_url_se_retira_y_se_conserva(tmp_path):
    """Las dos mitades: deja de ser fuente y no se pierde.

    Un perfil en un directorio sigue siendo prueba de que la inmobiliaria
    existe. Lo único que deja de ser es fuente de inventario, y el §11 pide
    conservar la evidencia.
    """
    ruta = tmp_path / "capa.jsonl"
    escribir(ruta, [{"canonical_agency_id": "roomix:a", "domain": URL}])
    assert retirar_en(ruta, ("domain",), {"roomix:a": URL}, aplicar=True) == 1
    fila = leer(ruta)[0]
    assert fila["domain"] is None
    assert fila["url_retirada_como_fuente"] == URL
    assert "directorio institucional" in fila["url_retirada_porque"]


def test_MUERDE_no_se_toca_a_quien_tiene_OTRA_url(tmp_path):
    """El riesgo real de una herramienta que borra: llevarse lo que no debe.

    Dos agencias del mismo archivo, una con la url compartida y otra con su
    sitio propio. Si el filtro fuera por agencia y no por valor, la segunda
    perdería una fuente buena.
    """
    ruta = tmp_path / "capa.jsonl"
    escribir(ruta, [{"canonical_agency_id": "roomix:a", "domain": URL},
                    {"canonical_agency_id": "roomix:b",
                     "domain": "https://sitiopropio.com.ar"}])
    retirar_en(ruta, ("domain",), {"roomix:a": URL, "roomix:b": URL},
               aplicar=True)
    filas = {f["canonical_agency_id"]: f for f in leer(ruta)}
    assert filas["roomix:a"]["domain"] is None
    assert filas["roomix:b"]["domain"] == "https://sitiopropio.com.ar"


def test_la_barra_final_no_esconde_la_coincidencia(tmp_path):
    """`/socios` y `/socios/` son la misma url.

    En el padrón real conviven las dos formas: si la comparación fuera
    literal, la mitad quedaría sin retirar y el efecto sería parcial, que en
    esto es lo mismo que nulo.
    """
    ruta = tmp_path / "capa.jsonl"
    escribir(ruta, [{"canonical_agency_id": "roomix:a",
                     "domain": "https://CIR.org.ar/socios/"}])
    assert retirar_en(ruta, ("domain",), {"roomix:a": URL}, aplicar=True) == 1
    assert leer(ruta)[0]["domain"] is None


def test_en_seco_no_escribe_nada(tmp_path):
    ruta = tmp_path / "capa.jsonl"
    escribir(ruta, [{"canonical_agency_id": "roomix:a", "domain": URL}])
    antes = ruta.read_bytes()
    assert retirar_en(ruta, ("domain",), {"roomix:a": URL}, aplicar=False) == 1
    assert ruta.read_bytes() == antes


def test_un_archivo_que_no_existe_no_es_un_error(tmp_path):
    assert retirar_en(tmp_path / "no-esta.jsonl", ("domain",),
                      {"roomix:a": URL}, aplicar=True) == 0


def test_solo_se_retiran_las_clases_que_no_son_de_nadie():
    """`OFICINAS_DE_RED` y `POSIBLE_DUPLICADO` quedan afuera a propósito.

    En una red el sitio SÍ es de alguna de las oficinas y hay que decidir de
    cuál; en un duplicado el arreglo puede ser de identidad y no de fuente.
    Retirar la fuente en esos casos sería resolver un problema con la
    herramienta equivocada.
    """
    from retirar_fuente_compartida import CLASES
    assert set(CLASES) == {"DIRECTORIO_INSTITUCIONAL", "BUSCADOR_DE_PORTAL"}


def test_normalizar_no_confunde_dos_urls_distintas():
    assert normalizar("https://cir.org.ar/socios") != normalizar(
        "https://cir.org.ar/socios-2")

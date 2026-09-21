# -*- coding: utf-8 -*-
"""Que la separacion de causas no vuelva a mezclarlas.

Los tests que muerden son los que distinguen causas parecidas: una ficha
rechazada por el validador y una sin ciudad se ven igual en el campo -las dos
tienen `valor: null`- y no son el mismo problema. Una explica un catalogo
demasiado estricto y la otra una fuente pobre.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.de_donde_falta_la_geografia import (  # noqa: E402
    EXTRACCION_FALLIDA, NO_INTENTADA, PRESENTE, RECHAZADA, SIN_NINGUNA_PISTA,
    SOLO_POR_BARRIO, SOLO_POR_COORDENADA, SOLO_POR_DIRECCION,
    barrio_es_una_frase, causa_de_la_ciudad, leer_jsonl, medir_el_snapshot,
    normalizar, repite_la_provincia_de_su_inmobiliaria)


def ficha(**campos: object) -> dict[str, object]:
    """Una propiedad con los campos que se le pasen, el resto vacios."""
    plantilla = {nombre: {"valor": None, "estado": "NOT_PROVIDED"}
                 for nombre in ("ciudad", "barrio", "direccion", "latitud")}
    for nombre, celda in campos.items():
        plantilla[nombre] = celda
    return {"campos": plantilla}


def test_ciudad_presente_es_ciudad_presente():
    assert causa_de_la_ciudad(ficha(
        ciudad={"valor": "Rosario", "estado": "PROVIDED_EXTRACTED"})) == PRESENTE


def test_MUERDE_rechazada_por_validacion_no_es_lo_mismo_que_faltante():
    """Las dos tienen `valor: null`. Confundirlas invierte la conclusion.

    Si se cuentan juntas, un catalogo que rechaza mil ciudades parece una
    fuente que no las publica, y el arreglo se busca donde no esta.
    """
    rechazada = ficha(ciudad={"valor": None, "estado": "PROVIDED_REJECTED"})
    faltante = ficha(ciudad={"valor": None, "estado": "NOT_PROVIDED"})
    assert causa_de_la_ciudad(rechazada) == RECHAZADA
    assert causa_de_la_ciudad(faltante) == SIN_NINGUNA_PISTA


def test_MUERDE_el_rechazo_gana_sobre_la_coordenada():
    """Una ficha rechazada tambien puede tener coordenadas.

    Lo que la explica es el rechazo. Si gana la coordenada, el informe dice
    "solo inferible" sobre algo que el validador ya vio y descarto, y el
    rechazo desaparece de la cuenta.
    """
    caso = ficha(ciudad={"valor": None, "estado": "PROVIDED_REJECTED"},
                 latitud={"valor": -32.95, "estado": "PROVIDED_EXTRACTED"})
    assert causa_de_la_ciudad(caso) == RECHAZADA


def test_extraccion_fallida_y_no_intentada_se_distinguen():
    assert causa_de_la_ciudad(ficha(
        ciudad={"valor": None, "estado": "EXTRACTION_FAILED"})) == EXTRACCION_FALLIDA
    assert causa_de_la_ciudad(ficha(
        ciudad={"valor": None, "estado": "NOT_ATTEMPTED"})) == NO_INTENTADA


def test_las_pistas_se_ordenan_de_la_mas_fuerte_a_la_mas_debil():
    assert causa_de_la_ciudad(ficha(
        latitud={"valor": -32.95, "estado": "PROVIDED_EXTRACTED"},
        barrio={"valor": "Sarandi", "estado": "PROVIDED_EXTRACTED"},
    )) == SOLO_POR_COORDENADA
    assert causa_de_la_ciudad(ficha(
        barrio={"valor": "Sarandi", "estado": "PROVIDED_EXTRACTED"},
        direccion={"valor": "Mendoza 1700", "estado": "PROVIDED_EXTRACTED"},
    )) == SOLO_POR_BARRIO
    assert causa_de_la_ciudad(ficha(
        direccion={"valor": "Mendoza 1700", "estado": "PROVIDED_EXTRACTED"},
    )) == SOLO_POR_DIRECCION


def test_una_latitud_cero_sigue_siendo_una_coordenada():
    """Cero es un valor, no un vacio. El ecuador existe.

    Es el mismo error que el RPC ya evita al guardar `precio = 0`; aca bastaba
    con un `if lat:` para perderlo.
    """
    caso = ficha(latitud={"valor": 0.0, "estado": "PROVIDED_EXTRACTED"})
    assert causa_de_la_ciudad(caso) == SOLO_POR_COORDENADA


def test_MUERDE_un_barrio_que_es_una_frase_recortada():
    """Los casos reales, copiados del snapshot."""
    assert barrio_es_una_frase(
        "tranquila Parrilla techada Pileta descubierta Termo de gas Videos")
    assert barrio_es_una_frase("en pleno centro de la ciudad y a la versatilidad de sus")
    assert barrio_es_una_frase("Fisherton Fecha de entrega Noviembre 2025")


def test_los_barrios_de_verdad_no_se_marcan():
    """La otra mitad: sin esto la deteccion es inutil porque marca todo."""
    for bueno in ("Centro", "Nueva Cordoba", "Lomas de Zamora Oeste",
                  "Nuestra Senora de Lourdes", "Villa Urquiza", "Pineyro"):
        assert not barrio_es_una_frase(bueno), bueno


def test_un_barrio_vacio_no_es_una_frase():
    assert not barrio_es_una_frase(None)
    assert not barrio_es_una_frase("   ")


def test_MUERDE_la_jerga_se_busca_como_palabra_entera():
    """`\\b` mal puesto ya mordio cinco veces en este proyecto.

    "Pisos" contiene "piso" y "Ambientes" contiene "ambiente": si el patron no
    exige palabra entera, `Villa Piso` y cualquier barrio con esas letras
    adentro quedan marcados. Y al reves, tiene que seguir mordiendo el plural
    real.
    """
    assert not barrio_es_una_frase("Pisonero")
    assert not barrio_es_una_frase("Ambientes Norte".replace("Ambientes", "Amb"))
    assert barrio_es_una_frase("Casa de 3 ambientes en zona tranquila y muy")


def test_la_provincia_se_compara_sin_acentos_ni_mayusculas():
    cuenta = repite_la_provincia_de_su_inmobiliaria(
        [("a", "CORDOBA"), ("a", "Córdoba"), ("a", "Santa Fe")],
        {"a": "Córdoba"})
    assert cuenta == {"igual": 2, "distinta": 1, "sin_padron": 0}


def test_una_propiedad_sin_provincia_no_cuenta_para_ningun_lado():
    """Contarla como "distinta" inflaria la unica cifra que importa aca."""
    cuenta = repite_la_provincia_de_su_inmobiliaria(
        [("a", None), ("a", ""), ("a", "Córdoba")], {"a": "Córdoba"})
    assert cuenta == {"igual": 1, "distinta": 0, "sin_padron": 0}


def test_una_agencia_sin_padron_se_reporta_aparte():
    """No se puede afirmar nada de una agencia cuya provincia no conocemos."""
    cuenta = repite_la_provincia_de_su_inmobiliaria(
        [("desconocida", "Córdoba")], {})
    assert cuenta == {"igual": 0, "distinta": 0, "sin_padron": 1}


def test_normalizar_aplana_acentos_y_espacios():
    assert normalizar("  Río   NEGRO ") == "rio negro"
    assert normalizar(None) == ""


def test_una_linea_rota_no_voltea_la_lectura(tmp_path: Path):
    """Un artefacto de 22.000 lineas escrito por una cola que se corta.

    Abortar por una linea partida perderia el informe entero.
    """
    ruta = tmp_path / "x.jsonl"
    ruta.write_text('{"a": 1}\nno es json\n\n{"a": 2}\n', encoding="utf-8")
    assert [f["a"] for f in leer_jsonl(ruta)] == [1, 2]


def test_un_archivo_que_no_existe_no_explota(tmp_path: Path):
    assert list(leer_jsonl(tmp_path / "no_esta.jsonl")) == []


def test_MUERDE_el_municipio_resuelto_que_quedo_solo_en_area_nombre(tmp_path: Path):
    """El hueco que explica `municipality: null` en el autocompletado.

    El dato esta -el nivel dice MUNICIPIO y el nombre esta escrito- pero en
    otra columna que la que el consumidor lee. Sin esta medicion se concluye
    "el snapshot no tiene jerarquia geografica", que es falso: la tiene y no
    la expone.
    """
    ruta = tmp_path / "snap.sqlite3"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        "create table propiedades (agency_id text, provincia text, "
        "departamento text, municipio text, localidad text, barrio text, "
        "latitud real, area_nivel text, area_nombre text)")
    conexion.executemany(
        "insert into propiedades values (?,?,?,?,?,?,?,?,?)",
        [("a", "Santa Fe", None, None, None, "Centro", -32.9, "MUNICIPIO", "Rosario"),
         ("a", "Santa Fe", None, "Rosario", None, None, None, "MUNICIPIO", "Rosario"),
         ("a", "Santa Fe", None, None, "Funes", None, None, "LOCALIDAD", "Funes")])
    conexion.commit()
    conexion.close()

    medida = medir_el_snapshot(ruta)
    assert medida["total"] == 3
    assert medida["municipio_solo_en_area_nombre"] == 1
    assert medida["columnas"]["municipio"] == 1
    assert medida["area_nivel"] == {"MUNICIPIO": 2, "LOCALIDAD": 1}


def test_el_snapshot_se_abre_en_solo_lectura(tmp_path: Path):
    """La medicion no puede ser capaz de escribir lo que mide."""
    ruta = tmp_path / "snap.sqlite3"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        "create table propiedades (agency_id text, provincia text, "
        "departamento text, municipio text, localidad text, barrio text, "
        "latitud real, area_nivel text, area_nombre text)")
    conexion.commit()
    conexion.close()
    antes = ruta.stat().st_mtime_ns
    medir_el_snapshot(ruta)
    assert ruta.stat().st_mtime_ns == antes

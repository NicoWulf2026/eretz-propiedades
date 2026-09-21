# -*- coding: utf-8 -*-
"""Parar las dos colas porque el guardian hizo su trabajo.

La regla paraba con **cualquier** descarte. Descartar es lo que el guardian
hace, asi que mezclaba «el guardian se equivoco» —grave y compartido— con «el
guardian funciono» —su operacion normal—.

Medido sobre los 100 rechazos registrados en el corpus: **los 100 son
correctos**. Ninguno traia precio ni schema, y son cosas como
`area_cliente.php?sec=sol` y `quienes-somos.php`. Con eso la regla vieja paro
las dos colas dos veces en un dia, `gama` y `bottai`; `bottai` descarto 1
sobre 234.

Lo que estos tests protegen es que aflojar la regla **no** apague el caso que
la justifica: un rechazo que si parecia una propiedad.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.defect_triage import (  # noqa: E402
    descarte_parecia_una_propiedad, paro_por_el_guardian_de_forma)


def institucional(url: str = "https://x.com/quienes-somos.php") -> dict:
    """Un rechazo como los 100 del corpus: nada de propiedad."""
    return {"source_url": url, "precio": None, "tipo_ld": None,
            "operacion_en_texto": False, "fotos": 1}


def test_MUERDE_un_descarte_correcto_entre_muchas_fichas_no_para_la_cola():
    """El caso `bottai`, exacto: 1 descarte sobre 234 fichas buenas.

    `area_cliente.php?sec=sol` no tiene precio ni schema. Parar las dos colas
    por eso cuesta horas de rendimiento por trabajo bien hecho.
    """
    corrida = {"descartadas_por_forma": 1, "detalles_obtenidos": 233,
               "_descartes": [institucional(
                   "https://bottai.com.ar/area_cliente.php?sec=sol")]}
    assert paro_por_el_guardian_de_forma(corrida) is None


def test_MUERDE_un_descarte_con_precio_si_para():
    """El caso que justifica que la regla exista, y que nunca paso todavia.

    Si el guardian empieza a rechazar fichas con precio, cada agencia de la
    familia pierde inventario en silencio. Por eso se deja armado.
    """
    corrida = {"descartadas_por_forma": 3, "detalles_obtenidos": 200,
               "_descartes": [institucional(), institucional(),
                              {"source_url": "https://x.com/p/9-casa",
                               "precio": 145000, "tipo_ld": None, "fotos": 8}]}
    motivo = paro_por_el_guardian_de_forma(corrida)
    assert motivo is not None
    assert "TENIAN precio o schema" in motivo
    assert "1 de 3" in motivo


def test_MUERDE_un_descarte_con_schema_tambien_para():
    corrida = {"descartadas_por_forma": 1, "detalles_obtenidos": 50,
               "_descartes": [{"source_url": "https://x.com/p/1",
                               "precio": None, "tipo_ld": "Product",
                               "fotos": 6}]}
    assert paro_por_el_guardian_de_forma(corrida) is not None


def test_MUERDE_operacion_en_texto_no_alcanza_para_sospechar():
    """88 de los 100 rechazos del corpus la traian en True.

    Entre ellos `historia.php`, `ubicacion.php` y `como_llegar.php` del portal
    de `gama`: la palabra «venta» esta en el menu del sitio. Si contara,
    aflojar la regla no aflojaria nada y el 88 % de los descartes correctos
    seguiria parando las colas.
    """
    assert not descarte_parecia_una_propiedad(
        {"operacion_en_texto": True, "precio": None, "tipo_ld": None,
         "fotos": 19, "source_url": "https://x.com/historia.php"})


def test_MUERDE_si_no_sobrevivio_ninguna_ficha_se_para_igual():
    """El caso `gama`: 96 descartes, cero propiedades.

    Cada rechazo era correcto y aun asi habia algo que mirar —su fuente era
    un perfil de portal—. Una agencia que termina en cero necesita
    explicacion aunque el guardian tenga razon.
    """
    corrida = {"descartadas_por_forma": 48, "detalles_obtenidos": 0,
               "_descartes": [institucional() for _ in range(48)]}
    motivo = paro_por_el_guardian_de_forma(corrida)
    assert motivo is not None
    assert "ninguna sobrevivio" in motivo


def test_MUERDE_sin_evidencia_de_los_descartes_se_para_como_antes():
    """El silencio no es una respuesta tranquilizadora.

    Un registro viejo, sin `_descartes`, no permite afirmar que los rechazos
    estuvieran bien. Aflojar ahi seria aflojar a ciegas.
    """
    corrida = {"descartadas_por_forma": 5, "detalles_obtenidos": 100}
    motivo = paro_por_el_guardian_de_forma(corrida)
    assert motivo is not None
    assert "sin evidencia" in motivo


def test_una_lista_de_descartes_vacia_con_cuenta_en_cero_no_para():
    assert paro_por_el_guardian_de_forma(
        {"descartadas_por_forma": 0, "_descartes": []}) is None


def test_un_precio_cero_cuenta_como_precio():
    """Cero es un valor. Un aviso a $0 es raro, no es la ausencia de precio.

    Con `if descarte.get("precio")` este caso se leeria como institucional y
    el rechazo pasaria sin mirarse.
    """
    assert descarte_parecia_una_propiedad({"precio": 0, "tipo_ld": None,
                                           "fotos": 8})


def test_MUERDE_el_conteo_serializado_alcanza_sin_el_detalle():
    """El paquete del certificador no trae `_descartes`.

    Las claves con guion bajo no se serializan, asi que el registro que ve el
    triaje en el paquete tiene la cuenta y no el detalle. Si la regla
    dependiera solo del detalle, el camino del certificador —que es el que
    para las colas— caeria siempre en «sin evidencia» y nada habria cambiado.
    """
    corrida = {"descartadas_por_forma": 1, "detalles_obtenidos": 232,
               "descartes_con_senal": 0, "descartes_con_senal_ejemplos": []}
    assert paro_por_el_guardian_de_forma(corrida) is None


def test_el_conteo_serializado_tambien_hace_parar():
    corrida = {"descartadas_por_forma": 4, "detalles_obtenidos": 90,
               "descartes_con_senal": 2,
               "descartes_con_senal_ejemplos": ["https://x.com/p/9-casa"]}
    motivo = paro_por_el_guardian_de_forma(corrida)
    assert motivo is not None and "2 de 4" in motivo


def test_el_conteo_serializado_gana_sobre_el_detalle():
    """Si los dos estan, manda el que esta en los dos caminos.

    Que discrepen significaria que una de las dos lecturas quedo vieja; la
    que sobrevive a la serializacion es la que el triaje ve en produccion.
    """
    corrida = {"descartadas_por_forma": 1, "detalles_obtenidos": 10,
               "descartes_con_senal": 0, "descartes_con_senal_ejemplos": [],
               "_descartes": [{"source_url": "https://x/p/1", "precio": 1000}]}
    assert paro_por_el_guardian_de_forma(corrida) is None


def test_MUERDE_una_pagina_de_categoria_con_un_precio_no_es_sospechosa():
    """`arquitectura inmobiliaria` paro las dos colas por esto.

    Sus 9 rechazos son paginas de CATEGORIA —`ventas-locales`,
    `alquileres-monoambientes`, tituladas «3 dormitorios»— y una muestra un
    precio en el listado. Con el precio solo, eso alcanzaba para sospechar.

    Las nueve tienen exactamente UNA foto, y una pagina que no llega al piso
    de fotos no es publicable como propiedad por ningun camino: el guardian
    la rechaza por ahi, no por el precio.
    """
    categoria = {"source_url": "https://urbanorosario.com.ar/ventas-monoambientes",
                 "precio": 21400.0, "tipo_ld": None, "fotos": 1}
    assert not descarte_parecia_una_propiedad(categoria)
    corrida = {"descartadas_por_forma": 9, "detalles_obtenidos": 40,
               "_descartes": [categoria] + [institucional() for _ in range(8)]}
    assert paro_por_el_guardian_de_forma(corrida) is None


def test_MUERDE_el_afinado_no_apaga_el_caso_que_lo_justifica():
    """Las fichas de `alma di matteo` traian 8 fotos y precio.

    Si el piso de fotos apagara tambien ese caso, la regla dejaria de servir
    justo para lo que se construyo.
    """
    real = {"source_url": "https://www.almadimatteo.com.ar/lotes/Ranelagh/ranelagh.html",
            "precio": 130000.0, "tipo_ld": None, "fotos": 8}
    assert descarte_parecia_una_propiedad(real)
    corrida = {"descartadas_por_forma": 6, "detalles_obtenidos": 0,
               "_descartes": [real]}
    motivo = paro_por_el_guardian_de_forma(corrida)
    assert motivo is not None and "TENIAN precio o schema" in motivo


def test_un_schema_sin_fotos_tampoco_alcanza():
    """El piso de fotos vale igual para la otra senal fuerte."""
    assert not descarte_parecia_una_propiedad(
        {"precio": None, "tipo_ld": "Product", "fotos": 0})
    assert descarte_parecia_una_propiedad(
        {"precio": None, "tipo_ld": "Product", "fotos": 5})


def test_MUERDE_el_tope_absoluto_no_frena_un_3_por_ciento():
    """`brunetti`: 13 fichas de 428 sin `tipo_propiedad`, el 3,04 %.

    Con el tope en 10 eso paraba las dos colas. Re-medido sobre los 67 casos
    de `EXTRACTION_FAILED` del corpus, mover el tope de 10 a cualquier valor
    hasta 100 cambia exactamente este caso: es el porcentaje mas bajo de su
    banda, y los demas entre 10 y 30 fallos son 45 %, 75 %, 96 % y 100 %.

    Se quedo en 15 y no en 50 porque la decision de la manana fue deliberada
    en dejar `27 de 395` y `20 de 254` del lado de STOP, y subirlo mas los
    habria pisado sin evidencia nueva sobre ellos.
    """
    from scripts.defect_triage import (TOPE_DE_FICHAS_MENORES,
                                       TOPE_PORCENTUAL_MENOR)
    assert 13 <= TOPE_DE_FICHAS_MENORES
    assert 13 / 428 <= TOPE_PORCENTUAL_MENOR


def test_MUERDE_lo_grande_sigue_siendo_grande():
    """Los cuatro casos que el tope tiene que seguir frenando, con sus
    numeros reales. Si alguien sube el tope hasta taparlos, esto muerde."""
    from scripts.defect_triage import (TOPE_DE_FICHAS_MENORES,
                                       TOPE_PORCENTUAL_MENOR)
    for fallos, total in ((1206, 1213), (724, 724), (179, 502), (80, 159),
                          (27, 395), (20, 254)):
        menor = fallos <= TOPE_DE_FICHAS_MENORES and fallos / total <= TOPE_PORCENTUAL_MENOR
        assert not menor, f"{fallos} de {total} no puede ser menor"


def test_el_tope_absoluto_sigue_atrapando_dano_grande_con_porcentaje_chico():
    """Su unico proposito: 60 fichas perdidas en una agencia de 1.213 son el
    4,9 % —pasa el porcentual— y tienen que seguir parando."""
    from scripts.defect_triage import (TOPE_DE_FICHAS_MENORES,
                                       TOPE_PORCENTUAL_MENOR)
    fallos, total = 60, 1213  # 4,9 %: pasa el porcentual, lo frena el absoluto
    assert fallos / total <= TOPE_PORCENTUAL_MENOR
    assert fallos > TOPE_DE_FICHAS_MENORES

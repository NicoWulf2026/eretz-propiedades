#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Combinaciones que no pueden ser ciertas, y que por eso no se publican.

No es validacion de formato: es aritmetica de inmuebles. Un dormitorio ES un
ambiente, lo cubierto es parte de lo total, un lote no tiene banos y una
superficie de cero metros no es una superficie. Cuando los numeros dicen otra
cosa, alguno vino de donde no debia -casi siempre de las "propiedades
relacionadas" al pie de la misma pagina-.

Cuando dos valores se contradicen no se elige uno. No hay forma de saber cual
salio de la ficha y cual del vecino, y quedarse con el equivocado es peor que
quedarse sin ninguno: un dato ausente se ve, un dato incorrecto se publica.

Medido: el corpus generico pasaba de 7,01% de propiedades con al menos una
incoherencia a 0,00%; WordPress tenia 10,08%.

Modulo puro: no baja nada, no toca la base, y se puede probar entero.
"""
from __future__ import annotations

import re
from typing import Any

# Argentina entera cae adentro de este rectangulo. Una coordenada afuera no es
# una correccion posible: o es de otro pais o esta mal leida, y en los dos casos
# poner la propiedad en el mapa donde no esta es peor que no ponerla.
LAT_MIN, LAT_MAX = -56.0, -21.0
LON_MIN, LON_MAX = -74.0, -53.0

# Lo que aparece entre las imagenes de una ficha y no es una foto de la
# propiedad: el logo de la inmobiliaria, el cartel de "sin imagen" que el
# sitio pone cuando no hay fotos, y la miniatura de YouTube del video del
# tour, que es el poster del video y no una foto.
NO_ES_FOTO = re.compile(
    r"(logo|placeholder|avatar|icon|sprite|banner|whatsapp|favicon"
    r"|no[-_]?imagen|sin[-_]?imagen|no[-_]?image|nofoto|img\.youtube\.com)", re.I)

SUPERFICIES = ("superficie_total", "superficie_cubierta")
ATRIBUTOS_DE_VIVIENDA = ("dormitorios", "banos", "ambientes",
                         "superficie_cubierta")


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def revisar(p: dict) -> list[str]:
    """Corrige `p` en el lugar y devuelve que se descarto y por que."""
    fuera: list[str] = []

    for campo in SUPERFICIES:
        v = _num(p.get(campo))
        if v is not None and v <= 0:
            p[campo] = None
            fuera.append(f"{campo}_no_positiva")

    dorm, amb = _num(p.get("dormitorios")), _num(p.get("ambientes"))
    if dorm and amb and dorm > amb:
        p["dormitorios"] = p["ambientes"] = None
        fuera.append("dormitorios>ambientes")

    cub, tot = _num(p.get("superficie_cubierta")), _num(p.get("superficie_total"))
    if cub and tot and cub > tot:
        p["superficie_cubierta"] = p["superficie_total"] = None
        fuera.append("cubierta>total")

    if p.get("tipo_propiedad") == "terreno":
        for campo in ATRIBUTOS_DE_VIVIENDA:
            if p.get(campo):
                p[campo] = None
                fuera.append(f"{campo}_en_un_terreno")

    lat, lon = _num(p.get("latitud")), _num(p.get("longitud"))
    if lat is not None and lon is not None:
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            # El par se va junto: media coordenada no ubica nada.
            p["latitud"] = p["longitud"] = None
            fuera.append("coordenada_fuera_de_argentina")

    fotos = p.get("imagenes")
    if isinstance(fotos, list):
        limpias = [u for u in fotos if isinstance(u, str)
                   and not NO_ES_FOTO.search(u)]
        if len(limpias) != len(fotos):
            p["imagenes"] = limpias
            fuera.append("imagenes_que_no_son_fotos")

    precio = _num(p.get("precio"))
    if precio is not None and precio <= 0:
        p["precio"] = p["moneda"] = None
        fuera.append("precio_no_positivo")

    return fuera

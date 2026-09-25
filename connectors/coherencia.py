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

# Tipos donde una superficie de hectareas es el dato correcto y no un error.
TIPOS_DE_TIERRA = {"terreno", "lote", "campo", "chacra", "quinta", "fraccion",
                   "isla", "estancia", "loteo"}

# Diez hectareas. Ver la explicacion en `revisar`.
SUPERFICIE_EDIFICADA_MAXIMA = 100_000
ATRIBUTOS_DE_VIVIENDA = ("dormitorios", "banos", "ambientes",
                         "superficie_cubierta")


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# Un precio escrito con un solo digito repetido -111.111.111- es el relleno
# que pone el sitio cuando no quiere publicar el valor. Solo se descarta si
# ademas es absurdo para un inmueble: "USD 99.999" es un precio de venta
# perfectamente normal y no se toca. Hay 17 asi en 150.000 propiedades, y
# una de ellas es un dos ambientes a 1.111 millones de dolares.
RELLENO_USD = 10_000_000
RELLENO_ARS = 1_000_000_000


def _es_relleno(precio: float, moneda: Any) -> bool:
    digitos = str(int(precio))
    if len(digitos) < 6 or len(set(digitos)) != 1:
        return False
    tope = RELLENO_ARS if str(moneda).upper() == "ARS" else RELLENO_USD
    return precio >= tope


RE_COCHERA = re.compile(r"\b(?:cocheras?|garages?|estacionamientos?)\b")
# Cualquier mencion de ambientes o dormitorios -en cifras o en letras:
# «TRES AMBIENTE CON COCHERA»-, «con cochera», o un tipo edificado.
RE_DESCRIBE_VIVIENDA = re.compile(
    r"\bambientes?\b|\bamb\b|\bdormitorios?\b|\bdorm\b|\b\d+\s*(?:amb|dorm)|\bcon\s+cocheras?\b"
    r"|\b(?:semi\s*piso|semipiso|piso|departamento|depto|casa|chalet|duplex|triplex|ph"
    r"|monoambiente|galpon|local|oficina|complejo|edificio|quinta)\b")


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                   if not unicodedata.combining(c))


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

    # Una superficie enorme es normal en el campo y absurda en un
    # departamento. `aagaard.com.ar` publica `Terreno: 50000000 m2` en un dos
    # ambientes de 45 m2 cubiertos -cincuenta kilometros cuadrados- y otras dos
    # fichas dicen `Terreno: 50.0 Ha` y `180.0 Ha` sobre 45 y 180 metros
    # construidos. Son datos cargados mal en el backoffice de la inmobiliaria,
    # no una lectura nuestra: la ficha los muestra asi.
    #
    # No se corrige el valor. Que `180.0 Ha` sea probablemente `180 m2` es una
    # sospecha razonable y sigue siendo una invencion; se descarta y se anota.
    #
    # El tope se eligio con el corpus: entre los tipos edificados el maximo real
    # son 20.000 m2 de un departamento y el percentil 99 de `casa` es 8.700. Con
    # diez hectareas se descartan cuatro propiedades en 58.427.
    #
    # Sin tipo no se decide nada: un tipo desconocido puede ser un campo.
    tipo = str(p.get("tipo_propiedad") or "").lower()
    tot = _num(p.get("superficie_total"))
    if tot and tipo and tipo not in TIPOS_DE_TIERRA and tot > SUPERFICIE_EDIFICADA_MAXIMA:
        p["superficie_total"] = None
        fuera.append("superficie_total_absurda_para_el_tipo")

    # Una cochera no tiene dormitorios ni varios ambientes: 157 de 594 en los
    # paquetes del 25-09. Decide el titulo, que viaja en `p` como dato de
    # solo lectura: si dice cochera y no describe una vivienda sobran los
    # conteos (`farina` «Newbery 9192 – Cochera», 1 dormitorio de la meta de
    # Houzez); si describe una vivienda o no nombra tipo, sobra el tipo
    # (`berrueta` «3 AMBIENTES AL FRENTE»). Sin titulo no se decide.
    if (p.get("tipo_propiedad") == "cochera" and "titulo" in p
            and ((_num(p.get("dormitorios")) or 0) >= 1
                 or (_num(p.get("ambientes")) or 0) >= 2)):
        titulo = _sin_tildes(str(p.get("titulo") or ""))
        if RE_COCHERA.search(titulo) and not RE_DESCRIBE_VIVIENDA.search(titulo):
            for campo in ("dormitorios", "ambientes"):
                if p.get(campo):
                    p[campo] = None
                    fuera.append(f"{campo}_en_una_cochera")
        else:
            p["tipo_propiedad"] = None
            fuera.append("tipo_propiedad_cochera_con_dormitorios")

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
    if precio is not None and _es_relleno(precio, p.get("moneda")):
        p["precio"] = p["moneda"] = None
        fuera.append("precio_de_relleno")
    precio = _num(p.get("precio"))
    if precio is not None and precio <= 0:
        p["precio"] = p["moneda"] = None
        fuera.append("precio_no_positivo")

    return fuera

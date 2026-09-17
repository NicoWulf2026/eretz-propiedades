#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ranking TECNICO: que resultado responde mejor a lo que la persona pidio.

Separado a proposito del ranking comercial. Este no sabe quien paga ni quien
tiene contrato: ordena por lo que se puede defender mirando el dato. Mezclar
las dos cosas en una sola formula las vuelve imposibles de auditar por separado,
y despues nadie puede decir por que una propiedad salio primera.

**Lo que puntua, y por que.**

  coincidencia   lo que la persona escribio, encontrado en el titulo, el
                 barrio o el area. Un match en el titulo vale mas que uno
                 en la descripcion: el titulo lo escribio alguien para
                 describir la propiedad, la descripcion tambien menciona el
                 barrio de al lado
  ubicacion      una propiedad con localidad demostrada se puede ubicar; una
                 con area de nivel provincia, casi no. El nivel del area ES
                 la calidad de la ubicacion
  completitud    cuantos de los campos que una persona mira estan. No es
                 calidad de la propiedad: es cuanto se puede decir de ella
  imagenes       una ficha sin fotos se abre y se cierra. Las primeras pesan;
                 la vigesima no agrega nada
  conflicto      una propiedad en GEO_CONFLICT no se esconde -sigue siendo
                 real- pero no puede encabezar una busqueda por ubicacion

**Lo que NO puntua.** El precio. Ordenar por precio es una preferencia de la
persona, no una medida de calidad, y meterlo en el ranking le saca esa
decision.

No escribe en ninguna base.
"""
from __future__ import annotations

from typing import Any
import unicodedata

# Same Unicode semantics as filtering category Mn character-by-character,
# but translation runs in C. The finite table is built once, not per request.
_COMBINING_MARKS = dict.fromkeys(
    n for n in range(0x110000) if unicodedata.category(chr(n)) == 'Mn')

RANKING_VERSION = "eretz_ranking_tecnico_v1"

# Cuanto vale cada senal. Los numeros son relativos entre si y estan puestos
# para que ninguna sola gane: la coincidencia textual manda, pero una
# coincidencia sin ubicacion no le gana a una con ubicacion y la misma
# coincidencia.
PESO = {
    "titulo": 50.0,
    "area": 30.0,
    "barrio": 25.0,
    "descripcion": 10.0,
    "ubicacion": 20.0,
    "completitud": 15.0,
    "imagenes": 10.0,
}

# El nivel del area ES la calidad de la ubicacion.
CALIDAD_DE_UBICACION = {"LOCALIDAD": 1.0, "MUNICIPIO": 0.6,
                        "DEPARTAMENTO": 0.3, "PROVINCIA": 0.1, "SIN_AREA": 0.0}

# Los campos que una persona mira en una tarjeta. No son todos los campos:
# `superficie_total` esta en el 26,5 % y castigar por ella ordenaria por
# suerte del scraping y no por utilidad.
CAMPOS_VISIBLES = ("titulo", "precio", "operacion", "tipo_propiedad",
                   "dormitorios", "superficie_cubierta")

# Mas de esto no mejora la ficha. La vigesima foto no cambia una decision.
FOTOS_UTILES = 6


def _plegar(texto: Any) -> str:
    if not isinstance(texto, str):
        return ""
    if texto.isascii():
        return texto.casefold()
    sin = unicodedata.normalize("NFD", texto).translate(_COMBINING_MARKS)
    return sin.casefold()


def coincidencia(propiedad: dict[str, Any], consulta: str) -> float:
    """Cuanto de lo que la persona escribio aparece, y donde."""
    q = _plegar(consulta).strip()
    if not q:
        return 0.0
    geo = propiedad.get("geo") or {}
    lugares = (
        ("titulo", propiedad.get("titulo")),
        ("area", (geo.get("area_busqueda") or {}).get("nombre")),
        ("barrio", (geo.get("barrio") or {}).get("nombre")),
        ("descripcion", propiedad.get("descripcion")),
    )
    puntos = 0.0
    for clave, valor in lugares:
        texto = _plegar(valor)
        if not texto:
            continue
        if q in texto:
            # Un match exacto del campo entero vale mas que uno adentro de un
            # parrafo: "Rosario" como area es la ciudad; "Rosario" adentro de
            # una descripcion puede ser el nombre de la calle.
            exacto = 1.0 if texto.strip() == q else 0.6
            puntos += PESO[clave] * exacto
    return puntos


def calidad_de_ubicacion(propiedad: dict[str, Any]) -> float:
    geo = propiedad.get("geo") or {}
    nivel = (geo.get("area_busqueda") or {}).get("nivel") or "SIN_AREA"
    base = CALIDAD_DE_UBICACION.get(nivel, 0.0)
    # Un conflicto entre la coordenada y lo que publico la fuente no esconde
    # la propiedad, pero tampoco puede encabezar una busqueda por ubicacion:
    # una de las dos ubicaciones esta mal.
    if geo.get("estado") == "GEO_CONFLICT":
        base *= 0.5
    return base


def completitud(propiedad: dict[str, Any]) -> float:
    """Cuanto se puede DECIR de la propiedad, no cuan buena es."""
    presentes = sum(1 for campo in CAMPOS_VISIBLES
                    if propiedad.get(campo) not in (None, "", 0, []))
    return presentes / len(CAMPOS_VISIBLES)


def fotos(propiedad: dict[str, Any]) -> float:
    cuantas = len(propiedad.get("imagenes") or [])
    return min(cuantas, FOTOS_UTILES) / FOTOS_UTILES


def puntaje(propiedad: dict[str, Any], consulta: str = "") -> dict[str, Any]:
    """El puntaje y sus partes.

    Se devuelven las partes y no solo el total porque un ranking que no se
    puede explicar no se puede corregir: cuando alguien pregunte por que una
    propiedad salio primera, la respuesta tiene que estar en el dato.
    """
    partes = {
        "coincidencia": coincidencia(propiedad, consulta),
        "ubicacion": PESO["ubicacion"] * calidad_de_ubicacion(propiedad),
        "completitud": PESO["completitud"] * completitud(propiedad),
        "imagenes": PESO["imagenes"] * fotos(propiedad),
    }
    return {"ranking_version": RANKING_VERSION,
            "total": round(sum(partes.values()), 3),
            "partes": {k: round(v, 3) for k, v in partes.items()}}


def ordenar(propiedades: list[dict[str, Any]],
            consulta: str = "") -> list[dict[str, Any]]:
    """Ordena y deja el puntaje adentro de cada fila.

    El desempate final es por `id` y no por orden de llegada: sin un desempate
    estable, dos consultas identicas devuelven ordenes distintos y la
    paginacion repite o saltea filas.
    """
    con_puntaje = []
    for propiedad in propiedades:
        fila = dict(propiedad)
        fila["ranking"] = puntaje(propiedad, consulta)
        con_puntaje.append(fila)
    con_puntaje.sort(key=lambda f: (-f["ranking"]["total"], str(f.get("id"))))
    return con_puntaje

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que es una propiedad publicable de ERETZ, y donde puede aparecer.

La regla que ordena todo esto: **una propiedad real incompleta sobrevive**. Que
falte un dato no la vuelve invalida; le quita ALCANCE. Por eso el contrato no
devuelve un si/no sino el conjunto de lugares donde esa propiedad puede
mostrarse sin mentir.

La diferencia no es teorica. Con un contrato binario, exigir `operacion`
-ausente en 10.916 de las 58.427 candidatas- borraria del portal 10.916
propiedades que existen, tienen titulo, precio, fotos y direccion. Con alcances,
esas 10.916 siguen teniendo ficha propia y siguen apareciendo en el listado
general; lo unico que no pueden es aparecer en el filtro "alquiler", porque
nadie sabe si lo son.

Cuatro estados por campo, que NO son lo mismo:

  EXTRACTED               el dato esta
  SOURCE_NOT_PROVIDED     la fuente no lo publica; no hay nada que arreglar
  REJECTED_BY_VALIDATION  vino y no se lo pudo creer -un precio sin moneda, una
                          coordenada fuera del pais, dormitorios > ambientes-
  EXTRACTION_FAILED       la fuente lo publica y nosotros no lo leimos. Es el
                          unico que es un defecto NUESTRO

**Limite honesto de este modulo.** Sobre la pre-ingesta se pueden demostrar
`EXTRACTED` y `REJECTED_BY_VALIDATION`, porque el rechazo queda escrito en
`problemas` y en `atributos_descartados`. Separar `SOURCE_NOT_PROVIDED` de
`EXTRACTION_FAILED` exige saber si la fuente publicaba el campo, y esa senal
vive en los paquetes de certificacion, no en la fila. Mientras no este, se
devuelve `AUSENTE_SIN_DIAGNOSTICO` en vez de adivinar cual de los dos es.
Marcar todo como `SOURCE_NOT_PROVIDED` seria comodo y esconderia justamente los
defectos que hay que encontrar.

No escribe en ninguna base.
"""
from __future__ import annotations

from typing import Any

CONTRATO_VERSION = "property_contract_v1"

EXTRACTED = "EXTRACTED"
SOURCE_NOT_PROVIDED = "SOURCE_NOT_PROVIDED"
REJECTED_BY_VALIDATION = "REJECTED_BY_VALIDATION"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
AUSENTE_SIN_DIAGNOSTICO = "AUSENTE_SIN_DIAGNOSTICO"

# --------------------------------------------------------------------------
# Clases de campo
# --------------------------------------------------------------------------
# Sin esto no hay propiedad: no se puede mostrar, ni deduplicar, ni volver a
# la fuente. Es lo UNICO cuya ausencia descarta.
IDENTIDAD = ("source_url", "hash_dedup", "canonical_agency_id")

# Algo que mostrarle a una persona. Alcanza con uno.
EXHIBICION = ("titulo", "descripcion")

# Deciden en que filtros puede aparecer. Nunca si existe.
BUSQUEDA = ("operacion", "tipo_propiedad", "precio", "moneda", "ciudad",
            "provincia", "latitud", "longitud")

# Todo lo demas mejora la ficha y no condiciona nada.
ENRIQUECIMIENTO = ("ambientes", "dormitorios", "banos", "superficie_total",
                   "superficie_cubierta", "direccion", "barrio", "imagenes")

TODOS = IDENTIDAD + EXHIBICION + BUSQUEDA + ENRIQUECIMIENTO

# --------------------------------------------------------------------------
# Alcances
# --------------------------------------------------------------------------
FICHA = "FICHA"                      # su propia pagina
LISTADO = "LISTADO"                  # el listado general
FILTRO_OPERACION = "FILTRO_OPERACION"
FILTRO_TIPO = "FILTRO_TIPO"
FILTRO_PRECIO = "FILTRO_PRECIO"
FILTRO_CIUDAD = "FILTRO_CIUDAD"
MAPA = "MAPA"

# Que rechazo de validacion afecta a que campo. La cadena la escribe el
# guardian de coherencia del connector y aca solo se lee.
RECHAZOS = {
    "precio sin moneda": ("moneda",),
    "latitud fuera de Argentina": ("latitud", "longitud"),
    "longitud fuera de Argentina": ("latitud", "longitud"),
}
DESCARTES = {
    "dormitorios>ambientes": ("dormitorios", "ambientes"),
    "cubierta>total": ("superficie_cubierta", "superficie_total"),
}


def _presente(valor: Any) -> bool:
    return valor not in (None, "", [], {}, 0)


def rechazos_de(fila: dict[str, Any]) -> dict[str, str]:
    """Que campo quedo vacio POR VALIDACION, y por que motivo."""
    afectados: dict[str, str] = {}
    for motivo in (fila.get("problemas") or {}):
        for campo in RECHAZOS.get(motivo, ()):
            afectados[campo] = motivo
    descartado = (fila.get("extra") or {}).get("atributos_descartados")
    if isinstance(descartado, str):
        for campo in DESCARTES.get(descartado, ()):
            afectados.setdefault(campo, descartado)
    return afectados


def estado_de_campo(fila: dict[str, Any], campo: str,
                    fuente_lo_publica: bool | None = None) -> str:
    """El estado de un campo, con la evidencia que haya.

    `fuente_lo_publica` viene de la certificacion cuando existe. Sin ella no se
    puede separar `SOURCE_NOT_PROVIDED` de `EXTRACTION_FAILED`, y se dice.
    """
    if _presente(fila.get(campo)):
        return EXTRACTED
    rechazado = rechazos_de(fila).get(campo)
    if rechazado:
        return REJECTED_BY_VALIDATION
    if fuente_lo_publica is True:
        return EXTRACTION_FAILED
    if fuente_lo_publica is False:
        return SOURCE_NOT_PROVIDED
    return AUSENTE_SIN_DIAGNOSTICO


def alcances(fila: dict[str, Any]) -> tuple[set[str], list[str]]:
    """Donde puede aparecer esta propiedad, y por que no en el resto."""
    razones: list[str] = []

    faltan_identidad = [c for c in IDENTIDAD if not _presente(fila.get(c))]
    if faltan_identidad:
        # Lo unico que descarta. Sin url ni identidad no hay a que volver.
        return set(), [f"sin identidad: falta {', '.join(faltan_identidad)}"]

    if not any(_presente(fila.get(c)) for c in EXHIBICION):
        return set(), ["sin titulo ni descripcion: no hay nada que mostrar"]

    permitidos = {FICHA, LISTADO}

    if _presente(fila.get("operacion")):
        permitidos.add(FILTRO_OPERACION)
    else:
        razones.append("sin operacion: no entra al filtro venta/alquiler")

    if _presente(fila.get("tipo_propiedad")):
        permitidos.add(FILTRO_TIPO)
    else:
        razones.append("sin tipo: no entra al filtro casa/departamento")

    if _presente(fila.get("precio")) and _presente(fila.get("moneda")):
        permitidos.add(FILTRO_PRECIO)
    else:
        # Un precio sin moneda no es un precio: 90.000 puede ser dolares o
        # pesos y la diferencia es de un orden de magnitud.
        razones.append("sin precio con moneda: no entra al filtro por precio")

    if _presente(fila.get("ciudad")):
        permitidos.add(FILTRO_CIUDAD)
    else:
        razones.append("sin ciudad canonica: no entra al filtro por ciudad")

    if _presente(fila.get("latitud")) and _presente(fila.get("longitud")):
        permitidos.add(MAPA)
    else:
        razones.append("sin coordenadas: no se puede ubicar en el mapa")

    return permitidos, razones


def evaluar(fila: dict[str, Any],
            fuente: dict[str, bool] | None = None) -> dict[str, Any]:
    """El veredicto completo del contrato para una propiedad."""
    fuente = fuente or {}
    permitidos, razones = alcances(fila)
    estados = {c: estado_de_campo(fila, c, fuente.get(c)) for c in TODOS}
    return {
        "contrato_version": CONTRATO_VERSION,
        "publicable": bool(permitidos),
        "alcances": sorted(permitidos),
        "razones_de_exclusion": razones,
        "estados_de_campo": estados,
        "campos_rechazados_por_validacion": sorted(
            c for c, e in estados.items() if e == REJECTED_BY_VALIDATION),
        "campos_que_fallo_la_extraccion": sorted(
            c for c, e in estados.items() if e == EXTRACTION_FAILED),
        "database_writes": 0,
    }

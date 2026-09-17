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

import re
import math
from typing import Any

from connectors.geografia import CAJA_ARGENTINA, geografia_publicable

CONTRATO_VERSION = "property_contract_v4"

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
# v2: `FILTRO_CIUDAD` afirmaba tener una ciudad cuando lo unico que habia era
# texto en el campo `ciudad` -un barrio contaba igual que una localidad
# censal-. Se parte en dos alcances que dicen cosas distintas:
FILTRO_LOCALIDAD = "FILTRO_LOCALIDAD"    # localidad censal DEMOSTRADA
AREA_BUSQUEDA = "AREA_BUSQUEDA"          # se la puede encontrar por su area
MAPA = "MAPA"

# Que rechazo de validacion afecta a que campo. La cadena la escribe el
# guardian de coherencia del connector y aca solo se lee.
RECHAZOS = {
    "precio sin moneda": ("moneda",),
    "latitud fuera de Argentina": ("latitud", "longitud"),
    "longitud fuera de Argentina": ("latitud", "longitud"),
}
# `dormitorios_en_un_terreno`, `superficie_cubierta_en_un_terreno`: el motivo
# nombra el campo que se descarto. Se lee del motivo en vez de enumerarlos,
# porque la lista de tipos la decide el guardian y no este contrato.
RE_DESCARTE_POR_TIPO = re.compile(r"^([a-z_]+?)_en_un_[a-z_]+$")

DESCARTES = {
    "dormitorios>ambientes": ("dormitorios", "ambientes"),
    "cubierta>total": ("superficie_cubierta", "superficie_total"),
}


# Un lote no tiene dormitorios, y no tenerlos no es que no los hayamos leido.
#
# La senal de "la fuente publica este campo" se agrega POR AGENCIA: si una
# inmobiliaria publica dormitorios en sus departamentos, la senal dice que los
# publica, y despues cada terreno sin dormitorios se contaba como defecto
# NUESTRO. Eran 2.969 de 11.875 -uno de cada cuatro-, y nos habrian mandado a
# buscar un bug de parser que no existe.
TIPOS_SIN_HABITACIONES = ("terreno", "lote", "fraccion", "campo", "chacra")
CAMPOS_DE_VIVIENDA = ("ambientes", "dormitorios", "banos", "superficie_cubierta")

# Estos SI pueden tener banos y ambientes -un local con dos ambientes y un
# toilette es corriente-, pero no dormitorios.
TIPOS_SIN_DORMITORIOS = ("cochera", "galpon", "deposito", "local", "oficina")


def campo_ajeno_al_tipo(tipo: Any, campo: str) -> bool:
    """Si este campo NO EXISTE para esta clase de propiedad.

    Conservador a proposito: solo lo que es imposible, no lo que es raro. Un
    local puede tener ambientes y bano; un terreno no puede tener ninguno de
    los cuatro.
    """
    t = (tipo or "").strip().lower()
    if not t:
        return False
    if any(x in t for x in TIPOS_SIN_HABITACIONES):
        return campo in CAMPOS_DE_VIVIENDA
    if any(x in t for x in TIPOS_SIN_DORMITORIOS):
        return campo == "dormitorios"
    return False


def _presente(valor: Any) -> bool:
    # This boundary sees normalized data. Placeholder rejection belongs to
    # source-specific normalization; accepted numeric zero is not missing.
    return valor is not None and valor != "" and valor != [] and valor != {}


def _coordenadas_validas(lat: Any, lon: Any) -> bool:
    if isinstance(lat, bool) or isinstance(lon, bool):
        return False
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError, OverflowError):
        return False
    south, north, west, east = CAJA_ARGENTINA
    return (math.isfinite(lat) and math.isfinite(lon)
            and south <= lat <= north and west <= lon <= east)


def rechazos_de(fila: dict[str, Any]) -> dict[str, str]:
    """Que campo quedo vacio POR VALIDACION, y por que motivo."""
    afectados: dict[str, str] = {}
    for motivo in (fila.get("problemas") or {}):
        for campo in RECHAZOS.get(motivo, ()):
            afectados[campo] = motivo
    descartado = (fila.get("extra") or {}).get("atributos_descartados")
    if isinstance(descartado, str):
        # El connector anota varios descartes separados por coma, y algunos
        # nombran el campo adentro del motivo: `dormitorios_en_un_terreno`.
        # Leer solo la tabla fija dejaba esos como si no los hubieramos
        # extraido, cuando el guardian de coherencia VIO el valor y lo
        # rechazo. Son cosas distintas: una es un defecto nuestro y la otra es
        # la validacion haciendo su trabajo.
        for motivo in descartado.split(","):
            motivo = motivo.strip()
            if not motivo:
                continue
            for campo in DESCARTES.get(motivo, ()):
                afectados.setdefault(campo, motivo)
            propio = RE_DESCARTE_POR_TIPO.match(motivo)
            if propio:
                afectados.setdefault(propio.group(1), motivo)
    return afectados


# Como se lee el resultado del resolver de geografia para el campo `ciudad`.
# Sin esto, el mismo artefacto decia a la vez "no extrajimos la ciudad" y
# "localidad canonica: Rosario" de la misma propiedad.
GEO_A_ESTADO = {
    # La validacion funciono: vio un nombre y se nego a afirmarlo.
    "CONTRADICTED_BY_COORDINATES": REJECTED_BY_VALIDATION,
    "AMBIGUOUS": REJECTED_BY_VALIDATION,
    # La fuente publico un barrio, no una ciudad. No fallamos en leer nada.
    "NOT_FOUND": SOURCE_NOT_PROVIDED,
    "SIN_UBICACION": SOURCE_NOT_PROVIDED,
}


def estado_de_campo(fila: dict[str, Any], campo: str,
                    fuente_lo_publica: bool | None = None,
                    geo: dict[str, Any] | None = None) -> str:
    """El estado de un campo, con la evidencia que haya.

    `fuente_lo_publica` viene de la certificacion cuando existe. Sin ella no se
    puede separar `SOURCE_NOT_PROVIDED` de `EXTRACTION_FAILED`, y se dice.

    Para `ciudad` manda el RESOLVER y no la columna cruda. Tokko publica la
    ubicacion en un solo campo, que cae en `barrio`: "Cordoba Capital" es una
    ciudad y esta ahi. Mirando la columna `ciudad` vacia, el gate reportaba
    1.092 propiedades como ciudad no extraida cuando no habia nada que leer en
    ese campo, y al mismo tiempo la cobertura decia que la localidad estaba
    resuelta.
    """
    if campo in ('ciudad', 'provincia') and (geo or {}).get('estado_geografico') == 'GEO_CONFLICT':
        return REJECTED_BY_VALIDATION
    if campo == "ciudad" and geo is not None:
        if _presente(geo.get("localidad_canonica")):
            return EXTRACTED
        return GEO_A_ESTADO.get(geo.get("match"), SOURCE_NOT_PROVIDED)
    if _presente(fila.get(campo)):
        return EXTRACTED
    rechazado = rechazos_de(fila).get(campo)
    if rechazado:
        return REJECTED_BY_VALIDATION
    # El tipo manda sobre la senal de la agencia: que la inmobiliaria publique
    # dormitorios en sus departamentos no hace que su terreno tenga.
    if campo_ajeno_al_tipo(fila.get("tipo_propiedad"), campo):
        return SOURCE_NOT_PROVIDED
    if fuente_lo_publica is True:
        return EXTRACTION_FAILED
    if fuente_lo_publica is False:
        return SOURCE_NOT_PROVIDED
    return AUSENTE_SIN_DIAGNOSTICO


def alcances(fila: dict[str, Any],
             geo: dict[str, Any] | None = None) -> tuple[set[str], list[str]]:
    """Donde puede aparecer esta propiedad, y por que no en el resto.

    `geo` trae las dimensiones canonicas ya resueltas y separadas por nivel.
    Sin el, la localidad no se afirma: no afirmarla es la respuesta correcta
    cuando no hay con que demostrarla."""
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

    # La localidad solo se afirma con evidencia canonica corroborada. Que la
    # fuente haya escrito algo en el campo `ciudad` no alcanza: `Villa del
    # Parque` es un barrio de CABA y resolvia a una localidad de Rio Negro.
    geo = geografia_publicable(geo)
    if _presente(geo.get("localidad_canonica")):
        permitidos.add(FILTRO_LOCALIDAD)
    else:
        razones.append("sin localidad canonica demostrada: no entra al filtro "
                       "por localidad")

    # El area de busqueda permite encontrarla sin afirmar que es su ciudad. El
    # nivel viaja con el valor; sin nivel, un municipio se lee como ciudad.
    area = (geo.get("area_busqueda") or {}) if isinstance(geo, dict) else {}
    if _presente(area.get("nombre")) and area.get("nivel") not in (None, "SIN_AREA"):
        permitidos.add(AREA_BUSQUEDA)
    else:
        razones.append("sin area de busqueda: no se la puede encontrar por "
                       "ubicacion")

    if (geo.get('estado_geografico') != 'GEO_CONFLICT'
            and _coordenadas_validas(fila.get("latitud"), fila.get("longitud"))):
        permitidos.add(MAPA)
    else:
        razones.append("sin coordenadas: no se puede ubicar en el mapa")

    return permitidos, razones


def evaluar(fila: dict[str, Any],
            fuente: dict[str, bool] | None = None,
            geo: dict[str, Any] | None = None) -> dict[str, Any]:
    """El veredicto completo del contrato para una propiedad."""
    fuente = fuente or {}
    permitidos, razones = alcances(fila, geo)
    estados = {c: estado_de_campo(fila, c, fuente.get(c), geo) for c in TODOS}
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

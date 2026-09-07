#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que eventos emite el frontend, y que se puede responder con ellos.

Un contrato de analytics no es una lista de nombres: es la lista de PREGUNTAS
que se van a poder contestar. Si los eventos no alcanzan para responder una
pregunta que importa, hay que saberlo ahora y no dentro de tres meses cuando
alguien la haga.

Las preguntas que este contrato responde:

  que busca la gente y no encuentra     `busqueda` con `resultados: 0`
  que filtros se usan de verdad         `filtro_aplicado`
  si el area de busqueda confunde       `area_usada` con su NIVEL
  que propiedades se miran              `ficha_vista`
  cuales generan contacto               `contacto`
  donde se rompe                        `error`

**El nivel del area viaja en el evento.** Es la unica forma de saber despues si
mostrar un municipio donde la gente espera una ciudad le sirvio o la confundio.
Sin ese dato, la pregunta no se puede contestar y la decision se toma por
intuicion.

**Nada de datos personales.** Ni IP, ni user agent, ni texto libre que la
persona haya escrito en un formulario de contacto. La consulta de busqueda SI
se guarda -es la pregunta central del producto- pero se corta a 120 caracteres:
nadie busca una casa con un parrafo, y un campo largo es donde termina pegado
un correo electronico.

Este modulo DEFINE el contrato y valida eventos. No los almacena: donde se
guardan es una decision de infraestructura que todavia no se tomo.
"""
from __future__ import annotations

import re
from typing import Any

ANALYTICS_VERSION = "eretz_analytics_v1"

LARGO_DE_CONSULTA = 120

# Lo que cada evento tiene que traer. Un evento al que le falta un campo
# obligatorio no se guarda a medias: se rechaza y se cuenta, porque un dataset
# con huecos silenciosos miente mas que uno vacio.
EVENTOS: dict[str, dict[str, Any]] = {
    "busqueda": {
        "obligatorios": ("consulta", "resultados"),
        "opcionales": ("area_nombre", "area_nivel", "filtros"),
        "responde": "que busca la gente, y sobre todo que busca y no encuentra",
    },
    "filtro_aplicado": {
        "obligatorios": ("filtro", "valor"),
        "opcionales": ("resultados",),
        "responde": "que filtros se usan de verdad y cuales sobran",
    },
    "area_usada": {
        "obligatorios": ("area_nombre", "area_nivel"),
        "opcionales": ("resultados",),
        "responde": "si mostrar un municipio donde la gente espera una ciudad "
                    "le sirvio o la confundio",
    },
    "listado_visto": {
        "obligatorios": ("resultados", "pagina"),
        "opcionales": ("orden",),
        "responde": "hasta que pagina llega la gente",
    },
    "ficha_vista": {
        "obligatorios": ("propiedad_id",),
        "opcionales": ("posicion_en_listado", "origen"),
        "responde": "que propiedades se miran, y desde donde se llega",
    },
    "contacto": {
        "obligatorios": ("propiedad_id", "medio"),
        "opcionales": ("agencia_id",),
        "responde": "cuales generan contacto: la unica metrica que le importa "
                    "a una inmobiliaria",
    },
    "sin_resultados": {
        "obligatorios": ("consulta",),
        "opcionales": ("filtros",),
        "responde": "el catalogo que falta, dicho por quien lo busco",
    },
    "error": {
        "obligatorios": ("donde", "clase"),
        "opcionales": ("estado_http",),
        "responde": "donde se rompe, sin el detalle que pueda traer datos de "
                    "la persona",
    },
}

# Campos que NUNCA se aceptan, aunque el frontend los mande por error. La lista
# es explicita a proposito: es mas facil de auditar que una regla.
PROHIBIDOS = ("ip", "user_agent", "email", "correo", "telefono", "nombre",
              "apellido", "mensaje", "direccion_ip", "cookie", "session_id")

RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
RE_TELEFONO = re.compile(r"(?:\+?54)?[\s-]?(?:\d[\s-]?){8,}")


def limpiar_consulta(texto: Any) -> str:
    """La consulta, cortada y sin lo que no deberia haber llegado.

    Nadie busca una casa con un parrafo. Un campo largo es donde termina
    pegado un correo electronico, y una vez guardado ya es un dato personal
    que hay que custodiar.
    """
    if not isinstance(texto, str):
        return ""
    sin_correo = RE_CORREO.sub(" ", texto)
    sin_telefono = RE_TELEFONO.sub(" ", sin_correo)
    return " ".join(sin_telefono.split())[:LARGO_DE_CONSULTA]


def validar(evento: dict[str, Any]) -> tuple[bool, list[str]]:
    """Si el evento se puede guardar, y si no, por que no."""
    problemas: list[str] = []
    nombre = evento.get("evento")
    definicion = EVENTOS.get(nombre or "")
    if not definicion:
        return False, [f"evento desconocido: {nombre!r}"]

    for campo in definicion["obligatorios"]:
        if evento.get(campo) in (None, ""):
            problemas.append(f"falta el campo obligatorio '{campo}'")

    for campo in evento:
        if campo.lower() in PROHIBIDOS:
            problemas.append(f"campo prohibido: '{campo}'")

    permitidos = ({"evento", "cuando"} | set(definicion["obligatorios"])
                  | set(definicion["opcionales"]))
    for campo in evento:
        if campo not in permitidos and campo.lower() not in PROHIBIDOS:
            problemas.append(f"campo no declarado en el contrato: '{campo}'")

    # El nivel del area es obligatorio donde el area aparece: sin el, la
    # pregunta que este evento existe para responder no se puede contestar.
    if evento.get("area_nombre") and not evento.get("area_nivel"):
        problemas.append("`area_nombre` sin `area_nivel`: el nivel es lo que "
                         "distingue una ciudad de un municipio")
    return not problemas, problemas


def normalizar(evento: dict[str, Any]) -> dict[str, Any]:
    """El evento listo para guardar. Nunca inventa campos que no vinieron."""
    limpio = {k: v for k, v in evento.items() if k.lower() not in PROHIBIDOS}
    if "consulta" in limpio:
        limpio["consulta"] = limpiar_consulta(limpio["consulta"])
    limpio["analytics_version"] = ANALYTICS_VERSION
    return limpio

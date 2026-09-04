#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que hacer ante un `NEEDS_FIX`: parar la cola o anotarlo y seguir.

Parar en cada defecto da maxima correccion y cuesta semanas de cola detenida.
Seguir siempre es rapido y certifica agencias con un defecto conocido encima.
Ninguna de las dos es la respuesta: **lo que decide es el RADIO del defecto**.

Un parser que no lee `superficie` en una estrategia que comparten 343
inmobiliarias no puede seguir corriendo: cada agencia que certifique despues
hereda el mismo error. Un sitio que anduvo lento media hora afecta a una sola
inmobiliaria y no justifica detener 758.

**La asimetria es deliberada: para clasificar algo como local hace falta
evidencia POSITIVA de que su causa es externa o acotada. Sin esa evidencia se
para.** No alcanza con que el defecto "parezca" local; no encontrar razones
para parar no es lo mismo que tener razones para seguir. Un defecto compartido
que se toma por local certifica mal a cientos de agencias, y un defecto local
que se toma por compartido cuesta una parada.

El paquete NUNCA queda como certificado. Con `CONTINUE` sigue siendo
`NEEDS_FIX` y entra a `AGENCY_DEFECT_QUEUE.jsonl` con su clasificacion y su
evidencia, pendiente de resolucion y recertificacion.

No escribe en ninguna base.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

TRIAGE_VERSION = "defect_triage_v1"

STOP = "STOP"
CONTINUE = "CONTINUE"

# Radios, de mayor a menor. El nombre dice a cuantas agencias puede alcanzar.
RADIO_COMPARTIDO = "COMPARTIDO"      # base, runner, certifier, geografia
RADIO_FAMILIA = "FAMILIA"            # un connector entero o generic/common
RADIO_ESTRATEGIA = "ESTRATEGIA"      # una estrategia de generico
RADIO_AGENCIA = "AGENCIA"            # esta inmobiliaria y ninguna otra

# Clases de error del descargador que hablan del SITIO, no de nosotros.
CLASES_EXTERNAS = ("ErrorTransitorio", "Bloqueado", "TimeoutError",
                   "URLError", "HTTPError", "ConnectionResetError",
                   "IncompleteRead", "socket.timeout")


def _corridas(resultado: dict[str, Any]) -> list[dict[str, Any]]:
    return [resultado.get(nombre) or {} for nombre in ("run1", "run2")]


def _campos_con_extraccion_fallida(resultado: dict[str, Any]) -> list[str]:
    cobertura = resultado.get("field_coverage") or {}
    return sorted(campo for campo, dato in cobertura.items()
                  if isinstance(dato, dict)
                  and dato.get("state") == "EXTRACTION_FAILED")


def _errores_externos(resultado: dict[str, Any]) -> dict[str, int]:
    """Errores del descargador, agrupados, que apuntan al sitio y no al parser."""
    fuera: dict[str, int] = {}
    for corrida in _corridas(resultado):
        for clave, cuantos in (corrida.get("errores_por_etapa") or {}).items():
            if any(clase in clave for clase in CLASES_EXTERNAS):
                fuera[clave] = fuera.get(clave, 0) + int(cuantos)
    return fuera


def firma(resultado: dict[str, Any], componente: str) -> str:
    """Identifica el PATRON del defecto, no la inmobiliaria.

    Dos defectos con la misma firma son el mismo problema apareciendo dos
    veces, y eso es motivo de corte por lote aunque cada uno se haya
    clasificado como local.
    """
    partes = [
        resultado.get("connector") or "",
        resultado.get("connector_strategy") or "",
        componente,
        "|".join(sorted(resultado.get("reasons") or [])),
        "|".join(_campos_con_extraccion_fallida(resultado)),
    ]
    return hashlib.sha256("::".join(partes).encode("utf-8")).hexdigest()[:12]


def clasificar(resultado: dict[str, Any]) -> dict[str, Any]:
    """STOP o CONTINUE, con la evidencia que lo justifica."""
    razones = list(resultado.get("reasons") or [])
    comparacion = resultado.get("comparison") or {}
    corridas = _corridas(resultado)
    auditoria = resultado.get("enumeration_audit") or {}
    revision = list(auditoria.get("review_reasons") or [])

    fallidos = _campos_con_extraccion_fallida(resultado)
    externos = _errores_externos(resultado)

    # ---------------- STOP: evidencia de radio transversal ----------------
    if fallidos:
        # La fuente publica el campo y no lo leimos. El que lee es el parser, y
        # el parser lo comparten todas las agencias de la familia.
        return _veredicto(
            STOP, resultado, "extraccion_transversal_de_atributos",
            RADIO_FAMILIA,
            f"la fuente publica {', '.join(fallidos)} y la extraccion fallo; "
            f"quien lee esos campos es codigo compartido")

    if comparacion.get("identity_collisions"):
        # `hash_dedup` se calcula en `connectors/base.py`.
        return _veredicto(
            STOP, resultado, "shared/base", RADIO_COMPARTIDO,
            f"{comparacion['identity_collisions']} colisiones de identidad; "
            f"el hash se calcula en codigo compartido")

    for corrida in corridas:
        if corrida.get("descartadas_por_forma"):
            return _veredicto(
                STOP, resultado, "guardian_de_forma_compartido", RADIO_FAMILIA,
                f"{corrida['descartadas_por_forma']} fichas descartadas por el "
                f"guardian de forma, que es compartido")
        if corrida.get("fichas_sin_contenido"):
            return _veredicto(
                STOP, resultado, "lectura_de_ficha_compartida", RADIO_FAMILIA,
                f"{corrida['fichas_sin_contenido']} fichas sin contenido: la "
                f"pagina respondio y no se pudo leer")
        if corrida.get("paginacion_interrumpida"):
            return _veredicto(
                STOP, resultado, "enumeracion_compartida", RADIO_FAMILIA,
                "la paginacion se interrumpio: la enumeracion es compartida")
        if corrida.get("imagenes_compartidas_descartadas"):
            return _veredicto(
                STOP, resultado, "imagenes_compartidas", RADIO_FAMILIA,
                f"{corrida['imagenes_compartidas_descartadas']} imagenes "
                f"compartidas descartadas; la regla es compartida")

    if "COLLAPSE_GT_80_PERCENT" in revision:
        return _veredicto(
            STOP, resultado, "perdida_sistematica_de_inventario",
            RADIO_FAMILIA,
            "el inventario colapso mas del 80 %: perdida sistematica")

    if resultado.get("status") == "RUNNER_ERROR":
        return _veredicto(
            STOP, resultado, "shared/runner", RADIO_COMPARTIDO,
            "el runner se cayo; hasta saber por que no se puede acotar")

    # ---------------- CONTINUE: evidencia positiva de radio acotado -------
    inventarios_distintos = any(
        "inventories differ" in r or "not idempotent" in r for r in razones)
    detalles_fallidos = sum(int(c.get("detalles_fallidos") or 0)
                            for c in corridas)

    if inventarios_distintos and detalles_fallidos and externos:
        return _veredicto(
            CONTINUE, resultado, "sitio_externo", RADIO_AGENCIA,
            f"{detalles_fallidos} detalles fallaron con errores de red o del "
            f"servidor ({', '.join(sorted(externos))}); el catalogo enumero "
            f"igual en las dos corridas")

    estados = [c.get("estado") for c in corridas if c.get("estado")]
    if "ENUMERACION_INCOMPLETA" in estados:
        # La enumeracion es codigo compartido. No se puede distinguir "el sitio
        # nos corto" de "nuestra paginacion no llego", asi que se para.
        return _veredicto(
            STOP, resultado, "enumeracion_compartida", RADIO_FAMILIA,
            "la enumeracion quedo incompleta y el enumerador es compartido; "
            "no se puede separar el sitio de nuestra paginacion")
    if "VARIANTE_NO_SOPORTADA" in estados:
        # El connector no reconoce la forma de este sitio. Es un hueco, no un
        # defecto que se propague: nadie mas certifica mal por esto, y darle
        # soporte es una estrategia nueva que no toca a las existentes.
        return _veredicto(
            CONTINUE, resultado, "variante_no_soportada", RADIO_ESTRATEGIA,
            "el connector no reconoce la forma de este sitio; es un hueco de "
            "cobertura, no un error que herede otra agencia")
    if "BLOQUEADA" in estados:
        return _veredicto(
            CONTINUE, resultado, "sitio_nos_bloquea", RADIO_AGENCIA,
            "el sitio nos bloqueo (403/429); es su decision, no nuestro parser")
    if "PRESUPUESTO_AGOTADO" in estados:
        return _veredicto(
            CONTINUE, resultado, "sitio_lento", RADIO_AGENCIA,
            "se agoto el presupuesto de tiempo: el sitio esta degradado")

    if any(c.get("presupuesto_agotado") for c in corridas):
        return _veredicto(
            CONTINUE, resultado, "sitio_lento", RADIO_AGENCIA,
            "se agoto el presupuesto de tiempo: el sitio esta degradado")

    if "LOW_INVENTORY_0_11" in revision and not fallidos:
        return _veredicto(
            CONTINUE, resultado, "inventario_chico", RADIO_AGENCIA,
            "inventario muy chico y ningun campo con extraccion fallida")

    # ---------------- Sin evidencia para acotar: se para ------------------
    return _veredicto(
        STOP, resultado, "sin_determinar", RADIO_COMPARTIDO,
        "no hay evidencia positiva de que la causa sea externa o acotada; "
        "no encontrar razones para parar no es tener razones para seguir")


def _veredicto(decision: str, resultado: dict[str, Any], componente: str,
               radio: str, evidencia: str) -> dict[str, Any]:
    return {
        "triage_version": TRIAGE_VERSION,
        "canonical_agency_id": resultado.get("canonical_agency_id"),
        "status": resultado.get("status"),
        "causa_observable": "; ".join(resultado.get("reasons") or []) or "(sin razones)",
        "decision": decision,
        "componente_sospechoso": componente,
        "radio_estimado": radio,
        "evidencia": evidencia,
        "connector": resultado.get("connector"),
        "connector_strategy": resultado.get("connector_strategy"),
        "strategy_fingerprint": resultado.get("strategy_fingerprint"),
        "firma_del_patron": firma(resultado, componente),
        "pendiente_de_resolucion": True,
        "certificado": False,
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# --------------------------------------------------------------------------
# Corte por lote
# --------------------------------------------------------------------------
DEFECTOS_PARA_CORTAR = 5
HORAS_PARA_CORTAR = 12


def debe_cortar_por_lote(pendientes: list[dict[str, Any]],
                         ahora: float | None = None) -> tuple[bool, str]:
    """Si conviene detenerse aunque cada defecto fuera continuable.

    Cinco defectos sueltos ya justifican una tanda de diagnostico, y dos con la
    misma firma dejaron de ser casualidad: es el mismo problema apareciendo dos
    veces, y eso es exactamente lo que un radio mal estimado produce.
    """
    if not pendientes:
        return False, ""

    if len(pendientes) >= DEFECTOS_PARA_CORTAR:
        return True, (f"{len(pendientes)} defectos pendientes sin resolver "
                      f"(umbral {DEFECTOS_PARA_CORTAR})")

    firmas: dict[str, int] = {}
    for defecto in pendientes:
        clave = defecto.get("firma_del_patron")
        if clave:
            firmas[clave] = firmas.get(clave, 0) + 1
    repetida = [f for f, n in firmas.items() if n >= 2]
    if repetida:
        return True, (f"dos defectos con la misma firma ({repetida[0]}): dejo "
                      f"de ser casualidad y el radio quedo mal estimado")

    if any(d.get("radio_estimado") in (RADIO_COMPARTIDO, RADIO_FAMILIA)
           for d in pendientes):
        return True, ("un defecto pendiente tiene radio compartido o de "
                      "familia: el radio crecio respecto de lo estimado")

    ahora = ahora if ahora is not None else time.time()
    marcas = [d.get("epoch") for d in pendientes if d.get("epoch")]
    if marcas and (ahora - min(marcas)) >= HORAS_PARA_CORTAR * 3600:
        horas = (ahora - min(marcas)) / 3600
        return True, (f"pasaron {horas:.1f} h desde el primer defecto "
                      f"pendiente (umbral {HORAS_PARA_CORTAR} h)")
    return False, ""

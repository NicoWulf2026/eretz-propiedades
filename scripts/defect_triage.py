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
import re
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


# Senales de que un sitio SI publica catalogo, aunque no lo hayamos podido
# enumerar. Se miran ENLACES y rutas, no vocabulario: una inmobiliaria sin
# catalogo igual dice "venta" y "propiedad" en su texto institucional, y
# contarlo como inventario seria el falso positivo simetrico.
#
# Los patrones salen de los dos casos reales, no de suponer:
#
#   alta.com.ar          Next.js con ruta /buscador; las fichas viven en
#                        /propiedad/<id> y el catalogo detras de
#                        /api/tokko/properties. 16 propiedades.
#   almadimatteo.com.ar  HTML estatico; el menu enlaza casasychalets/,
#                        deptosyph/, duplex/, lotes/, locales/ y alquileres/,
#                        y cada ficha es un .html en su carpeta. 28 fichas.
#
# Entre las dos, 44 propiedades que el sistema dio por inexistentes.

# Rutas de ficha individual.
RE_URL_DE_FICHA = re.compile(
    r"""href=["'][^"']*/(?:propiedad|propiedades|inmueble|inmuebles|ficha|"""
    r"""listing|emprendimiento)/[^"']{2,90}["']""", re.I)

# Un endpoint de catalogo referenciado desde el cliente.
RE_API_DE_CATALOGO = re.compile(
    r"""["'][^"']*/api/[^"']*(?:propert|propiedad|inmueble|listing|tokko|"""
    r"""wasi|search)[^"']*["']""", re.I)

# Un contador publicado: "16 propiedades encontradas".
RE_CONTADOR = re.compile(
    r"(\d{1,5})\s*(?:propiedades|inmuebles|resultados|avisos)", re.I)

# Enlaces a una pagina de busqueda o listado.
RE_RUTA_DE_BUSQUEDA = re.compile(
    r"""href=["'][^"']*/(?:buscador|busqueda|buscar|listado|catalogo|"""
    r"""propiedades|inmuebles)(?:[/?."']|["'])""", re.I)

# Enlaces a categorias del rubro. Es la forma que toma un catalogo estatico:
# el menu lleva a una pagina por tipo y ahi cuelgan las fichas.
RE_CATEGORIA = re.compile(
    r"""href=["'][^"']*(?:casas?ychalets?|casas|departamentos?|deptos?|"""
    r"""duplex|lotes|terrenos|locales|galpones|cocheras|campos|"""
    r"""alquileres?|ventas?)[^"']*\.(?:html?|php|aspx)["']""", re.I)


def senales_de_catalogo(html: str) -> list[str]:
    """Evidencia estructural de que hay inventario publicado."""
    if not html:
        return []
    senales = []
    fichas = set(RE_URL_DE_FICHA.findall(html))
    if fichas:
        senales.append(f"{len(fichas)} enlaces con forma de ficha")
    categorias = set(RE_CATEGORIA.findall(html))
    if len(categorias) >= 2:
        senales.append(f"{len(categorias)} paginas de categoria del rubro")
    if RE_API_DE_CATALOGO.search(html):
        senales.append("endpoint de catalogo referenciado en el cliente")
    if RE_RUTA_DE_BUSQUEDA.search(html):
        senales.append("enlace a una pagina de busqueda o listado")
    contador = RE_CONTADOR.search(html)
    if contador and int(contador.group(1)) > 0:
        senales.append(f"contador publicado: {contador.group(0).strip()}")
    return senales


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

    # Antes de leer un colapso como perdida sistematica hay que haber podido
    # LEER el sitio. `varelanegociosinmobiliarios.com` no respondio en 102 s en
    # ninguna de las dos corridas: su inventario "colapso" al 0 % porque nunca
    # se llego a la portada, y eso no es un defecto transversal nuestro sino un
    # sitio caido. Sin esta puerta, cualquier caida ajena para la cola entera
    # con un veredicto de radio FAMILIA que no se sostiene.
    inaccesibles = [c for c in corridas
                    if c.get("estado") in ("ERROR_DISCOVERY", "ERROR_LISTADO")]
    if len(inaccesibles) == len(corridas) and corridas:
        return _veredicto(
            CONTINUE, resultado, "fuente_inaccesible", RADIO_AGENCIA,
            "no se pudo llegar al sitio en ninguna de las dos corridas: "
            f"{'; '.join(sorted({str(c.get('detalle') or 'sin detalle')[:60] for c in inaccesibles}))}")

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

    # Fichas que fallaron por la red o por el servidor del sitio. NO se exige
    # que los inventarios difieran: la rama pedia eso y su propia evidencia
    # decia "el catalogo enumero igual en las dos corridas", o sea que el
    # codigo y el texto se contradecian.
    #
    # Que coincidan es MAS evidencia de salud, no menos. `andrea gianfelice`
    # enumero 153 las dos veces, obtuvo 152 las dos veces, y fallo siempre la
    # misma ficha con un error de red: el triage no supo clasificarlo y paro
    # las dos colas por un radio COMPARTIDO que no existia.
    if detalles_fallidos and externos:
        coinciden = not inventarios_distintos
        return _veredicto(
            CONTINUE, resultado, "sitio_externo", RADIO_AGENCIA,
            f"{detalles_fallidos} detalles fallaron con errores de red o del "
            f"servidor ({', '.join(sorted(externos))}); "
            + ("el catalogo enumero igual en las dos corridas"
               if coinciden else
               "y eso explica que los inventarios difieran"))

    estados = [c.get("estado") for c in corridas if c.get("estado")]
    if "ENUMERACION_INCOMPLETA" in estados:
        # La enumeracion es codigo compartido. No se puede distinguir "el sitio
        # nos corto" de "nuestra paginacion no llego", asi que se para.
        return _veredicto(
            STOP, resultado, "enumeracion_compartida", RADIO_FAMILIA,
            "la enumeracion quedo incompleta y el enumerador es compartido; "
            "no se puede separar el sitio de nuestra paginacion")
    if "VARIANTE_NO_SOPORTADA" in estados:
        # "No reconoci la forma" NO es "no hay inventario". Si el sitio muestra
        # estructura de catalogo, lo que esta en juego son propiedades reales
        # que no estamos publicando, y eso pesa mas que ahorrarse una parada.
        senales = resultado.get("senales_de_catalogo") or []
        if senales:
            return _veredicto(
                STOP, resultado, "posible_perdida_de_inventario", RADIO_FAMILIA,
                f"el sitio publica catalogo y no lo pudimos enumerar: "
                f"{'; '.join(senales)}")
        return _veredicto(
            CONTINUE, resultado, COMPONENTE_VARIANTE, RADIO_ESTRATEGIA,
            "el connector no reconoce la forma de este sitio y no se hallaron "
            "senales de catalogo publicado")
    if "BLOQUEADA" in estados:
        return _veredicto(
            CONTINUE, resultado, "sitio_nos_bloquea", RADIO_AGENCIA,
            "el sitio nos bloqueo (403/429); es su decision, no nuestro parser")
    if {"ERROR_DISCOVERY", "ERROR_LISTADO"} & set(estados):
        return _veredicto(
            CONTINUE, resultado, "fuente_inaccesible", RADIO_AGENCIA,
            "una de las corridas no pudo llegar al sitio; es la red o el "
            "servidor, no nuestro parser")
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
# El componente que se anota cuando no reconocimos la forma del sitio. Es
# un sintoma con tantas causas como formas de sitio hay, no un patron.
COMPONENTE_VARIANTE = "variante_no_soportada"

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
        # `variante_no_soportada` no es un patron: es un sintoma. La firma se
        # arma con conector, estrategia, componente y razones, y para "no
        # reconoci la forma del sitio" esas cuatro cosas son identicas siempre,
        # asi que agrupa causas que no tienen nada que ver. Medido sobre las
        # que compartian la firma ef05c0690dea:
        #
        #   armanino   una SPA de React
        #   amud       jQuery contra la API de la plataforma SOM
        #   bergo      HTTP 200 con el cuerpo VACIO
        #   bottai     un catalogo real con una forma de url que no conocemos
        #   alta       16 propiedades detras de un /buscador (ya arreglada)
        #
        # Cinco causas, una firma. La regla -"dos con la misma firma dejo de
        # ser casualidad"- es buena justamente porque la firma identifica un
        # patron; donde no lo identifica, para la cola por nada. Estas siguen
        # contando para el umbral de cinco y para el radio, que no dependen de
        # que la firma signifique algo.
        if defecto.get("componente_sospechoso") == COMPONENTE_VARIANTE:
            continue
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

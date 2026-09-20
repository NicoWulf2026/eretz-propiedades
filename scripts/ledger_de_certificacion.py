#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Cual de todas las filas de una agencia es su resultado vigente. NEXT-001.

No escribe nada. `database_writes: 0`.

Por que existe
--------------
Codex dejo el defecto descrito y confirmado por implementacion, y sin resolver:

- `agency_certifier.py :: read_jsonl` saltea el `ValueError` de una linea
  invalida **en silencio**, y acepta cualquier JSON y no solo objetos;
- `run_agency_certification_queue.py :: latest_results` y
  `backfill_strategy_fingerprints.py :: latest_results` toman el **ultimo
  append por agencia, sin ordenar ni comparar `checked_at`**.

Con dos workers escribiendo el mismo archivo, el orden de append no es el orden
temporal: el que termino despues pudo haber empezado antes. Y una linea
truncada por un `Stop-Process -Force` -que ya paso en este proyecto- desaparece
sin dejar rastro, dejando elegido un cierre viejo como si nada.

Lo que se midio antes de escribir esto
--------------------------------------
Sobre el ledger real, 2.501 filas:

    lineas con JSON invalido                                   0
    filas que no son objeto / sin canonical_agency_id          0
    agencias donde el ultimo append NO es el checked_at mayor  0
    grupos agencia+checked_at con mas de un status             0

Los 35 grupos agencia+`checked_at` repetidos que Codex no habia caracterizado
difieren **solo** en `strategy_fingerprint`, `connector_strategy`,
`fingerprint_schema_version`, `operational_metrics` y
`fingerprint_backfilled_from_terminal_evidence`. Son reescrituras del backfill,
no evidencia de certificacion en conflicto.

**El riesgo es real en el codigo y todavia no ocurrio en los datos.** Por eso
esto es endurecimiento y no reparacion, y por eso no bloqueaba relanzar la cola.

Por que este modulo esta FUERA de la huella
-------------------------------------------
Elegir que fila representa a una agencia es lectura de artefactos, no
extraccion. No cambia lo que se certifica: cambia que cierre anterior se
considera vigente, o sea si hay que recertificar. Es la misma categoria que
`read_jsonl` y `append_jsonl`, que `CERTIFIER_OPERACIONALES` ya excluye de
`shared/certifier` como "lectura de artefactos" y "escritura de bitacora".

Vale decirlo explicito porque la lista de componentes de `shared/*` es por
ruta, y un modulo nuevo no entra solo. Si algun dia esto empieza a decidir
**contenido** y no seleccion, tiene que entrar a la huella.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

# Campos cuya diferencia, a igual instante, NO es evidencia en conflicto sino
# una reescritura de metadatos. Son exactamente los cinco que difieren en los
# 35 grupos reales del ledger; cualquier otro campo distinto a igual instante
# se considera ambiguo.
CAMPOS_DE_REFRESH = frozenset({
    "strategy_fingerprint", "connector_strategy", "fingerprint_schema_version",
    "operational_metrics", "fingerprint_backfilled_from_terminal_evidence",
    "certifier_version", "connector_version",
})

# Lo que, si difiere a igual instante, son dos corridas que vieron cosas
# distintas. Se listan aparte y no por descarte: agregar un campo nuevo al
# resultado no deberia volver ambiguo a medio padron sin que nadie lo decida.
CAMPOS_DE_VEREDICTO = ("status", "enumeration_audit", "official_url",
                       "connector", "reasons")


class LineaInvalida(ValueError):
    """Una linea del ledger no se pudo leer. No es lo mismo que no existir."""


class Ambiguo(ValueError):
    """Dos resultados del mismo instante con veredictos distintos.

    No se elige: se reporta. Quedarse con el que mas gusta seria convertir
    evidencia contradictoria en un veredicto, que es la unica cosa que este
    proyecto no puede hacer.
    """


def _instante(texto: Any) -> float | None:
    """ISO-8601 a epoch, tratando offsets equivalentes como el mismo momento.

    `10:00-03:00` y `13:00Z` son el mismo instante; compararlos como texto los
    ordena mal e inventa una ambiguedad que no existe.
    """
    if not isinstance(texto, str) or not texto.strip():
        return None
    crudo = texto.strip().replace("Z", "+00:00")
    try:
        fecha = datetime.datetime.fromisoformat(crudo)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=datetime.timezone.utc)
    return fecha.timestamp()


def leer_ledger(ruta: Path | str, estricto: bool = True
                ) -> Any:
    """Las filas validas y, siempre, cuales no lo eran.

    Con `estricto` -el default- una linea ilegible levanta `LineaInvalida` con
    su numero de linea. Sin el, devuelve `(filas, numeros_invalidos)`: tolerar
    esta permitido, tolerar **en silencio** no.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return [] if estricto else ([], [])
    filas: list[dict[str, Any]] = []
    invalidas: list[int] = []
    with ruta.open(encoding="utf-8", errors="replace") as fh:
        for numero, linea in enumerate(fh, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except ValueError:
                invalidas.append(numero)
                continue
            if not isinstance(fila, dict) or not fila.get(
                    "canonical_agency_id"):
                invalidas.append(numero)
                continue
            filas.append(fila)
    if estricto and invalidas:
        raise LineaInvalida(
            f"{len(invalidas)} lineas ilegibles en {ruta.name}: "
            f"{invalidas[:10]}. Un resultado que no se pudo leer no es un "
            f"resultado que no existe.")
    return filas if estricto else (filas, invalidas)


def _difieren_en_veredicto(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    return [campo for campo in CAMPOS_DE_VEREDICTO if a.get(campo) != b.get(campo)]


def resultado_vigente(filas: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La fila que representa a esta agencia hoy.

    Gana el `checked_at` mas nuevo, no el ultimo append. Una fila sin fecha
    legible no puede ganarle a una fechada: sin fecha no hay forma de saber si
    es mas nueva, y adivinarlo es como se elige un cierre viejo sin enterarse.

    A igual instante, si las filas difieren en algo del veredicto se levanta
    `Ambiguo`. Si difieren solo en metadatos -el caso de los 35 grupos reales-
    gana la ultima escrita, que es la reescritura mas reciente.
    """
    if not filas:
        return None
    fechadas = [(t, i, f) for i, f in enumerate(filas)
                if (t := _instante(f.get("checked_at"))) is not None]
    if not fechadas:
        return filas[-1]
    mayor = max(t for t, _, _ in fechadas)
    empatadas = [(i, f) for t, i, f in fechadas if t == mayor]
    empatadas.sort()
    elegida = empatadas[-1][1]
    for _, otra in empatadas[:-1]:
        distintos = _difieren_en_veredicto(elegida, otra)
        if distintos:
            raise Ambiguo(
                f"dos resultados de {elegida.get('canonical_agency_id')} en "
                f"{elegida.get('checked_at')} difieren en {distintos}: "
                f"{elegida.get('status')} contra {otra.get('status')}. "
                f"No se elige entre dos evidencias distintas.")
    return elegida


def vigentes_por_agencia(ruta: Path | str
                         ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Lo que la cola y el backfill necesitan, con sus problemas aparte.

    Una agencia ambigua se reporta y se EXCLUYE de los vigentes: no se elige
    por ella. Pero no se tira el resto del padron, porque el §11 pide conservar
    lo que si se puede afirmar.
    """
    filas, invalidas = leer_ledger(ruta, estricto=False)
    if invalidas:
        raise LineaInvalida(
            f"{len(invalidas)} lineas ilegibles: {invalidas[:10]}")
    por_agencia: dict[str, list[dict[str, Any]]] = {}
    for fila in filas:
        por_agencia.setdefault(fila["canonical_agency_id"], []).append(fila)
    vigentes: dict[str, dict[str, Any]] = {}
    problemas: dict[str, str] = {}
    for agencia, suyas in por_agencia.items():
        try:
            elegida = resultado_vigente(suyas)
        except Ambiguo as error:
            problemas[agencia] = str(error)
            continue
        if elegida is not None:
            vigentes[agencia] = elegida
    return vigentes, problemas

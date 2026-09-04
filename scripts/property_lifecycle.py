#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El ciclo de vida de una propiedad. Conservador por diseno.

La regla que ordena todo: **una ausencia puntual NO es una baja**. Una
propiedad que hoy no aparece puede ser un timeout, un listado paginado a la
mitad, un sitio que cambio de plantilla o un aviso que se movio de pagina. En
un agregador el error se ve enseguida: la inmobiliaria llama para preguntar por
que no esta su propiedad.

Estados:

  ACTIVA      se la vio en la ultima enumeracion confiable
  AUSENTE     no se la vio, pero todavia no alcanza para concluir nada
  INACTIVA    ausente en N enumeraciones confiables seguidas. REVERSIBLE
  RETIRADA    hay prueba positiva de que ya no esta: su propia ficha responde
              404 o 410. No se llega aca por ausencia, se llega por evidencia
  REACTIVADA  volvio a aparecer despues de estar AUSENTE o INACTIVA

La distincion entre `INACTIVA` y `RETIRADA` es la misma que ordena el resto del
sistema: **ausencia de evidencia no es evidencia de ausencia**. `INACTIVA` dice
"hace rato que no la vemos" y se deshace sola si reaparece. `RETIRADA` afirma
que la propiedad ya no existe, y eso solo se afirma cuando la fuente lo dice.

Una enumeracion en la que no se puede confiar NO produce ausencias. Si la
fuente no respondio, si la paginacion se corto o si el presupuesto se agoto, lo
que no se vio no estuvo ausente: no se lo busco. Contarlo seria fabricar bajas
a partir de nuestros propios fallos, que es exactamente como se borra
inventario vivo.

ESTADO DE ACTIVACION: la regla NO esta encendida, y no por falta de codigo.
`evaluate_deletions.py` mide sobre los artefactos reales que la ausencia
consecutiva mas larga observada es **1**, sobre 1.565 ausencias comparables.
La pregunta que habilita encenderla -cuantas de las que desaparecieron
volvieron- todavia no tiene datos, porque hacen falta pasadas repetidas en el
tiempo sobre las mismas fuentes. Hasta entonces esto especifica y simula.

No escribe en ninguna base.
"""
from __future__ import annotations

from typing import Any, Iterable

LIFECYCLE_VERSION = "property_lifecycle_v1"

ACTIVA = "ACTIVA"
AUSENTE = "AUSENTE"
INACTIVA = "INACTIVA"
RETIRADA = "RETIRADA"
REACTIVADA = "REACTIVADA"

# Tres enumeraciones confiables seguidas sin verla. El numero no es magico: es
# el que ya venia propuesto en `evaluate_deletions.py` y todavia no tuvo
# ocasion de dispararse ni una vez.
AUSENCIAS_PARA_INACTIVA = 3

# Lo que dice la fuente cuando una ficha ya no existe.
CODIGOS_DE_BAJA = (404, 410)


class Observacion:
    """Lo que una corrida vio -o no- de una propiedad.

    `enumeracion_confiable` es la clave: cuando es falsa, esta observacion no
    puede producir una ausencia porque no se busco de verdad.
    """

    __slots__ = ("vista", "enumeracion_confiable", "codigo_de_la_ficha")

    def __init__(self, vista: bool, enumeracion_confiable: bool = True,
                 codigo_de_la_ficha: int | None = None) -> None:
        self.vista = vista
        self.enumeracion_confiable = enumeracion_confiable
        self.codigo_de_la_ficha = codigo_de_la_ficha


def enumeracion_confiable(corrida: dict[str, Any]) -> bool:
    """Si de esta corrida se pueden deducir ausencias.

    Lo decide el propio runner al registrar la corrida: si no respondio, si la
    paginacion se interrumpio, si la enumeracion quedo incompleta o si se
    quedo sin presupuesto, lo que no se vio no estuvo ausente.
    """
    if corrida.get("estado") != "OK":
        return False
    if corrida.get("paginacion_interrumpida"):
        return False
    if corrida.get("presupuesto_agotado"):
        return False
    return bool(corrida.get("enumeracion_completa", True))


def transicion(estado: str, ausencias: int,
               observacion: Observacion) -> tuple[str, int]:
    """El estado siguiente y el contador de ausencias.

    Funcion pura: mismo estado y misma observacion dan siempre lo mismo, que es
    lo que permite simular la regla sobre el historico antes de encenderla.
    """
    if observacion.codigo_de_la_ficha in CODIGOS_DE_BAJA:
        # La fuente lo afirma. Es el unico camino a RETIRADA.
        return RETIRADA, ausencias

    if observacion.vista:
        if estado in (AUSENTE, INACTIVA):
            return REACTIVADA, 0
        if estado == RETIRADA:
            # Reapareció despues de una baja confirmada. Pasa: una inmobiliaria
            # republica un aviso. Vuelve a la vida y el contador arranca limpio.
            return REACTIVADA, 0
        return ACTIVA, 0

    if not observacion.enumeracion_confiable:
        # No se la vio porque no se la busco bien. No es una ausencia.
        return estado, ausencias

    if estado == RETIRADA:
        return RETIRADA, ausencias

    ausencias += 1
    if ausencias >= AUSENCIAS_PARA_INACTIVA:
        return INACTIVA, ausencias
    return AUSENTE, ausencias


def recorrer(observaciones: Iterable[Observacion],
             estado: str = ACTIVA) -> dict[str, Any]:
    """Aplica la maquina a una secuencia de corridas."""
    ausencias = 0
    historia: list[str] = []
    for observacion in observaciones:
        estado, ausencias = transicion(estado, ausencias, observacion)
        historia.append(estado)
    return {
        "lifecycle_version": LIFECYCLE_VERSION,
        "estado": estado,
        "ausencias_consecutivas": ausencias,
        "historia": historia,
        "umbral": AUSENCIAS_PARA_INACTIVA,
        "database_writes": 0,
    }

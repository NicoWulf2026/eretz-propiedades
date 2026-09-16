# -*- coding: utf-8 -*-
"""Una fuente que se contradice a sí misma no decide la provincia.

**Rojo a propósito. El arreglo NO está aplicado** y toca código semántico: va a
la ventana.

EL CASO, medido el 2026-09-16 sobre `analia requena propiedades`:

    status                  CERTIFIED_COMPLETE
    razones                 "two complete idempotent runs passed"
    provincia               EXTRACTED, cobertura 1.0
    valor en las 143        "Ciudad Autónoma de Buenos Aires"

Y la misma ficha dice, en su prosa:

    "Casa en Barrio Atlantida ... entre Santa Clara del Mar y la Ruta
     Provincial 11. Entorno forestal ... Cercanía a Santa Clara"

Camet Norte, Santa Clara del Mar y la Ruta Provincial 11 son Partido de Mar
Chiquita, **provincia de Buenos Aires**. No CABA. La fuente publica
`"addressRegion": "Ciudad Autónoma de Buenos Aires"` en su JSON-LD y se
contradice con su propio texto.

130 de 143 propiedades llevan esa provincia. La certificación no lo nota
—y no tiene por qué: dos corridas idénticas prueban que enumeramos bien, no
que el dato sea cierto—. Es la diferencia entre COMPLETO y CORRECTO.

Lo que el §45 pide: ante un GEO_CONFLICT se preservan las evidencias y **no se
elige automáticamente**. Hoy elegimos, y elegimos mal.

El barrido sobre la flota acota el alcance: es la única agencia con provincia
uniforme contradicha por sus propias localidades. La otra que apareció
—`falco`, 1 de 62— es un falso positivo del detector: Parque Avellaneda **sí**
es CABA.
"""
import re

import pytest

# Localidades que no pueden estar en CABA. Es una lista corta y verificable, no
# una heuristica: son partidos de la costa y del interior bonaerense.
FUERA_DE_CABA = re.compile(
    r"(?i)\b(camet|santa clara del mar|mar chiquita|atlantida|mar del plata|"
    r"pinamar|villa gesell|necochea|miramar|carilo)\b")


def hay_conflicto(provincia: str, texto_de_la_ficha: str) -> bool:
    """La provincia declarada contra lo que dice el cuerpo de la ficha."""
    if not provincia or "ciudad aut" not in provincia.lower():
        return False
    return bool(FUERA_DE_CABA.search(texto_de_la_ficha or ""))


FICHA = ("Casa en Barrio Atlantida. Ubicada entre Santa Clara del Mar y la "
         "Ruta Provincial 11. Entorno forestal. Barrio tranquilo. "
         "Cercania a Santa Clara del Mar.")


def test_el_detector_ve_el_conflicto():
    assert hay_conflicto("Ciudad Autónoma de Buenos Aires", FICHA) is True


def test_no_marca_una_propiedad_de_CABA_de_verdad():
    """`Parque Avellaneda` ES un barrio de CABA. Marcarlo seria el error
    inverso: apagar una provincia correcta."""
    ficha = "Departamento en Venta en Parque Avellaneda, a metros del parque."
    assert hay_conflicto("Ciudad Autónoma de Buenos Aires", ficha) is False


def test_no_opina_cuando_la_provincia_es_otra():
    """El detector sólo mira el caso CABA. Con otra provincia no hay nada que
    contradecir y afirmar un conflicto seria inventar."""
    assert hay_conflicto("Buenos Aires", FICHA) is False
    assert hay_conflicto(None, FICHA) is False


@pytest.mark.xfail(strict=True, reason="defecto abierto: ante un GEO_CONFLICT "
                                       "la provincia se toma igual en vez de "
                                       "quedar en blanco con su evidencia")
def test_ROJO_una_provincia_en_conflicto_no_se_publica():
    """Lo que el §45 pide y hoy no pasa.

    Se replica el camino actual: la provincia sale del JSON-LD de la fuente y
    nadie la contrasta con el cuerpo. Poner el contraste adentro del test lo
    haria pasar, y entonces probaria la solucion en vez del defecto.
    """
    de_la_fuente = "Ciudad Autónoma de Buenos Aires"   # addressRegion del JSON-LD
    provincia_publicada = de_la_fuente                 # <-- falta el contraste
    assert provincia_publicada is None, (
        "se publica CABA para una propiedad de Mar Chiquita; el §45 pide "
        "dejarla vacia y guardar las dos evidencias, no elegir")

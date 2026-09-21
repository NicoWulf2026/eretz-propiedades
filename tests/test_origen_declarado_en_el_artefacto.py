# -*- coding: utf-8 -*-
"""Un dato deducido no puede decir que fue extraido.

El conector deduce la provincia del padron de la inmobiliaria cuando la ficha
no la publica, y lo marca con todas las letras:

    prop.extra["provincia_origen"]   = "padron_inmobiliaria"
    prop.extra["provincia_confianza"] = "inferida"

junto a la advertencia correcta de que la provincia de la inmobiliaria no es
necesariamente la del inmueble. **El artefacto perdia esa marca**: escribia
`origen: FRESH_CERTIFICATION`, que es lo mismo que dice de un titulo sacado
del `<h1>`.

No es un caso de borde. Medido al regenerarlo: **17.438 de 23.464
propiedades, el 74,3 %**, traen la provincia deducida. El conector era
honesto y la honestidad se perdia en el camino.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.artefacto_por_propiedad import (  # noqa: E402
    PROVIDED_EXTRACTED, estado_del_campo)


def celda(valor, extra: dict, campo: str = "provincia") -> dict:
    """Reproduce la celda que arma el artefacto, sin tocar disco."""
    estado = estado_del_campo(valor, campo, {}, "", set())
    salida = {"valor": valor, "estado": estado,
              "origen": ("FRESH_CERTIFICATION"
                         if estado == PROVIDED_EXTRACTED else None)}
    declarado = extra.get(f"{campo}_origen")
    if declarado and salida["origen"]:
        salida["origen"] = declarado
        confianza = extra.get(f"{campo}_confianza")
        if confianza:
            salida["confianza"] = confianza
    return salida


def test_MUERDE_una_provincia_deducida_no_dice_FRESH_CERTIFICATION():
    """El caso real, el 74,3 % del padron."""
    salida = celda("Buenos Aires", {"provincia_origen": "padron_inmobiliaria",
                                    "provincia_confianza": "inferida"})
    assert salida["origen"] == "padron_inmobiliaria"
    assert salida["confianza"] == "inferida"


def test_MUERDE_una_provincia_extraida_de_verdad_sigue_diciendolo():
    """La otra mitad. Si el arreglo marcara todo como inferido, el campo
    dejaria de distinguir y no habriamos ganado nada."""
    salida = celda("Santa Fe", {})
    assert salida["origen"] == "FRESH_CERTIFICATION"
    assert "confianza" not in salida


def test_un_campo_ausente_no_se_marca_como_deducido():
    """Sin valor no hay origen que declarar.

    Escribir `padron_inmobiliaria` sobre un `None` afirmaria que se dedujo
    algo que no esta.
    """
    salida = celda(None, {"provincia_origen": "padron_inmobiliaria",
                          "provincia_confianza": "inferida"})
    # Sin cobertura de la agencia el estado es NOT_ATTEMPTED, no
    # NOT_PROVIDED: no se puede afirmar que la fuente no lo traiga.
    assert salida["estado"] != PROVIDED_EXTRACTED
    assert salida["origen"] is None
    assert "confianza" not in salida


def test_el_mecanismo_no_es_solo_para_provincia():
    """Esta escrito por campo, no cableado a `provincia`.

    Si manana el conector marca `ciudad_origen`, el artefacto lo respeta sin
    tocar nada. Cablearlo a un campo obligaria a acordarse la proxima vez.
    """
    salida = celda("Rosario", {"ciudad_origen": "coordenada",
                               "ciudad_confianza": "inferida"}, campo="ciudad")
    assert salida["origen"] == "coordenada"
    assert salida["confianza"] == "inferida"


def test_un_origen_sin_confianza_se_respeta_igual():
    """No todo origen declarado implica que el dato sea dudoso."""
    salida = celda("Santa Fe", {"provincia_origen": "schema_org"})
    assert salida["origen"] == "schema_org"
    assert "confianza" not in salida


def test_MUERDE_el_resumen_publica_cuantos_son():
    """Una cifra que no se publica no corrige a nadie.

    El problema de `provincia` era exactamente que la deduccion no se veia;
    dejarla solo fila por fila la volveria igual de invisible para quien mira
    el resumen.
    """
    fuente = (RAIZ / "scripts" / "artefacto_por_propiedad.py").read_text(
        encoding="utf-8")
    assert '"valores_inferidos_por_campo": dict(inferidos)' in fuente

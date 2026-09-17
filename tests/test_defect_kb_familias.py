# -*- coding: utf-8 -*-
"""La precedencia de la base de firmas: medición antes que prosa, y sin ascensos.

Dos invariantes, y la segunda es la que importa a largo plazo.

La primera es útil: cuando abrimos el sitio y medimos algo, esa señal le gana a
una expresión regular sobre el texto que yo escribí. Este archivo ya pagó lo
contrario —la primera versión decía `slug` en singular y doce agencias con la
misma causa quedaron sin clasificar—.

La segunda es una prohibición. `SIN_RASTRO_DE_CATALOGO` significa "fuimos y no
se ve catálogo". Es evidencia y merece su propio cajón, pero **no explica
nada**. Si algún día alguien la mapea a una familia diagnosticada, el tablero
va a mostrar progreso donde no lo hay, y ése es el modo de falla más caro de
todos: el que se ve bien.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from defect_kb import (  # noqa: E402
    FIRMA_MEDIDA_A_FAMILIA, FIRMA_MEDIDA_SIN_DIAGNOSTICO, familia_de,
)

MEDIDAS = {
    "franchi inmobiliaria": "SITEMAP_CON_FICHAS",
    "david rodriguez propiedades": "NAVEGACION_SOLO_JAVASCRIPT",
    "analia verga propiedades": "FUENTE_ES_PORTAL_AJENO",
    "castro estudio inmobiliario": "SIN_RASTRO_DE_CATALOGO",
    "bergo servicios inmobiliarios": "SIN_CONTENIDO",
}

# Prosa que la regex SÍ reconoce, para poder probar quién gana.
TEXTO_QUE_MATCHEA = "el patron_ficha no reconoce la forma de sus urls"


def test_la_medicion_le_gana_a_la_regex_sobre_prosa():
    """El mismo texto, dos agencias, dos familias distintas.

    Sin la medición las dos caerían en `FORMA_DE_URL_NO_RECONOCIDA` por cómo
    quedó redactado el diagnóstico, y una de ellas es un perfil de portal: su
    problema no es la forma de la URL, es de quién es el inventario.
    """
    assert familia_de(TEXTO_QUE_MATCHEA, "roomix:analia verga propiedades",
                      MEDIDAS) == "PORTAL_COMO_FUENTE"
    assert familia_de(TEXTO_QUE_MATCHEA, "roomix:agencia sin medicion",
                      MEDIDAS) == "FORMA_DE_URL_NO_RECONOCIDA"


def test_sin_medicion_la_regex_sigue_funcionando():
    assert familia_de(TEXTO_QUE_MATCHEA, "roomix:cualquiera", {}) == \
        "FORMA_DE_URL_NO_RECONOCIDA"
    assert familia_de("un texto que no matchea nada", "roomix:x", {}) == \
        "SIN_CLASIFICAR"


def test_MUERDE_una_firma_sin_diagnostico_no_puede_ascender_a_familia():
    """La prohibición central: evidencia de ausencia no es un diagnóstico.

    Si `SIN_RASTRO_DE_CATALOGO` apareciera en el mapa de familias
    diagnosticadas, 18 agencias pasarían de "no sabemos" a "resuelto" sin que
    nadie haya averiguado nada.
    """
    for firma in FIRMA_MEDIDA_SIN_DIAGNOSTICO:
        assert firma not in FIRMA_MEDIDA_A_FAMILIA, (
            f"{firma} es evidencia de ausencia, no una causa: mapearla a una "
            f"familia diagnosticada inventa progreso")


def test_sin_rastro_de_catalogo_abre_una_pregunta_y_no_la_cierra():
    """Queda en su cajón propio, y el nombre dice qué falta decidir (§71)."""
    familia = familia_de("texto que no matchea nada",
                         "roomix:castro estudio inmobiliario", MEDIDAS)
    assert familia == "SIN_CATALOGO_VISIBLE_FALTA_DECIDIR_TERMINAL"
    assert familia not in FIRMA_MEDIDA_A_FAMILIA.values()


def test_la_prosa_le_gana_al_cajon_de_ausencia():
    """Si hay un diagnóstico escrito, vale más que "no se ve catálogo".

    El orden importa: medición diagnóstica, después prosa, y sólo al final el
    cajón de ausencia. Al revés, un diagnóstico real quedaría tapado por la
    constatación de que el sitio se ve vacío.
    """
    assert familia_de(TEXTO_QUE_MATCHEA, "roomix:castro estudio inmobiliario",
                      MEDIDAS) == "FORMA_DE_URL_NO_RECONOCIDA"


@pytest.mark.parametrize("firma,familia", sorted(FIRMA_MEDIDA_A_FAMILIA.items()))
def test_toda_firma_diagnostica_mapea_a_una_familia_no_vacia(firma, familia):
    assert familia and familia != "SIN_CLASIFICAR"

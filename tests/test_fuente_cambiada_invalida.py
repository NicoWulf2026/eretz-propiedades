# -*- coding: utf-8 -*-
"""Un resultado sacado de otra url no describe la fuente de hoy.

El caso real: el 2026-09-16 se movió la fuente de tres agencias de un perfil de
portal ajeno a su dominio propio. `emir elhelou` tenía una diferida vigente y su
huella de estrategia no había cambiado, así que la cola daba el resultado por
vigente y la salteaba. El cambio de fuente habría quedado **inerte** y el
canario habría parecido estar corriendo sin correr nunca.

Lo que hace peligroso a ese modo de falla no es que rompa algo: es que no rompe
nada visible. Todo sigue verde y el trabajo simplemente no ocurre.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts import run_agency_certification_queue as cola  # noqa: E402

PORTAL = "https://www.agroads.com.ar/e/emir-elhelou-estudio-inmobiliario/"
PROPIO = "https://estudioelhelou.com.ar"


def _hace(horas: float) -> str:
    """Una fecha relativa al reloj real, no una constante del calendario.

    Las cuatro afirmaciones positivas de este archivo se escribieron con
    fechas fijas del 2026-09-16 y pasaron ese dia. El 2026-09-20 fallaron las
    cuatro, y no porque el codigo cambiara: `diferida_vigente` mide el TTL
    -72 h, 24 h si la firma es critica- contra `checked_at`, con
    `ahora = time.time()`. Una fecha fija envejece; el TTL no.

    Es el mismo defecto que este proyecto ya arreglo en el codigo -anclar el
    TTL en la firma en vez de en la ultima mirada- reaparecido en los tests.
    Un test que aprueba hoy y reprueba el jueves sin que nadie toque nada no
    esta midiendo el codigo: esta midiendo el almanaque.
    """
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() - horas * 3600))


# Dentro del TTL de 72 h, con margen para que la corrida no lo cruce.
DIFERIDA = [{"componente": "variante_no_soportada", "radio": "FAMILIA",
             "cuando": _hace(2.0)}]


def previo(url: str) -> dict:
    """Un NEEDS_FIX diagnosticado, que sin esta regla se daria por vigente."""
    return {
        "status": "NEEDS_FIX",
        "official_url": url,
        "connector": "generico",
        "connector_strategy": "generic/no_inventory",
        "strategy_fingerprint": cola.strategy_fingerprint(
            "generico", "generic/no_inventory"),
        "checked_at": _hace(1.5),
    }


def test_sin_cambio_de_fuente_el_resultado_sigue_vigente():
    """La regla nueva no puede reintroducir la recertificación masiva.

    El anti-retrabajo bajó el día de 41,6 h de worker a 22,8 justamente
    evitando repetir diagnósticos escritos. Si esta comprobación devolviera
    False cuando la url no cambió, se perdería todo eso.
    """
    assert cola.is_current_result(previo(PORTAL), {}, DIFERIDA, PORTAL)


def test_MUERDE_si_la_fuente_cambio_el_resultado_deja_de_estar_vigente():
    assert not cola.is_current_result(previo(PORTAL), {}, DIFERIDA, PROPIO)


def test_la_barra_final_no_cuenta_como_cambio_de_fuente():
    """`https://x.com` y `https://x.com/` son la misma fuente.

    Sin normalizar, cada reanudación recertificaría agencias por una barra.
    """
    assert cola.is_current_result(previo("https://estudioelhelou.com.ar/"),
                                  {}, DIFERIDA, "https://estudioelhelou.com.ar")


def test_sin_fuente_de_hoy_la_regla_no_opina():
    """Los llamadores viejos siguen funcionando igual.

    `agency_rollout_preflight` llama sin el parámetro nuevo; que eso empiece a
    devolver False marcaría medio universo como stale de golpe.
    """
    assert cola.is_current_result(previo(PORTAL), {}, DIFERIDA)
    assert cola.is_current_result(previo(PORTAL), {}, DIFERIDA, None)


def test_un_resultado_sin_url_registrada_no_se_invalida_por_esto():
    """Los cierres de identidad no guardan `official_url`.

    Invalidarlos acá los mandaría a recertificar por un campo que nunca
    tuvieron.
    """
    sin_url = {k: v for k, v in previo(PORTAL).items() if k != "official_url"}
    assert cola.is_current_result(sin_url, {}, DIFERIDA, PROPIO)


def test_MUERDE_una_diferida_vencida_no_mantiene_vigente_el_resultado():
    """Lo que el almanaque estaba tapando, ahora afirmado a proposito.

    Las cuatro afirmaciones positivas de arriba pasaron a rojo el 2026-09-20
    porque sus fechas fijas habian envejecido mas alla del TTL. El sintoma
    parecia una regresion del codigo y no lo era; peor todavia, mientras
    duraron en verde nadie estaba comprobando que el TTL venciera de verdad.

    Con fechas relativas esa comprobacion hay que escribirla, y es esta: una
    diferida de hace 100 h -por encima de las 72 h- deja de sostener el
    resultado aunque la fuente no haya cambiado.
    """
    vencida = [{"componente": "variante_no_soportada", "radio": "FAMILIA",
                "cuando": _hace(100.0)}]
    viejo = previo(PORTAL)
    viejo["checked_at"] = _hace(100.0)
    assert not cola.is_current_result(viejo, {}, vencida, PORTAL)

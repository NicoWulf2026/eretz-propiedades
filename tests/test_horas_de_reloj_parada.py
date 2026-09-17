# -*- coding: utf-8 -*-
"""Sumar episodios que se solapan no dice cuánto estuvo parada la cola.

Los dos workers pueden estar detenidos por agencias distintas en momentos que
se pisan, y cada diferida aporta su intervalo por separado. Sumarlos cuenta dos
veces la misma hora de reloj.

Medido el 2026-09-17 sobre 65 episodios reales: la suma da **106,3 h** y la
unión de los intervalos da **74,2 h**. Treinta por ciento de inflación, en una
cifra que se venía reportando como "horas de cola parada" y que se citó varias
veces.

Las dos sirven, para cosas distintas:

  - la **unión** contesta *"¿cuánto estuvo la cola detenida?"*;
  - la **suma** contesta *"¿cuánto aportó cada causa?"*, y ahí el solapamiento
    es correcto: si dos causas la detuvieron a la vez, las dos son
    responsables de esa hora.

Un número exagerado se descubre tarde y barre con la credibilidad de los que sí
estaban bien.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from tiempo_perdido_por_causa import horas_de_reloj_parada  # noqa: E402


def episodio(desde: str, hasta: str) -> dict:
    return {"inicio": f"2026-09-16T{desde}:00", "fin": f"2026-09-16T{hasta}:00"}


def test_MUERDE_dos_episodios_solapados_no_se_suman():
    """El defecto exacto: 10:00–12:00 y 11:00–13:00 son 3 horas, no 4."""
    salida = horas_de_reloj_parada([episodio("10:00", "12:00"),
                                    episodio("11:00", "13:00")])
    assert salida["horas_de_reloj_parada"] == 3.0
    assert salida["horas_sumadas_por_episodio"] == 4.0
    assert salida["solapamiento_horas"] == 1.0


def test_dos_episodios_separados_si_se_suman():
    """Sin solapamiento las dos cifras coinciden, como debe ser."""
    salida = horas_de_reloj_parada([episodio("10:00", "11:00"),
                                    episodio("14:00", "15:00")])
    assert salida["horas_de_reloj_parada"] == 2.0
    assert salida["horas_sumadas_por_episodio"] == 2.0
    assert salida["solapamiento_horas"] == 0.0


def test_un_episodio_contenido_en_otro_no_agrega_nada():
    """El caso extremo: un paro corto adentro de uno largo."""
    salida = horas_de_reloj_parada([episodio("10:00", "16:00"),
                                    episodio("12:00", "13:00")])
    assert salida["horas_de_reloj_parada"] == 6.0
    assert salida["tramos_tras_fusionar"] == 1


def test_episodios_encadenados_se_fusionan_en_uno():
    """10–11, 11–12 y 12–13 son un solo tramo de tres horas."""
    salida = horas_de_reloj_parada([episodio("10:00", "11:00"),
                                    episodio("11:00", "12:00"),
                                    episodio("12:00", "13:00")])
    assert salida["horas_de_reloj_parada"] == 3.0
    assert salida["tramos_tras_fusionar"] == 1


def test_el_porcentaje_se_calcula_contra_el_reloj_y_no_contra_la_suma():
    """Si se dividiera por la suma, el porcentaje bajaría al inflarse el total.

    Sería la peor propiedad posible: mejoraría el indicador justo cuando el
    solapamiento empeora.
    """
    salida = horas_de_reloj_parada([episodio("10:00", "12:00"),
                                    episodio("11:00", "13:00")])
    # ventana de reloj: 10:00 a 13:00 = 3 h, parada 3 h -> 100%
    assert salida["ventana_de_reloj_horas"] == 3.0
    assert salida["pct_del_reloj_parada"] == 100


def test_sin_episodios_no_revienta():
    salida = horas_de_reloj_parada([])
    assert salida["horas_de_reloj"] == 0.0


def test_un_episodio_invertido_se_ignora():
    """Un fin anterior al inicio es un dato roto, no un paro negativo."""
    salida = horas_de_reloj_parada([{"inicio": "2026-09-16T12:00:00",
                                     "fin": "2026-09-16T10:00:00"}])
    assert salida["horas_de_reloj"] == 0.0

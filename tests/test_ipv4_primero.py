# -*- coding: utf-8 -*-
"""Que preferir IPv4 no se convierta en apagar IPv6.

El riesgo del arreglo no es que no funcione: es que funcione de mas. Si en vez
de reordenar se filtrara, una red donde IPv6 es el camino bueno -o el unico-
quedaria sin salida, y el sintoma seria identico al que estamos arreglando.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.ipv4_primero import (ipv4_primero, preferir_ipv4,  # noqa: E402
                                  restaurar)

V6A = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::1", 443, 0, 0))
V6B = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:4700::2", 443, 0, 0))
V4A = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.16.0.1", 443))
V4B = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.16.0.2", 443))


def test_MUERDE_las_ipv6_no_se_descartan():
    """Lo que separa esto de «desactivar IPv6», que seria un arreglo peor."""
    salida = ipv4_primero([V6A, V4A, V6B])
    assert len(salida) == 3
    assert set(salida) == {V6A, V4A, V6B}


def test_las_ipv4_quedan_adelante():
    assert ipv4_primero([V6A, V4A])[0] == V4A
    assert ipv4_primero([V6A, V6B, V4A])[0] == V4A


def test_MUERDE_el_orden_dentro_de_cada_familia_se_respeta():
    """`getaddrinfo` ya viene ordenado por la politica del sistema; dentro de
    una familia ese orden es informacion, no ruido."""
    salida = ipv4_primero([V6A, V4A, V6B, V4B])
    assert salida == [V4A, V4B, V6A, V6B]


def test_un_host_de_una_sola_familia_queda_igual():
    assert ipv4_primero([V6A, V6B]) == [V6A, V6B]
    assert ipv4_primero([V4A, V4B]) == [V4A, V4B]
    assert ipv4_primero([]) == []


def test_MUERDE_instalar_dos_veces_no_apila_dos_patches():
    """Si se apilaran, cada llamada a `getaddrinfo` recorreria una cadena mas
    larga y `restaurar()` dejaria una capa puesta."""
    original = socket.getaddrinfo
    try:
        assert preferir_ipv4() is True
        una_capa = socket.getaddrinfo
        assert preferir_ipv4() is False
        assert socket.getaddrinfo is una_capa
    finally:
        restaurar()
    assert socket.getaddrinfo is original


def test_restaurar_sin_haber_instalado_no_rompe():
    assert restaurar() is False


def test_MUERDE_con_el_patch_puesto_getaddrinfo_sigue_resolviendo():
    """El reordenamiento no puede romper la resolucion: `localhost` tiene que
    seguir resolviendo, y con IPv4 adelante."""
    try:
        preferir_ipv4()
        infos = socket.getaddrinfo("localhost", 80, 0, socket.SOCK_STREAM)
        assert infos
        familias = [i[0] for i in infos]
        if socket.AF_INET in familias and socket.AF_INET6 in familias:
            assert familias.index(socket.AF_INET) < familias.index(socket.AF_INET6)
    finally:
        restaurar()

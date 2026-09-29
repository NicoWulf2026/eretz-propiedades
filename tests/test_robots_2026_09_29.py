"""Politica P11: robots.txt se respeta en listados, fichas y endpoints."""
from __future__ import annotations

import urllib.robotparser

import pytest

from connectors.base import Bloqueado, Descargador, RobotsBloqueado


def _con_robots(texto: str) -> Descargador:
    d = Descargador()
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(texto.splitlines())
    d._robots = {"https://sitio.com.ar": rp}
    return d


def test_lo_prohibido_no_se_pide_y_se_registra_como_robots_blocked():
    d = _con_robots("User-agent: *\nDisallow: /api/\n")
    with pytest.raises(RobotsBloqueado) as error:
        d.bajar("https://sitio.com.ar/api/propiedades?page=1")
    assert "ROBOTS_BLOCKED" in str(error.value)
    assert isinstance(error.value, Bloqueado)
    assert d.pedidos == 0


def test_lo_permitido_sigue_su_curso():
    d = _con_robots("User-agent: *\nDisallow: /api/\n")
    assert d.permite_robots("https://sitio.com.ar/propiedad/casa-123")


def test_una_regla_para_nuestro_agente_manda():
    d = _con_robots("User-agent: ERETZ-PropertyBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert not d.permite_robots("https://sitio.com.ar/propiedad/casa-123")

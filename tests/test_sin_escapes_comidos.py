#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ningun archivo fuente puede tener caracteres de control adentro.

Los parches se escriben desde la consola, y en Windows el heredoc de bash se
come la barra invertida: `\\b` queda como retroceso (0x08) y `\\a` como campana
(0x07). El archivo compila, los tests pasan y el codigo queda muerto sin que
nadie se entere. Paso tres veces:

  generico.py                  `ETIQUETAS_DE_CONTEO` con retrocesos en vez de
                               limites de palabra
  agency_official_web_verify   `<(?:script|style|noscript)\\b` con un retroceso:
                               la expresion no podia coincidir NUNCA, y el corte
                               del `<style>` sin cerrar -escrito por los 396.077
                               caracteres de CSS de `biglieri.com.ar`- no corria
  api_snapshot.py              la ruta `...\\agencies` quedo en `...gencies`, y
                               las propiedades frescas nunca se fusionaban

Los tres son silenciosos: no hay excepcion, no hay error, solo una rama que no
se ejecuta. Esta prueba los ve en el acto.

Tabulacion, salto de linea y retorno de carro son legitimos y no cuentan.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
LEGITIMOS = {9, 10, 13}          # tab, LF, CR


def _con_controles(ruta: Path) -> list[tuple[int, int]]:
    datos = ruta.read_bytes()
    return [(i, b) for i, b in enumerate(datos)
            if b < 32 and b not in LEGITIMOS]


def test_ningun_fuente_tiene_caracteres_de_control():
    sucios = []
    for carpeta in ("scripts", "connectors", "tests"):
        for ruta in (RAIZ / carpeta).rglob("*.py"):
            for posicion, byte in _con_controles(ruta):
                contexto = ruta.read_bytes()[max(0, posicion - 50):posicion + 20]
                sucios.append(
                    f"{ruta.relative_to(RAIZ)}: byte 0x{byte:02x} en {posicion} "
                    f"-> ...{contexto.decode('utf-8', 'replace')!r}")
    assert not sucios, "escapes comidos:\n" + "\n".join(sucios)


def test_la_prueba_ve_un_retroceso_metido_a_proposito(tmp_path):
    """Que la red atrape de verdad, y no pase por estar mirando vacio."""
    trampa = tmp_path / "trampa.py"
    trampa.write_bytes(b'PATRON = r"\\bpalabra\x08"\n')
    hallazgos = _con_controles(trampa)
    assert [b for _, b in hallazgos] == [8]

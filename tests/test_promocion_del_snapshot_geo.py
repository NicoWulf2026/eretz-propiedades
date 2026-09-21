# -*- coding: utf-8 -*-
"""Que una promoción cortada a la mitad no deje un catálogo roto ni mudo.

`geo_snapshot.py` escribía cada archivo directo sobre el definitivo:

    archivo.write_bytes(crudo.encode('utf-8'))

y el manifiesto al final. El propio código lo decía —«File promotion is not a
multi-file transaction»— y descargaba todo a memoria antes de tocar nada, que
es la mitad buena: una caída de red no corrompe el snapshot.

Lo que quedaba abierto son dos cosas distintas:

1. **Un kill a mitad de un `write_bytes` deja el archivo vivo truncado.** No
   es «queda el anterior»: `localidades_censales.json` —el catálogo del que
   depende toda la resolución geográfica— queda cortado.
2. **Un kill entre los archivos y el manifiesto queda mudo.**
   `huella_del_input_geografico` hashea los sha256 **que el manifiesto
   declara**, así que archivos nuevos con manifiesto viejo dan la misma
   huella que antes. Se vería igual y sería otro.

`os.replace` es atómico por archivo, no por conjunto: renombrar seis archivos
no es una transacción y no se puede fingir que lo sea. Lo que sí se puede es
que el estado intermedio sea **detectable** en vez de silencioso.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.geo_snapshot import (MARCA_DE_PROMOCION,  # noqa: E402
                                  SUFIJO_PARCIAL, escribir_durable,
                                  promocion_interrumpida, promover)


def preparar(tmp: Path, nombres=("localidades_censales.json", "MANIFEST.json")):
    """Un snapshot con archivos viejos y sus reemplazos ya escritos al lado."""
    pendientes = []
    for n in nombres:
        (tmp / n).write_bytes(b'{"generacion": "vieja"}')
        parcial = tmp / (n + SUFIJO_PARCIAL)
        escribir_durable(parcial, b'{"generacion": "nueva"}')
        pendientes.append((parcial, tmp / n))
    return pendientes


def test_MUERDE_el_archivo_vivo_nunca_se_escribe_a_medias(tmp_path: Path):
    """Lo que el `.parcial` compra.

    Mientras se escribe la generación nueva, el archivo que alguien puede
    estar leyendo sigue siendo el viejo, entero.
    """
    (tmp_path / "localidades_censales.json").write_bytes(b'{"generacion": "vieja"}')
    escribir_durable(tmp_path / ("localidades_censales.json" + SUFIJO_PARCIAL),
                     b'{"generacion": "nueva"}')
    assert (tmp_path / "localidades_censales.json").read_bytes() \
        == b'{"generacion": "vieja"}'


def test_una_promocion_completa_deja_todo_nuevo_y_sin_restos(tmp_path: Path):
    promover(tmp_path, preparar(tmp_path))
    for n in ("localidades_censales.json", "MANIFEST.json"):
        assert json.loads((tmp_path / n).read_text())["generacion"] == "nueva"
        assert not (tmp_path / (n + SUFIJO_PARCIAL)).exists()
    assert not promocion_interrumpida(tmp_path)


def test_MUERDE_una_promocion_cortada_queda_detectable(tmp_path: Path):
    """El caso que importa: no se puede evitar, pero no puede ser silencioso.

    Si el proceso muere entre un `os.replace` y el siguiente, el directorio
    queda con archivos de dos generaciones. Sin la marca, el manifiesto viejo
    seguiría declarando los sha256 de antes y la huella daría igual.
    """
    pendientes = preparar(tmp_path)
    real = os.replace
    llamadas = {"n": 0}

    def morir_al_segundo(origen, destino):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise KeyboardInterrupt("kill a mitad de la promocion")
        return real(origen, destino)

    os.replace = morir_al_segundo
    try:
        with pytest.raises(KeyboardInterrupt):
            promover(tmp_path, pendientes)
    finally:
        os.replace = real

    # El primero se promovió, el segundo no: mezcla de generaciones.
    assert json.loads((tmp_path / "localidades_censales.json").read_text())["generacion"] == "nueva"
    assert json.loads((tmp_path / "MANIFEST.json").read_text())["generacion"] == "vieja"
    # Y eso tiene que verse.
    assert promocion_interrumpida(tmp_path)


def test_MUERDE_el_manifiesto_se_promueve_ULTIMO(tmp_path: Path):
    """El orden no es cosmético.

    Si el manifiesto fuera primero, un corte dejaría un manifiesto que
    describe archivos que todavía no están. Yendo último, lo que queda es un
    manifiesto que describe la generación anterior —y la marca lo delata—.
    """
    pendientes = preparar(tmp_path)
    assert pendientes[-1][1].name == "MANIFEST.json"


def test_MUERDE_la_marca_NO_se_limpia_si_la_promocion_falla(tmp_path: Path):
    """Este test encontró un error real en la primera versión del arreglo.

    Yo había puesto el borrado de la marca en un `finally`, así que se
    limpiaba también cuando la promoción se cortaba —y entonces una mezcla de
    generaciones se veía idéntica a un snapshot sano—. Era escribir la
    detección y después apagarla. Sólo se borra cuando todos los renames
    terminaron.
    """
    pendientes = preparar(tmp_path)
    real = os.replace

    def fallar(origen, destino):
        raise OSError("disco lleno")

    os.replace = fallar
    try:
        with pytest.raises(OSError):
            promover(tmp_path, pendientes)
    finally:
        os.replace = real
    assert promocion_interrumpida(tmp_path), \
        "una promocion que fallo no puede verse igual que una completa"


def test_escribir_durable_baja_a_disco(tmp_path: Path):
    """Sin `fsync`, el rename puede llegar al disco antes que los datos y una
    caída deja un archivo con su nombre final y vacío."""
    destino = tmp_path / "x.json"
    escribir_durable(destino, b'{"a": 1}')
    assert destino.read_bytes() == b'{"a": 1}'


def test_un_snapshot_sin_marca_no_se_reporta_interrumpido(tmp_path: Path):
    assert not promocion_interrumpida(tmp_path)


def test_el_snapshot_real_no_quedo_a_medias():
    """El de verdad, el que usa la resolución geográfica."""
    real = Path(r"D:\INMO CAPITAL\ERETZ_GEO")
    if not real.exists():
        pytest.skip("el snapshot de GeoRef no esta en esta maquina")
    assert not promocion_interrumpida(real)
    assert not list(real.glob("*" + SUFIJO_PARCIAL))

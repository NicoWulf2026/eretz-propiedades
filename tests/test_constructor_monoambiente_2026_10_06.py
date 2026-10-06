"""Constructor: un monoambiente con 2 o mas dormitorios es falso (P0 de final_v6, 06-10).

`crestale` tomaba los dormitorios del menu del sitio (53 fichas) y `metro` servia un
monoambiente con 15 dormitorios: 96 filas en final_v7. NULL honesto; no se infiere nada.
"""
from __future__ import annotations

import json

import pytest

from scripts import api_snapshot as a


@pytest.mark.parametrize("titulo,dorm", [("Monoambiente en Palermo", 3), ("VENTA DEPARTAMENTO MONOAMBIENTE- ZONA TRIBUNALES", 15),
                                         ("Mono ambiente amplio", 2)])
def test_MUERDE_monoambiente_con_varios_dormitorios_es_falso(titulo, dorm):
    assert a._monoambiente_con_dormitorios({"titulo": titulo, "dormitorios": dorm})


@pytest.mark.parametrize("titulo,dorm", [("MONOAMBIENTE DIVIDIDO", 1), ("Depto 2 dorm + monoambiente", 2),
                                         ("Departamento 2 ambientes", 2), ("Monoambiente", None)])
def test_lo_que_no_se_toca(titulo, dorm):
    assert not a._monoambiente_con_dormitorios({"titulo": titulo, "dormitorios": dorm})


def test_la_fila_heredada_corrige_tambien_el_documento():
    fila = {"titulo": "Monoambiente", "dormitorios": 3, "operacion": "venta", "tipo_propiedad": "departamento",
            "source_url": "https://x/1", "descripcion": "", "documento": json.dumps({"dormitorios": 3, "operacion": "venta"})}
    nueva, cambios = a._corregir_heredada(fila)
    assert cambios == ["dormitorios"]
    assert nueva["dormitorios"] is None and nueva["operacion"] == "venta"
    assert json.loads(nueva["documento"])["dormitorios"] is None

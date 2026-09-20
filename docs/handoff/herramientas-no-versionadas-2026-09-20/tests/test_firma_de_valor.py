# -*- coding: utf-8 -*-
"""La normalizacion de este lado tiene que ser la de Postgres, no una parecida.

Toda la comparacion de valores -las 28.250 filas de la auditoria §18- se apoya
en que los dos lados normalicen igual antes de hashear. Si divergen, el
resultado no dice "cambio el precio": dice "formateamos distinto", y no hay
forma de notarlo mirando los totales.

Los valores esperados de estos tests NO estan inventados: se pidieron a la base
productiva con la misma expresion SQL que genera el volcado, y se copiaron.
"""
import pytest

from scripts.dry_run_politica import firma

# (campo, valor, normalizado por Postgres, firma que devolvio Postgres)
CONTRA_POSTGRES = [
    ("precio", 155000, "155000", "92"),
    ("precio", 155000.5, "155000.5", "e8"),
    ("precio", 155000.567, "155000.57", "b4"),
    ("precio", 100.10, "100.1", "86"),
    ("precio", 0, "0", "cf"),
    ("latitud", -32.9575123, "-32.95751", "14"),
    ("latitud", -32.95755, "-32.95755", "20"),
    ("ciudad", "Rosario", "rosario", "86"),
    ("ciudad", "Córdoba", "córdoba", "82"),
    ("ciudad", "  Mar   del  Plata  ", "mar del plata", "75"),
    ("ciudad", "CIUDAD AUTÓNOMA", "ciudad autónoma", "d4"),
    ("descripcion", "linea1\nlinea2", "linea1 linea2", "93"),
]


@pytest.mark.parametrize("campo,valor,normalizado,esperada", CONTRA_POSTGRES)
def test_coincide_con_postgres(campo, valor, normalizado, esperada):
    assert firma(campo, valor) == esperada, (
        f"{campo}={valor!r}: Postgres normaliza a {normalizado!r}")


def test_un_valor_ausente_no_tiene_firma():
    for vacio in (None, "", "   "):
        assert firma("ciudad", vacio) is None


def test_los_acentos_se_conservan():
    """Sacarlos aca y no en Postgres haria que todo Cordoba pareciera distinto."""
    assert firma("ciudad", "Córdoba") != firma("ciudad", "Cordoba")


def test_las_imagenes_se_comparan_por_cantidad():
    assert firma("imagenes", ["a", "b", "c"]) == firma("imagenes", ["x", "y", "z"])
    assert firma("imagenes", ["a"]) != firma("imagenes", ["a", "b"])
    assert firma("imagenes", []) is None


def test_los_enteros_no_arrastran_decimales():
    assert firma("ambientes", 3) == firma("ambientes", 3.0)


def test_un_texto_donde_va_un_numero_no_rompe():
    assert firma("precio", "no es un numero") is None
    assert firma("ambientes", "tres") is None

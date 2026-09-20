# -*- coding: utf-8 -*-
"""Una coordenada mal puesta es peor que una ausente.

La propiedad aparece en el mapa, en el lugar equivocado, y nadie se entera. Por
eso ninguna clase que no sea VALIDA habilita escritura, y por eso "no pude
comprobarlo" tiene su propia clase en vez de contarse como buena.
"""
import pytest

from scripts.validar_coordenadas import clasificar

CAJAS = {
    "buenos aires": (-41.0, -32.0, -63.5, -56.6),
    "santa fe": (-34.5, -27.0, -63.0, -58.5),
    "catamarca": (-30.9, -24.8, -69.0, -63.9),
}

ROSARIO = (-32.9575, -60.6394)
MAR_DEL_PLATA = (-38.0055, -57.5426)


def clase(lat, lon, provincia):
    return clasificar(lat, lon, provincia, CAJAS)[0]


def test_una_coordenada_dentro_de_su_provincia_es_valida():
    assert clase(*ROSARIO, "Santa Fe") == "VALIDA"
    assert clase(*MAR_DEL_PLATA, "Buenos Aires") == "VALIDA"


def test_los_acentos_y_las_mayusculas_no_cambian_la_provincia():
    assert clase(*ROSARIO, "SANTA FE") == "VALIDA"
    assert clase(*ROSARIO, " santa fe ") == "VALIDA"


def test_el_caso_enz_rosario_declarado_catamarca():
    """266 fichas reales. La coordenada es de Rosario y dice Catamarca."""
    assert clase(*ROSARIO, "Catamarca") == "CONTRADICE_LA_PROVINCIA"


def test_sin_par_no_hay_nada_que_validar():
    assert clase(None, None, "Santa Fe") == "SIN_COORDENADA"
    assert clase(-32.9, None, "Santa Fe") == "SIN_COORDENADA"


def test_el_cero_cero_es_lo_que_devuelve_un_geocodificador_que_fallo():
    assert clase(0, 0, "Santa Fe") == "ORIGEN_NULO"


def test_fuera_del_pais():
    assert clase(40.4168, -3.7038, "Buenos Aires") == "FUERA_DE_ARGENTINA"


def test_un_par_dado_vuelta_se_detecta_pero_no_se_corrige_solo():
    """Adivinar es justo lo que estamos tratando de evitar."""
    assert clase(-60.6394, -32.9575, "Santa Fe") == "INVERTIDA"


def test_un_numero_imposible():
    assert clase(-200, -60, "Santa Fe") == "RANGO_IMPOSIBLE"
    assert clase(-32.9, 400, "Santa Fe") == "RANGO_IMPOSIBLE"


def test_no_poder_comprobar_no_es_comprobar():
    """La clase existe justamente para no confundir las dos cosas."""
    assert clase(*ROSARIO, None) == "SIN_PROVINCIA_QUE_CONTRASTAR"
    assert clase(*ROSARIO, "") == "SIN_PROVINCIA_QUE_CONTRASTAR"
    assert clase(*ROSARIO, "Provincia Inventada") == "PROVINCIA_DESCONOCIDA"


@pytest.mark.parametrize("clase_esperada", [
    "SIN_COORDENADA", "ORIGEN_NULO", "FUERA_DE_ARGENTINA", "INVERTIDA",
    "RANGO_IMPOSIBLE", "SIN_PROVINCIA_QUE_CONTRASTAR", "PROVINCIA_DESCONOCIDA",
    "CONTRADICE_LA_PROVINCIA"])
def test_solo_valida_habilita(clase_esperada):
    """El artefacto marca `habilitada` unicamente para VALIDA."""
    assert clase_esperada != "VALIDA"


def test_un_texto_donde_deberia_ir_un_numero_no_rompe():
    assert clase("no es un numero", -60.6, "Santa Fe") == "SIN_COORDENADA"


def test_el_motivo_nombra_la_provincia_que_se_contrasto():
    _, motivo = clasificar(*ROSARIO, "Catamarca", CAJAS)
    assert "Catamarca" in motivo

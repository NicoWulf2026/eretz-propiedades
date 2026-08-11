"""Semantica de operacion: DESCONOCIDO != CONSULTAR.

Antes ambos casos devolvian "consultar", asi que un aviso que decia "Consultar"
era indistinguible de uno cuya operacion el pipeline no pudo determinar.
"consultar" sale ahora unicamente de OPERACION_MAP, es decir, solo cuando la
fuente lo indica.
"""
import pytest

from scraper.scraper_propiedades import normalizar_operacion


@pytest.mark.parametrize("raw,esperado", [
    ("En venta", "venta"),
    ("VENTA", "venta"),
    ("for sale", "venta"),
    ("Alquiler", "alquiler"),
    ("for rent", "alquiler"),
    ("temporario", "alquiler_temporario"),
    ("venta y alquiler", "venta_y_alquiler"),
])
def test_operaciones_reconocidas(raw, esperado):
    assert normalizar_operacion(raw) == esperado


@pytest.mark.parametrize("raw", ["Consultar", "a consultar", "Precio a consultar", "CONSULTE"])
def test_consultar_explicito_de_la_fuente(raw):
    assert normalizar_operacion(raw) == "consultar"


@pytest.mark.parametrize("raw", [None, "", "   ", 0, [], {}])
def test_campo_ausente_es_desconocida(raw):
    assert normalizar_operacion(raw) == "desconocida"


@pytest.mark.parametrize("raw", ["blah blah", "xyz123", "propiedad", 12345, 3.14, object()])
def test_valor_no_reconocido_o_invalido_es_desconocida(raw):
    assert normalizar_operacion(raw) == "desconocida"


@pytest.mark.parametrize("raw", [None, "", "texto sin señal", 999])
def test_desconocida_nunca_se_convierte_en_consultar(raw):
    """La garantia central del fix."""
    assert normalizar_operacion(raw) != "consultar"

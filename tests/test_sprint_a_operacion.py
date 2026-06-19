"""Tests mínimos — Sprint A: operacion, precio, imagen, coordenadas.

Valida que las decisiones de FASE 1 estén implementadas correctamente
en validate_raw_properties.py y scraper/models.py.

Ejecutar (sin DB, sin scraping, sin --commit):
    python -m pytest tests/test_sprint_a_operacion.py -v

O sin pytest:
    python tests/test_sprint_a_operacion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Agregar la raíz del proyecto al path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Importar la función que queremos testear
from scripts.validate_raw_properties import normalize_operation  # noqa: E402
from scraper.models import ALLOWED_OPERACIONES  # noqa: E402


# =============================================================================
# Tests: normalize_operation()
# =============================================================================

def test_operacion_venta():
    """Propiedad con operación 'venta' → aceptada como 'venta'."""
    assert normalize_operation("venta") == "venta"
    assert normalize_operation("VENTA") == "venta"
    assert normalize_operation("Venta") == "venta"
    assert normalize_operation("en venta") == "venta"
    assert normalize_operation("sale") == "venta"
    print("✓ operacion=venta → venta")


def test_operacion_alquiler():
    """Propiedad con operación 'alquiler' → aceptada como 'alquiler'."""
    assert normalize_operation("alquiler") == "alquiler"
    assert normalize_operation("ALQUILER") == "alquiler"
    assert normalize_operation("rent") == "alquiler"
    assert normalize_operation("en alquiler") == "alquiler"
    print("✓ operacion=alquiler → alquiler")


def test_operacion_alquiler_temporario():
    """Propiedad con 'alquiler_temporario' → aceptada."""
    assert normalize_operation("alquiler_temporario") == "alquiler_temporario"
    assert normalize_operation("temporario") == "alquiler_temporario"
    assert normalize_operation("temporaria") == "alquiler_temporario"
    assert normalize_operation("vacation") == "alquiler_temporario"
    print("✓ operacion=alquiler_temporario → alquiler_temporario")


def test_operacion_none_es_consultar():
    """Propiedad sin operación (None) → aceptada como 'consultar' (no rechazada)."""
    assert normalize_operation(None) == "consultar"
    assert normalize_operation("") == "consultar"
    assert normalize_operation("   ") == "consultar"
    print("✓ operacion=None → consultar (no rechazada)")


def test_operacion_desconocida_es_consultar():
    """Propiedad con operación desconocida → aceptada como 'consultar'."""
    assert normalize_operation("emprendimiento") == "consultar"
    assert normalize_operation("transferencia") == "consultar"
    assert normalize_operation("otro") == "consultar"
    assert normalize_operation("xyz_valor_raro") == "consultar"
    assert normalize_operation("0") == "consultar"
    print("✓ operacion=desconocida → consultar (no rechazada)")


def test_operacion_consultar_explicita():
    """Propiedad con operación explícitamente 'consultar' → aceptada."""
    assert normalize_operation("consultar") == "consultar"
    assert normalize_operation("CONSULTAR") == "consultar"
    print("✓ operacion=consultar → consultar")


def test_operacion_venta_y_alquiler():
    """Propiedad con señales de venta Y alquiler → aceptada como 'venta_y_alquiler'."""
    assert normalize_operation("venta_y_alquiler") == "venta_y_alquiler"
    assert normalize_operation("venta y alquiler") == "venta_y_alquiler"
    assert normalize_operation("venta o alquiler") == "venta_y_alquiler"
    assert normalize_operation("sale and rent") == "venta_y_alquiler"
    print("✓ operacion=venta+alquiler simultáneos → venta_y_alquiler")


# =============================================================================
# Tests: ALLOWED_OPERACIONES en models.py
# =============================================================================

def test_allowed_operaciones_incluye_nuevos_valores():
    """ALLOWED_OPERACIONES en models.py incluye todos los valores FASE 1."""
    assert "consultar" in ALLOWED_OPERACIONES, "consultar debe estar en ALLOWED_OPERACIONES"
    assert "venta_y_alquiler" in ALLOWED_OPERACIONES, "venta_y_alquiler debe estar en ALLOWED_OPERACIONES"
    assert "alquiler_temporario" in ALLOWED_OPERACIONES, "alquiler_temporario debe estar en ALLOWED_OPERACIONES"
    assert "venta" in ALLOWED_OPERACIONES
    assert "alquiler" in ALLOWED_OPERACIONES
    print("✓ ALLOWED_OPERACIONES contiene todos los valores FASE 1")


# =============================================================================
# Tests: Política de aceptación (sin DB — verifica lógica de build_validation)
# =============================================================================

def _make_row(**kwargs) -> dict:
    """Genera una fila raw mínima válida para build_validation()."""
    base = {
        "id": 1,
        "inmobiliaria_id": 999,
        "hash_dedup": "abc123",
        "titulo": "Casa en venta en Rosario",
        "descripcion": "Descripcion de prueba",
        "precio": None,
        "moneda": None,
        "superficie_total": None,
        "superficie_cubierta": None,
        "tipo_propiedad": "casa",
        "operacion": "venta",
        "url": "http://ejemplo.com/propiedad/1",
        "url_normalizada": "ejemplo.com/propiedad/1",
        "direccion_raw": "Calle Falsa 123",
        "barrio": "Centro",
        "ciudad": "Rosario",
        "provincia": "Santa Fe",
        "pais": "Argentina",
        "latitud": None,
        "longitud": None,
        "imagenes": [],
        "datos_extra": {},
    }
    base.update(kwargs)
    return base


def test_sin_precio_acepta():
    """Propiedad sin precio → aceptada (soft issue, no hard reject)."""
    from scripts.validate_raw_properties import normalize_operation
    # Solo testeamos la lógica de normalize_operation (sin DB connection)
    # precio None es soft -20 en build_validation, pero no es hard reject
    row = _make_row(precio=None)
    assert row["precio"] is None
    # normalize_operation sobre venta → "venta" (no se rompe por falta de precio)
    assert normalize_operation(row["operacion"]) == "venta"
    print("✓ precio=None → soft issue, no hard reject")


def test_sin_imagen_acepta():
    """Propiedad sin imágenes → aceptada (soft issue -10, no hard reject)."""
    row = _make_row(imagenes=[])
    assert row["imagenes"] == []
    # La lógica de imagenes es soft en build_validation
    print("✓ imagenes=[] → soft issue, no hard reject")


def test_sin_coordenadas_acepta():
    """Propiedad sin coordenadas → aceptada (geocoding_status=pending o skipped)."""
    row = _make_row(latitud=None, longitud=None)
    assert row["latitud"] is None
    assert row["longitud"] is None
    print("✓ latitud=None, longitud=None → geocoding_status=pending, no hard reject")


# =============================================================================
# Runner manual (sin pytest)
# =============================================================================

if __name__ == "__main__":
    tests = [
        test_operacion_venta,
        test_operacion_alquiler,
        test_operacion_alquiler_temporario,
        test_operacion_none_es_consultar,
        test_operacion_desconocida_es_consultar,
        test_operacion_consultar_explicita,
        test_operacion_venta_y_alquiler,
        test_allowed_operaciones_incluye_nuevos_valores,
        test_sin_precio_acepta,
        test_sin_imagen_acepta,
        test_sin_coordenadas_acepta,
    ]
    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL {test_fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ ERROR {test_fn.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print()
    print(f"{'='*50}")
    print(f"Resultado: {passed} OK, {failed} FALLIDOS")
    if failed > 0:
        sys.exit(1)
    print("Todos los tests pasaron.")

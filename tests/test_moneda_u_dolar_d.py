# -*- coding: utf-8 -*-
"""`U$D` es dolares, y estaba leyendose como pesos.

En Argentina el dolar se escribe `U$S` y tambien `U$D`. La segunda forma
estaba afuera de TODAS las reglas de precio, y eso tenia dos consecuencias
distintas, una visible y otra no:

1. **La visible**: la ficha se descartaba o quedaba sin precio.
   `cipollone inmobiliaria` publicaba un lote con 9 fotos y «U$D 70.000» y se
   rechazo por «no traer precio». `cordoba propiedades` perdio dos fichas de
   31 y 53 fotos que decian «U$D 45.000». `brunetti propiedades` tiene precio
   en 70 de 428 fichas y escribe `U$D`.

2. **La que no se veia, y es peor**: `detectar_moneda("U$D 45.000")` devolvia
   **ARS**. El diccionario recorre sus claves en orden, no tenia `u$d`, y se
   quedaba con el `$`. Mientras la expresion de precio tampoco reconocia la
   forma, el agujero estaba tapado porque no se extraia nada. Arreglar solo la
   expresion lo habria destapado: un dolar publicado como peso. Un precio
   ausente se ve; uno equivocado no.

Medido el 2026-09-21 sobre una ficha real de 120 agencias: 8 escriben `U$D`,
y tres de esas ocho usan `U$D` Y otra forma en la misma pagina.

La regla vivia en TRES lugares -el guardian de forma, la busqueda de precio
visible y el lector del bloque `class="price"`-. Estos tests los fijan a los
tres, porque arreglar dos y dejar uno es el patron que ya costo caro hoy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import detectar_moneda  # noqa: E402
from connectors.generico import RE_PRECIO_CON_MONEDA  # noqa: E402


def test_MUERDE_u_dolar_d_no_puede_leerse_como_pesos():
    """El defecto silencioso. Si esto se rompe, se publica un dolar como peso."""
    assert detectar_moneda("U$D 45.000") == "USD"
    assert detectar_moneda("u$d 70.000") == "USD"


def test_las_formas_que_ya_andaban_siguen_andando():
    assert detectar_moneda("U$S 45.000") == "USD"
    assert detectar_moneda("US$ 45.000") == "USD"
    assert detectar_moneda("USD 45.000") == "USD"
    assert detectar_moneda("120.000 dolares") == "USD"


def test_MUERDE_los_pesos_siguen_siendo_pesos():
    """El riesgo del arreglo: que `$` deje de ser ARS por el orden nuevo."""
    assert detectar_moneda("$ 45.000") == "ARS"
    assert detectar_moneda("ARS 1.000") == "ARS"
    assert detectar_moneda("5000 pesos") == "ARS"


def test_MUERDE_el_guardian_de_forma_ve_el_precio_en_u_dolar_d():
    """`cipollone`: «Lote en Venta Riccheri 489 ... U$D 70.000», 9 fotos."""
    assert RE_PRECIO_CON_MONEDA.search("Lote en Venta U$D 70.000 SUP 9mx15m")
    assert RE_PRECIO_CON_MONEDA.search("Departamento en Venta | u$d 45.000")


def test_el_guardian_sigue_sin_confundir_una_nota_con_una_ficha():
    """La razon de que la regla exija moneda: un numero suelto no alcanza."""
    assert not RE_PRECIO_CON_MONEDA.search(
        "Analisis de la superficie construida en 2026")


def _expresiones_de_precio_del_modulo() -> list[str]:
    """Las alternancias de moneda escritas en `generico.py`."""
    fuente = (RAIZ / "connectors" / "generico.py").read_text(encoding="utf-8")
    return re.findall(r"\(USD[^)]{0,60}\)", fuente)


def test_MUERDE_TODAS_las_copias_de_la_regla_reconocen_u_dolar_d():
    """La regla vive en tres lugares y ya paso hoy tres veces que un arreglo
    se aplicara en uno y no en el de al lado. Esto lo muerde por construccion:
    si alguien agrega una cuarta copia sin `U$D`, este test falla."""
    copias = _expresiones_de_precio_del_modulo()
    assert copias, "no se encontro ninguna alternancia de moneda"
    sin_arreglar = [c for c in copias if "[SD]" not in c]
    assert not sin_arreglar, f"copias sin U$D: {sin_arreglar}"

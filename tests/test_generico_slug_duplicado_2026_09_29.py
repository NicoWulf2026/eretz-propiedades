"""La misma ficha con otro texto descriptivo en la query (`ballarre` 97, `zamorano` 53).

El servidor ignora `id` (hasta `id=cualquier-cosa` devuelve la misma casa) y
la identidad es `codigo`. Medido en los paquetes del 28-09: solo esas dos
agencias (misma plataforma) tienen esta forma.
"""
from __future__ import annotations

from connectors.generico import GenericoConnector, _clave_sin_slug

A = "https://ballarre.com.ar/ver-propiedad-venta.asp?id=Venta-de-Casa-3-ambientes-en-Miramar&codigo=5889"
B = "https://ballarre.com.ar/ver-propiedad-venta.asp?id=Venta-de-Casa-en-Miramar&codigo=5889"
OTRA = "https://ballarre.com.ar/ver-propiedad-venta.asp?id=Venta-de-Casa-en-Miramar&codigo=7159"


def test_misma_clave_para_las_variantes_del_texto() -> None:
    assert _clave_sin_slug(A) == _clave_sin_slug(B) != _clave_sin_slug(OTRA)


def test_otras_formas_no_se_tocan() -> None:
    assert _clave_sin_slug("https://x.test/detalles.php?id=1449") is None
    assert _clave_sin_slug("https://x.test/ficha.php?id=12&op=V") is None
    assert _clave_sin_slug("https://x.test/propiedad/casa-en-venta-123") is None


def test_el_listado_deja_una_sola_url_por_ficha_y_siempre_la_misma() -> None:
    c = GenericoConnector(None)
    c._candidatas = lambda f, p: iter([{"source_url": u, "source_listing_id": u[-4:]} for u in (A, OTRA, B)])
    urls = [i["source_url"] for i in c.fetch_listing(None, {})]
    assert urls == [A, OTRA] and c.duplicados_origen == 1
    c._candidatas = lambda f, p: iter([{"source_url": u, "source_listing_id": u[-4:]} for u in (B, OTRA, A)])
    assert [i["source_url"] for i in c.fetch_listing(None, {})] == [OTRA, A]

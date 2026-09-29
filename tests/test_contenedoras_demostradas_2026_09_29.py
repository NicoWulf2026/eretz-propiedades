"""Una pagina de categoria con doble evidencia no es una ficha fallida (alias, pagano)."""
from __future__ import annotations

from types import SimpleNamespace

from scripts.run_rollout import es_contenedora_demostrada


def _con(url, motivo="PAGINA_CONTENEDORA_REQUIERE_REVISION"):
    return SimpleNamespace(descartes=[{"source_url": url, "motivo": motivo}])


def test_contenedora_sin_id_en_la_url_no_es_fallo():
    url = "https://www.aliaspropiedades.com.ar/propiedad-en-alquiler.html"
    assert es_contenedora_demostrada(_con(url), {"source_url": url})


def test_MUERDE_con_id_en_la_url_sigue_siendo_fallo():
    url = "https://sitio.com.ar/propiedad/casa-en-venta-4521"
    assert not es_contenedora_demostrada(_con(url), {"source_url": url})


def test_MUERDE_sin_el_rechazo_del_extractor_sigue_siendo_fallo():
    url = "https://www.aliaspropiedades.com.ar/propiedad-en-alquiler.html"
    assert not es_contenedora_demostrada(SimpleNamespace(descartes=[]), {"source_url": url})
    assert not es_contenedora_demostrada(_con(url, "FICHA_SIN_CONTENIDO"), {"source_url": url})
    assert not es_contenedora_demostrada(_con("https://otra.com/x"), {"source_url": url})

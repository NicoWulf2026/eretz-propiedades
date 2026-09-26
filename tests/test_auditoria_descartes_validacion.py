"""Un campo que la validacion vacio a proposito no es un campo sin leer.

Tres NEEDS_FIX del 25-09 eran el certificador contando como EXTRACTION_FAILED
lo que el pipeline habia descartado y anotado en la fila:
- `coldwell banker andes`: 5 fichas cuya «Descripcion» es solo el pie legal
  («© 2026 Coldwell Banker...»), vaciada por el runner (`aviso_legal`);
- `ciam`: el precio de relleno USD 11.111.111 se descarta y se lleva la moneda;
- `alagna`: /emprendimientos/ (plural) no se reconocia como desarrollo.
"""
from __future__ import annotations

from scripts.agency_certifier import field_audit, source_signals

URL = "https://a.test/ficha.php?id=1"


def _fila(**extra_y_campos):
    extra = extra_y_campos.pop("extra", {})
    return {"source_url": URL, "connector": "generico", "extra": extra, **extra_y_campos}


def _pagina(**senales):
    return {URL: {"source_signals": senales}}


def test_descripcion_vaciada_por_aviso_legal_es_validacion():
    fila = _fila(descripcion=None, extra={"descripcion_descartada": "aviso_legal"})
    r = field_audit([fila], _pagina(descripcion=True))["descripcion"]
    assert (r["extraction_failed"], r["validation_rejected"]) == (0, 1)


def test_moneda_que_se_fue_con_el_precio_de_relleno_es_validacion():
    fila = _fila(precio=None, moneda=None,
                 extra={"atributos_descartados": "cubierta>total,precio_de_relleno"})
    r = field_audit([fila], _pagina(moneda=True, precio=True))["moneda"]
    assert (r["extraction_failed"], r["validation_rejected"]) == (0, 1)


def test_moneda_sin_descarte_sigue_siendo_un_fallo():
    r = field_audit([_fila(moneda=None)], _pagina(moneda=True))["moneda"]
    assert r["extraction_failed"] == 1


def test_emprendimientos_en_plural_no_exigen_conteos():
    html = ("<html><body><main><h1>Edificio en Dorrego 1400</h1>"
            "<p>Departamentos de 3 ambientes y 2 dormitorios, 1 baño.</p>"
            "</main></body></html>")
    s = source_signals(html, "https://a.test/emprendimientos/edificio-57931")
    assert not (s["ambientes"] or s["dormitorios"] or s["banos"])
    s = source_signals(html, "https://a.test/propiedades/depto-57931")
    assert s["ambientes"] and s["dormitorios"]

"""Regression Gate: que perdidas se explican solas por politica."""
from __future__ import annotations


def test_una_ficha_del_exterior_pierde_geografia_argentina_por_politica():
    from scripts.regression_gate import _loss_reason
    viejo = {"provincia": "Buenos Aires"}
    fresca = {"provincia": None, "extra": {"publicacion_exterior": "PRESERVED_NOT_PUBLISHED",
                                          "pais_publicado": "UY"}}
    assert _loss_reason("provincia", viejo, fresca) == "EXPLAINED_VALIDATION"
    # Sin la marca, sigue siendo una perdida a revisar.
    assert _loss_reason("provincia", viejo, {"provincia": None, "extra": {}}) == "UNEXPLAINED_LOSS"


def test_perder_el_pie_legal_como_descripcion_es_una_correccion():
    from scripts.regression_gate import _loss_reason
    viejo = {"descripcion": "© 2026 Coldwell Banker. Todos los derechos reservados. Coldwell..."}
    assert _loss_reason("descripcion", viejo, {"descripcion": None, "extra": {}}) == "EXPLAINED_VALIDATION"
    real = {"descripcion": "Casa de 3 dormitorios con jardin y pileta."}
    assert _loss_reason("descripcion", real, {"descripcion": None, "extra": {}}) == "UNEXPLAINED_LOSS"

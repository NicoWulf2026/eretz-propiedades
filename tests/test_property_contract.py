"""El contrato de propiedad: qué sobrevive y dónde puede aparecer."""
from __future__ import annotations

from scripts.property_contract import (AUSENTE_SIN_DIAGNOSTICO, EXTRACTED,
                                       EXTRACTION_FAILED,
                                       REJECTED_BY_VALIDATION,
                                       SOURCE_NOT_PROVIDED, alcances, evaluar,
                                       estado_de_campo)


def _propiedad(**cambios):
    base = {"source_url": "https://alfa.com.ar/p/1", "hash_dedup": "h1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "descripcion": "Muy linda", "operacion": "venta",
            "tipo_propiedad": "casa", "precio": 100000.0, "moneda": "USD",
            "ciudad": "Rosario", "provincia": "Santa Fe",
            "latitud": -32.95, "longitud": -60.66}
    base.update(cambios)
    return base


def test_una_propiedad_real_incompleta_sobrevive():
    """La regla que ordena todo el contrato. Exigir `operacion` habría borrado
    del portal 10.916 propiedades que existen, con título, precio, fotos y
    dirección. Pierden el filtro venta/alquiler, no la existencia."""
    permitidos, razones = alcances(_propiedad(operacion=None, tipo_propiedad=None,
                                              precio=None, moneda=None,
                                              ciudad=None, latitud=None,
                                              longitud=None))
    assert "FICHA" in permitidos
    assert "LISTADO" in permitidos
    assert "FILTRO_OPERACION" not in permitidos
    assert razones  # dice por qué, en castellano


def test_sin_identidad_no_hay_propiedad():
    """Lo único que descarta de verdad: sin url no hay a qué volver, y sin
    `hash_dedup` no se la puede deduplicar ni actualizar."""
    for falta in ("source_url", "hash_dedup", "canonical_agency_id"):
        permitidos, razones = alcances(_propiedad(**{falta: None}))
        assert permitidos == set(), falta
        assert "sin identidad" in razones[0]


def test_sin_nada_que_mostrar_tampoco():
    permitidos, razones = alcances(_propiedad(titulo=None, descripcion=None))
    assert permitidos == set()
    assert "nada que mostrar" in razones[0]
    # Con uno de los dos alcanza.
    assert "FICHA" in alcances(_propiedad(titulo=None))[0]
    assert "FICHA" in alcances(_propiedad(descripcion=None))[0]


def test_un_precio_sin_moneda_no_es_un_precio():
    """90.000 puede ser dólares o pesos, y la diferencia es un orden de
    magnitud. La validación lo rechaza y el contrato lo registra como rechazo,
    no como ausencia."""
    fila = _propiedad(moneda=None, problemas={"precio sin moneda": True})
    assert estado_de_campo(fila, "moneda") == REJECTED_BY_VALIDATION
    assert "FILTRO_PRECIO" not in alcances(fila)[0]
    assert "FICHA" in alcances(fila)[0]


def test_un_par_imposible_marca_los_dos_campos():
    """`dormitorios>ambientes` es imposible: no se sabe cuál de los dos está
    mal, así que el guardián descarta los dos y el contrato lo dice de los
    dos."""
    fila = _propiedad(dormitorios=None, ambientes=None,
                      extra={"atributos_descartados": "dormitorios>ambientes"})
    assert estado_de_campo(fila, "dormitorios") == REJECTED_BY_VALIDATION
    assert estado_de_campo(fila, "ambientes") == REJECTED_BY_VALIDATION


def test_no_se_adivina_por_que_falta_un_campo():
    """`SOURCE_NOT_PROVIDED` y `EXTRACTION_FAILED` no son lo mismo: el primero
    no tiene arreglo y el segundo es un defecto nuestro. Sin la señal de la
    fuente no se puede separar, y marcar todo como "la fuente no lo publica"
    escondería justamente los defectos que hay que encontrar."""
    fila = _propiedad(banos=None)
    assert estado_de_campo(fila, "banos") == AUSENTE_SIN_DIAGNOSTICO
    assert estado_de_campo(fila, "banos", fuente_lo_publica=True) == EXTRACTION_FAILED
    assert estado_de_campo(fila, "banos", fuente_lo_publica=False) == SOURCE_NOT_PROVIDED


def test_un_campo_presente_esta_extraido():
    assert estado_de_campo(_propiedad(), "precio") == EXTRACTED
    # El cero no es un valor para estos campos: 0 dormitorios no se publica.
    assert estado_de_campo(_propiedad(dormitorios=0), "dormitorios") != EXTRACTED


def test_el_veredicto_declara_su_version():
    """Cambiar el contrato tiene que verse en el artefacto; si no, no se puede
    auditar con qué reglas se decidió."""
    v = evaluar(_propiedad())
    assert v["contrato_version"] == "property_contract_v1"
    assert v["publicable"] is True
    assert v["database_writes"] == 0
    assert set(v["alcances"]) == {"FICHA", "LISTADO", "FILTRO_OPERACION",
                                  "FILTRO_TIPO", "FILTRO_PRECIO",
                                  "FILTRO_CIUDAD", "MAPA"}

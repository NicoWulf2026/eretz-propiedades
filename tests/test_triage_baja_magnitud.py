# -*- coding: utf-8 -*-
"""Un defecto chico no para la cola; uno grande si, y nada tapa un COMPLETE falso.

La regla de baja magnitud existe para no gastar un ciclo completo de
diagnostico y relanzamiento por una ficha. Lo que estos tests cuidan es lo
otro: que al aflojar no se haya abierto una puerta.

El orden de los chequeos importa tanto como los umbrales. Antes, el defecto de
campo se evaluaba PRIMERO y devolvia, asi que una ficha con un campo ilegible
tapaba el diagnostico de una colision de identidad o de una enumeracion corta
en el mismo resultado. Varios tests fijan justamente eso.
"""
import pytest

from scripts.defect_triage import (CONTINUE, RADIO_AGENCIA, RADIO_FAMILIA,
                                   STOP, clasificar)


def resultado(campos=None, **extra):
    """Un resultado sano al que se le agrega lo que cada test quiera romper."""
    base = {
        "canonical_agency_id": "roomix:prueba",
        "status": "NEEDS_FIX",
        "reasons": [],
        "comparison": {"identity_collisions": 0, "missing_in_run2": 0,
                       "new_in_run2": 0, "same_url_set": True,
                       "idempotent": True},
        "enumeration_audit": {"review_reasons": []},
        "run1": {"estado": "OK", "enumeradas": 200, "detalles_fallidos": 0,
                 "errores_por_etapa": {}},
        "run2": {"estado": "OK", "enumeradas": 200, "detalles_fallidos": 0,
                 "errores_por_etapa": {}},
        "field_coverage": {},
    }
    if campos:
        base["field_coverage"] = {
            campo: {"state": "EXTRACTION_FAILED", "extraction_failed": n,
                    "source_provided": p}
            for campo, (n, p) in campos.items()}
    base.update(extra)
    return base


# --- A a D: la escala del defecto de campo ------------------------------

def test_una_ficha_de_275_no_para():
    """`conti`: 1 de 275. Tres ciclos de diagnostico por una ficha, no."""
    t = clasificar(resultado({"descripcion": (1, 275)}))
    assert t["decision"] == CONTINUE
    assert t["radio_estimado"] == RADIO_AGENCIA
    assert "275" in t["evidencia"]


def test_cuatro_de_doscientos_no_para():
    t = clasificar(resultado({"banos": (4, 200)}))
    assert t["decision"] == CONTINUE


def test_cinco_de_doscientos_si_para():
    """El tope absoluto es 4: el quinto ya no es 'una ficha rara'."""
    t = clasificar(resultado({"banos": (5, 200)}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "extraccion_transversal_de_atributos"


def test_diez_de_doscientos_para():
    t = clasificar(resultado({"banos": (10, 200)}))
    assert t["decision"] == STOP


def test_el_porcentaje_manda_aunque_sean_pocas_fichas():
    """3 de 5 es el 60 %: pocas fichas, pero casi todas las que hay."""
    t = clasificar(resultado({"ambientes": (3, 5)}))
    assert t["decision"] == STOP


def test_alcanza_con_que_un_campo_exceda():
    """`christian arce`: una ficha de ambientes, pero nueve de operacion."""
    t = clasificar(resultado({"ambientes": (1, 77), "operacion": (9, 77)}))
    assert t["decision"] == STOP


def test_sin_source_provided_no_se_difiere():
    """Sin denominador no hay proporcion, y sin proporcion no se afloja."""
    t = clasificar(resultado({"banos": (1, 0)}))
    assert t["decision"] == STOP


# --- E y F: lo que tiene que seguir parando -----------------------------

def test_el_precio_de_blanco_sigue_parando():
    """1.207 de 1.211. El caso que justifica que el corte exista."""
    t = clasificar(resultado({"precio": (1207, 1211)}))
    assert t["decision"] == STOP


def test_una_corrida_que_vio_menos_que_la_otra_para():
    """`carames`: 207 urls contra 177, con 30 que desaparecieron."""
    t = clasificar(resultado(
        comparison={"identity_collisions": 0, "missing_in_run2": 30,
                    "run1_urls": 207, "run2_urls": 177, "same_url_set": False,
                    "idempotent": False}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "inventario_inestable_entre_corridas"
    assert t["radio_estimado"] == RADIO_FAMILIA


def test_el_inventario_faltante_se_lee_del_dato_y_no_del_relato():
    """El agujero real: las razones hablaban de otra cosa y el numero estaba.

    `carames` traia como unica razon que se habia quedado sin presupuesto de
    tiempo. La deteccion buscaba las frases 'inventories differ' o 'not
    idempotent' entre las razones, no las encontraba, y daba por bueno un
    resultado al que le faltaban 30 propiedades.
    """
    t = clasificar(resultado(
        reasons=["one or both runs ran out of time budget before finishing; "
                 "the comparison between them is not conclusive"],
        comparison={"identity_collisions": 0, "missing_in_run2": 30,
                    "run1_urls": 207, "run2_urls": 177},
        run1={"estado": "OK", "detalles_fallidos": 2,
              "errores_por_etapa": {"detalle/ErrorTransitorio": 2}},
        run2={"estado": "OK", "detalles_fallidos": 0,
              "errores_por_etapa": {}}))
    assert t["decision"] == STOP, (
        "dos errores de red no explican treinta propiedades faltantes")
    assert t["componente_sospechoso"] == "inventario_inestable_entre_corridas"


def test_que_la_segunda_corrida_encuentre_MAS_no_para_por_esto():
    """`grupo norte`: run2 encontro 2 mas. No se perdio nada."""
    t = clasificar(resultado(
        comparison={"identity_collisions": 0, "missing_in_run2": 0,
                    "new_in_run2": 2, "run1_urls": 192, "run2_urls": 194}))
    assert t["componente_sospechoso"] != "inventario_inestable_entre_corridas"


# --- G a J: lo que el defecto chico no puede tapar ----------------------

def test_un_defecto_chico_no_tapa_una_colision_de_identidad():
    """Antes, el campo se evaluaba primero y devolvia sin mirar esto."""
    t = clasificar(resultado({"descripcion": (1, 275)},
                             comparison={"identity_collisions": 7,
                                         "missing_in_run2": 0}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "shared/base"


def test_un_defecto_chico_no_tapa_inventario_faltante():
    t = clasificar(resultado({"descripcion": (1, 275)},
                             comparison={"identity_collisions": 0,
                                         "missing_in_run2": 30,
                                         "run1_urls": 207,
                                         "run2_urls": 177}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "inventario_inestable_entre_corridas"


def test_un_defecto_chico_no_tapa_una_enumeracion_incompleta():
    """`diego malizia`: una pagina de cuatro, declarandose agotada."""
    t = clasificar(resultado(
        {"banos": (1, 200)},
        run1={"estado": "ENUMERACION_INCOMPLETA", "enumeradas": 20,
              "detalles_fallidos": 0, "errores_por_etapa": {}},
        run2={"estado": "OK", "enumeradas": 64, "detalles_fallidos": 0,
              "errores_por_etapa": {}}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "enumeracion_compartida"


def test_un_defecto_chico_no_tapa_fichas_descartadas_por_forma():
    t = clasificar(resultado(
        {"banos": (1, 200)},
        run1={"estado": "OK", "descartadas_por_forma": 12,
              "detalles_fallidos": 0, "errores_por_etapa": {}},
        run2={"estado": "OK", "descartadas_por_forma": 12,
              "detalles_fallidos": 0, "errores_por_etapa": {}}))
    assert t["decision"] == STOP


def test_el_defecto_menor_se_sigue_anotando_entero():
    """Diferir por magnitud no es esconder: la evidencia queda escrita."""
    t = clasificar(resultado({"superficie_total": (1, 152)}))
    assert t["decision"] == CONTINUE
    assert "superficie_total" in t["evidencia"]
    assert "1 de 152" in t["evidencia"]
    assert t["componente_sospechoso"] == "extraccion_de_baja_magnitud"


def test_sin_defectos_no_inventa_uno_menor():
    t = clasificar(resultado())
    assert t["componente_sospechoso"] != "extraccion_de_baja_magnitud"


@pytest.mark.parametrize("campos,esperado", [
    ({"descripcion": (1, 275)}, CONTINUE),
    ({"banos": (4, 300)}, CONTINUE),
    ({"banos": (5, 300)}, STOP),
    ({"precio": (1207, 1211)}, STOP),
    ({"ambientes": (48, 59)}, STOP),
    ({"ambientes": (11, 23)}, STOP),
])
def test_tabla_de_casos_reales(campos, esperado):
    assert clasificar(resultado(campos))["decision"] == esperado

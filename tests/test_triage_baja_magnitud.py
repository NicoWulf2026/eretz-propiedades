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


# --- K a N: el corte por lote no lo pide un defecto de una ficha -------

from scripts.defect_triage import (COMPONENTE_MENOR,  # noqa: E402
                                   debe_cortar_por_lote)


def pendiente(componente, radio=RADIO_AGENCIA, firma=None):
    return {"componente_sospechoso": componente, "radio_estimado": radio,
            "firma_del_patron": firma, "epoch": 0}


def test_cinco_defectos_de_una_ficha_no_cortan():
    """La politica de magnitud seria inutil si el umbral los juntara igual.

    Cinco agencias con una ficha ilegible cada una no justifican parar las dos
    colas: son cinco cosas que ya decidimos no diagnosticar.
    """
    cortar, motivo = debe_cortar_por_lote(
        [pendiente(COMPONENTE_MENOR, firma=f"f{i}") for i in range(5)],
        ahora=0)
    assert not cortar, motivo


def test_cinco_defectos_de_verdad_si_cortan():
    cortar, motivo = debe_cortar_por_lote(
        [pendiente("variante_no_soportada", firma=f"f{i}") for i in range(5)],
        ahora=0)
    assert cortar
    assert "5 defectos" in motivo


def test_los_menores_no_inflan_el_umbral():
    """Cuatro menores y uno real son cinco entradas y un solo defecto."""
    pendientes = [pendiente(COMPONENTE_MENOR, firma=f"m{i}") for i in range(4)]
    pendientes.append(pendiente("variante_no_soportada", firma="real"))
    cortar, motivo = debe_cortar_por_lote(pendientes, ahora=0)
    assert not cortar, motivo


def test_pero_dos_menores_con_la_misma_firma_siguen_cortando():
    """Si el mismo campo falla poco en dos agencias, dejo de ser magnitud.

    Es un patron, y la regla de firma repetida tiene que verlo aunque cada caso
    por separado sea chico.
    """
    cortar, motivo = debe_cortar_por_lote(
        [pendiente(COMPONENTE_MENOR, firma="misma"),
         pendiente(COMPONENTE_MENOR, firma="misma")], ahora=0)
    assert cortar
    assert "misma firma" in motivo


# --- O a R: descartar imagenes compartidas no es perderlas ---------------

def con_imagenes(descartadas, cobertura, present=None, total=None):
    r = resultado()
    r["run1"]["imagenes_compartidas_descartadas"] = descartadas
    r["run2"]["imagenes_compartidas_descartadas"] = descartadas
    if cobertura is not None:
        r["field_coverage"]["imagenes"] = {
            "state": "EXTRACTED", "coverage": cobertura,
            "normalized_present": present, "normalized_total": total}
    return r


def test_descartar_miniaturas_ajenas_no_para():
    """`fdc`: 1.616 descartadas y las 202 fichas con fotos.

    Son las cuatro miniaturas de OTRAS propiedades que kiteprop pone en la
    barra lateral; la galeria propia va en tamanyo lg y no se toca.
    """
    t = clasificar(con_imagenes(1616, 1.0, 202, 202))
    assert t["componente_sospechoso"] != "imagenes_compartidas"


def test_borrar_las_fotos_si_para():
    """`coldwell banker de la vera cruz`: 516 descartadas, cero fotos en 258."""
    t = clasificar(con_imagenes(516, 0.0, 0, 258))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "imagenes_compartidas"
    assert "0.0" in t["evidencia"]


def test_el_numero_de_descartadas_no_ordena_nada():
    """La que mas descarta es justamente la unica que no pierde."""
    sana = clasificar(con_imagenes(1616, 1.0, 202, 202))
    rota = clasificar(con_imagenes(249, 0.2889, 13, 45))
    assert sana["componente_sospechoso"] != "imagenes_compartidas"
    assert rota["decision"] == STOP


def test_sin_el_dato_de_cobertura_se_mantiene_el_corte():
    """No poder mirar no es haber mirado y no haber encontrado nada."""
    t = clasificar(con_imagenes(800, None))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "imagenes_compartidas"


# --- S a V: una muestra de uno no es el 100 % -----------------------------

from scripts.defect_triage import MUESTRA_MINIMA  # noqa: E402


def con_inventario(campos, enumeradas):
    r = resultado(campos)
    r["enumeration_audit"] = {"enumerated": enumeradas, "review_reasons": []}
    return r


def test_una_pagina_de_una_sobre_un_inventario_grande_no_para():
    """`baron`: banos falla 1 de 1, y hay 182 propiedades enumeradas.

    Esa unica pagina era /emprendimientos/imperio-baron, un proyecto de 24
    pisos que no tiene un valor unico de banos. Uno sobre 182 es 0,5 %.
    """
    t = clasificar(con_inventario({"banos": (1, 1)}, 182))
    assert t["decision"] == CONTINUE
    assert t["componente_sospechoso"] == "extraccion_de_baja_magnitud"


def test_pero_si_el_inventario_tambien_es_chico_para():
    """Uno de uno sobre cinco propiedades sigue siendo el 20 %."""
    t = clasificar(con_inventario({"banos": (1, 1)}, 5))
    assert t["decision"] == STOP


def test_sin_inventario_conocido_no_se_afloja():
    """Sin con que comparar, la muestra chica se trata como antes."""
    t = clasificar(con_inventario({"banos": (1, 1)}, 0))
    assert t["decision"] == STOP


def test_la_muestra_grande_sigue_usando_su_propia_proporcion():
    """Con la senyal viendo el campo en muchas fichas, el denominador es ese.

    3 de 5 seria el 60 %, pero con MUESTRA_MINIMA fichas vistas la proporcion
    ya es informativa y no hay que ir a buscar el inventario.
    """
    t = clasificar(con_inventario({"ambientes": (3, MUESTRA_MINIMA + 5)}, 500))
    assert t["decision"] == STOP, "3 sobre 15 es el 20 %: no es menor"


# --- W a Z: lo que la fuente dice que tiene ------------------------------

def con_techo(enumeradas, declarado, campos=None):
    r = resultado(campos)
    r["run1"]["enumeradas"] = enumeradas
    r["run2"]["enumeradas"] = enumeradas
    r["enumeration_audit"] = {"enumerated": enumeradas,
                              "declared_total": declarado,
                              "review_reasons": []}
    return r


def test_un_catalogo_corto_para_aunque_no_falle_ningun_campo():
    """`alberti`: 102 de 168 declaradas, y habia cerrado CERTIFIED_COMPLETE."""
    t = clasificar(con_techo(102, 168))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "catalogo_declarado_mayor_que_el_enumerado"
    assert "168" in t["evidencia"] and "102" in t["evidencia"]


def test_un_defecto_menor_no_tapa_el_catalogo_corto():
    """El orden importa: el hueco se mira antes que el campo."""
    t = clasificar(con_techo(102, 168, {"banos": (1, 1)}))
    assert t["decision"] == STOP
    assert t["componente_sospechoso"] == "catalogo_declarado_mayor_que_el_enumerado"


def test_una_diferencia_chica_no_para():
    """`abriola`: 264 de 274. Un techo declarado suele incluir despublicadas."""
    t = clasificar(con_techo(264, 274))
    assert t["componente_sospechoso"] != "catalogo_declarado_mayor_que_el_enumerado"


def test_pocas_invisibles_en_un_catalogo_grande_no_paran():
    """Diez sobre tres mil es el 0,3 %: las dos condiciones se exigen juntas."""
    t = clasificar(con_techo(2990, 3000))
    assert t["componente_sospechoso"] != "catalogo_declarado_mayor_que_el_enumerado"


def test_enumerar_todo_lo_declarado_no_para():
    t = clasificar(con_techo(182, 182))
    assert t["componente_sospechoso"] != "catalogo_declarado_mayor_que_el_enumerado"


# --------------------------------------------------------------------------
# El tope porcentual estuvo en 0,02 y frenaba de mas. Medido sobre los 382
# casos historicos con 4 fallas o menos, el 63 % de las fallas chicas caia
# afuera y paraba las dos colas: `3 de 103`, `4 de 129`, `2 de 54`.
#
# Entre 0,10 y 0,30 los datos tienen un hueco -pasar de 0,10 a 0,25 suma dos
# casos-, asi que el corte esta donde el salto, no donde me parecia.
# --------------------------------------------------------------------------

def _resultado(campo: str, fallas: int, provistos: int, enumeradas: int):
    return {"field_coverage": {campo: {"state": "EXTRACTION_FAILED",
                                       "extraction_failed": fallas,
                                       "source_provided": provistos}},
            "enumeration_audit": {"enumerated": enumeradas}}


def test_MUERDE_dos_fallas_sobre_cincuenta_y_cuatro_son_menores():
    """El paro de `abril negocios inmobiliarios` que destapo el tope.

    Dos propiedades sin coordenada sobre 54 pararon las dos colas. La fuente
    las publica y no las leimos -es un defecto de verdad- pero no es uno que
    justifique detener el padron entero.
    """
    from scripts.defect_triage import _es_de_baja_magnitud
    assert _es_de_baja_magnitud(_resultado("latitud", 2, 54, 54), ["latitud"])


def test_tres_de_ciento_tres_tambien():
    from scripts.defect_triage import _es_de_baja_magnitud
    assert _es_de_baja_magnitud(_resultado("ambientes", 3, 103, 103),
                                ["ambientes"])


def test_MUERDE_cuando_el_campo_falla_en_TODO_lo_que_hay_no_es_menor():
    """`cavacini` con 3 de 3 y `alder` con 4 de 4.

    Son pocas fichas en absoluto y el 100 % de las que tienen el campo. Un
    tope solo absoluto las habria dado por menores, que es exactamente el
    error que el porcentual existe para evitar. Subirlo no puede borrarlo.
    """
    from scripts.defect_triage import _es_de_baja_magnitud
    assert not _es_de_baja_magnitud(_resultado("ambientes", 3, 3, 3),
                                    ["ambientes"])
    assert not _es_de_baja_magnitud(_resultado("ambientes", 4, 4, 4),
                                    ["ambientes"])


def test_cinco_fallas_siguen_sin_ser_menores_por_muchas_que_haya():
    """El tope absoluto no se movio: cinco fichas son cinco fichas."""
    from scripts.defect_triage import _es_de_baja_magnitud
    assert not _es_de_baja_magnitud(_resultado("ambientes", 5, 5000, 5000),
                                    ["ambientes"])

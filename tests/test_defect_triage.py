"""Triage de defectos: parar por radio, no por reflejo."""
from __future__ import annotations

import time

from scripts.defect_triage import (CONTINUE, DEFECTOS_PARA_CORTAR,
                                   HORAS_PARA_CORTAR, RADIO_AGENCIA,
                                   RADIO_COMPARTIDO, RADIO_FAMILIA, STOP,
                                   clasificar, debe_cortar_por_lote, firma)


def _resultado(**cambios):
    base = {
        "canonical_agency_id": "roomix:alfa", "status": "NEEDS_FIX",
        "connector": "generico", "connector_strategy": "generic/html_catalog",
        "strategy_fingerprint": "abc123",
        "reasons": ["run inventories differ"],
        "comparison": {"identity_collisions": 0},
        "run1": {"estado": "OK", "detalles_fallidos": 0},
        "run2": {"estado": "OK", "detalles_fallidos": 0},
        "field_coverage": {}, "enumeration_audit": {"review_reasons": []},
    }
    base.update(cambios)
    return base


# ------------------------------ STOP --------------------------------------

def test_un_campo_que_la_fuente_publica_y_no_leimos_detiene_la_cola():
    """El que lee ese campo es el parser, y el parser lo comparten todas las
    agencias de la familia. Cada una que certifique después hereda el error."""
    v = clasificar(_resultado(field_coverage={
        "superficie_total": {"state": "EXTRACTION_FAILED"}}))
    assert v["decision"] == STOP
    assert v["radio_estimado"] == RADIO_FAMILIA
    assert "superficie_total" in v["evidencia"]


def test_una_colision_de_identidad_detiene_por_shared_base():
    """`hash_dedup` se calcula en `connectors/base.py`: no hay forma de que sea
    un problema de una sola inmobiliaria."""
    v = clasificar(_resultado(comparison={"identity_collisions": 3}))
    assert v["decision"] == STOP
    assert v["componente_sospechoso"] == "shared/base"
    assert v["radio_estimado"] == RADIO_COMPARTIDO


def test_el_guardian_de_forma_y_las_fichas_vacias_detienen():
    for campo in ("descartadas_por_forma", "fichas_sin_contenido",
                  "paginacion_interrumpida", "imagenes_compartidas_descartadas"):
        v = clasificar(_resultado(run2={"estado": "OK", campo: 4}))
        assert v["decision"] == STOP, campo
        assert v["radio_estimado"] == RADIO_FAMILIA, campo


def test_una_perdida_sistematica_de_inventario_detiene():
    v = clasificar(_resultado(
        enumeration_audit={"review_reasons": ["COLLAPSE_GT_80_PERCENT"]}))
    assert v["decision"] == STOP


def test_sin_evidencia_para_acotar_se_para():
    """La asimetría deliberada: no encontrar razones para parar no es lo mismo
    que tener razones para seguir. Un defecto compartido tomado por local
    certifica mal a cientos de agencias; uno local tomado por compartido cuesta
    una parada."""
    v = clasificar(_resultado(reasons=["algo que nadie vio antes"]))
    assert v["decision"] == STOP
    assert v["componente_sospechoso"] == "sin_determinar"
    assert "no es tener razones para seguir" in v["evidencia"]


def test_un_runner_error_detiene():
    v = clasificar(_resultado(status="RUNNER_ERROR"))
    assert v["decision"] == STOP
    assert v["radio_estimado"] == RADIO_COMPARTIDO


# ---------------------------- CONTINUE ------------------------------------

def test_un_sitio_degradado_no_detiene_la_cola():
    """El caso real de `aconcagua propiedades`: 16 fichas perdidas en la
    segunda corrida, todas con error de red, y el catálogo enumeró 77 en las
    dos. Recertificada aparte dio COMPLETE. Eso no justifica detener 758."""
    v = clasificar(_resultado(
        reasons=["run inventories differ", "second run is not idempotent"],
        run2={"estado": "OK", "detalles_fallidos": 16,
              "errores_por_etapa": {"detalle/ErrorTransitorio": 16}}))
    assert v["decision"] == CONTINUE
    assert v["radio_estimado"] == RADIO_AGENCIA
    assert v["pendiente_de_resolucion"] is True
    assert v["certificado"] is False


def test_un_estado_de_corrida_desconocido_detiene():
    """Los estados que el runner produce son cinco y están mapeados uno por
    uno. Uno que no se reconoce no se puede acotar, y ante duda se para."""
    v = clasificar(_resultado(run1={"estado": "ALGO_NUEVO"}))
    assert v["decision"] == STOP
    assert v["componente_sospechoso"] == "sin_determinar"


def test_un_sitio_lento_no_detiene():
    v = clasificar(_resultado(run2={"estado": "OK", "presupuesto_agotado": True}))
    assert v["decision"] == CONTINUE


def test_inventario_chico_sin_fallas_de_extraccion_no_detiene():
    v = clasificar(_resultado(
        enumeration_audit={"review_reasons": ["LOW_INVENTORY_0_11"]}))
    assert v["decision"] == CONTINUE


def test_el_inventario_chico_no_tapa_un_fallo_de_extraccion():
    """Si además falló la extracción, el radio deja de estar acotado."""
    v = clasificar(_resultado(
        enumeration_audit={"review_reasons": ["LOW_INVENTORY_0_11"]},
        field_coverage={"precio": {"state": "EXTRACTION_FAILED"}}))
    assert v["decision"] == STOP


def test_un_defecto_continuable_nunca_queda_certificado():
    v = clasificar(_resultado(run1={"estado": "BLOQUEADA"}))
    assert v["certificado"] is False
    assert v["pendiente_de_resolucion"] is True
    for clave in ("causa_observable", "componente_sospechoso", "radio_estimado",
                  "evidencia", "strategy_fingerprint", "cuando",
                  "canonical_agency_id", "decision"):
        assert v.get(clave) is not None, clave


# --------------------------- corte por lote --------------------------------

def test_cinco_defectos_pendientes_cortan():
    pendientes = [{"firma_del_patron": f"f{i}", "radio_estimado": RADIO_AGENCIA,
                   "epoch": time.time()} for i in range(DEFECTOS_PARA_CORTAR)]
    corta, motivo = debe_cortar_por_lote(pendientes)
    assert corta and "pendientes" in motivo


def test_dos_defectos_con_la_misma_firma_cortan():
    """Dejó de ser casualidad: es el mismo problema apareciendo dos veces, que
    es justo lo que produce un radio mal estimado."""
    pendientes = [{"firma_del_patron": "misma", "radio_estimado": RADIO_AGENCIA,
                   "epoch": time.time()} for _ in range(2)]
    corta, motivo = debe_cortar_por_lote(pendientes)
    assert corta and "misma firma" in motivo


def test_un_radio_que_crecio_corta():
    pendientes = [{"firma_del_patron": "a", "radio_estimado": RADIO_FAMILIA,
                   "epoch": time.time()}]
    corta, motivo = debe_cortar_por_lote(pendientes)
    assert corta and "radio" in motivo


def test_doce_horas_desde_el_primer_defecto_cortan():
    ahora = time.time()
    pendientes = [{"firma_del_patron": "a", "radio_estimado": RADIO_AGENCIA,
                   "epoch": ahora - HORAS_PARA_CORTAR * 3600 - 1}]
    corta, motivo = debe_cortar_por_lote(pendientes, ahora=ahora)
    assert corta and "h desde el primer defecto" in motivo


def test_un_defecto_local_reciente_no_corta():
    pendientes = [{"firma_del_patron": "a", "radio_estimado": RADIO_AGENCIA,
                   "epoch": time.time()}]
    assert debe_cortar_por_lote(pendientes)[0] is False
    assert debe_cortar_por_lote([])[0] is False


def test_la_firma_identifica_el_patron_y_no_la_inmobiliaria():
    a = _resultado(canonical_agency_id="roomix:alfa")
    b = _resultado(canonical_agency_id="roomix:beta")
    assert firma(a, "x") == firma(b, "x")
    distinto = _resultado(connector_strategy="generic/sitemap")
    assert firma(distinto, "x") != firma(a, "x")


def test_cada_estado_de_corrida_tiene_su_propio_radio():
    """Validado contra los 73 defectos reales del histórico. La primera versión
    metía todo lo que no era `OK` en "la fuente no respondió", y así etiquetaba
    16 casos de `VARIANTE_NO_SOPORTADA` con una causa falsa: no es que el sitio
    no contestó, es que nuestro connector no reconoce su forma.
    """
    def _con(estado):
        return clasificar(_resultado(run1={"estado": estado}))

    # Hueco de cobertura: nadie más certifica mal por esto, y darle soporte es
    # una estrategia nueva que no toca a las existentes.
    v = _con("VARIANTE_NO_SOPORTADA")
    assert (v["decision"], v["radio_estimado"]) == (CONTINUE, "ESTRATEGIA")
    assert v["componente_sospechoso"] == "variante_no_soportada"

    # El sitio decide bloquearnos; no es el parser.
    assert _con("BLOQUEADA")["decision"] == CONTINUE
    assert _con("PRESUPUESTO_AGOTADO")["decision"] == CONTINUE

    # El enumerador es compartido y no se puede separar "el sitio nos cortó"
    # de "nuestra paginación no llegó": se para.
    v = _con("ENUMERACION_INCOMPLETA")
    assert (v["decision"], v["radio_estimado"]) == (STOP, RADIO_FAMILIA)

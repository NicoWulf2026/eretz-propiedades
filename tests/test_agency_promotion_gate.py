from __future__ import annotations

from scripts.agency_promotion_gate import (BLOCKED, REVIEW, SAFE,
                                           SIN_EVIDENCIA, clasificar,
                                           clave_nombre, dominio_de)


def registro(*, estado_web="OFFICIAL_WEB_HIGH_CONFIDENCE",
             dominio="inmobiliaria.com.ar", tipo_web="OFFICIAL_WEB",
             cruce="HIGH_CONFIDENCE_EXISTING") -> dict:
    return {
        "directory": {"status": estado_web, "selected_domain": dominio},
        "platform": {"web_kind": tipo_web, "domain": dominio},
        "resolution": {"evidence": {"crosswalk_state": cruce}},
        "live": {}, "source": {},
    }


def clasificar_una(reg, homonimas=0, grupo=1, en_dominio=1, lectura=None):
    return clasificar(reg, homonimas_en_main=homonimas,
                      miembros_del_grupo=grupo,
                      inmobiliarias_en_el_dominio=en_dominio,
                      lectura=lectura)


def test_una_homonima_en_main_nunca_se_promueve() -> None:
    """El riesgo de una promocion falsa no es perder una fila: es crear una
    duplicada de una inmobiliaria que ya existe. Ya pasa en produccion con
    `inmobiliaria salerno` (3535) y `salerno inmobiliaria` (6334), el mismo
    negocio partido en dos fichas."""
    estado, motivos = clasificar_una(registro(), homonimas=1)
    assert estado == BLOCKED
    assert "HOMONIMA_EN_MAIN" in motivos


def test_el_orden_de_las_palabras_no_esconde_una_homonima() -> None:
    """"Inmobiliaria Bechara" y "bechara inmobiliaria" son el mismo negocio.
    Comparar el nombre en orden encontraba 0 coincidencias sobre 4.953;
    comparar el conjunto de palabras encuentra 56."""
    assert clave_nombre("Inmobiliaria Bechara") == clave_nombre(
        "bechara inmobiliaria")
    assert clave_nombre("Operaciones Inmobiliarias Daniela Valdez") == (
        clave_nombre("daniela valdez operaciones inmobiliarias"))
    # Y no fusiona dos apellidos distintos.
    assert clave_nombre("Inmobiliaria De Luca") != clave_nombre(
        "Inmobiliaria De Lucia")


def test_una_duplicada_del_propio_universo_tampoco_se_promueve() -> None:
    """Promover las dos mitades de un duplicado crea en main exactamente el
    problema que ya tenemos."""
    estado, motivos = clasificar_una(registro(), grupo=2)
    assert estado == BLOCKED
    assert "DUPLICADA_EN_EL_UNIVERSO" in motivos


def test_el_perfil_de_un_portal_no_es_una_inmobiliaria_promovible() -> None:
    estado, motivos = clasificar_una(
        registro(tipo_web="EXTERNAL_PORTAL_PROFILE"))
    assert estado == BLOCKED
    assert "LA_WEB_NO_ES_PROPIA" in motivos


def test_un_dominio_compartido_va_a_revision_y_no_a_promocion() -> None:
    """Hay dominios de plataforma que comparten inmobiliarias sin relacion, y
    `re max urbana` / `re max time` son sucursales distintas del mismo dominio.
    Un dominio no identifica a una inmobiliaria."""
    estado, motivos = clasificar_una(registro(), en_dominio=3)
    assert estado == REVIEW
    assert "DOMINIO_COMPARTIDO" in motivos


def test_una_identidad_de_web_ambigua_va_a_revision() -> None:
    estado, motivos = clasificar_una(
        registro(estado_web="OFFICIAL_WEB_AMBIGUOUS"))
    assert estado == REVIEW
    assert "IDENTIDAD_DE_WEB_AMBIGUA" in motivos


def test_sin_web_no_hay_evidencia_suficiente() -> None:
    """Sin web no queda mas que el nombre, y el nombre solo es exactamente lo
    que produce duplicadas."""
    for estado_web in ("NO_EXISTING_WEB_DATA", "SEARCH_SECOND_PASS_REQUIRED",
                       "NO_INDEPENDENT_WEBSITE"):
        estado, motivos = clasificar_una(
            registro(estado_web=estado_web, dominio=""))
        assert estado == SIN_EVIDENCIA, estado_web
        assert motivos == ["SIN_WEB_QUE_CORROBORE_LA_IDENTIDAD"]


def test_solo_se_promueve_con_todas_las_invariantes_demostradas() -> None:
    estado, motivos = clasificar_una(registro(), lectura="SOSTIENE_SU_EVIDENCIA")
    assert estado == SAFE
    assert set(motivos) == {"WEB_LEIDA_SOSTIENE_SU_EVIDENCIA", "SIN_HOMONIMA",
                            "SIN_DUPLICADA", "DOMINIO_PROPIO"}


def test_un_estado_de_web_que_nadie_leyo_no_alcanza_para_promover() -> None:
    """Las 939 promovibles cumplian la invariante 4 con `free_web_audit_v1`, la
    auditoria que puntuo URLs SIN ABRIRLAS. `OFFICIAL_WEB_HIGH_CONFIDENCE` lo
    traen 597 de 598 dominios descubiertos, asi que no distingue nada: al leer
    esas 939 aparecieron 24 apuntando a una web ajena -el cuartel de Bomberos
    de San Lorenzo, el canal tn.com.ar, turismo municipal de Mar del Plata-.

    Promover inserta una fila en `main`. Un estado declarado no alcanza.
    """
    estado, motivos = clasificar_una(registro(), lectura=None)
    assert estado == SIN_EVIDENCIA
    assert motivos[0] == "WEB_NUNCA_LEIDA"


def test_leer_la_pagina_y_ver_que_es_de_otro_bloquea() -> None:
    """Es mas fuerte que cualquier estado de descubrimiento: se miro."""
    for veredicto in ("DOMINIO_AJENO_DEMOSTRADO", "DOMINIO_DE_OTRO_PAIS"):
        estado, motivos = clasificar_una(registro(), lectura=veredicto)
        assert estado == BLOCKED, veredicto
        assert f"LA_WEB_NO_ES_PROPIA_{veredicto}" in motivos


def test_una_web_leida_vale_aunque_el_directorio_no_la_conozca() -> None:
    """18 de las `INSUFFICIENT_EVIDENCE` tenian como unico bloqueo no tener web
    en el directorio. Su web existe y se leyo; el directorio no la conocia."""
    sin_dominio = registro(estado_web="NO_EXISTING_WEB_DATA", dominio="")
    assert clasificar_una(sin_dominio)[0] == SIN_EVIDENCIA
    estado, motivos = clasificar_una(sin_dominio, lectura="VERIFICADA_ARGENTINA")
    assert estado == SAFE
    assert "WEB_LEIDA_VERIFICADA_ARGENTINA" in motivos


def test_el_bloqueo_gana_sobre_la_revision() -> None:
    """Una candidata que es duplicada Y tiene el dominio compartido no puede
    terminar en revision: lo que la descalifica ya esta probado."""
    estado, _ = clasificar_una(registro(), grupo=2, en_dominio=3)
    assert estado == BLOCKED


def test_el_dominio_se_compara_sin_esquema_ni_www() -> None:
    assert dominio_de(registro(dominio="https://www.Alfa.com.ar/")) == (
        "alfa.com.ar")

"""El ciclo de vida: una ausencia puntual no es una baja."""
from __future__ import annotations

from scripts.property_lifecycle import (ACTIVA, AUSENCIAS_PARA_INACTIVA,
                                        AUSENTE, INACTIVA, REACTIVADA,
                                        RETIRADA, Observacion,
                                        enumeracion_confiable, recorrer,
                                        transicion)

VISTA = Observacion(vista=True)
NO_VISTA = Observacion(vista=False)


def test_una_ausencia_puntual_no_da_de_baja():
    """Puede ser un timeout, un listado paginado a la mitad o un aviso que se
    movió de página. Se anota y se sigue."""
    estado, ausencias = transicion(ACTIVA, 0, NO_VISTA)
    assert estado == AUSENTE
    assert ausencias == 1


def test_hacen_falta_tres_ausencias_confiables_seguidas():
    r = recorrer([NO_VISTA] * AUSENCIAS_PARA_INACTIVA)
    assert r["estado"] == INACTIVA
    assert r["historia"][:2] == [AUSENTE, AUSENTE]
    # Una menos no alcanza.
    assert recorrer([NO_VISTA] * (AUSENCIAS_PARA_INACTIVA - 1))["estado"] == AUSENTE


def test_una_enumeracion_en_la_que_no_se_confia_no_produce_ausencias():
    """Si la fuente no respondió o la paginación se cortó, lo que no se vio no
    estuvo ausente: no se lo buscó. Contarlo sería fabricar bajas a partir de
    nuestros propios fallos, que es como se borra inventario vivo."""
    dudosa = Observacion(vista=False, enumeracion_confiable=False)
    r = recorrer([dudosa] * 10)
    assert r["estado"] == ACTIVA
    assert r["ausencias_consecutivas"] == 0


def test_reaparecer_deshace_la_inactivacion():
    """`INACTIVA` dice "hace rato que no la vemos" y se deshace sola."""
    r = recorrer([NO_VISTA, NO_VISTA, NO_VISTA, VISTA])
    assert r["estado"] == REACTIVADA
    assert r["ausencias_consecutivas"] == 0


def test_solo_la_fuente_puede_confirmar_una_baja():
    """Ausencia de evidencia no es evidencia de ausencia. A `RETIRADA` no se
    llega por no verla, se llega porque su propia ficha responde 404."""
    assert recorrer([NO_VISTA] * 50)["estado"] == INACTIVA
    muerta = Observacion(vista=False, codigo_de_la_ficha=404)
    assert transicion(ACTIVA, 0, muerta)[0] == RETIRADA
    assert transicion(ACTIVA, 0, Observacion(vista=False,
                                             codigo_de_la_ficha=410))[0] == RETIRADA


def test_una_retirada_puede_volver():
    """Una inmobiliaria republica un aviso. Vuelve a la vida con el contador
    limpio."""
    r = recorrer([Observacion(vista=False, codigo_de_la_ficha=404), VISTA])
    assert r["historia"] == [RETIRADA, REACTIVADA]
    assert r["ausencias_consecutivas"] == 0


def test_que_corrida_habilita_deducir_ausencias():
    assert enumeracion_confiable({"estado": "OK", "enumeracion_completa": True})
    assert not enumeracion_confiable({"estado": "ERROR"})
    assert not enumeracion_confiable({"estado": "OK", "paginacion_interrumpida": True})
    assert not enumeracion_confiable({"estado": "OK", "presupuesto_agotado": True})
    assert not enumeracion_confiable({"estado": "OK", "enumeracion_completa": False})


def test_la_maquina_es_pura():
    """Mismo estado y misma observación dan siempre lo mismo, que es lo que
    permite simular la regla sobre el histórico antes de encenderla."""
    assert transicion(AUSENTE, 1, NO_VISTA) == transicion(AUSENTE, 1, NO_VISTA)
    assert recorrer([VISTA])["database_writes"] == 0

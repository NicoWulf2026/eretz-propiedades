# -*- coding: utf-8 -*-
"""Una provincia no leida no para a la familia: solo puede dejar NULL, nunca un dato falso (07-10).

Del 07-10 03:06 al 20:50, siete paros FAMILIA/corte por lote del mismo hueco: la fuente nombra la
provincia en la prosa o dentro de la direccion completa (caldeo, dori martin, fabiana sapuna,
fittipaldi -dentro de un href de Google Maps-, fuentes 19 de 170...) y el auditor la cuenta como
provista. Todos verificados contra la fuente: NULL honesto. Cada paro dejaba una familia entera
afuera de la cola hasta el diagnostico.

La agencia NO se certifica: sigue en NEEDS_FIX. Lo que cambia es el radio: la falla de leer la
provincia no puede producir un valor equivocado ni perder propiedades, asi que no justifica frenar
a las demas. Cualquier OTRO campo fallado junto con la provincia sigue parando a la familia.
"""
from scripts.defect_triage import CONTINUE, RADIO_AGENCIA, RADIO_FAMILIA, STOP, clasificar
from tests.test_triage_baja_magnitud import resultado


def test_MUERDE_provincia_sola_no_para_a_la_familia():
    t = clasificar(resultado({"provincia": (19, 19)}))  # `fuentes`: 19 de 170, todo en prosa
    assert t["decision"] == CONTINUE
    assert t["radio_estimado"] == RADIO_AGENCIA
    assert "provincia" in t["evidencia"]


def test_MUERDE_provincia_en_todas_las_fichas_tampoco():
    t = clasificar(resultado({"provincia": (66, 66)}))
    assert t["decision"] == CONTINUE and t["radio_estimado"] == RADIO_AGENCIA


def test_provincia_con_otro_campo_sigue_parando_la_familia():
    t = clasificar(resultado({"provincia": (19, 19), "dormitorios": (30, 40)}))
    assert t["decision"] == STOP
    assert t["radio_estimado"] == RADIO_FAMILIA


def test_otro_campo_solo_sigue_parando_la_familia():
    t = clasificar(resultado({"precio": (30, 40)}))
    assert t["decision"] == STOP and t["radio_estimado"] == RADIO_FAMILIA


def test_la_provincia_no_tapa_un_diagnostico_mas_grave():
    t = clasificar(resultado({"provincia": (19, 19)},
                             comparison={"identity_collisions": 3, "missing_in_run2": 0, "new_in_run2": 0,
                                         "same_url_set": True, "idempotent": True}))
    assert t["decision"] == STOP

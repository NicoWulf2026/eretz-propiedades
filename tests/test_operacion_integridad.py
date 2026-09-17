# -*- coding: utf-8 -*-
"""Los defectos silenciosos entran al reporte, o no los ve nadie.

Los dos que se agregan comparten forma y por eso van juntos: **no hacen ruido**.
No detienen la cola, no ensucian un log y no bajan ningún número visible.

  - el id estable que colapsa: `baron inmobiliaria` tiene el id `300` en 36
    propiedades distintas, y `identity_collisions` del mismo registro dice 0;
  - la calidad degradada en agencias terminales buenas: hoy se publican como si
    estuvieran enteras.

Un defecto que sólo aparece si alguien se acuerda de abrir un artefacto es, en
la práctica, un defecto que no se ve.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

from operacion_reporte import integridad  # noqa: E402


def preparar(tmp_path: Path, colisiones: dict | None = None,
             gates: list[dict] | None = None) -> Path:
    if colisiones is not None:
        (tmp_path / "ERETZ_COLISION_DE_IDS.json").write_text(
            json.dumps(colisiones, ensure_ascii=False), encoding="utf-8")
    if gates is not None:
        (tmp_path / "ERETZ_GATES_INDEPENDIENTES.jsonl").write_text(
            "".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gates),
            encoding="utf-8")
    return tmp_path


def test_MUERDE_las_colisiones_de_id_llegan_al_reporte(tmp_path):
    salida = integridad(preparar(tmp_path, colisiones={
        "agencias_con_ids_colapsados": 25,
        "de_esas_certified_complete": 10,
        "de_esas_con_identity_collisions_cero": 25,
    }))
    assert salida["ids_estables_colapsados"]["agencias"] == 25
    # Que diez esten CERTIFIED_COMPLETE es lo que convierte el dato en aviso:
    # son las que siguen hacia dedupe y publicacion.
    assert salida["ids_estables_colapsados"]["de_esas_certified_complete"] == 10


def test_la_calidad_degradada_en_terminales_buenas_llega_al_reporte(tmp_path):
    gates = [{"shadow_disagreement": True}, {"shadow_disagreement": True},
             {"shadow_disagreement": False}]
    salida = integridad(preparar(tmp_path, gates=gates))
    dato = salida["calidad_degradada_en_terminales_buenas"]
    assert dato["agencias"] == 2 and dato["de"] == 3


def test_el_reporte_dice_que_el_inventario_NO_esta_afectado(tmp_path):
    """La nota no es adorno: sin ella el número se lee como pérdida.

    25 agencias con ids colapsados suena a inventario perdido y no lo es:
    `enumerated` cuenta urls. Un aviso que se malinterpreta hacia el pánico es
    tan caro como uno que no aparece.
    """
    salida = integridad(preparar(tmp_path, colisiones={
        "agencias_con_ids_colapsados": 25}))
    assert "inventario NO esta afectado" in \
        salida["ids_estables_colapsados"]["nota"]


def test_el_shadow_declara_que_sus_falsos_positivos_no_estan_medidos(tmp_path):
    """135 de 411 es una tasa alta y la honestidad va pegada al número.

    Hay verdad de campo sobre UNA agencia. Presentar 135 sin esa advertencia
    invitaría a tratarlos como defectos confirmados.
    """
    salida = integridad(preparar(tmp_path, gates=[{"shadow_disagreement": True}]))
    dato = salida["calidad_degradada_en_terminales_buenas"]
    assert dato["modo"].startswith("SHADOW")
    assert "SIN medir" in dato["nota"]


def test_sin_artefactos_el_reporte_no_inventa_ni_revienta(tmp_path):
    """Los artefactos son opcionales: se generan aparte y pueden no existir.

    Si su ausencia rompiera el reporte operacional, un script auxiliar podría
    dejar ciega la herramienta principal.
    """
    assert integridad(tmp_path) == {}


def test_un_artefacto_corrupto_no_tumba_el_reporte(tmp_path):
    (tmp_path / "ERETZ_COLISION_DE_IDS.json").write_text("{roto",
                                                         encoding="utf-8")
    assert integridad(tmp_path) == {}

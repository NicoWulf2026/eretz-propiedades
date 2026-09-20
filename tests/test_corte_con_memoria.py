# -*- coding: utf-8 -*-
"""Un corte por lote es un pedido de atención. Repetirlo no agrega nada.

Los tres últimos cortes del worker 1 pararon en **la misma agencia**
—`gomez servicios inmobiliarios`— con **exactamente los mismos cinco
defectos**: `fernanda aciuolo`, `fios`, `forchino`, `gentina`, `gianini`.
Ninguna de las cinco tiene diferida escrita. La cola se relanza, recorre el
mismo tramo, reacumula los mismos cinco y vuelve a cortar.

Es la tercera vez que este proyecto lee un registro histórico como si fuera una
lista de pendientes. Las dos anteriores: el corrector de fuentes, que reaplicó
una propuesta retirada, y los tests con fecha fija, que medían el almanaque.

El corte sigue existiendo y sigue cortando. Lo que cambia es **qué cuenta**:
sólo los defectos que no provocaron ya un corte. El registro completo se
conserva —el radio, el ranking y los reportes lo siguen usando entero—.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from defect_triage import (DEFECTOS_PARA_CORTAR, RADIO_AGENCIA,  # noqa: E402
                           RADIO_FAMILIA, anotar_corte,
                           debe_cortar_por_lote, defectos_ya_cortados,
                           identidad_de_defecto)


def defecto(agencia: str, *, componente: str = "inventario_chico",
            firma: str = "f", radio: str = RADIO_AGENCIA,
            huella: str = "h1") -> dict:
    return {"canonical_agency_id": f"roomix:{agencia}",
            "componente_sospechoso": componente,
            "firma_del_patron": firma, "radio_estimado": radio,
            "strategy_fingerprint": huella, "epoch": time.time()}


LOS_CINCO = ["fernanda aciuolo", "fios", "forchino", "gentina", "gianini"]


def cinco() -> list[dict]:
    """Los cinco reales del corte que se repitió tres veces."""
    return [defecto(a, firma=f"f{i}") for i, a in enumerate(LOS_CINCO)]


def test_el_primer_corte_sigue_cortando():
    """Lo que no se puede romper: el corte existe por una razón buena.

    Cinco defectos sueltos sin resolver justifican una tanda de diagnóstico.
    Si esta afirmación se cayera, la memoria habría apagado el mecanismo en vez
    de sacarle la repetición.
    """
    corta, motivo = debe_cortar_por_lote(cinco())
    assert corta and "pendientes" in motivo


def test_MUERDE_el_mismo_lote_no_corta_dos_veces(tmp_path):
    """El caso `gomez`, exacto: tres cortes idénticos medidos en el log."""
    ruta = tmp_path / "cortes.jsonl"
    lote = cinco()
    assert debe_cortar_por_lote(lote)[0] is True
    anotar_corte(ruta, lote, "5 defectos pendientes sin resolver")

    corta, motivo = debe_cortar_por_lote(
        cinco(), ya_cortados=defectos_ya_cortados(ruta))
    assert corta is False, motivo


def test_cinco_defectos_NUEVOS_si_cortan_despues_de_un_corte(tmp_path):
    """La otra mitad, y la que impide que esto apague el mecanismo.

    Si después de un corte aparecen cinco defectos distintos, hay información
    nueva y hay que parar. Una memoria que también los silenciara convertiría
    el arreglo en un apagado.
    """
    ruta = tmp_path / "cortes.jsonl"
    anotar_corte(ruta, cinco(), "primer corte")
    otros = [defecto(f"agencia{i}", firma=f"g{i}")
             for i in range(DEFECTOS_PARA_CORTAR)]
    corta, motivo = debe_cortar_por_lote(
        otros, ya_cortados=defectos_ya_cortados(ruta))
    assert corta is True and "pendientes" in motivo


def test_un_lote_mezclado_cuenta_solo_lo_nuevo(tmp_path):
    """Cuatro ya vistos y uno nuevo son un defecto nuevo, no cinco."""
    ruta = tmp_path / "cortes.jsonl"
    lote = cinco()
    anotar_corte(ruta, lote, "primer corte")
    mezclado = cinco()[:4] + [defecto("agencia nueva", firma="zz")]
    assert debe_cortar_por_lote(
        mezclado, ya_cortados=defectos_ya_cortados(ruta))[0] is False


def test_MUERDE_si_cambio_la_huella_el_defecto_vuelve_a_contar(tmp_path):
    """Cambiamos el código: el defecto de antes puede no ser el de ahora.

    La identidad incluye `strategy_fingerprint` justamente para esto. Sin ese
    campo, un arreglo que no funcionó quedaría silenciado para siempre, que es
    el modo de falla peligroso de cualquier memoria.
    """
    ruta = tmp_path / "cortes.jsonl"
    anotar_corte(ruta, cinco(), "primer corte")
    despues = [defecto(a, firma=f"f{i}", huella="h2")
               for i, a in enumerate(LOS_CINCO)]
    assert debe_cortar_por_lote(
        despues, ya_cortados=defectos_ya_cortados(ruta))[0] is True


def test_el_radio_transversal_tampoco_se_repite(tmp_path):
    """Un radio que ya provocó un corte no vuelve a provocarlo.

    Pero ojo con lo que esto NO toca: un defecto de radio FAMILIA sigue
    generando su propio STOP por la vía de `decision == STOP`, que tiene su
    mecanismo de diferidas aparte. Acá sólo se silencia la repetición del
    CORTE POR LOTE.
    """
    ruta = tmp_path / "cortes.jsonl"
    uno = [defecto("transversal", radio=RADIO_FAMILIA)]
    assert debe_cortar_por_lote(uno)[0] is True
    anotar_corte(ruta, uno, "radio compartido")
    assert debe_cortar_por_lote(
        [defecto("transversal", radio=RADIO_FAMILIA)],
        ya_cortados=defectos_ya_cortados(ruta))[0] is False


def test_las_doce_horas_no_reviven_un_lote_ya_cortado(tmp_path):
    """El reloj no es información nueva sobre un defecto ya señalado."""
    ruta = tmp_path / "cortes.jsonl"
    ahora = time.time()
    viejo = [defecto("una", firma="a")]
    viejo[0]["epoch"] = ahora - 20 * 3600
    assert debe_cortar_por_lote(viejo, ahora=ahora)[0] is True
    anotar_corte(ruta, viejo, "doce horas")
    otra_vez = [defecto("una", firma="a")]
    otra_vez[0]["epoch"] = ahora - 40 * 3600
    assert debe_cortar_por_lote(
        otra_vez, ahora=ahora,
        ya_cortados=defectos_ya_cortados(ruta))[0] is False


def test_la_identidad_no_depende_de_la_fecha_ni_del_texto():
    """Dos apariciones del mismo defecto en pasadas distintas son una sola.

    Si la identidad incluyera `cuando` o `evidencia` —que traen la hora y el
    conteo del momento— cada pasada produciría una identidad nueva y la memoria
    no recordaría nada.
    """
    a = defecto("x")
    b = defecto("x")
    b["cuando"] = "2026-09-30T10:00:00"
    b["evidencia"] = "otro texto, otro conteo"
    b["epoch"] = a["epoch"] + 9999
    assert identidad_de_defecto(a) == identidad_de_defecto(b)


def test_un_registro_de_cortes_corrupto_no_silencia_nada(tmp_path):
    """Falla del lado seguro.

    Si el archivo no se puede leer, la respuesta correcta es **cortar de más**,
    no de menos: un corte sobrante cuesta un relanzamiento, y uno faltante deja
    corriendo código sospechado.
    """
    ruta = tmp_path / "cortes.jsonl"
    ruta.write_text("{esto no es json\n", encoding="utf-8")
    assert defectos_ya_cortados(ruta) == frozenset()
    assert debe_cortar_por_lote(
        cinco(), ya_cortados=defectos_ya_cortados(ruta))[0] is True


def test_sin_archivo_todavia_se_comporta_como_siempre(tmp_path):
    assert defectos_ya_cortados(tmp_path / "no-existe.jsonl") == frozenset()


def test_el_corte_anotado_conserva_evidencia(tmp_path):
    """El §11 pide conservar evidencia: se anota qué lote y por qué."""
    ruta = tmp_path / "cortes.jsonl"
    anotar_corte(ruta, cinco(), "5 defectos pendientes sin resolver")
    filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    assert len(filas) == 1
    assert filas[0]["motivo"] == "5 defectos pendientes sin resolver"
    assert len(filas[0]["defectos"]) == 5
    assert "fios" in json.dumps(filas[0], ensure_ascii=False)

# -*- coding: utf-8 -*-
"""Un paro solo se atraviesa si es EXACTAMENTE el que ya se diagnostico.

Lo que se prueba aca no es que la cola siga: es que siga *poco*. La lista de
diferidas no puede convertirse en un interruptor de apagado del corte por radio
transversal, porque ese corte es lo unico que impide certificar cientos de
agencias con codigo compartido roto.
"""
import json

from scripts.defect_triage import STOP
from scripts.run_agency_certification_queue import (diferidos,
                                                    paro_ya_diagnosticado)

FIRMA = {"componente_sospechoso": "extraccion_transversal_de_atributos",
         "radio_estimado": "FAMILIA", "decision": STOP}


def _escribir(tmp_path, filas):
    (tmp_path / "AGENCY_DEFECTS_DIFERIDOS.jsonl").write_text(
        "\n".join(json.dumps(f, ensure_ascii=False) for f in filas),
        encoding="utf-8")
    return tmp_path


def test_sin_lista_no_se_difiere_nada(tmp_path):
    assert diferidos(tmp_path) == {}
    assert paro_ya_diagnosticado(None, FIRMA) is None


def test_una_entrada_sin_firma_no_atraviesa_el_paro(tmp_path):
    """El caso historico: difiere del lote, no del paro."""
    d = diferidos(_escribir(tmp_path, [
        {"canonical_agency_id": "roomix:armanino", "diagnostico": "js"}]))
    assert paro_ya_diagnosticado(d["roomix:armanino"], FIRMA) is None


def test_una_entrada_con_la_firma_exacta_lo_atraviesa(tmp_path):
    d = diferidos(_escribir(tmp_path, [
        {"canonical_agency_id": "roomix:bottega propiedades",
         "diagnostico": "publica ambientes y la extraccion no los toma",
         "componente": "extraccion_transversal_de_atributos",
         "radio": "FAMILIA"}]))
    coincide = paro_ya_diagnosticado(d["roomix:bottega propiedades"], FIRMA)
    assert coincide is not None
    assert "ambientes" in coincide["diagnostico"]


def test_otro_componente_vuelve_a_parar(tmp_path):
    """Si la misma agencia falla por otra cosa, eso es un defecto nuevo."""
    d = diferidos(_escribir(tmp_path, [
        {"canonical_agency_id": "roomix:bottega propiedades",
         "diagnostico": "publica ambientes y la extraccion no los toma",
         "componente": "extraccion_transversal_de_atributos",
         "radio": "FAMILIA"}]))
    otro = dict(FIRMA, componente_sospechoso="descubrimiento_de_catalogo")
    assert paro_ya_diagnosticado(d["roomix:bottega propiedades"], otro) is None


def test_un_radio_mayor_vuelve_a_parar(tmp_path):
    """Diferir FAMILIA no difiere GLOBAL."""
    d = diferidos(_escribir(tmp_path, [
        {"canonical_agency_id": "roomix:bottega propiedades",
         "diagnostico": "publica ambientes y la extraccion no los toma",
         "componente": "extraccion_transversal_de_atributos",
         "radio": "FAMILIA"}]))
    mayor = dict(FIRMA, radio_estimado="GLOBAL")
    assert paro_ya_diagnosticado(d["roomix:bottega propiedades"], mayor) is None


def test_media_firma_no_alcanza(tmp_path):
    """Con componente y sin radio -o al reves- el paro se respeta."""
    for parcial in ({"componente": "extraccion_transversal_de_atributos"},
                    {"radio": "FAMILIA"}):
        d = diferidos(_escribir(tmp_path, [
            {"canonical_agency_id": "x", "diagnostico": "algo", **parcial}]))
        assert paro_ya_diagnosticado(d["x"], FIRMA) is None


def test_sin_diagnostico_escrito_no_entra_a_la_lista(tmp_path):
    d = diferidos(_escribir(tmp_path, [
        {"canonical_agency_id": "y", "componente": "x", "radio": "FAMILIA"}]))
    assert "y" not in d


# --- varias firmas por agencia ------------------------------------------
#
# `carlos castano` lo trajo el 2026-09-11: estaba diferida por no leer unos
# atributos y despues su sitio entro en obra, con un defecto distinto. Con una
# sola entrada por agencia la segunda pisaba a la primera.

DOS_FIRMAS = [
    {"canonical_agency_id": "roomix:carlos castano propiedades",
     "diagnostico": "el sitemap indice se consume entero y entran taxonomias",
     "componente": "extraccion_transversal_de_atributos", "radio": "FAMILIA"},
    {"canonical_agency_id": "roomix:carlos castano propiedades",
     "diagnostico": "el sitio esta en obra: property-sitemap.xml da 404",
     "componente": "perdida_sistematica_de_inventario", "radio": "FAMILIA"},
]


def test_una_agencia_puede_tener_varias_firmas(tmp_path):
    d = diferidos(_escribir(tmp_path, DOS_FIRMAS))
    assert len(d["roomix:carlos castano propiedades"]) == 2


def test_la_segunda_firma_no_pisa_a_la_primera(tmp_path):
    d = diferidos(_escribir(tmp_path, DOS_FIRMAS))
    entradas = d["roomix:carlos castano propiedades"]
    vieja = paro_ya_diagnosticado(entradas, FIRMA)
    assert vieja is not None, "la firma vieja tiene que seguir cubriendo"
    assert "taxonomias" in vieja["diagnostico"]


def test_cada_firma_anota_su_propio_diagnostico(tmp_path):
    """Si coincide la segunda, el log no puede contar la historia de la primera."""
    d = diferidos(_escribir(tmp_path, DOS_FIRMAS))
    entradas = d["roomix:carlos castano propiedades"]
    nueva = paro_ya_diagnosticado(
        entradas, {"componente_sospechoso": "perdida_sistematica_de_inventario",
                   "radio_estimado": "FAMILIA", "decision": STOP})
    assert nueva is not None
    assert "en obra" in nueva["diagnostico"]


def test_varias_firmas_no_aflojan_el_corte(tmp_path):
    """Tener dos no abre la puerta a un tercero."""
    d = diferidos(_escribir(tmp_path, DOS_FIRMAS))
    tercero = {"componente_sospechoso": "imagenes_compartidas",
               "radio_estimado": "FAMILIA", "decision": STOP}
    assert paro_ya_diagnosticado(
        d["roomix:carlos castano propiedades"], tercero) is None


def test_la_lista_real_difiere_bottega_y_solo_por_su_defecto():
    """Contra el archivo de la corrida, no contra uno inventado."""
    from pathlib import Path
    salida = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    if not (salida / "AGENCY_DEFECTS_DIFERIDOS.jsonl").exists():
        return
    d = diferidos(salida)
    bottega = d.get("roomix:bottega propiedades")
    assert bottega, "bottega tiene que estar diferida"
    assert paro_ya_diagnosticado(bottega, FIRMA) is not None
    # Y las historicas siguen sin poder atravesar un paro.
    for agencia in ("roomix:armanino negocios inmobiliarios",
                    "roomix:attaguile propiedades"):
        if agencia in d:
            assert paro_ya_diagnosticado(d[agencia], FIRMA) is None

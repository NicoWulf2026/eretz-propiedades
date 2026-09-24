# -*- coding: utf-8 -*-
"""Una certificación no puede llevar la huella de un código que no corrió.

`strategy_fingerprint` lee de disco en el momento en que se la pide, y el
certificador la estampa al TERMINAR la agencia. Un worker corre con el código
que cargó al arrancar. Si alguien edita un conector con los workers en marcha,
la certificación siguiente sale con la huella del código NUEVO habiendo corrido
el VIEJO: parece vigente y no lo es.
"""
from __future__ import annotations

import json
from pathlib import Path

import scripts.agency_fingerprints as af
from scripts.agency_fingerprints import (archivos_de_la_huella,
                                         codigo_cambiado_desde_el_arranque,
                                         current_code_evidence,
                                         fingerprint_components)
from scripts.run_agency_certification_queue import sin_huella_ajena


def test_la_guarda_conoce_todos_los_archivos_de_la_huella(monkeypatch):
    """Un archivo que entra en la huella y no en la lista es un cambio que
    la guarda no vería."""
    leidos: set[str] = set()
    original = Path.read_text

    def registrar(self, *a, **k):
        leidos.add(str(self.resolve()))
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", registrar)
    af._semantic_file_cacheado.cache_clear()
    af._archivo_sin_operativas.cache_clear()
    for conector, estrategia in (("generico", "generic/html_catalog"),
                                 ("generico", "generic/sitemap"),
                                 ("generico", "generic/php_ajax_search"),
                                 ("tokko", "tokko"), ("wasi", "wasi"),
                                 ("wordpress", "wordpress"),
                                 ("century21", "century21")):
        fingerprint_components(conector, estrategia)
    conocidos = {str(p.resolve()) for p in archivos_de_la_huella()}
    codigo = {p for p in leidos if p.endswith(".py")}
    assert codigo <= conocidos, sorted(codigo - conocidos)


def test_sin_cambios_no_hay_nada_que_reportar():
    assert codigo_cambiado_desde_el_arranque() == []


def test_MUERDE_un_archivo_editado_despues_de_arrancar_se_detecta(monkeypatch):
    antes, geo = af._ESTADO_AL_IMPORTAR
    alterado = tuple((r, (m or 0) - 1, t) if r.endswith("base.py") else (r, m, t)
                     for r, m, t in antes)
    monkeypatch.setattr(af, "_ESTADO_AL_IMPORTAR", (alterado, geo))
    cambiados = codigo_cambiado_desde_el_arranque()
    assert len(cambiados) == 1 and cambiados[0].endswith("base.py")


def test_MUERDE_el_resultado_en_vuelo_pierde_la_huella_y_deja_de_ser_vigente(
        tmp_path):
    canonical = "roomix:prueba"
    import hashlib
    paquete = tmp_path / "agencies" / hashlib.sha256(
        canonical.encode()).hexdigest()[:16]
    paquete.mkdir(parents=True)
    resultado = {"canonical_agency_id": canonical,
                 "status": "CERTIFIED_COMPLETE",
                 "fingerprint_schema_version": af.FINGERPRINT_SCHEMA_VERSION,
                 "connector": "tokko", "connector_strategy": "tokko",
                 "strategy_fingerprint": af.strategy_fingerprint("tokko", "tokko")}
    (paquete / "certification.json").write_text(json.dumps(resultado),
                                                 encoding="utf-8")
    assert current_code_evidence(resultado) is True

    corregido = sin_huella_ajena(tmp_path, resultado, ["connectors/tokko.py"])
    assert current_code_evidence(corregido) is False
    assert corregido["status"] == "CERTIFIED_COMPLETE"  # no se toca nada más
    assert corregido["codigo_cambio_en_vuelo"] == ["connectors/tokko.py"]
    en_disco = json.loads((paquete / "certification.json").read_text(
        encoding="utf-8"))
    assert en_disco["strategy_fingerprint"] is None

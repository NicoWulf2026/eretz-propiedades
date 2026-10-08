"""Los AFIRMABLE viejos sin estado del resolver se vuelven a abrir; no se ascienden por decreto (mision 08-10)."""
from __future__ import annotations

import json

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verificar_webs_del_directorio as v  # noqa: E402


def _rec(resolucion="NOT_FOUND_IN_ERETZ", dominio="https://vieja.com.ar"):
    return {"resolution": {"resolution_status": resolucion}, "live": {}, "source": {},
            "platform": {"web_kind": "OFFICIAL_WEB", "domain": dominio}, "directory": {}, "verificada": {}}


def test_toma_solo_los_viejos_sin_resolver_y_abre_su_url(tmp_path, monkeypatch):
    destino = tmp_path / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
    filas = [
        {"canonical_agency_id": "roomix:vieja", "estado": "AFIRMABLE", "official_url": "https://registro-viejo.com.ar"},
        {"canonical_agency_id": "roomix:completa", "estado": "AFIRMABLE", "official_url": "https://ok.com.ar",
         "estado_del_resolver": "OFFICIAL_WEB_VERIFIED"},
        {"canonical_agency_id": "roomix:en_main", "estado": "AFIRMABLE", "official_url": "https://m.com.ar"},
    ]
    destino.write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
    monkeypatch.setattr(v, "DESTINO", destino)
    catalogo = {"roomix:vieja": _rec(), "roomix:completa": _rec(), "roomix:en_main": _rec("RESOLVED"),
                "roomix:sin_registro": _rec()}
    cohorte = v.cohorte_sin_resolver(catalogo)
    assert [c for c, _ in cohorte] == ["roomix:vieja"]
    # Se abre la url del registro viejo, que es la que hay que confirmar o descartar.
    assert cohorte[0][1]["platform"]["domain"] == "https://registro-viejo.com.ar"


def test_la_ultima_fila_manda(tmp_path, monkeypatch):
    destino = tmp_path / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl"
    filas = [{"canonical_agency_id": "roomix:x", "estado": "AFIRMABLE", "official_url": "https://a.com.ar"},
             {"canonical_agency_id": "roomix:x", "estado": "AFIRMABLE", "official_url": "https://a.com.ar",
              "estado_del_resolver": "OFFICIAL_WEB_HIGH_CONFIDENCE"}]
    destino.write_text("\n".join(json.dumps(f) for f in filas), encoding="utf-8")
    monkeypatch.setattr(v, "DESTINO", destino)
    assert v.cohorte_sin_resolver({"roomix:x": _rec()}) == []


def test_candidatas_sin_web_solo_las_de_dominio_propio_y_raiz_primero(monkeypatch):
    rec = {"resolution": {"resolution_status": "NOT_FOUND_IN_ERETZ"}, "live": {}, "source": {},
           "platform": {}, "verificada": {},
           "directory": {"candidate_urls": ["https://www.zonaprop.com.ar/inmobiliarias/beber",
                                            "https://www.beberinmobiliariaguemes.com.ar/venta/",
                                            "https://empresite.eleconomista.es/BEBER.html",
                                            "http://beberinmobiliaria.com.ar/"]}}
    cohorte = v.cohorte_candidatas_sin_web({"roomix:beber negocios inmobiliarios": rec})
    assert [r["platform"]["domain"] for _c, r in cohorte] == [
        "http://beberinmobiliaria.com.ar/", "https://www.beberinmobiliariaguemes.com.ar/venta/"]

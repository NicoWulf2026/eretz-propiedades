"""Que se suma, que se refresca por alias y que se retira de la snapshot."""
from __future__ import annotations

import json
import sqlite3

from scripts.snapshot_certificadas import (Conocidas, conocidas_de, decidir,
                                           numeros_de_url, paquetes_vigentes)

AG = "roomix:uno"


def _pre(filas):
    """Una preingestion minima: (canonical, status, hash, url_normalizada, fila)."""
    db = sqlite3.connect(":memory:")
    db.execute("create table rows (row_json text, canonical_id text, status text, "
               "hash_dedup text, url_normalized text)")
    for canonical, status, h, url, fila in filas:
        db.execute("insert into rows values (?,?,?,?,?)",
                   (json.dumps(fila), canonical, status, h, url))
    return conocidas_de(db)


def _fila(h, url, aviso, **extra):
    return dict({"hash_dedup": h, "source_url": url, "source_listing_id": aviso,
                 "inmobiliaria_id": 7, "canonical_agency_id": AG,
                 "titulo": f"Casa {aviso}", "precio": 100000, "moneda": "USD"}, **extra)


def _cert(status="CERTIFIED_COMPLETE"):
    return {"canonical_agency_id": AG, "status": status, "checked_at": "2026-09-28T10:00:00"}


PRE = [
    (AG, "CANDIDATE", "h-vieja", "a.com/p/7779042-casa-vieja",
     {"source_url": "https://a.com/p/7779042-casa-vieja", "source_listing_id": "7779042",
      "titulo": "Casa vieja", "precio": 1}),
    (AG, "CANDIDATE", "h-vendida", "a.com/p/5550001-vendida",
     {"source_url": "https://a.com/p/5550001-vendida", "source_listing_id": "5550001",
      "titulo": "Vendida", "precio": 2}),
]


def test_una_propiedad_sin_ninguna_senal_previa_se_suma_limpia():
    d = decidir([(_cert(), [_fila("h-nueva", "https://a.com/p/9990001-nueva", "9990001",
                                  descripcion="Linda casa <script>var x=1;</script>")])],
                _pre(PRE))
    assert [f["hash_dedup"] for f in d.nuevas] == ["h-nueva"]
    nueva = d.nuevas[0]
    assert "script" not in (nueva["descripcion"] or "")
    assert nueva["_snapshot_certificadas"]["agencia"] == AG


def test_el_mismo_aviso_con_url_nueva_refresca_a_la_fila_servida():
    fresca = _fila("h-slug-nuevo", "https://a.com/p/7779042-casa-renovada", "7779042")
    d = decidir([(_cert(), [fresca])], _pre(PRE))
    assert d.nuevas == []
    assert d.alias == {"h-vieja": fresca}


def test_ante_cualquier_senal_de_que_ya_esta_no_se_suma():
    # Mismo numero en la URL con otro id declarado, y misma firma de titulo.
    por_numero = _fila("h-a", "https://a.com/ficha/7779042", "otro-id")
    por_firma = _fila("h-b", "https://a.com/x/nada", "zz", titulo="Vendida", precio=2)
    d = decidir([(_cert(), [por_numero, por_firma])], _pre(PRE))
    assert d.nuevas == []
    assert d.motivos["numero_de_url_ya_visto"] == 1
    assert d.motivos["misma_firma"] == 1


def test_solo_un_inventario_completo_retira_lo_que_ya_no_publica():
    vigente = [_fila("h-vieja", "https://a.com/p/7779042-casa-vieja", "7779042")]
    assert decidir([(_cert(), vigente)], _pre(PRE)).retirables == {"h-vendida"}
    assert decidir([(_cert("CERTIFIED_BEST_AVAILABLE"), vigente)], _pre(PRE)).retirables == set()


def test_url_reclamada_por_dos_agencias_no_se_suma_y_la_web_ajena_tampoco():
    otra = {"canonical_agency_id": "roomix:dos", "status": "CERTIFIED_COMPLETE",
            "checked_at": "2026-09-28T10:00:00"}
    fila = _fila("h-x", "https://comun.com/p/4440001", "4440001")
    d = decidir([(_cert(), [fila]), (otra, [dict(fila, hash_dedup="h-y")])], _pre([]))
    assert d.nuevas == [] and d.motivos["url_de_varias_agencias"] == 2
    d = decidir([(_cert(), [fila])], _pre([]), ajenas={AG})
    assert d.nuevas == [] and d.motivos["omitida_web_ajena"] == 1


def test_solo_cuenta_el_cierre_vigente_del_ledger(tmp_path):
    paquetes = tmp_path / "agencies"
    for nombre, status, cuando in (("uno", "CERTIFIED_COMPLETE", "2026-09-20T10:00:00"),):
        carpeta = paquetes / nombre
        carpeta.mkdir(parents=True)
        (carpeta / "certification.json").write_text(json.dumps(
            {"canonical_agency_id": AG, "status": status, "checked_at": cuando}))
        (carpeta / "properties_run2.jsonl").write_text(json.dumps(_fila("h", "https://a.com/p/1234", "1234")))
    ledger = tmp_path / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    filas = [{"canonical_agency_id": AG, "status": "CERTIFIED_COMPLETE", "checked_at": "2026-09-20T10:00:00"},
             {"canonical_agency_id": AG, "status": "NEEDS_FIX", "checked_at": "2026-09-27T10:00:00"}]
    ledger.write_text("\n".join(json.dumps(f) for f in filas) + "\n")
    # El paquete certificado es de antes que el NEEDS_FIX vigente: no aporta.
    assert paquetes_vigentes(paquetes, ledger) == []


def test_numeros_de_url_ignora_el_host_y_los_numeros_cortos():
    assert numeros_de_url("https://www.9010inmobiliaria.com.ar/p-17_x?id=123456") == {"123456"}
    assert isinstance(Conocidas().numeros, dict)

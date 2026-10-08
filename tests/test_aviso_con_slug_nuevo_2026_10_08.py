"""Un aviso que ya se sirve no vuelve como alta porque la fuente le cambio el slug.

08-10, candidata sprint_rc3: P2 freno el despliegue por 14 duplicados probables con
altas (tope 10). Los 14 eran el MISMO aviso dos veces: la fila servida con el slug
viejo (`/p/10500121-...-Rivadavia-627`) y el paquete certificado nuevo con el slug
editado (`/p/10500121-...-Rivadavia-621`). La fila servida habia entrado por un
paquete (SUMADA_CERTIFICADA), no esta en la preingestion, asi que `decidir` no la
conocia; y `_servidas_a_conservar` la conservaba porque su hash no volvia. La regla
`numero_de_url_ya_visto` de la preingestion se aplica ahora tambien a lo servido
huerfano: el aviso nuevo no entra y la fila servida sigue tal cual (P1/P8).
"""
from __future__ import annotations

import sqlite3

from scripts.api_snapshot import _sin_avisos_ya_servidos

VIEJA = "https://www.inmobiliariamusuliotis.com.ar/p/10500121-Departamento-en-Alquiler-en-Concordia-Rivadavia-627"
NUEVA = "https://www.inmobiliariamusuliotis.com.ar/p/10500121-Departamento-en-Alquiler-en-Concordia-Rivadavia-621"
AGENCIA = "roomix:juan martin musuliotis negocios inmobiliarios"


def _origen(tmp_path, hashes):
    con = sqlite3.connect(tmp_path / "origen.sqlite3")
    con.execute("create table rows (hash_dedup text, status text, row_json text)")
    con.executemany("insert into rows values (?, 'CANDIDATE', '{}')", [(h,) for h in hashes])
    return con


def _servida(tmp_path, filas):
    ruta = tmp_path / "servida.sqlite3"
    con = sqlite3.connect(ruta)
    con.execute("create table propiedades (id text, agency_id text, source_url text)")
    con.executemany("insert into propiedades values (?, ?, ?)", filas)
    con.commit(); con.close()
    return ruta


def _nueva(h, url, agencia=AGENCIA):
    return {"hash_dedup": h, "source_url": url, "_snapshot_certificadas": {"agencia": agencia}}


def test_MUERDE_el_slug_nuevo_de_un_aviso_servido_no_es_un_alta(tmp_path):
    servida = _servida(tmp_path, [("viejo", AGENCIA, VIEJA)])
    quedan, iguales = _sin_avisos_ya_servidos(_origen(tmp_path, []), servida,
                                              [_nueva("nuevo", NUEVA)], set())
    assert quedan == [] and iguales == 1


def test_la_fila_servida_que_el_paquete_sigue_listando_se_refresca(tmp_path):
    # Mismo hash en el paquete: no es huerfana, la fila fresca entra como siempre.
    servida = _servida(tmp_path, [("viejo", AGENCIA, VIEJA)])
    nuevas = [_nueva("viejo", VIEJA)]
    quedan, iguales = _sin_avisos_ya_servidos(_origen(tmp_path, []), servida, nuevas, set())
    assert quedan == nuevas and iguales == 0


def test_otra_agencia_con_el_mismo_numero_no_bloquea(tmp_path):
    servida = _servida(tmp_path, [("viejo", "roomix:otra", VIEJA)])
    nuevas = [_nueva("nuevo", NUEVA)]
    assert _sin_avisos_ya_servidos(_origen(tmp_path, []), servida, nuevas, set()) == (nuevas, 0)


def test_lo_servido_retirado_por_politica_no_bloquea_el_alta(tmp_path):
    servida = _servida(tmp_path, [("viejo", AGENCIA, VIEJA)])
    nuevas = [_nueva("nuevo", NUEVA)]
    assert _sin_avisos_ya_servidos(_origen(tmp_path, []), servida, nuevas, {"viejo"}) == (nuevas, 0)


def test_lo_que_sigue_en_la_preingestion_no_es_huerfano(tmp_path):
    # La preingestion lo tiene: la regla de `decidir` ya lo cubre por esa via.
    servida = _servida(tmp_path, [("viejo", AGENCIA, VIEJA)])
    nuevas = [_nueva("nuevo", NUEVA)]
    assert _sin_avisos_ya_servidos(_origen(tmp_path, ["viejo"]), servida, nuevas, set()) == (nuevas, 0)


def test_numeros_cortos_no_cuentan_como_id_de_aviso(tmp_path):
    # Una altura de calle de 4 cifras no identifica un aviso (mismo criterio que P2).
    servida = _servida(tmp_path, [("viejo", AGENCIA, "https://x.com.ar/casa-zacagnini-6600")])
    nuevas = [_nueva("nuevo", "https://x.com.ar/otra-casa-zacagnini-6600")]
    assert _sin_avisos_ya_servidos(_origen(tmp_path, []), servida, nuevas, set()) == (nuevas, 0)


def test_sin_servida_no_filtra(tmp_path):
    nuevas = [_nueva("nuevo", NUEVA)]
    assert _sin_avisos_ya_servidos(_origen(tmp_path, []), None, nuevas, set()) == (nuevas, 0)

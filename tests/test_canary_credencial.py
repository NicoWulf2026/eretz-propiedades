#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Con que usuario se entra a escribir, y con cual no.

El canary asume el rol de escritura con SET LOCAL, que es lo correcto: el
privilegio dura la transaccion y se suelta solo. Pero eso solo tiene sentido si
se ENTRA con un usuario que no podia escribir de por si. Entrando como
superusuario, el SET LOCAL es decorativo: la restriccion que el rol minimo
existe para imponer ya se salteo antes de la primera sentencia.

Estaba cableado para tomar la URL que hubiera configurada, y la que habia era la
del superusuario. Fallaba por contrasena vencida, no por diseno: el dia que
alguien la renovara habria escrito como postgres sin que nadie lo notara.

Estos tests fijan la unica regla que importa aca: si el usuario no es el de solo
lectura, no se entra, y se dice por que.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.property_write_canary import (PROHIBIDOS,  # noqa: E402
                                           USUARIO_ESPERADO, VARIABLES_RO,
                                           elegir_credencial, usuario_de)

RO = "postgresql://eretz_preview_ro:x@host:5432/db"
SUPER = "postgresql://postgres:x@host:5432/db"


def limpiar(monkeypatch):
    for v in VARIABLES_RO + ("SUPABASE_POOLER_DATABASE_URL",
                             "SUPABASE_DATABASE_URL"):
        monkeypatch.delenv(v, raising=False)


def test_el_usuario_se_lee_de_la_url():
    assert usuario_de(RO) == "eretz_preview_ro"
    assert usuario_de(SUPER) == "postgres"
    assert usuario_de("") == ""


def test_se_prefiere_la_credencial_de_solo_lectura(monkeypatch):
    limpiar(monkeypatch)
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL", RO)
    monkeypatch.setenv("SUPABASE_DATABASE_URL", SUPER)
    url, via = elegir_credencial()
    assert url == RO
    assert USUARIO_ESPERADO in via


def test_el_pooler_gana_cuando_existe(monkeypatch):
    """El endpoint directo de Supabase es IPv6 por diseno; desde una red sin
    IPv6 utilizable no resuelve y el canary parece roto sin estarlo."""
    limpiar(monkeypatch)
    pooler = "postgresql://eretz_preview_ro:x@pooler:6543/db"
    monkeypatch.setenv("ERETZ_PREVIEW_RO_POOLER_URL", pooler)
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL", RO)
    assert elegir_credencial()[0] == pooler


def test_el_superusuario_no_se_usa_aunque_sea_lo_unico_que_hay(monkeypatch):
    limpiar(monkeypatch)
    monkeypatch.setenv("SUPABASE_DATABASE_URL", SUPER)
    url, via = elegir_credencial()
    assert url == ""
    assert "postgres" in via


def test_ninguno_de_los_privilegiados_pasa(monkeypatch):
    for quien in PROHIBIDOS:
        limpiar(monkeypatch)
        monkeypatch.setenv("SUPABASE_DATABASE_URL",
                           "postgresql://%s:x@host:5432/db" % quien)
        assert elegir_credencial()[0] == "", quien


def test_una_variable_ro_apuntando_a_un_privilegiado_tampoco_pasa(monkeypatch):
    """El nombre de la variable no es evidencia de nada: lo que decide es el
    usuario que viaja en la URL."""
    limpiar(monkeypatch)
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL", SUPER)
    url, via = elegir_credencial()
    assert url == ""
    assert "prohibido" in via


def test_sin_nada_configurado_lo_dice(monkeypatch):
    limpiar(monkeypatch)
    url, via = elegir_credencial()
    assert url == ""
    assert "ninguna" in via


def test_an_unlisted_admin_or_writer_is_not_mistaken_for_read_only(monkeypatch):
    limpiar(monkeypatch)
    monkeypatch.setenv('ERETZ_PREVIEW_RO_URL', 'postgresql://unlisted_admin:x@host/db')
    assert elegir_credencial()[0] == ''


def test_pooler_project_suffix_does_not_break_valid_ro_login(monkeypatch):
    limpiar(monkeypatch)
    url = 'postgresql://eretz_preview_ro.project:x@host/db'
    monkeypatch.setenv('ERETZ_PREVIEW_RO_POOLER_URL', url)
    assert elegir_credencial()[0] == url


def test_wrong_live_session_refuses_before_set_role_or_insert(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from scripts import property_write_canary as canary
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.fetchone.return_value = ('unlisted_admin', 'unlisted_admin', 'test_database')
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    monkeypatch.setattr(canary, 'cargar_env', lambda: None)
    monkeypatch.setattr(canary, 'elegir_credencial', lambda: (RO, 'test RO fixture'))
    monkeypatch.setattr(canary, 'leer', lambda path: [{'source_url': 'https://agency.test/p/123'}])
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda *args, **kwargs: connection))
    monkeypatch.setattr(sys, 'argv', ['canary', '--entrada', 'never-read.jsonl', '--escribir'])
    assert canary.main() == 3
    assert cursor.execute.call_count == 1
    assert cursor.execute.call_args.args[0].startswith('select current_user')


def test_la_explicacion_no_puede_llevar_la_contrasena(monkeypatch):
    limpiar(monkeypatch)
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL",
                       "postgresql://eretz_preview_ro:SECRETO123@h:5432/db")
    _, via = elegir_credencial()
    assert "SECRETO123" not in via


def test_el_camino_de_escritura_sigue_siendo_el_minimo():
    src = (Path(__file__).resolve().parents[1] / "scripts"
           / "property_write_canary.py").read_text(encoding="utf-8")
    assert "SET LOCAL ROLE" in src
    assert "ON CONFLICT (hash_dedup) DO NOTHING" in src
    assert "internal_scraping.propiedades_raw" in src
    # y sigue haciendo ROLLBACK salvo que se pida lo contrario
    assert "--escribir" in src

# -*- coding: utf-8 -*-
"""La guarda de escritura, en las tres puertas y no en una.

`SupabaseClient` expone seis escritores. Cuatro no los llama nadie, y uno de
esos cuatro -`batch_save_only_changed`- hace un PATCH con lista NEGRA de tres
campos: puede reasignar una propiedad a otra inmobiliaria y reescribir su
`hash_dedup`, sin comprobar contra que fila escribe y sin dejar auditoria.

La proteccion ya existia y estaba en una sola de las tres entradas:

    scripts/run_manifest.py       -> cliente envuelto
    scraper/playwright_scraper.py -> cliente CRUDO
    scraper/run.py                -> cliente CRUDO

Esto cubre las otras dos. Los tests que muerden son los que comprueban que la
guarda **no** deja pasar los escritores sin uso y que **si** deja pasar las
lecturas: una guarda que rompe las lecturas no se aplica, y entonces no
protege nada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scraper"))

from scraper.clients import EscrituraVigilada  # noqa: E402


class ClienteFalso:
    table = "propiedades"

    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def _anotar(self, nombre: str):
        def metodo(*args, **kwargs):
            self.llamadas.append(nombre)
            return nombre
        return metodo

    def __getattr__(self, nombre: str):
        return self._anotar(nombre)


def vigilado(*escrituras: str) -> EscrituraVigilada:
    return EscrituraVigilada(ClienteFalso(), escrituras or
                             ("batch_save_only_new", "batch_save_safe_merge"))


@pytest.mark.parametrize("escritor", [
    "batch_save_only_changed", "update_location", "mark_as_inactive",
    "save_historial", "save"])
def test_MUERDE_los_escritores_sin_uso_no_pasan(escritor):
    """Los cinco que hoy no llama nadie. `batch_save_only_changed` es el peligroso."""
    with pytest.raises(RuntimeError, match="escritura no autorizada"):
        getattr(vigilado(), escritor)


def test_MUERDE_las_lecturas_que_los_scrapers_necesitan_si_pasan():
    """Si estas se bloquearan, la guarda no se podria aplicar y no protegeria nada.

    Es exactamente por esto que no se reuso `_InsertOnlySupabaseProxy` tal
    cual: bloquea todo lo que no sean sus dos metodos.
    """
    guarda = vigilado()
    assert guarda.get_all_existing_urls() == "get_all_existing_urls"
    assert guarda.get_active_urls_by_fuente() == "get_active_urls_by_fuente"


def test_las_escrituras_autorizadas_pasan_y_llegan_al_cliente():
    cliente = ClienteFalso()
    guarda = EscrituraVigilada(cliente, ("batch_save_only_new",))
    guarda.batch_save_only_new([{"url": "https://x.test/p/1"}])
    assert cliente.llamadas == ["batch_save_only_new"]


def test_MUERDE_un_metodo_nuevo_queda_bloqueado_por_defecto():
    """Lo que hace que esto sirva a futuro.

    Una lista negra dejaria entrar cualquier escritor agregado despues; una
    lista blanca lo bloquea hasta que alguien lo autorice a proposito.
    """
    with pytest.raises(RuntimeError, match="escritura no autorizada"):
        vigilado().borrar_todo


def test_MUERDE_no_se_autoriza_una_lectura_como_si_fuera_escritura():
    """No rompe nada hoy y hace ilegible la lista el dia que importe."""
    with pytest.raises(ValueError, match="no son escrituras"):
        EscrituraVigilada(ClienteFalso(), ("get_all_existing_urls",))


def test_el_mensaje_dice_donde_paso():
    guarda = EscrituraVigilada(ClienteFalso(), (), donde="playwright_scraper")
    with pytest.raises(RuntimeError, match="playwright_scraper"):
        guarda.mark_as_inactive


def test_MUERDE_las_tres_entradas_envuelven_el_cliente():
    """La razon de ser de todo esto: que no quede ninguna puerta cruda.

    Se lee el codigo fuente porque construir los clientes de verdad exige
    credenciales y red. Es una prueba de forma, y la forma es justamente lo
    que se rompio: el cliente estaba envuelto en un archivo y crudo en dos.
    """
    crudo = "SupabaseClient(session, SUPABASE_URL"
    for ruta in ("scraper/playwright_scraper.py", "scraper/run.py"):
        fuente = (RAIZ / ruta).read_text(encoding="utf-8")
        assert "EscrituraVigilada(" in fuente, ruta
        # La construccion cruda sigue existiendo, pero solo adentro de la guarda.
        posicion = fuente.index(crudo)
        antes = fuente[max(0, posicion - 200):posicion]
        assert "EscrituraVigilada(" in antes, ruta
    manifest = (RAIZ / "scripts" / "run_manifest.py").read_text(encoding="utf-8")
    assert "_InsertOnlySupabaseProxy(raw_supabase)" in manifest

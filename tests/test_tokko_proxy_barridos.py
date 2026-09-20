# -*- coding: utf-8 -*-
"""La API de Tokko reordena entre pedidos, y el proxy hacía una sola pasada.

`alta inmobiliaria` paró la cola con radio COMPARTIDO y `sin_determinar`:

    run1  16 propiedades   OK   cobertura 1.0
    run2  18 propiedades   OK   cobertura 1.0
    reasons: run inventories differ, second run is not idempotent

Dos corridas idénticas, once segundos de diferencia, inventarios distintos. No
es rotación del catálogo: es lo que el propio conector de Tokko ya tiene
documentado y resuelto desde hace tiempo, en su hermano:

    Tokko reordena el conjunto entre pedidos: dos barridos identicos devuelven
    subconjuntos distintos, asi que una sola pasada deja afuera entre un 6% y
    un 14% del inventario aunque recorra todas las paginas que el total
    declarado implica.

16 de 18 es el 11 % faltante, justo dentro de esa banda.

`connectors/tokko.py` lo resuelve repitiendo el barrido mientras aparezca
material nuevo. `generic/tokko_proxy` —que lee la MISMA API desde el frontend
propio de la agencia— no heredó la contramedida y barría una sola vez.

Hoy es una agencia. Lo que cuesta no es su inventario: es que cada pasada de
la cola se detiene en ella con radio COMPARTIDO, y eso para los dos workers.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.base import Descargador, Fuente  # noqa: E402
from connectors.generico import GenericoConnector  # noqa: E402

TODOS = [f"{i}" for i in range(1, 19)]          # 18 propiedades reales


class ApiQueReordena(Descargador):
    """Devuelve subconjuntos distintos en cada barrido, como hace Tokko.

    En el primer barrido esconde dos; en el segundo las muestra y esconde
    otras dos. Ninguna pasada sola ve las dieciocho.
    """

    def __init__(self):
        self.barrido = 0
        self.pedidos: list[str] = []

    def bajar(self, url: str, *a, **k) -> str:
        self.pedidos.append(url)
        if "offset=0" in url and "limit=1&" in url:
            return json.dumps({"count": 18, "objects": [{"id": "1"}]})
        offset = int(url.split("offset=")[1].split("&")[0])
        if offset == 0:
            self.barrido += 1
        escondidas = {"17", "18"} if self.barrido <= 1 else {"1", "2"}
        visibles = [i for i in TODOS if i not in escondidas]
        trozo = visibles[offset:offset + 50]
        return json.dumps({"count": 18,
                           "objects": [{"id": i} for i in trozo]})

    def url_segura(self, url: str) -> str:
        return url


def plan_proxy() -> dict:
    return {"variante": "TOKKO_PROXY_JSON", "soportada": True,
            "base": "https://alta.test", "tokko_proxy_ruta": "/api/tokko/properties",
            "total_declarado": 18}


def fuente() -> Fuente:
    return Fuente(canonical_agency_id="roomix:alta", agency_name="Alta",
                  official_url="https://alta.test")


def test_MUERDE_un_solo_barrido_no_ve_todo_y_dos_si():
    """El caso `alta inmobiliaria`, exacto.

    Con un barrido salen 16 de 18. La contramedida es la misma que ya usa el
    conector de Tokko: repetir mientras aparezca material nuevo.
    """
    descargador = ApiQueReordena()
    conector = GenericoConnector(descargador)
    avisos = list(conector.fetch_listing(fuente(), plan_proxy()))
    ids = {a["source_listing_id"] for a in avisos}
    assert len(ids) == 18, sorted(ids, key=int)


def test_no_se_repiten_propiedades_entre_barridos():
    """Un id ya visto no se emite de nuevo.

    Sin esa guarda, dos barridos duplicarían el inventario y la agencia
    cerraría con el doble de propiedades que tiene.
    """
    conector = GenericoConnector(ApiQueReordena())
    avisos = list(conector.fetch_listing(fuente(), plan_proxy()))
    ids = [a["source_listing_id"] for a in avisos]
    assert len(ids) == len(set(ids))


def test_MUERDE_no_se_barre_para_siempre_si_no_aparece_nada_nuevo():
    """Una API estable tiene que cerrar en un barrido y no golpear de más.

    Repetir sin freno multiplicaría los pedidos a una fuente ajena por el
    número de barridos, que es justo lo que el límite de ritmo evita.
    """

    class ApiEstable(ApiQueReordena):
        def bajar(self, url, *a, **k):
            self.pedidos.append(url)
            if "limit=1&" in url:
                return json.dumps({"count": 18, "objects": [{"id": "1"}]})
            offset = int(url.split("offset=")[1].split("&")[0])
            trozo = TODOS[offset:offset + 50]
            return json.dumps({"count": 18,
                               "objects": [{"id": i} for i in trozo]})

    descargador = ApiEstable()
    conector = GenericoConnector(descargador)
    avisos = list(conector.fetch_listing(fuente(), plan_proxy()))
    assert len({a["source_listing_id"] for a in avisos}) == 18
    # Un barrido que alcanza el total declarado no dispara otro.
    paginas = [u for u in descargador.pedidos if "limit=1&" not in u]
    assert len(paginas) <= 2, paginas


def test_sin_total_declarado_igual_se_repite_mientras_aparezca_material():
    """No se depende de `count`, que puede mentir.

    El comentario del propio bucle lo dice: un total declarado que miente
    cortaría la enumeración antes de tiempo. El criterio de corte es que un
    barrido no aporte nada nuevo.
    """
    plan = plan_proxy()
    plan["total_declarado"] = None
    conector = GenericoConnector(ApiQueReordena())
    ids = {a["source_listing_id"]
           for a in conector.fetch_listing(fuente(), plan)}
    assert len(ids) == 18

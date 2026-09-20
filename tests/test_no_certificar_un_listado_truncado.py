# -*- coding: utf-8 -*-
"""«No sé si terminé» no puede seguir contándose como «terminé».

El 2026-09-20 Tokko cambió cómo arma la url de paginación y el conector quedó
sin poder pedir la página 2. Devolvía los 20 avisos de la primera y el bucle
cortaba en `else: break`. `aagaard` declara 295 y se enumeraron 20.

Esa vez **la cola lo atrapó**, porque la fuente declaraba un total y la guarda
`catalogo_declarado_mayor_que_el_enumerado` comparó. Pero la guarda depende de
que la fuente declare, y la protección se caía justo donde no declara:

    r["enumeracion_completa"] = (r["cobertura"] is None
                                 or r["cobertura"] >= COBERTURA_MINIMA)

`cobertura is None` significa «no hay total declarado», o sea **no sé**, y
estaba escrito como **sí**. Medido sobre las 166 certificaciones vigentes: 150
tienen techo declarado y **16 no lo tienen**, y esas 16 no las mira nadie.

La distinción que faltaba no es entre «completo» y «corto» sino entre dos
maneras de terminar:

- la paginación **se agotó** —una página no trajo ids nuevos, o se llegó a la
  última—: eso sí prueba exhaustividad, aunque no haya total declarado;
- la paginación **no pudo continuar** —no sabemos pedir la página 2—: eso no
  prueba nada, y es lo que pasó con Tokko.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from run_rollout import COBERTURA_MINIMA, enumeracion_es_completa  # noqa: E402


def test_con_total_declarado_y_cobertura_suficiente_es_completa():
    assert enumeracion_es_completa(cobertura=1.0, paginacion_imposible=False)
    assert enumeracion_es_completa(cobertura=COBERTURA_MINIMA,
                                   paginacion_imposible=False)


def test_con_total_declarado_y_cobertura_corta_no_es_completa():
    assert not enumeracion_es_completa(cobertura=0.07,
                                       paginacion_imposible=False)


def test_sin_total_declarado_la_paginacion_agotada_si_prueba():
    """No se rompe el caso de siempre.

    La mayoría de las fuentes no publican un total, y que una página no traiga
    ids nuevos es una prueba legítima de que se llegó al final. Exigirles un
    total declarado dejaría medio padrón sin poder cerrar nunca.
    """
    assert enumeracion_es_completa(cobertura=None, paginacion_imposible=False)


def test_MUERDE_sin_total_y_sin_poder_paginar_NO_es_completa():
    """El agujero exacto: «no sé» estaba escrito como «sí».

    Es el caso Tokko sin la red de seguridad del total declarado. Sin esto,
    un listado truncado en la primera página se certifica en silencio, y son
    16 las certificaciones vigentes que hoy dependen de que esto funcione.
    """
    assert not enumeracion_es_completa(cobertura=None,
                                       paginacion_imposible=True)


def test_MUERDE_ni_siquiera_con_cobertura_alta_si_no_se_pudo_paginar():
    """Una cobertura alta contra un total mal publicado no salva nada.

    `berrueta` declara 197 y sirve 193: los contadores de las fuentes se
    equivocan. Si además no pudimos paginar, la cobertura se calculó sobre lo
    único que vimos y no significa lo que parece.
    """
    assert not enumeracion_es_completa(cobertura=1.0,
                                       paginacion_imposible=True)


def test_el_conector_tokko_declara_cuando_no_puede_paginar():
    """La señal tiene que nacer donde se sabe, no inferirse después.

    Un TFW con fichas en la primera página y sin query de paginación sólo
    puede devolver esa página. Eso se sabe en `discover`, antes de bajar nada
    más, y es ahí donde se anota.
    """
    from connectors.tokko import TokkoConnector
    plan = {"usa_tfw": True, "ids_primera_pagina": 20,
            "pagina_por_query": False, "query_paginacion": None}
    assert TokkoConnector.paginacion_imposible(plan) is True


def test_el_conector_tokko_no_la_declara_cuando_si_puede():
    from connectors.tokko import TokkoConnector
    plan = {"usa_tfw": True, "ids_primera_pagina": 20,
            "pagina_por_query": True, "query_paginacion": "?o=2,2&p="}
    assert TokkoConnector.paginacion_imposible(plan) is False


def test_sin_fichas_en_la_primera_pagina_no_es_un_truncamiento():
    """Cero fichas no es un listado cortado: es otra cosa, y tiene su defecto.

    Marcarlo como truncamiento mezclaría «no pudimos paginar» con «no hay
    nada», que se diagnostican distinto.
    """
    from connectors.tokko import TokkoConnector
    plan = {"usa_tfw": True, "ids_primera_pagina": 0,
            "pagina_por_query": False, "query_paginacion": None}
    assert TokkoConnector.paginacion_imposible(plan) is False


# --------------------------------------------------------------------------
# La otra mitad: la paginacion que se corta EN EL CAMINO.
#
# Auditados los cinco conectores, los cinco tienen un
# `except (ErrorTransitorio, Bloqueado): break` en su bucle de listado. Una
# caida de red a mitad de la paginacion se leia igual que haber llegado al
# final. Es el mismo malentendido que el de Tokko, en otro lugar.
# --------------------------------------------------------------------------

def test_MUERDE_todos_los_conectores_marcan_la_interrupcion():
    """Cada bucle de listado que corta por red tiene que dejarlo escrito.

    Este test es una lista explicita y no un conteo: si aparece un conector
    nuevo con su propio bucle, hay que agregarlo a mano, y eso es
    deliberado. Un conteo automatico habria dejado pasar en silencio al
    siguiente, que es exactamente como `generic/common` perdio doce metodos.
    """
    import re
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1] / "connectors"
    esperados = {"tokko.py": 1, "century21.py": 1, "wasi.py": 1,
                 "wordpress.py": 2}
    for archivo, cuantos in esperados.items():
        fuente = (raiz / archivo).read_text(encoding="utf-8")
        marcas = len(re.findall(r"self\.paginacion_interrumpida = True",
                                fuente))
        assert marcas == cuantos, f"{archivo}: {marcas} marcas, esperadas {cuantos}"


def test_el_conector_base_arranca_sin_la_marca():
    from connectors.base import Connector
    assert Connector().paginacion_interrumpida is False


def test_MUERDE_una_paginacion_interrumpida_no_puede_ser_completa():
    """Sin esto, una caida de red certifica un catalogo a medias.

    Y es peor que el caso de Tokko, porque no deja ninguna huella: el
    conector devuelve lo que alcanzo a leer y nada dice que falto.
    """
    assert not enumeracion_es_completa(cobertura=None,
                                       paginacion_imposible=True)
    assert not enumeracion_es_completa(cobertura=0.99,
                                       paginacion_imposible=True)


def test_wordpress_distingue_el_404_del_final_de_una_caida_de_red():
    """WordPress devuelve 404 en la pagina que ya no existe: eso SI es el final.

    Marcarlo como interrupcion pondria en duda a las 21 agencias de WordPress
    que hoy cierran bien, que es el error contrario y igual de caro.
    """
    from pathlib import Path
    fuente = (Path(__file__).resolve().parents[1] / "connectors"
              / "wordpress.py").read_text(encoding="utf-8")
    assert "except ErrorPermanente:" in fuente
    assert "eso SI\n                # es el final del listado" in fuente

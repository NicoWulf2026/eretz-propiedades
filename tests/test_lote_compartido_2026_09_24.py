# -*- coding: utf-8 -*-
"""Tres reglas escritas dos veces que dijeron cosas distintas.

Cada una va en código compartido —`shared/source_policy`, `shared/certifier`,
`shared/runner`— y por eso van juntas: una sola invalidación de huellas en vez
de tres.
"""
from __future__ import annotations

import pytest

from scripts.agency_web_discovery import es_portal


# ---------------------------------------------------------------------------
# 1. La lista de portales.
#
# `buscainmueble.com` figuraba como web oficial de 4 agencias de la cola y
# produjo 295 «propiedades» que eran páginas de categoría del portal —las
# MISMAS 98 para tres agencias distintas—. `verificador_identidad_v2` lo
# conocía; `agency_web_discovery`, que es lo que consulta el certificador, no.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.buscainmueble.com/inmobiliarias/alonso-propiedades/casas/venta",
    "https://www.todoprops.com/inmobiliarias/santa-fe",
    "https://www.inmobusqueda.com/inmobiliaria/x",
    "https://www.inmoup.com.ar/inmobiliarias/x",
])
def test_MUERDE_estos_portales_no_son_la_web_de_nadie(url):
    assert es_portal(url)


@pytest.mark.parametrize("url", [
    "https://inmobiliarianaventura.com.ar",      # contiene «navent», no lo es
    "https://www.lachozapropiedades.com.ar",     # contiene «choza»
    "https://contipropiedades.com.ar/propiedad/882/chalet",
    "https://www.remax.com.ar/oficinas/ultra",   # oficina de franquicia: aparte
])
def test_una_marca_de_portal_se_compara_por_etiqueta_no_por_subcadena(url):
    assert not es_portal(url)


def test_MUERDE_las_dos_listas_de_portales_no_pueden_divergir():
    """Cada marca que el verificador de identidad reconoce como portal la
    reconoce también la política de fuentes. Las redes de franquicia quedan
    afuera a propósito: su página de oficina ES la casa de la inmobiliaria, y
    la política de fuentes las trata aparte."""
    from scripts.verificador_identidad_v2 import PORTALES
    franquicias = {"remax.com", "century21", "coldwellbanker"}
    faltan = [p for p in PORTALES if p not in franquicias
              and not es_portal(f"https://www.{p.split('.')[0]}.com.ar/x")]
    assert faltan == []


def test_el_certificador_rechaza_una_fuente_que_es_un_perfil_de_portal():
    from scripts.agency_certifier import external_portal
    assert external_portal(
        "https://www.buscainmueble.com/inmobiliarias/analia-verga-propiedades")


# ---------------------------------------------------------------------------
# 2. `compare_runs` compara identidades, no urls crudas (ítem 19).
#
# `eckert` paró diciendo «30 propiedades que la primera corrida vio no
# aparecieron en la segunda». No faltaba ninguna: la corrida 1 las vio con
# `www.` y la 2 sin. `hash_dedup` ya normaliza eso, y la propia función lo
# usaba dos líneas más abajo para contar identidades.
# ---------------------------------------------------------------------------

def _prop(url, hash_dedup):
    return {"source_url": url, "hash_dedup": hash_dedup, "_cambio": "SIN_CAMBIOS"}


def test_MUERDE_el_www_no_es_una_propiedad_distinta():
    from scripts.agency_certifier import compare_runs
    run1 = {"_props": [_prop(f"https://www.eckert.test/site/properties/{i}/x", f"h{i}")
                       for i in range(30)]}
    run2 = {"_props": [_prop(f"https://eckert.test/site/properties/{i}/x", f"h{i}")
                       for i in range(30)]}
    c = compare_runs(run1, run2)
    assert c["missing_in_run2"] == 0
    assert c["new_in_run2"] == 0
    assert c["same_url_set"] is True
    assert c["idempotent"] is True


def test_una_propiedad_que_falta_de_verdad_sigue_faltando():
    from scripts.agency_certifier import compare_runs
    run1 = {"_props": [_prop("https://www.x.test/p/1", "h1"),
                       _prop("https://www.x.test/p/2", "h2")]}
    run2 = {"_props": [_prop("https://x.test/p/1", "h1")]}
    c = compare_runs(run1, run2)
    assert c["missing_in_run2"] == 1
    assert c["same_url_set"] is False
    assert c["idempotent"] is False


# ---------------------------------------------------------------------------
# 3. El contador de rechazos sospechosos usa la regla del triaje (ítem 9).
#
# `bunader`: sus 8 rechazos tienen CERO fotos, el triaje los da por buenos, y
# el paro salió igual porque el contador del runner —que el triaje prefiere—
# se había quedado sin la condición de fotos.
# ---------------------------------------------------------------------------

def test_MUERDE_un_rechazo_sin_fotos_no_es_sospechoso_para_el_runner():
    from scripts.run_rollout import descartes_sospechosos
    sin_fotos = {"source_url": "https://x.test/a", "precio": 100000, "fotos": 0}
    una_foto = {"source_url": "https://x.test/b", "precio": 100000, "fotos": 1}
    con_fotos = {"source_url": "https://x.test/c", "precio": 100000, "fotos": 8}
    assert descartes_sospechosos([sin_fotos, una_foto]) == []
    assert descartes_sospechosos([con_fotos]) == [con_fotos]


def test_el_runner_y_el_triaje_dicen_lo_mismo_de_cada_rechazo():
    from scripts.defect_triage import descarte_parecia_una_propiedad
    from scripts.run_rollout import descartes_sospechosos
    casos = [{"precio": None, "tipo_ld": None, "fotos": 9},
             {"precio": 1, "fotos": 9}, {"tipo_ld": "House", "fotos": 9},
             {"precio": 1, "fotos": 2}, {"tipo_ld": "House", "fotos": 0}]
    for d in casos:
        assert (d in descartes_sospechosos([d])) == descarte_parecia_una_propiedad(d)


def test_el_nombre_registrable_coincide_con_el_del_verificador():
    from scripts.agency_web_discovery import nombre_registrable
    from scripts.verificador_identidad_v2 import registrable
    for host in ("www.buscainmueble.com", "inmoup.com.ar", "choza.ai",
                 "x.zonaprop.com.ar", "zonaprop.com.ar.official.test",
                 "clasificados.lavoz.com.ar", "remax.com.ar"):
        assert nombre_registrable(host) == registrable(host).split(".")[0], host


def test_MUERDE_un_sitio_que_se_llama_como_un_portal_bajo_otro_dominio_no_lo_es():
    assert not es_portal("https://zonaprop.com.ar.official.test/p/1")
    assert es_portal("https://x.zonaprop.com.ar:443/p/1")

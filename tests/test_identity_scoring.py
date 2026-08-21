# -*- coding: utf-8 -*-
"""Tests del scoring de identidad.

El caso que da nombre a media suite: `inmobiliarialopez.com` tiene el nombre,
responde 200, tiene SSL, y vende ropa. Ninguna coincidencia de nombre deberia
poder salvar eso.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load("identity_scoring")

INMO = ("Inmobiliaria en Rosario. Venta y alquiler de departamentos. "
        "Tasaciones sin cargo. Corredor inmobiliario matriculado.")


def ent(**kw):
    base = {"nombre_original": "Lopez Propiedades", "ciudad": "Rosario",
            "provincia": "Santa Fe", "telefono": None, "email": None,
            "direccion": None, "matricula": [], "zonas_observadas": []}
    base.update(kw)
    return base


def sitio(texto="", titulo="", **kw):
    base = {"titulo": titulo, "texto": texto, "http": 200}
    base.update(kw)
    return base


# ------------------------------------------------- la regla del otro rubro
def test_una_tienda_de_ropa_se_rechaza_aunque_tenga_el_nombre():
    s = sitio("Lopez Propiedades. Venta de indumentaria. Remeras y jeans. "
              "Todos los talles. Envios a todo el pais.", "Lopez Propiedades")
    p = sc.puntuar(ent(), s)
    assert p.rechazado_por_rubro
    assert p.rubro_detectado == "indumentaria"
    assert sc.clasificar(p) == sc.OTHER_ENTITY


def test_un_estudio_juridico_tambien_se_rechaza():
    s = sitio("Lopez y Asociados. Estudio juridico. Abogados especialistas en "
              "sucesiones y derecho penal.", "Lopez")
    assert sc.clasificar(sc.puntuar(ent(), s)) == sc.OTHER_ENTITY


def test_una_inmobiliaria_que_menciona_locales_no_se_confunde_con_ferreteria():
    """El vocabulario inmobiliario presente desactiva el rechazo."""
    s = sitio("Lopez Propiedades. Alquiler de locales comerciales y "
              "departamentos. Tasaciones.", "Lopez Propiedades")
    assert sc.detectar_otro_rubro(s["texto"], "Lopez Propiedades") is None


def test_una_sola_mencion_ajena_no_alcanza_para_rechazar():
    s = sitio("Lopez Propiedades vende un local que antes fue una ferreteria. "
              "Tasaciones y alquileres.")
    assert sc.detectar_otro_rubro(s["texto"], "Lopez Propiedades") is None


def test_el_nombre_de_la_entidad_no_prueba_el_rubro():
    """Una tienda llamada `Lopez Propiedades` no es una inmobiliaria por como se
    llama."""
    texto = "Lopez Propiedades. Remeras, jeans, todos los talles."
    assert sc.detectar_otro_rubro(texto, "Lopez Propiedades") == "indumentaria"
    # sin descontar el nombre, se salvaria sola
    assert sc.detectar_otro_rubro(texto) is None


# ------------------------------------------------- señales fuertes
def test_el_telefono_coincidente_pesa_mucho():
    e = ent(telefono="+54 341 4551234")
    s = sitio(INMO + " Contacto: 0341 455-1234", "Lopez Propiedades")
    p = sc.puntuar(e, s)
    assert any(x.clave == "telefono" for x in p.positivas)
    assert sc.clasificar(p) == "VERIFIED"


def test_un_telefono_contradictorio_penaliza():
    e = ent(telefono="+54 341 4551234")
    s = sitio(INMO + " Contacto: 011 5555-9999", "Lopez Propiedades")
    p = sc.puntuar(e, s)
    assert any(x.clave == "telefono_distinto" for x in p.negativas)


def test_el_email_coincidente_cuenta():
    e = ent(email="contacto@lopezprop.com.ar")
    s = sitio(INMO + " Escribinos a contacto@lopezprop.com.ar", "Lopez")
    assert any(x.clave == "email" for x in sc.puntuar(e, s).positivas)


def test_la_matricula_coincidente_cuenta():
    e = ent(matricula=["CMCPSI 5770"])
    s = sitio(INMO + " CMCPSI 5770", "Lopez Propiedades")
    p = sc.puntuar(e, s)
    assert any(x.clave == "matricula" for x in p.positivas)
    assert sc.clasificar(p) == "VERIFIED"


def test_la_direccion_coincidente_cuenta():
    e = ent(direccion="San Martin 1234")
    s = sitio(INMO + " Nos encontras en San Martin 1234", "Lopez Propiedades")
    assert any(x.clave == "direccion" for x in sc.puntuar(e, s).positivas)


# ------------------------------------------------- homonimas y localidad
def test_localidad_incompatible_penaliza():
    e = ent(ciudad="Rosario")
    s = sitio("Garcia Propiedades. Inmobiliaria en Cordoba capital. Tasaciones.",
              "Garcia", localidades_detectadas=["cordoba"])
    p = sc.puntuar(e, s)
    assert any(x.clave == "localidad_incompatible" for x in p.negativas)


def test_localidad_coincidente_suma():
    s = sitio(INMO, "Lopez Propiedades")
    assert any(x.clave == "localidad" for x in sc.puntuar(ent(), s).positivas)


# ------------------------------------------------- umbrales
def test_las_señales_debiles_no_alcanzan_solas():
    """Nombre parcial + provincia + rubro suman muy por debajo del umbral."""
    s = sitio("Propiedades en Santa Fe. Alquileres.", "Propiedades")
    p = sc.puntuar(ent(), s)
    assert sc.clasificar(p) == "INSUFICIENTE"


def test_nombre_exacto_mas_localidad_llega_a_alta_confianza():
    s = sitio(INMO, "Lopez Propiedades")
    p = sc.puntuar(ent(), s)
    assert p.total >= sc.UMBRAL_ALTA
    assert sc.clasificar(p) in ("HIGH_CONFIDENCE", "VERIFIED")


def test_el_puntaje_siempre_se_explica():
    p = sc.puntuar(ent(), sitio(INMO, "Lopez Propiedades"))
    assert "total=" in p.explicacion and p.scoring_version == sc.SCORING_VERSION


def test_un_sitio_sin_rastro_del_nombre_penaliza():
    s = sitio(INMO.replace("Inmobiliaria", "Inmobiliaria"), "Otra Cosa")
    p = sc.puntuar(ent(), s)
    assert any(x.clave == "sin_rastro_del_nombre" for x in p.negativas)


# ------------------------------------------------- URL historica
def test_url_historica_que_era_un_portal():
    r = sc.diagnosticar_url_historica("https://www.zonaprop.com.ar/lopez", None)
    assert r["estado"] == sc.HISTORICAL_INVALID
    assert "portal" in r["detalle"]


def test_url_historica_muerta():
    r = sc.diagnosticar_url_historica("https://lopez.com.ar", {"http": None})
    assert r["estado"] == sc.HISTORICAL_INVALID


def test_url_historica_que_redirige_a_dominio_nuevo():
    r = sc.diagnosticar_url_historica(
        "https://lopez.com.ar",
        {"http": 200, "url": "https://lopezpropiedades.com.ar/", "texto": INMO})
    assert r["estado"] == sc.HISTORICAL_REPLACED
    assert "lopezpropiedades" in r["nuevo_dominio"]


def test_url_historica_tomada_por_otro_rubro():
    r = sc.diagnosticar_url_historica(
        "https://lopez.com.ar",
        {"http": 200, "url": "https://lopez.com.ar",
         "texto": "Venta de indumentaria. Remeras, jeans, todos los talles."})
    assert r["estado"] == sc.HISTORICAL_INVALID
    assert "otro rubro" in r["detalle"]


def test_url_historica_todavia_vigente():
    r = sc.diagnosticar_url_historica(
        "https://lopez.com.ar", {"http": 200, "url": "https://lopez.com.ar", "texto": INMO})
    assert r["estado"] == "vigente"


# ------------------------------------------------- scrapeability
def test_scrapeability_detecta_listados():
    r = sc.diagnosticar_scrapeabilidad({"http": 200, "texto": "ver ficha de la propiedad"})
    assert r["scrapeability_status"] == sc.SCRAPE_READY


def test_scrapeability_detecta_bloqueo():
    r = sc.diagnosticar_scrapeabilidad({"http": 403, "texto": ""})
    assert r["scrapeability_status"] == sc.SCRAPE_BLOCKED


def test_scrapeability_detecta_plataforma():
    r = sc.diagnosticar_scrapeabilidad({"http": 200, "texto": "wp-content/themes ficha propiedad"})
    assert r["plataforma"] == "wordpress"


def test_scrapeability_sin_listados():
    r = sc.diagnosticar_scrapeabilidad({"http": 200, "texto": "somos una empresa"})
    assert r["scrapeability_status"] == sc.SCRAPE_NO_LISTINGS


def test_el_diagnostico_no_scrapea_nada():
    """Solo mira lo que ya se bajo: no abre conexiones."""
    import inspect
    src = inspect.getsource(sc.diagnosticar_scrapeabilidad)
    for prohibido in ("urlopen", "requests.", "httpx", "socket.", "urllib"):
        assert prohibido not in src, prohibido


# ------------------------------------------------- notas periodisticas
def test_una_nota_sobre_la_inmobiliaria_no_es_su_web():
    """El caso real que aparecio en la prueba con Tavily: un articulo de revista
    sobre RE/MAX Solutions puntuaba 49 y se llevaba el puesto de web oficial."""
    u = ("https://www.revistaareatres.com.ar/arquitectura/"
         "remax-solutions-lanza-su-tercer-edicion-de-hot-house-la-campana")
    p = sc.puntuar(ent(nombre_original="Remax Solutions", ciudad="Mendoza"),
                   sitio("Revista. Redaccion. Inmobiliaria en Mendoza. Leer mas.",
                         "Remax Solutions lanza", url=u))
    assert p.rechazado_por_rubro
    assert sc.clasificar(p) == sc.OTHER_ENTITY


def test_la_home_de_una_inmobiliaria_no_es_una_nota():
    assert not sc.es_articulo("https://remaxsolutions.com.ar/")
    assert not sc.es_articulo("https://remaxsolutions.com.ar/propiedades")
    assert not sc.es_articulo("https://alfa.com.ar/quienes-somos")


def test_una_url_con_fecha_es_una_nota():
    assert sc.es_articulo("https://diario.com.ar/2026/03/nota-sobre-la-inmobiliaria")


def test_una_ruta_profunda_con_slug_largo_es_una_nota():
    assert sc.es_articulo("https://medio.com/seccion/titulo-largo-de-la-nota-publicada-hoy")


def test_un_aviso_de_empleo_no_es_la_web_de_la_inmobiliaria():
    """Serper devolvio una oferta de trabajo de agente inmobiliario que nombraba
    a la agencia."""
    p = sc.puntuar(ent(nombre_original="RE/MAX Exclusivo"),
                   sitio("Oferta de trabajo. Agente inmobiliario. Enviá tu CV. "
                         "Postulate a esta vacante.", "Trabajo en RE/MAX Exclusivo"))
    assert p.rechazado_por_rubro and p.rubro_detectado == "empleo"

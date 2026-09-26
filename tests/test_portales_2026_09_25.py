"""Portales que figuraban como web oficial con identidad READY.

Medido el 25-09 sobre los paquetes de certificación: `benjamin ferreyra`
bajó 842 fichas de `proppies.app/inmobiliarias/...`, y `fernandez marull`
tenía como web una ficha de `propia.com.ar` («el buscador de propiedades de
la región», más de 2000 corredores de Rosario) y enumeró los enlaces señuelo
de Cloudflare como si fueran sus propiedades. Los otros tres son directorios
verificados en su portada.
"""
from __future__ import annotations

import pytest

from scripts.agency_certifier import external_portal
from scripts.agency_web_discovery import es_portal


@pytest.mark.parametrize("url", [
    "https://proppies.app/inmobiliarias/benjamin-ferreyra-brokers-inmobiliarios-337",
    "https://propia.com.ar/propiedad/departamento-en-venta-con-la-mejor-vista-de-rosario",
    "https://liderprop.com/es-ar/propiedades/inmobiliaria--4293/",
    "https://lujanprop.com.ar/inmobiliaria/arte",
    "https://aspenbienesraices.com.ar/inmobiliaria/ak-bienes-raices-inversiones/",
])
def test_MUERDE_estos_portales_no_son_la_web_de_ninguna_inmobiliaria(url):
    assert es_portal(url)
    assert external_portal(url)


@pytest.mark.parametrize("url", [
    "https://www.inmobiliariapropia.com.ar",
    "https://propiasa.com.ar/propiedades",
    "https://www.lujanpropiedades.com.ar",
])
def test_el_nombre_se_compara_entero_no_por_subcadena(url):
    assert not es_portal(url)


@pytest.mark.parametrize("url", [
    "https://www.inmobiliariapropia.com.ar",
    "https://www.lujanpropiedades.com.ar",
    "https://liderpropiedades.com.ar",
])
def test_el_verificador_por_subcadena_no_atrapa_inmobiliarias(url):
    from scripts.verificador_identidad_v2 import es_portal_url
    assert not es_portal_url(url)


@pytest.mark.parametrize("url", [
    # `danisa robledo`: portal multi-corredor de Santa Fe («Ser corredor en MU»).
    "https://www.mercado-unico.com/propiedades/69019270b5bada00113d470b",
    # `casagrande`: directorio de comercios de Uruguay (restaurantes).
    "https://www.smartservices.uy/agencia-inmobiliaria/montevideo/index.php?p=2",
    # `gama`: guia turistica de Rosario (historia.php, ubicacion.php).
    "http://www.365litoralargentino.com/santa_fe/rosario/gama-inmobiliaria_e.html",
    # `bertomeu`: directorio de socios de la Camara Inmobiliaria Argentina.
    "https://cia.org.ar/nuevo-directorio/",
    # `cerro`: guia de empresas de Cordoba.
    "https://empresasdecordoba.com/pagina/Cerro-Inmobiliaria-Miguel-A-Caceres/",
    # `chenlo`: portal de la Asociacion de Martilleros de Lanus.
    "https://propuestasinmobiliarias.com.ar/agents.php",
])
def test_MUERDE_un_directorio_general_tampoco_es_la_web_de_la_inmobiliaria(url):
    assert es_portal(url)
    assert external_portal(url)


def test_cia_org_ar_se_compara_por_dominio_entero():
    assert not es_portal("https://agencia.org.ar/")
    assert not es_portal("https://garcia.org.ar/")

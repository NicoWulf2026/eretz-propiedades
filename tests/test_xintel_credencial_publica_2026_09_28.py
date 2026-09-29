"""Credencial PUBLICA de cliente de Xintel (politica del usuario, 2026-09-28).

Se usa read-only cuando la publica el sitio oficial al navegador -HTML o su
JavaScript propio, tratados igual- y es la que su frontend usa para consultar
su catalogo. No: claves de otro dominio, rotuladas como secretas o token, sin
contexto Xintel, ni de una inmobiliaria para otra. La procedencia se registra
como PUBLIC_CLIENT_CREDENTIAL sin el valor.

En vivo el 28-09: `aloise` (config.js) 43/43 y `labastida` (llamada del
buscador) 65 de 66 declaradas, con detalle normalizado.
"""
from __future__ import annotations

import json

from connectors.base import ErrorPermanente, Fuente
from connectors.generico import GenericoConnector, credencial_xintel_en

CLAVE = "ABCDEFGHIJKLMNOPQRSTUVWXY"
CONFIG = ("const CONFIG = { xintel: { enabled: true, empresa: 'GAB', apiKey: '" + CLAVE + "', "
          "baseURL: 'https://xintelapi.com.ar/' } };")
LLAMADA = ("$.ajax({ type:'GET', url:'https://xintel.com.ar/api/', data:{ "
           "'json':'datos.select.buscador', 'inm':'LLB', 'apiK':'" + CLAVE + "' } });")


def test_la_configuracion_publica_del_frontend_se_reconoce() -> None:
    assert credencial_xintel_en(CONFIG) == ("GAB", CLAVE)
    assert credencial_xintel_en(LLAMADA) == ("LLB", CLAVE)


def test_sin_contexto_xintel_no_es_una_credencial_de_cliente() -> None:
    assert credencial_xintel_en("const c = { empresa: 'GAB', apiKey: '" + CLAVE + "' };") is None


def test_una_clave_rotulada_como_secreta_no_se_usa() -> None:
    texto = ("// xintelapi.com.ar\nconst xintel = { empresa: 'GAB', secretToken: 'x', "
             "private_apiKey: '" + CLAVE + "' };")
    assert credencial_xintel_en(texto) is None
    rotulada = "fetch('https://xintelapi.com.ar/'); const x = {inm: 'GAB', /* secret */ apiKey: '" + CLAVE + "'}"
    assert credencial_xintel_en(rotulada) is None


BASE = "https://sitio.test"
FUENTE = Fuente("roomix:sitio", "Sitio", BASE, 1)


class Falso:
    def __init__(self, script_src: str, script: str):
        self.script_src, self.script = script_src, script

    def bajar(self, url):
        if url in (BASE, BASE + "/"):
            return (f'<html><script src="{self.script_src}"></script>'
                    '<p>Provisto por <a href="http://xintel.com.ar">Xintel</a></p></html>')
        if url == self.script_src or url == BASE + self.script_src:
            return self.script
        if url.startswith("https://xintelapi.com.ar/"):
            return json.dumps({"resultado": {"fichas": [], "datos": {"cantidadFichas": "0"}}})
        raise ErrorPermanente(url)


def test_el_javascript_propio_del_sitio_cuenta_igual_que_el_html() -> None:
    c = GenericoConnector(Falso("/js/config.js", CONFIG))
    plan = c.discover(FUENTE)
    assert plan["variante"] == "XINTEL_API" and plan["xintel_inm"] == "GAB"
    procedencia = plan["xintel_credencial"]
    assert procedencia["tipo"] == "PUBLIC_CLIENT_CREDENTIAL" and procedencia["provider"] == "Xintel"
    assert procedencia["source_url"] == BASE + "/js/config.js" and procedencia["agency"] == "roomix:sitio"
    assert CLAVE not in json.dumps(procedencia)


def test_un_script_de_otro_dominio_no_es_configuracion_del_sitio() -> None:
    c = GenericoConnector(Falso("https://cdn.otro.test/config.js", CONFIG))
    assert c.discover(FUENTE).get("variante") != "XINTEL_API"

"""Herramientas del puente LOCAL -> CLOUD: reduccion de fixtures y chequeo P18 de solo lectura."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _cargar(nombre):
    spec = importlib.util.spec_from_file_location(nombre, RAIZ / "scripts" / "cloud_bridge" / f"{nombre}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _cargar("capturar_fixture")
P = _cargar("p18_chequeo_lectura")

PAGINA = """<html><head><style>.x{}</style><script src="gtm.js"></script>
<script>dataLayer.push({})</script>
<script type="application/ld+json">{"@type":"Residence","telephone":"+54 9 223 555-1234","ts":1727712000123}</script>
<script id="wix-warmup-data" type="application/json">{"items":[{"_id":"a1","precio":1234567890}]}</script>
<link rel="stylesheet" href="s.css"></head>
<body onload="x()"><!-- comentario -->
<header><p>Contacto: ventas@agencia.com.ar - (0223) 155-123456</p><a href="https://wa.me/5492235551234">wa</a></header>
<main><div class="ficha"><h1 style="color:red">Casa en venta</h1>
<p class="ubicacion"><i class="fa fa-map-marker"><svg><path d="M0"/></svg></i> Laprida 1835, B7602FKK Mar del Plata</p>
<p>Superficie 50 M² 50 M²</p></div></main>
<iframe src="https://maps.example"></iframe><footer>Oficina: Laprida 1835</footer></body></html>"""


def test_quita_lo_irrelevante_y_conserva_la_estructura():
    salida, meta = C.reducir_html(PAGINA)
    for fuera in ("<style", "gtm.js", "dataLayer", "comentario", "<iframe", "stylesheet", "onload", "color:red", "<path"):
        assert fuera not in salida, fuera
    assert 'class="fa fa-map-marker"' in salida and "Laprida 1835" in salida
    assert meta["scripts_conservados"] == []


def test_conserva_los_scripts_de_datos_pedidos_sin_corromper_numeros():
    salida, meta = C.reducir_html(PAGINA, scripts_ids=("wix-warmup-data",), con_json_ld=True)
    assert "wix-warmup-data" in meta["scripts_conservados"]
    assert "1234567890" in salida and "1727712000123" in salida      # ids y timestamps intactos
    assert "+54 9 223 555-1234" not in salida and "[TELEFONO]" in salida  # el telefono con forma, no


def test_redacta_contactos_del_texto_y_los_enlaces():
    salida, _ = C.reducir_html(PAGINA)
    assert "ventas@agencia.com.ar" not in salida and "[EMAIL]" in salida
    assert "155-123456" not in salida
    assert "wa.me/[TELEFONO]" in salida and "5492235551234" not in salida


def test_recorta_al_contexto_dom_del_texto():
    salida, _ = C.reducir_html(PAGINA, selector_texto="B7602FKK")
    assert salida.startswith("<!-- contexto DOM:") and "fa-map-marker" in salida
    assert "Superficie" in salida                     # hermano inmediato: contexto
    assert "Oficina" not in salida                    # el footer no es contexto de la ficha


def test_json_recorta_listas_y_redacta():
    datos = {"total": 812, "data": [{"id": i, "email": "x@y.com", "ts": 1727712000} for i in range(10)]}
    reducido = C.reducir_json(datos, 3)
    assert reducido["total"] == 812 and len(reducido["data"]) == 3
    assert reducido["data"][0] == {"id": 0, "email": "[EMAIL]", "ts": 1727712000}


def test_p18_veredictos():
    assert P.veredicto((True, True, True))[0] == "YES"
    assert P.veredicto((True, True, False))[0] == "NO"
    assert P.veredicto((True, False, None))[0] == "NO"
    assert P.veredicto((False, True, None))[0] == "UNABLE_TO_VERIFY"
    assert P.veredicto(None)[0] == "UNABLE_TO_VERIFY"


class _Cursor:
    def __init__(self, fila): self.fila, self.sql = fila, []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql): self.sql.append(sql)
    def fetchone(self): return self.fila


class _Conexion:
    def __init__(self, fila): self.cursor_ = _Cursor(fila); self.read_only = False; self.rolled = False
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return self.cursor_
    def rollback(self): self.rolled = True


def test_p18_solo_lectura_y_sin_filtrar_la_url(monkeypatch, capsys):
    url = "postgresql://eretz_preview_ro:SECRETO@host:5432/db"
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL", url)
    cn = _Conexion((True, True, True))
    assert P.main([], conectar=lambda u: cn) == 0
    salida = capsys.readouterr().out
    assert salida.startswith("YES") and "SECRETO" not in salida and "host" not in salida
    assert cn.read_only and cn.rolled
    assert all(s.strip().lower().startswith("select") for s in cn.cursor_.sql)


def test_p18_error_de_conexion_no_muestra_el_mensaje(monkeypatch, capsys):
    monkeypatch.setenv("ERETZ_PREVIEW_RO_URL", "postgresql://u:SECRETO@h/db")

    def falla(u):
        raise RuntimeError("could not connect to postgresql://u:SECRETO@h/db")

    assert P.main([], conectar=falla) == 2
    salida = capsys.readouterr().out
    assert salida.startswith("UNABLE_TO_VERIFY") and "SECRETO" not in salida


def test_p18_sin_variable(monkeypatch, capsys):
    monkeypatch.delenv("ERETZ_PREVIEW_RO_URL", raising=False)
    assert P.main([]) == 2
    assert capsys.readouterr().out.startswith("UNABLE_TO_VERIFY")


def test_telefonos_y_precios_en_el_texto_visible():
    for tel in ("(0223) 155-123456", "+54 9 223 555-1234", "2235551234", "223 555 1234"):
        assert C.redactar(f"llamar al {tel} hoy") == "llamar al [TELEFONO] hoy", tel
    for precio in ("USD 150000000", "$ 12.500.000", "U$S 1.250.000"):
        assert C.redactar(precio) == precio, precio
    assert C.redactar("Laprida 1835, B7602FKK Mar del Plata") == "Laprida 1835, B7602FKK Mar del Plata"
    assert C.redactar("Superficie 50 M² 50 M²") == "Superficie 50 M² 50 M²"


def test_reducir_html_tolera_link_anidado_ya_borrado():
    """html.parser anida <link> sin cerrar; borrar el de afuera no rompe el de adentro."""
    from scripts.cloud_bridge.capturar_fixture import reducir_html
    html = ('<html><head><link rel="stylesheet" href="a.css"><link rel="preload" href="b.js">'
            '<script src="x.js"></script></head><body><p><i class="fa fa-map-marker"></i> '
            'Calle 123, Mar del Plata</p></body></html>')
    reducido, _ = reducir_html(html, selector_texto="Calle 123")
    assert "Calle 123" in reducido and "a.css" not in reducido

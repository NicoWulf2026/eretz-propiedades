# -*- coding: utf-8 -*-
"""Tests de la arquitectura de connectors y del connector Tokko.

Todo con HTML fijo: ningun test toca la red. Un test que depende de que la web
de una inmobiliaria este arriba no dice si el codigo esta bien, dice si el
servidor de otro contesto hoy.

Lo que se persigue aca es el error caro: mezclar inventario entre inmobiliarias,
dar de baja propiedades vivas por un timeout, o duplicar todo en la segunda
corrida.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from connectors import base as B  # noqa: E402
from connectors.tokko import TokkoConnector, _campo, _texto_plano  # noqa: E402


# --------------------------------------------------------------- fixtures HTML
LISTADO = """
<html><head><link href="https://static.tokkobroker.com/tfw/css/estilo.css"></head>
<body><img src="https://static.tokkobroker.com/logos/33648/abc.png">
<a href="/Propiedades">Propiedades</a>
<ul class="resultados-list">
  <a href="/p/111-Casa-en-Venta-en-Cordoba">1</a>
  <a href="/p/222-Departamento-en-Alquiler-en-Rosario">2</a>
</ul>
<div class="pagination"><div id="loading"></div></div>
<span>2 Resultados</span>
<script>var jqxhr = $.ajax('?q=&currency=ANY&operation=&p=')</script>
</body></html>
"""

FICHA = """
<html><head><meta property="og:title" content="Departamento en Venta en Nueva Cordoba - Independencia al 300">
</head><body>
<div>Independencia al 300 VENTA USD55.000</div>
<div>Direcci&oacute;n Independencia al 300 Ubicaci&oacute;n Nueva Cordoba Ambientes 2
Total construido 40 m2 Dormitorios 1</div>
<div>INFORMACION BASICA Ambientes : 2 Dormitorios : 1 Banos : 1 Condicion: Bueno
Plantas : 1 Antiguedad : 40 Anos Situacion: Vacia Expensas: $ 85.000
Orientacion: Este Disposicion: Contrafrente</div>
<div>(REF. AAP8636261)</div>
<img src="https://static.tokkobroker.com/pictures/8636261_abc123.jpg">
<img src="https://static.tokkobroker.com/pictures/8636261_def456.jpg">
<img src="https://static.tokkobroker.com/pictures/9999999_otra.jpg">
<script>var map = new google.maps.LatLng(-31.4203028, -64.1853945);</script>
</body></html>
"""


class DescargadorFalso(B.Descargador):
    """Sirve HTML de un diccionario y cuenta los pedidos."""

    def __init__(self, paginas: dict[str, str], fallar: dict[str, Exception] | None = None):
        super().__init__(B.LimitadorDeRitmo(0.0))
        self.paginas = paginas
        self.fallar = fallar or {}
        self.pedidos_urls: list[str] = []

    def bajar(self, url: str) -> str:
        self.pedidos_urls.append(url)
        self.pedidos += 1
        if url in self.fallar:
            e = self.fallar[url]
            if isinstance(e, list):
                e = e.pop(0) if e else None
            if e is not None:
                raise e
        # La mas especifica gana: si "https://alfa.com.ar/" resolviera primero,
        # una ficha devolveria el listado y los tests pasarian por la razon
        # equivocada.
        for k in sorted(self.paginas, key=len, reverse=True):
            if url.startswith(k):
                return self.paginas[k]
        return ""


def fuente(aid="ag-1", url="https://alfa.com.ar/"):
    # No usar hash(): esta aleatorizado por proceso y volveria no reproducible
    # todo lo que dependa del id, empezando por hash_dedup.
    from scripts.run_tokko_canary import id_sustituto
    return B.Fuente(canonical_agency_id=aid, agency_name="Alfa Propiedades",
                    official_url=url, inmobiliaria_id=id_sustituto(aid))


def conector(paginas=None, fallar=None, cp=None):
    paginas = paginas or {"https://alfa.com.ar/": LISTADO,
                          "https://alfa.com.ar/Propiedades": LISTADO,
                          "https://alfa.com.ar/p/": FICHA}
    return TokkoConnector(descargador=DescargadorFalso(paginas, fallar), checkpoint=cp)


# ------------------------------------------------------------ reuso y contrato
def test_la_identidad_se_reusa_del_pipeline_existente():
    """Copiar el hash en vez de importarlo lo desincronizaria en silencio y
    empezaria a crear duplicados que nadie relaciona con este cambio."""
    assert B.REUSA_PIPELINE is True
    assert B.calcular_hash_dedup(7, "https://alfa.com.ar/p/1") == \
        B.calcular_hash_dedup(7, "https://www.alfa.com.ar/p/1/")


def test_el_vocabulario_es_el_del_schema_no_uno_nuevo():
    assert B.MONEDAS_VALIDAS == {"ARS", "USD"}
    assert "venta" in B.OPERACIONES_VALIDAS and "consultar" in B.OPERACIONES_VALIDAS
    assert "departamento" in B.TIPOS_VALIDOS


def test_el_pipeline_no_esta_acoplado_a_tokko():
    """base.py puede nombrar a Tokko en un comentario, pero no puede importarlo
    ni ramificar por el: agregar una plataforma no deberia tocar el nucleo."""
    fuente_base = (ROOT / "connectors" / "base.py").read_text(encoding="utf-8")
    sin_docstrings = re.sub(r'"""[\s\S]*?"""', "", fuente_base)
    codigo = "\n".join(l for l in sin_docstrings.splitlines()
                       if not l.strip().startswith("#"))
    assert "tokko" not in codigo.lower()


# ------------------------------------------------------------------- deteccion
def test_detecta_la_variante_estandar_de_tokko():
    plan = conector().discover(fuente())
    assert plan["variante"] == "TFW_ESTANDAR"
    assert plan["soportada"] is True
    assert plan["tokko_client_id"] == "33648"
    assert plan["total_declarado"] == 2


def test_una_variante_no_soportada_se_reporta_no_se_traga():
    """Devolver cero propiedades sin decir nada es la forma mas cara de fallar:
    parece que la inmobiliaria no publica, y en realidad no la sabemos leer."""
    html = '<html><body><script src="tokkobroker.com/x.js"></script></body></html>'
    plan = conector({"https://alfa.com.ar/": html}).discover(fuente())
    assert plan["variante"] == "TOKKO_FRONTEND_PROPIO"
    assert plan["soportada"] is False


def test_sin_marcador_tokko_no_se_inventa_soporte():
    plan = conector({"https://alfa.com.ar/": "<html><body>hola</body></html>"}).discover(fuente())
    assert plan["variante"] == "SIN_MARCADOR" and plan["soportada"] is False


# ----------------------------------------------------------------- paginacion
def test_la_paginacion_usa_el_query_que_la_pagina_trae_escrito():
    """Inventar '?page=2' devuelve la pagina uno otra vez, con http 200 y sin
    error. El query hay que leerlo del HTML."""
    c = conector()
    plan = c.discover(fuente())
    assert plan["query_paginacion"].endswith("&p=")
    assert plan["pagina_por_query"] is True


def test_pagina_hasta_agotar_y_corta_sin_ids_nuevos():
    p2 = LISTADO.replace("/p/111-", "/p/333-").replace("/p/222-", "/p/444-")
    vacia = "<html><body>sin resultados</body></html>"
    paginas = {"https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=2": p2,
               "https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=3": vacia,
               "https://alfa.com.ar/Propiedades": LISTADO,
               "https://alfa.com.ar/": LISTADO}
    c = conector(paginas)
    f = fuente()
    avisos = list(c.fetch_listing(f, c.discover(f)))
    assert [a["source_listing_id"] for a in avisos] == ["111", "222", "333", "444"]


def test_no_emite_el_mismo_aviso_dos_veces():
    c = conector()
    f = fuente()
    ids = [a["source_listing_id"] for a in c.fetch_listing(f, c.discover(f))]
    assert len(ids) == len(set(ids))


def test_una_variante_no_soportada_no_lista_nada():
    c = conector({"https://alfa.com.ar/": "<html>nada</html>"})
    f = fuente()
    assert list(c.fetch_listing(f, c.discover(f))) == []


# -------------------------------------------------------------- normalizacion
def norm():
    c = conector()
    f = fuente()
    return c.normalize({"source_listing_id": "8636261",
                        "source_url": "https://alfa.com.ar/p/8636261-x",
                        "pagina": 1}, f)


def test_normaliza_los_campos_principales():
    p = norm()
    assert p.precio == 55000.0 and p.moneda == "USD"
    assert p.operacion == "venta" and p.tipo_propiedad == "departamento"
    assert p.dormitorios == 1 and p.banos == 1 and p.ambientes == 2
    assert p.superficie_cubierta == 40.0
    assert p.latitud == pytest.approx(-31.4203028)


def test_la_direccion_se_lee_aunque_no_haya_dos_puntos():
    """La cabecera de Tokko escribe 'Direccion <valor> Ubicacion <valor>'. Sin
    saber donde corta el valor se leeria la ficha entera como direccion."""
    p = norm()
    assert p.direccion == "Independencia al 300"
    assert p.barrio == "Nueva Cordoba"


def test_un_valor_con_mayuscula_adentro_no_corta_el_campo():
    t = _texto_plano("<div>Ubicacion Nueva Cordoba Ambientes 2</div>")
    assert _campo(t, "Ubicacion") == "Nueva Cordoba"


def test_las_expensas_van_a_datos_extra_no_a_una_columna_nueva():
    """El schema no tiene columna de expensas; datos_extra si existe."""
    assert norm().extra["expensas"] == 85000.0


def test_lo_que_la_fuente_no_publica_queda_en_none():
    """Un dato inferido mal se publica y no se nota; uno ausente se ve."""
    p = norm()
    assert p.superficie_total is None
    assert p.provincia is None and p.ciudad is None


def test_una_ficha_vacia_no_inventa_nada():
    c = conector({"https://alfa.com.ar/p/": "<html><body></body></html>"})
    p = c.normalize({"source_listing_id": "1", "source_url": "https://alfa.com.ar/p/1-x"},
                    fuente())
    assert p.precio is None and p.moneda is None and p.imagenes == []


# ------------------------------------------------------------------- moneda
@pytest.mark.parametrize("txt,esperado", [
    ("USD", "USD"), ("U$S", "USD"), ("us$", "USD"), ("dolares", "USD"),
    ("$", "ARS"), ("pesos", "ARS"), ("", None), ("euros", None)])
def test_moneda(txt, esperado):
    assert B.detectar_moneda(txt) == esperado


@pytest.mark.parametrize("txt,esperado", [
    ("1.234.567", 1234567.0), ("55.000", 55000.0), ("1.234,56", 1234.56),
    ("120", 120.0), ("", None), ("consultar", None)])
def test_numeros_en_formato_argentino(txt, esperado):
    assert B.a_numero(txt) == esperado


def test_un_precio_sin_moneda_se_reporta_como_problema():
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://x.com/p/1", connector="t", precio=100)
    assert "precio sin moneda" in p.problemas()


# ---------------------------------------------------------------- operacion
@pytest.mark.parametrize("txt,esperado", [
    ("Casa en Venta", "venta"), ("Depto en Alquiler", "alquiler"),
    ("Alquiler temporario", "alquiler_temporario"), ("", None)])
def test_operacion(txt, esperado):
    assert B.detectar_operacion(txt) == esperado


def test_una_operacion_fuera_de_vocabulario_se_marca():
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://x.com/p/1", connector="t",
                               operacion="permuta")
    assert any("operacion fuera de vocabulario" in q for q in p.problemas())


# -------------------------------------------------------------------- fotos
def test_solo_se_asocian_las_fotos_de_esta_propiedad():
    """El carrusel de Tokko muestra fotos de otras fichas. La ruta lleva el id
    adelante, asi que la de otra propiedad se puede descartar."""
    p = norm()
    assert len(p.imagenes) == 2
    assert all("/8636261_" in u for u in p.imagenes)
    assert not any("9999999" in u for u in p.imagenes)


def test_no_se_descargan_binarios_de_imagen():
    src = (ROOT / "connectors" / "tokko.py").read_text(encoding="utf-8")
    assert ".content" not in src and "urlretrieve" not in src


# --------------------------------------------------- aislamiento entre agencias
def test_dos_inmobiliarias_nunca_comparten_hash():
    """Lo que impide mezclar inventario: la agencia entra en la identidad."""
    a = B.PropiedadNormalizada(canonical_agency_id="ag-1", source_listing_id="1",
                               source_url="https://x.com/p/1", connector="t",
                               inmobiliaria_id=1)
    b = B.PropiedadNormalizada(canonical_agency_id="ag-2", source_listing_id="1",
                               source_url="https://x.com/p/1", connector="t",
                               inmobiliaria_id=2)
    assert a.hash_dedup != b.hash_dedup


def test_la_procedencia_viaja_con_cada_propiedad():
    p = norm()
    assert p.provenance["canonical_agency_id"] == "ag-1"
    assert p.provenance["official_domain"] == "https://alfa.com.ar"
    assert p.provenance["source_platform"] == "TOKKO"


# -------------------------------------------------------------- idempotencia
def test_la_misma_propiedad_da_el_mismo_hash_en_dos_corridas():
    assert norm().hash_dedup == norm().hash_dedup


def test_el_fingerprint_ignora_el_momento_de_la_corrida():
    """Si scraped_at entrara en la huella, cada corrida veria cambios donde no
    los hubo y el incremental no serviria de nada."""
    a, b = norm(), norm()
    b.scraped_at = "2030-01-01T00:00:00"
    assert a.fingerprint == b.fingerprint


def test_la_segunda_corrida_no_crea_nada_nuevo(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    assert c.registrar(f, norm()) == "NUEVA"
    assert c.registrar(f, norm()) == "SIN_CAMBIOS"


def test_un_cambio_real_si_se_detecta(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    c.registrar(f, norm())
    p = norm()
    p.precio = 60000.0
    assert c.registrar(f, p) == "MODIFICADA"


# ------------------------------------------------------------------ reanudar
def test_el_checkpoint_sobrevive_al_reinicio(tmp_path):
    ruta = tmp_path / "cp.json"
    c1 = conector(cp=B.Checkpoint(ruta))
    f = fuente()
    c1.registrar(f, norm())
    c1.checkpoint.guardar()
    c2 = conector(cp=B.Checkpoint(ruta))
    assert c2.resume(f)["vistos"]
    assert c2.registrar(f, norm()) == "SIN_CAMBIOS"


def test_un_checkpoint_corrupto_no_voltea_la_corrida(tmp_path):
    ruta = tmp_path / "cp.json"
    ruta.write_text("{roto", encoding="utf-8")
    assert B.Checkpoint(ruta).de("ag-1")["vistos"] == {}


# ------------------------------------------------------------------- bajas
def _fuente_con_inventario(cp, cuantas=10):
    """Una fuente con inventario de verdad, a la que le falta UNA propiedad.

    Antes estos tests simulaban la baja con una enumeracion vacia. Eso ya no
    cuenta como baja, y con razon: una fuente que responde y no enumera nada es
    mucho mas probablemente un fallo de lectura que una inmobiliaria borrando su
    catalogo entero. Una baja real se ve con el resto del inventario en su lugar.
    """
    c = conector(cp=cp)
    f = fuente()
    cp.de("ag-1")["vistos"] = {f"h{i}": "fp" for i in range(cuantas)}
    presentes = {f"h{i}" for i in range(cuantas)} - {"h0"}
    return c, f, presentes


def test_una_sola_ausencia_no_da_de_baja(tmp_path):
    """Un 502 de diez minutos daria de baja el catalogo entero de golpe."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    c, f, presentes = _fuente_con_inventario(cp)
    r = c.identify_deleted_or_inactive(f, presentes, fuente_respondio=True)
    assert [x["hash_dedup"] for x in r] == ["h0"]
    assert r[0]["estado"] == "AUSENTE_PROVISORIA"


def test_recien_a_las_tres_ausencias_seguidas_se_confirma(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c, f, presentes = _fuente_con_inventario(cp)
    for _ in range(B.AUSENCIAS_PARA_BAJA):
        r = c.identify_deleted_or_inactive(f, presentes, fuente_respondio=True)
    assert r[0]["estado"] == "BAJA_CONFIRMADA"


def test_si_la_fuente_no_respondio_no_se_concluye_nada(tmp_path):
    """No se puede deducir una baja de un sitio que no contesto."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    c.registrar(f, norm())
    r = c.identify_deleted_or_inactive(f, set(), fuente_respondio=False)
    assert r[0]["estado"] == "SIN_EVIDENCIA_FUENTE_CAIDA"


def test_volver_a_ver_la_propiedad_borra_las_ausencias(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    c.registrar(f, norm())
    c.identify_deleted_or_inactive(f, set(), True)
    c.identify_deleted_or_inactive(f, {"8636261"}, True)
    assert cp.de("ag-1")["ausencias"].get("8636261") is None


# ---------------------------------------------------------- errores y reintentos
def test_un_403_no_se_reintenta():
    """Insistir contra un sitio que nos esta frenando es exactamente lo que no
    hay que hacer."""
    d = DescargadorFalso({}, {"https://alfa.com.ar/x": B.Bloqueado("http 403")})
    with pytest.raises(B.Bloqueado):
        d.bajar("https://alfa.com.ar/x")
    assert len(d.pedidos_urls) == 1


def test_un_404_es_ausencia_definitiva_no_error():
    c = conector({"https://alfa.com.ar/p/": FICHA},
                 {"https://alfa.com.ar/p/9-x": B.ErrorPermanente("http 404")})
    assert c.normalize({"source_listing_id": "9",
                        "source_url": "https://alfa.com.ar/p/9-x"}, fuente()) is None


def test_un_error_transitorio_se_anota_y_no_frena_la_fuente():
    c = conector({"https://alfa.com.ar/p/": FICHA},
                 {"https://alfa.com.ar/p/9-x": B.ErrorTransitorio("timeout")})
    assert c.normalize({"source_listing_id": "9",
                        "source_url": "https://alfa.com.ar/p/9-x"}, fuente()) is None
    assert c.errores and c.errores[0]["etapa"] == "detalle"


def test_el_backoff_esta_configurado():
    src = (ROOT / "connectors" / "base.py").read_text(encoding="utf-8")
    assert "demora *= 2" in src and "random.uniform" in src


def test_el_ritmo_es_por_host_y_esta_limitado():
    lim = B.LimitadorDeRitmo(0.05)
    t0 = __import__("time").monotonic()
    lim.esperar("a.com")
    lim.esperar("a.com")
    assert __import__("time").monotonic() - t0 >= 0.05


# --------------------------------------------------------- compatibilidad schema
def test_los_campos_normalizados_existen_en_el_schema_de_eretz():
    """Si el connector inventara columnas, el pipeline las descartaria sin avisar."""
    schema = (B.RUTA_PIPELINE / "internal_db_schema.sql").read_text(
        encoding="utf-8", errors="ignore")
    bloque = schema[schema.index("propiedades_raw ("):schema.index("propiedades_raw (") + 2500]
    for col in ("titulo", "descripcion", "precio", "moneda", "operacion",
                "tipo_propiedad", "latitud", "longitud", "imagenes", "datos_extra",
                "superficie_total", "superficie_cubierta", "barrio", "ciudad",
                "provincia", "hash_dedup", "scraped_at"):
        assert col in bloque, col


def test_todo_lo_extra_cabe_en_datos_extra():
    p = norm()
    assert isinstance(p.extra, dict)
    json.dumps(p.extra)  # tiene que ser serializable a jsonb


# --------------------------------------------------------- robustez del runner
def test_el_log_no_se_rompe_con_un_campo_vacio():
    """Una fuente sin total declarado volteo una corrida entera de 15 fuentes:
    dict.get(k, "-") devuelve None si la clave existe con valor None."""
    from scripts.run_tokko_canary import num
    assert num(None) == "   -"
    assert num(690) == " 690"
    assert num(None, 3) == "  -"


def test_los_artefactos_se_escriben_por_fuente_no_al_final():
    """Guardar solo al final ya costo perder 15 fuentes ya procesadas."""
    src = (ROOT / "scripts" / "run_tokko_canary.py").read_text(encoding="utf-8")
    assert 'ruta_inv.open("a"' in src and 'ruta_norm.open("a"' in src
    i_bucle = src.index("for i, x in enumerate(muestra, 1)")
    assert src.index('ruta_inv.open("a"') > i_bucle


def test_una_ficha_con_acentos_se_puede_bajar():
    """Los slugs de Tokko llevan acentos y urllib arma el pedido en ASCII: una
    de cada cinco fichas en castellano levantaba UnicodeEncodeError, y el error
    aparecia recien al abrir la conexion, disfrazado de falla del sitio."""
    cruda = "https://alfa.com.ar/p/123-Casa-en-Barrio-Céntrico-Córdoba"
    segura = B.Descargador.url_segura(cruda)
    assert "%C3%A9" in segura and "%C3%B3" in segura
    segura.encode("ascii")  # tiene que poder pedirse


def test_codificar_la_url_no_cambia_la_identidad():
    """Si la forma codificada y la legible dieran hashes distintos, la misma
    propiedad entraria dos veces."""
    legible = "https://alfa.com.ar/p/123-Barrio-Céntrico"
    assert B.calcular_hash_dedup(7, legible) ==         B.calcular_hash_dedup(7, B.Descargador.url_segura(legible))


def test_una_url_ya_codificada_no_se_codifica_dos_veces():
    ya = "https://alfa.com.ar/p/123-Barrio-C%C3%A9ntrico"
    assert B.Descargador.url_segura(ya) == ya


def test_el_id_de_agencia_es_estable_entre_procesos():
    """hash() de Python esta aleatorizado por proceso. Al entrar en hash_dedup,
    daba una identidad distinta en cada corrida: la segunda veia las 322
    propiedades como modificadas y la idempotencia fallaba sin que el connector
    tuviera nada que ver."""
    import subprocess
    codigo = ("import sys; sys.path.insert(0, r'%s');"
              "from scripts.run_tokko_canary import id_sustituto;"
              "print(id_sustituto('ag-1'))" % ROOT)
    salidas = {subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                              text=True).stdout.strip() for _ in range(2)}
    assert len(salidas) == 1 and salidas != {""}


def test_el_runner_no_usa_hash_para_identidad():
    src = (ROOT / "scripts" / "run_tokko_canary.py").read_text(encoding="utf-8")
    assert "abs(hash(" not in src
    assert "id_sustituto" in src


# =========================================================== connector WordPress
from connectors.wordpress import WordPressConnector  # noqa: E402

WP_TYPES = json.dumps({"post": {"rest_base": "posts"},
                       "property": {"rest_base": "property"}})
WP_ITEM = json.dumps([{
    "id": 116338, "link": "https://wp.com.ar/property/depto-la-plata/",
    "type": "property", "modified": "2026-08-01T10:00:00",
    "title": {"rendered": "Departamento en alquiler en La Plata"},
    "content": {"rendered": "<p>Depto USD 55.000 2 ambientes</p>"}}])


def wp_conector(paginas=None, cp=None):
    paginas = paginas or {
        "https://wp.com.ar/wp-json/wp/v2/types": WP_TYPES,
        "https://wp.com.ar/wp-json/wp/v2/property": WP_ITEM,
        "https://wp.com.ar/property/": "<html></html>",
    }
    return WordPressConnector(descargador=DescargadorFalso(paginas), checkpoint=cp)


def wp_fuente():
    return B.Fuente(canonical_agency_id="wp-1", agency_name="Alfa",
                    official_url="https://wp.com.ar/", inmobiliaria_id=99)


def test_wordpress_prefiere_la_rest_sobre_el_html():
    """La REST devuelve campos tipados y ahorra el parser entero: es el camino
    mas barato y por eso se prueba primero."""
    plan = wp_conector().discover(wp_fuente())
    assert plan["variante"] == "WORDPRESS_REST"
    assert plan["post_type"] == "property" and plan["soportada"] is True


def test_wordpress_ignora_los_post_types_que_no_son_inventario():
    plan = wp_conector().discover(wp_fuente())
    assert "post" not in (plan.get("post_types_inmo") or [])


def test_wordpress_sin_inventario_no_se_fuerza():
    """46% de los WordPress no publica inventario detectable. Devolver cero en
    silencio haria creer que la inmobiliaria no tiene propiedades."""
    c = wp_conector({"https://wp.com.ar/wp-json/wp/v2/types": json.dumps({"post": {}}),
                     "https://wp.com.ar/": "<html><a href='/nosotros/x'>x</a></html>"})
    plan = c.discover(wp_fuente())
    assert plan["soportada"] is False and plan["variante"] == "SIN_INVENTARIO"
    assert list(c.fetch_listing(wp_fuente(), plan)) == []


def test_wordpress_pagina_por_rest_y_corta_al_agotarse():
    c = wp_conector()
    f = wp_fuente()
    avisos = list(c.fetch_listing(f, c.discover(f)))
    assert [a["source_listing_id"] for a in avisos] == ["116338"]


def test_wordpress_usa_el_id_de_la_plataforma_como_identidad():
    c = wp_conector()
    f = wp_fuente()
    a = list(c.fetch_listing(f, c.discover(f)))[0]
    p = c.normalize(a, f)
    assert p.source_listing_id == "116338"
    assert p.connector == "wordpress"


def test_wordpress_respeta_la_convencion_de_moneda_del_pipeline():
    """El pipeline mapea "$" a ARS en normalize_currency. Un connector con una
    regla propia mas estricta deja precios sin moneda y crea una segunda verdad
    sobre el mismo dato."""
    assert B.detectar_moneda("$") == "ARS"
    assert B.detectar_moneda("USD") == "USD"


def test_wordpress_no_publica_cero_ambientes():
    """Un cero suelto del texto caia junto a la etiqueta. "0 ambientes" es peor
    que ausente: parece un dato verificado."""
    assert WordPressConnector._ambientes("0 ambientes", r"ambientes?") is None
    assert WordPressConnector._ambientes("3 ambientes", r"ambientes?") == 3


def test_wordpress_descarta_logos_y_placeholders_de_las_fotos():
    c = wp_conector({
        "https://wp.com.ar/wp-json/wp/v2/types": WP_TYPES,
        "https://wp.com.ar/wp-json/wp/v2/property": json.dumps([{
            "id": 1, "link": "https://wp.com.ar/property/x/", "type": "property",
            "title": {"rendered": "Casa USD 100.000"},
            "content": {"rendered": '<img src="https://wp.com.ar/logo.png">'
                                    '<img src="https://wp.com.ar/casa-1.jpg">'}}]),
        "https://wp.com.ar/property/x/": "<html></html>"})
    f = wp_fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert all("logo" not in u for u in p.imagenes)


def test_wordpress_produce_la_misma_representacion_normalizada():
    """El pipeline no debe distinguir de que connector vino la propiedad."""
    c = wp_conector()
    f = wp_fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert isinstance(p, B.PropiedadNormalizada)
    assert p.hash_dedup and p.fingerprint


def test_dos_connectors_distintos_no_colisionan_en_identidad():
    """La misma URL bajo dos inmobiliarias distintas tiene que dar hashes
    distintos, venga del connector que venga."""
    a = B.PropiedadNormalizada(canonical_agency_id="x", source_listing_id="1",
                               source_url="https://z.com/p/1", connector="tokko",
                               inmobiliaria_id=10)
    b = B.PropiedadNormalizada(canonical_agency_id="y", source_listing_id="1",
                               source_url="https://z.com/p/1", connector="wordpress",
                               inmobiliaria_id=20)
    assert a.hash_dedup != b.hash_dedup


# ------------------------------------------------------- cortesia vs concurrencia
def test_la_cortesia_es_por_host_no_global():
    """Un cerrojo unico para todos los hosts convierte el limite de cortesia en
    un limite global: con 8 fuentes en paralelo el rollout pasa de horas a dias."""
    import time as _t
    lim = B.LimitadorDeRitmo(0.3)
    lim.esperar("a.com")
    t0 = _t.monotonic()
    lim.esperar("b.com")          # otro host: no deberia esperar nada
    assert _t.monotonic() - t0 < 0.2


def test_el_mismo_host_si_espera():
    import time as _t
    lim = B.LimitadorDeRitmo(0.3)
    lim.esperar("a.com")
    t0 = _t.monotonic()
    lim.esperar("a.com")
    assert _t.monotonic() - t0 >= 0.25


def test_una_pagina_repetida_no_corta_el_listado_antes_de_tiempo():
    """Tokko reordena entre pedidos y a veces devuelve una pagina ya vista.
    Cortar en la primera repeticion costaba hasta un 11% del inventario, y como
    el total declarado seguia sin alcanzarse el error era invisible."""
    p1 = LISTADO.replace("2 Resultados", "60 Resultados")
    p3 = p1.replace("/p/111-", "/p/333-").replace("/p/222-", "/p/444-")
    paginas = {
        "https://alfa.com.ar/": p1,
        "https://alfa.com.ar/Propiedades": p1,
        "https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=2": p1,   # repetida
        "https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=3": p3,
        "https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=4": "<html>vacio</html>",
    }
    c = conector(paginas)
    f = fuente()
    ids = [a["source_listing_id"] for a in c.fetch_listing(f, c.discover(f))]
    assert ids == ["111", "222", "333", "444"]


def test_una_pagina_sin_ninguna_ficha_si_termina_el_listado():
    paginas = {"https://alfa.com.ar/": LISTADO,
               "https://alfa.com.ar/Propiedades": LISTADO,
               "https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=2":
                   "<html>sin resultados</html>"}
    c = conector(paginas)
    f = fuente()
    assert len(list(c.fetch_listing(f, c.discover(f)))) == 2


# ------------------------------------------------- fotos y ubicacion por connector
def test_solo_se_cuentan_fotos_ajenas_donde_se_pueden_verificar():
    """La ruta del CDN de Tokko lleva el id adelante y permite comprobarlo.
    WordPress no: las imagenes son adjuntos con nombre libre. Contar "ajenas"
    ahi daba 3.882 falsos positivos y tapaba los casos reales."""
    assert conector().foto_verificable() is True
    assert wp_conector().foto_verificable() is False


def test_tokko_reconoce_la_foto_de_su_propiedad():
    c = conector()
    p = norm()
    assert c.foto_es_de(p, f"https://static.tokkobroker.com/pictures/{p.source_listing_id}_a.jpg")
    assert not c.foto_es_de(p, "https://static.tokkobroker.com/pictures/999_a.jpg")


def test_la_ubicacion_del_padron_solo_rellena_lo_vacio():
    """Una ubicacion explicita de la ficha no se pisa con una inferencia."""
    c = conector()
    f = B.Fuente(canonical_agency_id="a", agency_name="Alfa",
                 official_url="https://alfa.com.ar/", inmobiliaria_id=1,
                 extra={"city": "Rosario", "province": "Santa Fe"})
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://alfa.com.ar/p/1", connector="t",
                               ciudad="Funes")
    p.provincia = "Cordoba"
    c.completar_ubicacion(p, f)
    assert p.ciudad == "Funes"                    # la explicita gana
    assert p.provincia == "Cordoba"               # la explicita tampoco se pisa
    assert "provincia_origen" not in p.extra


def test_la_ubicacion_inferida_queda_marcada_como_tal():
    """La provincia de la inmobiliaria no es necesariamente la del inmueble:
    quien consuma el dato tiene que poder distinguirlo."""
    c = conector()
    f = B.Fuente(canonical_agency_id="a", agency_name="Alfa",
                 official_url="https://alfa.com.ar/", inmobiliaria_id=1,
                 extra={"city": "recoleta", "province": "Santa Fe"})
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://alfa.com.ar/p/1", connector="t")
    c.completar_ubicacion(p, f)
    assert p.provincia == "Santa Fe"
    assert p.extra["provincia_confianza"] == "inferida"


def test_la_zona_del_padron_no_se_usa_como_ciudad():
    """El campo `city` del padron guarda barrios -"recoleta", "palermo",
    "centro"-, no ciudades. Copiarlo llenaria el dataset de barrios disfrazados
    de ciudades, y nadie lo notaria despues."""
    c = conector()
    f = B.Fuente(canonical_agency_id="a", agency_name="Alfa",
                 official_url="https://alfa.com.ar/", inmobiliaria_id=1,
                 extra={"city": "recoleta", "province": "Buenos Aires"})
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://alfa.com.ar/p/1", connector="t")
    c.completar_ubicacion(p, f)
    assert p.ciudad is None
    assert p.extra["zona_padron"] == "recoleta"


def test_sin_padron_no_se_inventa_ubicacion():
    c = conector()
    f = B.Fuente(canonical_agency_id="a", agency_name="Alfa",
                 official_url="https://alfa.com.ar/", inmobiliaria_id=1)
    p = B.PropiedadNormalizada(canonical_agency_id="a", source_listing_id="1",
                               source_url="https://alfa.com.ar/p/1", connector="t")
    c.completar_ubicacion(p, f)
    assert p.ciudad is None and p.provincia is None


def test_el_id_de_agencia_entra_en_un_integer_de_postgres():
    """La columna inmobiliaria_id es INTEGER y sha256[:8] llega a 4.294.967.295,
    mas del doble del maximo. Sin tope el insert falla recien contra la base,
    con el lote a medias."""
    from scripts.run_tokko_canary import id_sustituto
    for aid in ("ag-1", "ag-2", "zzz-9999", "a" * 40):
        assert 0 <= id_sustituto(aid) <= 2_147_483_647


def test_la_carga_rechaza_un_id_fuera_de_rango_antes_de_la_base():
    from scripts.ingest_to_pipeline import rechazos
    p = {"hash_dedup": "x", "inmobiliaria_id": 2_279_155_404,
         "source_url": "https://a.com/1", "operacion": "venta"}
    assert any("rango INTEGER" in m for m in rechazos(p))


def test_la_carga_usa_las_columnas_del_pipeline_no_una_lista_propia():
    from scripts.ingest_to_pipeline import RAW_COLUMNS
    origen = (B.RUTA_PIPELINE / "scripts" / "import_captured_props_to_neon.py").read_text(
        encoding="utf-8", errors="ignore")
    bloque = origen[origen.index("RAW_COLUMNS = ["):origen.index("VALID_OPERATIONS")]
    for c in RAW_COLUMNS:
        assert f'"{c}"' in bloque, c


def test_lo_que_no_tiene_columna_va_a_datos_extra():
    from scripts.ingest_to_pipeline import a_fila_raw
    fila = a_fila_raw({"hash_dedup": "h", "inmobiliaria_id": 1,
                       "source_url": "https://a.com/1", "ambientes": 3,
                       "extra": {"expensas": 85000}, "source_listing_id": "9"})
    extra = json.loads(fila["datos_extra"])
    assert extra["expensas"] == 85000 and extra["ambientes"] == 3
    assert extra["source_listing_id"] == "9"


def test_cada_corrida_registra_la_version_del_codigo():
    """Editar un connector con una corrida en vuelo hace que la segunda lea
    codigo distinto: todo sale MODIFICADA y la idempotencia parece rota cuando
    lo unico que cambio fue el codigo. Ya paso dos veces; que quede escrito en
    el resumen convierte un diagnostico campo por campo en una comparacion."""
    from scripts.run_rollout import version_del_codigo
    v = version_del_codigo("tokko")
    assert isinstance(v, str) and len(v) == 12
    assert v == version_del_codigo("tokko")
    # Agregar un connector nuevo no puede invalidar la comparacion de los otros.
    assert version_del_codigo("tokko") != version_del_codigo("wordpress")
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    assert '"version_codigo"' in src


# =========================================================== connector Century 21
from connectors.century21 import Century21Connector  # noqa: E402

C21_PERFIL = ('<html><a href="/v/resultados/oficina_68-revolution-s-a_local">'
              'Ver propiedades</a></html>')
C21_JSON = json.dumps({"totalHits": "2", "results": [
    {"id": 373936, "encabezado": "Venta | Departamento en Rosario", "precio": 42000,
     "moneda": "USD", "calle": "Av. Pellegrini", "colonia": "Martin",
     "estado": "Santa Fe", "banos": 1, "fechaModificacion": "2026-08-01",
     "fotos": {"totalFotos": 18,
               "propiedadThumbnail": ["https://cdn.21online.lat/a/1.jpg"]}},
    {"id": 373937, "encabezado": "Alquiler | Casa en Rosario", "precio": 500000,
     "moneda": "ARS", "banos": 2, "fotos": {}}]})


def c21_conector(paginas=None, cp=None):
    paginas = paginas or {
        "https://century21.com.ar/v/oficina/68-revolution-s-a-rosario": C21_PERFIL,
        "https://century21.com.ar/v/resultados/oficina_68-revolution-s-a_local?json=true":
            C21_JSON,
    }
    return Century21Connector(descargador=DescargadorFalso(paginas), checkpoint=cp)


def c21_fuente():
    return B.Fuente(canonical_agency_id="c21-68", agency_name="C21 Revolution",
                    official_url="https://century21.com.ar/v/oficina/68-revolution-s-a-rosario",
                    inmobiliaria_id=68)


def test_century21_lee_el_enlace_al_inventario_de_la_ficha():
    """El slug del perfil ("revolution-s-a-rosario-santa-fe-argentina") no es el
    del listado ("revolution-s-a"): no se puede derivar uno del otro, hay que
    leer el enlace que la propia ficha publica."""
    plan = c21_conector().discover(c21_fuente())
    assert plan["variante"] == "C21_JSON" and plan["soportada"] is True
    assert plan["ruta"].endswith("oficina_68-revolution-s-a_local")
    assert plan["total_declarado"] == 2


def test_century21_usa_el_json_no_el_html():
    """El listado renderizado en cliente son 650 KB sin un solo enlace a ficha.
    La misma url con ?json=true devuelve el resultado completo."""
    src = (ROOT / "connectors" / "century21.py").read_text(encoding="utf-8")
    assert "?json=true" in src


def test_century21_enumera_y_normaliza():
    c = c21_conector()
    f = c21_fuente()
    avisos = list(c.fetch_listing(f, c.discover(f)))
    assert [a["source_listing_id"] for a in avisos] == ["373936", "373937"]
    p = c.normalize(avisos[0], f)
    assert p.precio == 42000 and p.moneda == "USD" and p.operacion == "venta"
    assert p.direccion == "Av. Pellegrini" and p.provincia == "Santa Fe"
    assert p.imagenes == ["https://cdn.21online.lat/a/1.jpg"]
    assert p.problemas() == []


def test_century21_respeta_la_moneda_declarada():
    c = c21_conector()
    f = c21_fuente()
    avisos = list(c.fetch_listing(f, c.discover(f)))
    assert c.normalize(avisos[1], f).moneda == "ARS"


def test_century21_sin_fotos_no_inventa():
    c = c21_conector()
    f = c21_fuente()
    avisos = list(c.fetch_listing(f, c.discover(f)))
    assert c.normalize(avisos[1], f).imagenes == []


def test_century21_una_url_sin_oficina_no_se_soporta():
    c = c21_conector({"https://century21.com.ar/acercade": "<html></html>"})
    f = B.Fuente(canonical_agency_id="x", agency_name="x",
                 official_url="https://century21.com.ar/acercade", inmobiliaria_id=1)
    plan = c.discover(f)
    assert plan["soportada"] is False
    assert list(c.fetch_listing(f, plan)) == []


def test_los_tres_connectors_cumplen_la_misma_interfaz():
    """El pipeline no debe distinguir de que plataforma vino una propiedad."""
    for clase in (TokkoConnector, WordPressConnector, Century21Connector):
        for metodo in ("discover", "fetch_listing", "normalize", "resume",
                       "registrar", "identify_deleted_or_inactive"):
            assert callable(getattr(clase, metodo)), (clase.__name__, metodo)


# ------------------------------------------- extraccion de texto y descripcion
def test_el_markup_escapado_no_termina_dentro_de_la_descripcion():
    """Muchas descripciones traen el markup escapado en el propio HTML. Quitar
    etiquetas y desescapar despues devuelve ese markup al texto, y termina
    publicado dentro de la descripcion."""
    html = "<div>DESCRIPCION Casa linda&lt;div&gt;&lt;br&gt;&lt;/div&gt;con patio</div>"
    t = _texto_plano(html)
    assert "<div>" not in t and "&lt;" not in t
    assert "Casa linda" in t and "con patio" in t


def test_tokko_extrae_la_descripcion_de_la_ficha_que_ya_bajo():
    """Esta en el HTML que el connector ya descarga: no cuesta una peticion."""
    ficha = FICHA.replace("<div>(REF. AAP8636261)</div>",
                          "<div>DESCRIPCION Oportunidad de inversion sobre calle "
                          "Independencia, a metros del Patio Olmos, muy luminoso. "
                          "INFORMACION BASICA</div><div>(REF. AAP8636261)</div>")
    c = conector({"https://alfa.com.ar/": LISTADO,
                  "https://alfa.com.ar/Propiedades": LISTADO,
                  "https://alfa.com.ar/p/": ficha})
    p = c.normalize({"source_listing_id": "8636261",
                     "source_url": "https://alfa.com.ar/p/8636261-x"}, fuente())
    assert p.descripcion and "Oportunidad de inversion" in p.descripcion
    assert "INFORMACION" not in p.descripcion


def test_una_descripcion_demasiado_corta_no_cuenta():
    ficha = FICHA.replace("<div>(REF. AAP8636261)</div>", "<div>DESCRIPCION - INFORMACION</div>")
    c = conector({"https://alfa.com.ar/": LISTADO,
                  "https://alfa.com.ar/Propiedades": LISTADO,
                  "https://alfa.com.ar/p/": ficha})
    p = c.normalize({"source_listing_id": "1", "source_url": "https://alfa.com.ar/p/1-x"},
                    fuente())
    assert p.descripcion is None


def test_century21_usa_la_url_que_publica_la_fuente():
    """Construir "/v/propiedad/<id>" a mano daba una url inexistente, y
    source_url entra en el hash de identidad: cada propiedad habria quedado
    registrada con una direccion que no se puede abrir."""
    it = {"id": 1, "urlCorrectaPropiedad": "/propiedad/1_venta-casa/oficina_68"}
    assert Century21Connector._url_de(it, "1").endswith("/propiedad/1_venta-casa/oficina_68")


def test_century21_lee_las_coordenadas_de_la_raiz():
    c = c21_conector({
        "https://century21.com.ar/v/oficina/68-revolution-s-a-rosario": C21_PERFIL,
        "https://century21.com.ar/v/resultados/oficina_68-revolution-s-a_local?json=true":
            json.dumps({"totalHits": "1", "results": [{
                "id": 5, "encabezado": "Venta casa", "precio": 100, "moneda": "USD",
                "lat": -32.958, "lon": -60.635, "m2C": 34.8, "m2T": 39.7,
                "recamaras": 1, "municipio": "Rosario", "estado": "Santa Fe",
                "urlCorrectaPropiedad": "/propiedad/5_x"}]})})
    f = c21_fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert p.latitud == -32.958 and p.longitud == -60.635
    assert p.superficie_cubierta == 34.8 and p.superficie_total == 39.7
    assert p.ciudad == "Rosario" and p.dormitorios == 1


# ============================================================ connector generico
from connectors.generico import GenericoConnector, RE_FICHA  # noqa: E402

GEN_SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://alfa.com.ar/propiedades/710944-casa-en-venta</loc></url>
<url><loc>https://alfa.com.ar/propiedades/710945-depto-en-alquiler</loc></url>
<url><loc>https://alfa.com.ar/propiedades/</loc></url>
<url><loc>https://alfa.com.ar/contacto</loc></url>
</urlset>"""

GEN_FICHA = """<html><head>
<meta property="og:title" content="Casa en Venta en Rosario">
<script type="application/ld+json">{"@type":"Product","name":"Casa en Venta en Rosario",
"description":"Casa amplia con parque y cochera doble en zona residencial.",
"offers":{"@type":"Offer","price":"90000","priceCurrency":"USD"},
"address":{"@type":"PostalAddress","streetAddress":"Mitre 123",
"addressLocality":"Rosario","addressRegion":"Santa Fe"},
"geo":{"@type":"GeoCoordinates","latitude":-32.9587,"longitude":-60.6930},
"image":["https://alfa.com.ar/fotos/casa-1.jpg"]}</script>
</head><body><p>3 dormitorios 2 banos 170 m2 cubiertos</p>
<img src="https://alfa.com.ar/logo.png"></body></html>"""


def gen_conector(paginas=None, cp=None):
    paginas = paginas or {
        "https://alfa.com.ar/sitemap.xml": GEN_SITEMAP,
        "https://alfa.com.ar/propiedades/710944-casa-en-venta": GEN_FICHA,
        "https://alfa.com.ar/propiedades/710945-depto-en-alquiler": GEN_FICHA,
    }
    return GenericoConnector(descargador=DescargadorFalso(paginas), checkpoint=cp)


def test_generico_prefiere_el_sitemap():
    """El indice lista las fichas y evita recorrer el sitio a ciegas."""
    plan = gen_conector().discover(fuente())
    assert plan["variante"] == "SITEMAP" and plan["soportada"] is True
    assert plan["total_declarado"] == 2


def test_generico_no_confunde_el_listado_con_una_ficha():
    """"/propiedades/" es la pagina de listado, no una propiedad. Sin exigir un
    id o un slug largo entraria al inventario como si lo fuera."""
    assert not RE_FICHA.search("https://alfa.com.ar/propiedades/")
    assert not RE_FICHA.search("https://alfa.com.ar/contacto")
    assert RE_FICHA.search("https://alfa.com.ar/propiedades/710944-casa-en-venta")
    assert RE_FICHA.search("https://alfa.com.ar/inmuebles/casa-tres-dormitorios-rosario")


def test_generico_usa_schema_org_antes_que_el_texto():
    """schema.org es un contrato publico; el texto es una convencion visual que
    cambia con el tema del sitio."""
    c = gen_conector()
    f = fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert p.precio == 90000 and p.moneda == "USD"
    assert p.ciudad == "Rosario" and p.provincia == "Santa Fe"
    assert p.direccion == "Mitre 123"
    assert p.latitud == pytest.approx(-32.9587)
    assert p.extra["via"] == "json-ld"
    assert p.problemas() == []


def test_generico_cae_al_texto_cuando_no_hay_json_ld():
    # El relleno importa: una pagina de menos de 400 caracteres se descarta a
    # proposito, porque suele ser un error servido con http 200.
    ficha = ("<html><head><title>Casa en Venta</title></head><body>USD 55.000 "
             "3 dormitorios 2 banos" + " descripcion de la propiedad." * 20 +
             "</body></html>")
    c = gen_conector({"https://alfa.com.ar/sitemap.xml": GEN_SITEMAP,
                      "https://alfa.com.ar/propiedades/": ficha})
    f = fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert p.precio == 55000 and p.moneda == "USD"
    assert p.dormitorios == 3 and p.banos == 2


def test_generico_descarta_logos():
    c = gen_conector()
    f = fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert all("logo" not in u for u in p.imagenes)
    assert "https://alfa.com.ar/fotos/casa-1.jpg" in p.imagenes


def test_generico_sin_nada_no_se_fuerza():
    """Preferimos decir "no la supimos leer" antes que devolver cero y que
    parezca que la inmobiliaria no publica."""
    c = gen_conector({"https://alfa.com.ar/": "<html><a href='/nosotros'>x</a></html>"})
    f = fuente()
    plan = c.discover(f)
    assert plan["soportada"] is False
    assert list(c.fetch_listing(f, plan)) == []


def test_generico_conserva_el_id_de_la_plataforma():
    """El id tiene que poder rastrearse hasta la ficha de origen, nunca un hash
    inventado por nosotros."""
    assert GenericoConnector._id_de("https://a.com/propiedades/710944-casa") == "710944"
    assert GenericoConnector._id_de("https://a.com/inmuebles/casa-linda-rosario") == \
        "casa-linda-rosario"


def test_los_cuatro_connectors_cumplen_la_misma_interfaz():
    for clase in (TokkoConnector, WordPressConnector, Century21Connector,
                  GenericoConnector):
        for metodo in ("discover", "fetch_listing", "normalize", "resume",
                       "registrar", "identify_deleted_or_inactive"):
            assert callable(getattr(clase, metodo)), (clase.__name__, metodo)


def test_century21_no_toma_el_cero_como_medicion():
    """C21 devuelve 0 en m2C y m2T cuando no conoce la superficie. Grabarlo
    convierte "no se" en "cero metros", que parece un dato verificado y ademas
    dispara la incoherencia de cubierta mayor que total."""
    c = c21_conector({
        "https://century21.com.ar/v/oficina/68-revolution-s-a-rosario": C21_PERFIL,
        "https://century21.com.ar/v/resultados/oficina_68-revolution-s-a_local?json=true":
            json.dumps({"totalHits": "1", "results": [{
                "id": 7, "encabezado": "Venta casa", "precio": 100, "moneda": "USD",
                "m2C": 0, "m2T": 0, "urlCorrectaPropiedad": "/propiedad/7_x"}]})})
    f = c21_fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert p.superficie_cubierta is None and p.superficie_total is None
    assert p.problemas() == []


def test_century21_conserva_las_coordenadas_negativas():
    """Argentina esta entera en latitud y longitud negativas: un filtro de
    "mayor que cero" pensado para superficies borraria todas las coordenadas."""
    c = c21_conector({
        "https://century21.com.ar/v/oficina/68-revolution-s-a-rosario": C21_PERFIL,
        "https://century21.com.ar/v/resultados/oficina_68-revolution-s-a_local?json=true":
            json.dumps({"totalHits": "1", "results": [{
                "id": 8, "encabezado": "Venta casa", "precio": 100, "moneda": "USD",
                "lat": -32.958, "lon": -60.635, "m2C": 0,
                "urlCorrectaPropiedad": "/propiedad/8_x"}]})})
    f = c21_fuente()
    p = c.normalize(list(c.fetch_listing(f, c.discover(f)))[0], f)
    assert p.latitud == -32.958 and p.longitud == -60.635
    assert p.superficie_cubierta is None


def test_century21_reconoce_las_rutas_en_ingles():
    """La red sirve la misma pagina en dos idiomas y cambia AMBOS segmentos:
    /v/resultados/oficina_..._local y /v/results/office_..._local. Reconocer
    solo uno dejaba la mitad de las oficinas afuera sin que nada fallara."""
    from connectors.century21 import RE_LISTADO, RE_PERFIL
    assert RE_LISTADO.search("/v/results/office_65-billion-s-a_local")
    assert RE_LISTADO.search("/v/resultados/oficina_68-revolution-s-a_local")
    assert RE_PERFIL.search("/v/office/65-billion-s-a-palermo")
    assert RE_PERFIL.search("/v/oficina/64-dalera-la-plata")


def test_century21_pagina_con_el_termino_del_idioma():
    """En la version en ingles la paginacion es /page_N, no /pagina_N."""
    src = (ROOT / "connectors" / "century21.py").read_text(encoding="utf-8")
    assert '"page" if "/results/" in ruta else "pagina"' in src


# --------------------------------------------- identidad del checkpoint
def test_el_checkpoint_se_lleva_por_hash_no_por_id_de_la_fuente(tmp_path):
    """El id de la fuente sirve para rastrear la ficha, pero no siempre es
    unico: en los sitios propios se deriva de la url y dos rutas distintas
    pueden dar el mismo numero. Con esa clave el checkpoint pisaba una propiedad
    con otra y la corrida siguiente las reportaba modificadas sin motivo."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    a = B.PropiedadNormalizada(canonical_agency_id="ag-1", source_listing_id="1795",
                               source_url="https://alfa.com.ar/p/palermo-1795",
                               connector="generico", inmobiliaria_id=7, precio=100)
    b = B.PropiedadNormalizada(canonical_agency_id="ag-1", source_listing_id="1795",
                               source_url="https://alfa.com.ar/p/villa-mitre-1795",
                               connector="generico", inmobiliaria_id=7, precio=200)
    assert a.source_listing_id == b.source_listing_id
    assert a.hash_dedup != b.hash_dedup
    assert c.registrar(f, a) == "NUEVA"
    assert c.registrar(f, b) == "NUEVA"      # dos propiedades, no una modificada
    assert c.registrar(f, a) == "SIN_CAMBIOS"


def test_las_ausencias_se_comparan_con_la_misma_clave(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    p = B.PropiedadNormalizada(canonical_agency_id="ag-1", source_listing_id="1",
                               source_url="https://alfa.com.ar/p/1",
                               connector="t", inmobiliaria_id=7)
    c.registrar(f, p)
    assert c.identify_deleted_or_inactive(f, {p.hash_dedup}, True) == []
    r = c.identify_deleted_or_inactive(f, set(), True)
    assert r and r[0]["hash_dedup"] == p.hash_dedup
    assert r[0]["source_listing_id"] == "1"


# ------------------------------------------------- cadena de respaldo
def test_una_fuente_que_el_connector_de_plataforma_no_entiende_se_reintenta():
    """De las 48 fuentes WordPress sin inventario detectado, 21 tienen sitemap
    y 28 traen JSON embebido: el generico las lee sin saber nada de WordPress.
    Darlas por perdidas desperdicia inventario publicado y accesible."""
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    assert "respaldo" in src
    bloque = src[src.index("def procesar("):src.index("def _procesar_con(")]
    assert "VARIANTE_NO_SOPORTADA" in bloque and "ERROR_DISCOVERY" in bloque
    assert "rescatada_por_respaldo" in bloque


def test_el_respaldo_solo_cuenta_si_realmente_trajo_propiedades():
    """Marcar como rescatada una fuente donde el respaldo tampoco encontro nada
    inflaria la cobertura con fuentes vacias."""
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    bloque = src[src.index("def procesar("):src.index("def _procesar_con(")]
    assert 'alt.get("detalles_obtenidos")' in bloque


def test_wordpress_no_toma_una_busqueda_como_ficha():
    """La ruta de listado suele llamarse "buscar-propiedades", asi que la propia
    pagina de busqueda entra por el mismo patron que las fichas. Se colaron 56
    urls con filtros como si fueran propiedades."""
    from connectors.wordpress import _es_ficha
    assert not _es_ficha("https://a.com/buscar-propiedades/?sort=newest&search_status=10")
    assert not _es_ficha("https://a.com/propiedades/")
    assert _es_ficha("https://a.com/propiedades/casa-tres-dormitorios-rosario")
    assert _es_ficha("https://a.com/propiedades/12345-casa")


def test_wordpress_no_usa_la_query_como_identificador():
    """Un source_listing_id de 200 caracteres con filtros adentro no identifica
    nada: hubo 100 asi."""
    from connectors.wordpress import _id_de
    largo = "https://a.com/p/?sort=newest&" + "x=1&" * 60
    assert len(_id_de(largo)) <= 120
    assert _id_de("https://a.com/propiedades/12345-casa-linda") == "12345"


# ------------------------------------------- compuerta de escritura a la base
def test_la_compuerta_rechaza_todo_lo_que_no_es_una_ficha():
    """Segunda capa: aunque el connector filtre, lo que llega a la base se
    revisa otra vez. Las paginas que se cuelan son siempre las mismas y entran
    porque comparten la ruta con las fichas."""
    from scripts.write_eligibility import motivo_rechazo
    casos = [
        ("https://a.com/buscar-propiedades/?sort=newest", "query_string"),
        ("https://a.com/propiedades/page/3/", "paginacion"),
        ("https://a.com/category/casas/", "categoria_o_tag"),
        ("https://a.com/tag/rosario/", "categoria_o_tag"),
        ("https://a.com/2026/08/", "archivo_por_fecha"),
        ("https://a.com/nosotros/", "institucional"),
        ("https://a.com/feed/", "feed_o_recurso"),
        ("https://a.com/propiedades/", "solo_la_seccion"),
        ("https://a.com/busqueda/casas", "busqueda"),
    ]
    for url, esperado in casos:
        p = {"source_url": url, "source_listing_id": "123"}
        assert motivo_rechazo(p) == esperado, (url, motivo_rechazo(p))


def test_la_compuerta_deja_pasar_una_ficha_de_verdad():
    from scripts.write_eligibility import motivo_rechazo
    assert motivo_rechazo({"source_url": "https://a.com/propiedades/12345-casa",
                           "source_listing_id": "12345"}) is None


def test_un_id_derivado_de_una_query_no_pasa():
    """Hubo 57 propiedades con la query string entera como identificador."""
    from scripts.write_eligibility import motivo_rechazo
    p = {"source_url": "https://a.com/propiedades/casa-linda-rosario",
         "source_listing_id": "?sort=newest&search_status=10&search_city="}
    assert motivo_rechazo(p) == "id_derivado_de_query"


def test_sin_eretz_id_la_propiedad_no_llega_a_la_base():
    """Un id sintetico produciria filas que no pertenecen a ninguna
    inmobiliaria existente, y eso no se nota al insertar: aparece al unir las
    tablas, mucho despues."""
    src = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    assert "AGENCY_ID_PENDING" in src
    assert "eretz_id" in src
    assert "calcular_hash_dedup(real" in src


def test_generico_reconoce_la_ficha_colgada_de_la_raiz():
    """Muchos frontends propios no usan seccion: /8471-venta-casa-3-ambientes-
    en-adrogue. Ni el patron de Tokko ni el de seccion la ven, y la fuente
    quedaba en cero declarando 583 propiedades."""
    from connectors.generico import RE_FICHA_RAIZ
    assert RE_FICHA_RAIZ.search("/8471-venta-casa-3-ambientes-en-adrogue")
    assert RE_FICHA_RAIZ.search("/12345-alquiler-departamento-2-ambientes")
    assert RE_FICHA_RAIZ.search("/9911-venta-terreno-en-saint-thomas")


def test_un_numero_suelto_en_la_raiz_no_es_una_ficha():
    """Sin exigir que el slug diga de que se trata, cualquier ruta con un id
    entraria al inventario."""
    from connectors.generico import RE_FICHA_RAIZ
    assert not RE_FICHA_RAIZ.search("/12345-nuestra-empresa")
    assert not RE_FICHA_RAIZ.search("/2026-balance-anual")
    assert not RE_FICHA_RAIZ.search("/venta-casa-adrogue")


def test_un_404_al_paginar_es_el_final_no_un_fallo():
    """Varias fuentes devuelven 404 al pedir una pagina que ya no existe, en vez
    de una pagina vacia. Sin atraparlo, la excepcion subia y se perdian TODAS
    las propiedades ya enumeradas de esa inmobiliaria: paso con tres."""
    paginas = {"https://alfa.com.ar/": LISTADO,
               "https://alfa.com.ar/Propiedades": LISTADO}
    fallar = {"https://alfa.com.ar/Propiedades?q=&currency=ANY&operation=&p=2":
              B.ErrorPermanente("http 404")}
    c = conector(paginas, fallar)
    f = fuente()
    ids = [a["source_listing_id"] for a in c.fetch_listing(f, c.discover(f))]
    assert ids == ["111", "222"]          # lo enumerado se conserva


def test_un_gzip_truncado_no_tumba_la_descarga():
    """El limite de bytes puede cortar un gzip a la mitad, y decompress levanta
    EOFError, que no es OSError."""
    src = (ROOT / "connectors" / "base.py").read_text(encoding="utf-8")
    assert "except (OSError, EOFError):" in src


def test_el_censo_no_promete_un_conector_sin_inventario_a_la_vista():
    """Detectar la PLATAFORMA no es encontrar el INVENTARIO. Proponer connector
    solo por marcadores de WordPress hizo que 57 fuentes se dieran por
    recuperables y las 57 devolvieran cero: eran paginas institucionales, de
    proyectos o de colegios profesionales, sin fichas."""
    src = (ROOT / "scripts" / "classify_unsupported.py").read_text(encoding="utf-8")
    assert "PLATAFORMA_CONOCIDA_SIN_INVENTARIO" in src
    bloque = src[src.index('out["status"] = ('):src.index("    return out")]
    assert 'out["enumerated_inventory"]' in bloque
    assert 'out["connector_candidato"] = None' in bloque


def test_la_misma_url_bajo_dos_agencias_no_entra_dos_veces():
    """El hash lleva el id de agencia, asi que dos agencias con la MISMA url dan
    hashes distintos y las dos entrarian: dos copias del mismo inmueble bajo
    duenos distintos. El indice unico no las ve porque los hashes difieren."""
    src = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    assert "CROSS_AGENCY_DUPLICATE" in src
    bloque = src[src.index("cruzadas, conservadas"):src.index("elegibles = conservadas")]
    assert "canonical_agency_id" in bloque
    # No se fusiona: la copia descartada queda documentada, no borrada.
    assert "adjudicada_a" in src and "url_en_disputa" in src


def test_el_desempate_usa_evidencia_no_azar():
    """La copia que sobrevive es la de la agencia que la ficha identifica como
    publicante. La regla anterior conservaba la de mayor inventario, que le da
    el aviso a la agencia mas grande sin mirar de quien es."""
    gate = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    assert "aporte = Counter(" not in gate
    resolver = (ROOT / "scripts" / "resolve_cross_agency.py").read_text(encoding="utf-8")
    assert "def dueno_por_ficha" in resolver
    assert "CLEAR_OWNER" in resolver


# ------------------------------------------- resolucion de agencias pendientes
def test_dos_oficinas_de_la_misma_red_no_son_la_misma_inmobiliaria():
    """"Century 21 Di Girolamo" coincidia con "Century 21 MM Real Estate" por
    compartir "century" y "21". Adjudicarle el inventario de una oficina a otra
    es el error mas caro que puede cometer esta resolucion, y no se nota:
    las propiedades quedan bien formadas, en la agencia equivocada."""
    from scripts.resolve_pending_agencies import distintivos, FRANQUICIAS
    assert distintivos("Century 21 Di Girolamo") == {"girolamo"}
    assert distintivos("Century 21 MM Real Estate") == set()
    assert "century" in FRANQUICIAS and "remax" in FRANQUICIAS


def test_el_ruido_del_rubro_no_identifica_a_nadie():
    """Sin sacarlo, "Lopez Propiedades" y "Garcia Propiedades" comparten la
    mitad del nombre."""
    from scripts.resolve_pending_agencies import distintivos
    assert distintivos("Lopez Propiedades") == {"lopez"}
    assert distintivos("Garcia Negocios Inmobiliarios") == {"garcia"}


def test_sin_evidencia_fuerte_no_se_resuelve():
    """Una unica candidata por parecido de nombre no alcanza: hace falta mismo
    dominio o nombre exacto."""
    src = (ROOT / "scripts" / "resolve_pending_agencies.py").read_text(encoding="utf-8")
    assert 'ev & {"mismo_dominio", "nombre_exacto"}' in src
    assert "EXISTING if fuerte else AMBIGUA" in src


def test_ninguna_resolucion_se_aplica_sola():
    """El script clasifica y documenta; no reasigna ninguna propiedad."""
    src = (ROOT / "scripts" / "resolve_pending_agencies.py").read_text(encoding="utf-8")
    assert "No escribe en la base" in src
    for prohibido in ("INSERT", "UPDATE ", "psycopg"):
        assert prohibido not in src


# --------------------------------------------- conflictos entre inmobiliarias
def test_la_adjudicacion_no_se_decide_por_tamano_de_inventario():
    """Adjudicar por cantidad le da el aviso a la agencia mas grande sin mirar
    de quien es. La decide la evidencia de cada ficha."""
    gate = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    assert "aporte = Counter(" not in gate
    assert "CROSS_AGENCY_RESOLUTION" in gate
    assert 'r.get("liberable")' in gate


def test_sin_archivo_de_resolucion_no_se_libera_ningun_conflicto():
    gate = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    bloque = gate[gate.index("resolucion = {}"):gate.index("cruzadas, conservadas")]
    assert "leer(ruta_res)" in bloque       # si no existe, queda vacio


def test_la_ficha_identifica_a_su_oficina_en_century21():
    """En Century 21 el nombre de la oficina viene en `asesor` -"CENTURY 21
    Franchi"- mientras `oficina_c21` trae el nombre de pila del agente. Mirar un
    solo campo dejaba 389 conflictos sin resolver teniendo la respuesta al lado."""
    from scripts.resolve_cross_agency import dueno_por_ficha
    claims = [
        {"provenance": {"agency_name": "C21 Franchi"},
         "extra": {"oficina_c21": "Facundo", "asesor": "CENTURY 21 Franchi"}},
        {"provenance": {"agency_name": "Contacto c21"},
         "extra": {"oficina_c21": "Facundo", "asesor": "CENTURY 21 Franchi"}},
    ]
    dueno, motivo = dueno_por_ficha(claims, "https://century21.com.ar/propiedad/1_x/oficina_133-franchi")
    assert dueno is not None
    assert dueno["provenance"]["agency_name"] == "C21 Franchi"


def test_sin_evidencia_de_dueno_no_se_adjudica():
    from scripts.resolve_cross_agency import dueno_por_ficha
    claims = [{"provenance": {"agency_name": "Alfa Propiedades"}, "extra": {}},
              {"provenance": {"agency_name": "Beta Propiedades"}, "extra": {}}]
    dueno, _ = dueno_por_ficha(claims, "https://alquenia.com/p/1")
    assert dueno is None


def test_una_agencia_duplicada_en_el_padron_no_se_libera_sola():
    """Saber que dos fichas son la misma empresa no dice cual conserva ERETZ, y
    elegir mal deja el inventario colgando de un id que despues se unifica."""
    src = (ROOT / "scripts" / "resolve_cross_agency.py").read_text(encoding="utf-8")
    assert '"liberable": categoria == CLARO' in src
    assert "AGENCY_DUPLICATE_RESOLUTION_MANIFEST" in src


def test_ningun_claim_se_borra():
    """Los reclamos secundarios se documentan con su evidencia, no se pierden."""
    src = (ROOT / "scripts" / "write_eligibility.py").read_text(encoding="utf-8")
    assert "categoria_conflicto" in src and "adjudicada_a" in src


def test_el_write_set_no_puede_tener_una_url_dos_veces():
    ruta = Path(r"D:\INMO CAPITAL\DB_WRITE_ELIGIBLE.jsonl")
    if not ruta.exists():
        pytest.skip("todavia no se genero el write set")
    urls, hashes = [], []
    for l in ruta.open(encoding="utf-8"):
        if l.strip():
            d = json.loads(l)
            urls.append(d["source_url"])
            hashes.append(d["hash_dedup"])
    assert len(urls) == len(set(urls))
    assert len(hashes) == len(set(hashes))


# ------------------------------------------------- directorio de plataformas
def test_el_directorio_fusiona_todas_las_corridas():
    """Preferir la corrida mas reciente esconde lo que una corrida a medias
    todavia no proceso: con la segunda en curso, 511 fuentes Tokko ya
    terminadas figuraban como no intentadas."""
    src = (ROOT / "scripts" / "build_platform_directory.py").read_text(encoding="utf-8")
    bloque = src[src.index("corridas = sorted"):src.index("filas = []")]
    # Se recorren todas las corridas, y la que gana es la que trajo inventario,
    # no la ultima.
    assert "for corrida in corridas" in bloque
    assert 'previo.get("enumeradas", 0) >= (r.get("enumeradas") or 0)' in bloque


def test_las_propiedades_no_se_cuentan_dos_veces():
    """Sumar las dos corridas contaria cada propiedad dos veces: se usa la mas
    completa."""
    src = (ROOT / "scripts" / "build_platform_directory.py").read_text(encoding="utf-8")
    assert "mejor, n = None, -1" in src
    assert "if len(filas_p) > n:" in src


def test_la_plataforma_se_decide_por_la_evidencia_mas_fuerte():
    """Que un connector haya enumerado inventario vale mas que un marcador del
    HTML: el primero es un hecho, el segundo una pista."""
    src = (ROOT / "scripts" / "build_platform_directory.py").read_text(encoding="utf-8")
    i_roll = src.index('"el connector enumero inventario"')
    i_html = src.index('"marcadores del HTML"')
    assert i_roll < i_html


def test_el_directorio_reconcilia_su_propio_universo():
    """Un resumen truncado no es un detalle de presentacion: las categorias
    dejaban de sumar el universo y parecia que faltaban 114 agencias cuando lo
    que faltaba eran 21 categorias chicas que el top no imprimia."""
    ruta = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    if not ruta.exists():
        pytest.skip("todavia no se genero el directorio")
    filas = [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]
    total = len(filas)
    assert total == len({f["canonical_agency_id"] for f in filas})
    from collections import Counter as C
    assert sum(C(f["platform"] for f in filas).values()) == total
    assert sum(C(f["connector_status"] for f in filas).values()) == total
    assert all(f.get("platform") and f.get("connector_status") for f in filas)


def test_el_resumen_no_esconde_categorias():
    """Lo que no entra en el top se agrega como "otras N", con su cuenta."""
    src = (ROOT / "scripts" / "build_platform_directory.py").read_text(encoding="utf-8")
    assert "RECONCILIACION" in src
    assert "otras " in src and "cuenta_plat.most_common()[14:]" in src


# ------------------------------------------- formato del checkpoint
def test_un_cambio_de_formato_no_se_disfraza_de_bajas(tmp_path):
    """La clave de `vistos` paso de source_listing_id a hash_dedup. Comparar
    formatos distintos hizo aparecer 19.001 propiedades como ausentes de golpe.
    Una corrida contra un checkpoint viejo vale como linea base."""
    ruta = tmp_path / "cp.json"
    ruta.write_text(json.dumps({"fuentes": {"ag-1": {
        "vistos": {"7987": "abc", "7980": "def"}, "corridas": 1,
        "ausencias": {}, "ultima_pagina": 0, "completa": True}}}), encoding="utf-8")
    cp = B.Checkpoint(ruta)
    est = cp.de("ag-1")
    assert est["linea_base"] is True
    assert est["vistos"] == {}
    assert est["vistos_previos_descartados"] == 2
    c = conector(cp=cp)
    assert c.identify_deleted_or_inactive(fuente(), set(), True) == []


def test_un_checkpoint_del_formato_actual_si_compara(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    p = norm()
    c.registrar(f, p)
    cp.guardar()
    cp2 = B.Checkpoint(tmp_path / "cp.json")
    assert cp2.de("ag-1").get("linea_base") is not True
    assert conector(cp=cp2).registrar(f, norm()) == "SIN_CAMBIOS"


def test_la_huella_del_codigo_se_fija_al_arrancar():
    """Una corrida que empezo antes de una edicion seguia usando el codigo viejo
    en memoria pero reportaba la huella del archivo ya editado: las dos corridas
    parecian iguales cuando no lo eran."""
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    assert "_VERSION_AL_ARRANCAR" in src
    assert "version_del_codigo(a.connector)" in src


# ----------------------------------------- web propia vs perfil en un portal
def test_un_perfil_en_un_portal_no_es_la_web_de_la_inmobiliaria():
    """Contar fichas de todoprops o exhibidores de construex como web oficial
    infla "agencias con web" con paginas de terceros, y despues alguien lee ese
    numero como cobertura."""
    from scripts.reclassify_portal_profiles import clasificar
    for url in ("https://www.todoprops.com/inmobiliarias/inmobiliaria/alvarez",
                "https://www.construex.com.ar/exhibidores/atenea",
                "https://www.realestate.com.au/international/ar/lafinur",
                "https://www.zonaprop.com.ar/inmobiliarias/alfa",
                "https://www.facebook.com/alfapropiedades"):
        tipo, _ = clasificar(url)
        assert tipo == "EXTERNAL_PORTAL_PROFILE", url


def test_la_pagina_de_la_oficina_en_su_red_no_es_un_portal_ajeno():
    """Century 21 o RE/MAX son la casa de la oficina dentro de su franquicia:
    no es un dominio propio, pero tampoco un marketplace de terceros."""
    from scripts.reclassify_portal_profiles import clasificar
    for url in ("https://century21.com.ar/v/oficina/68-revolution",
                "https://remax-urbana.com.ar/propiedades/1"):
        assert clasificar(url)[0] == "OFFICIAL_OFFICE_PAGE", url


def test_un_dominio_propio_sigue_siendo_web_oficial():
    from scripts.reclassify_portal_profiles import clasificar
    for url in ("https://www.aagaard.com.ar/", "https://abppropiedades.com.ar"):
        assert clasificar(url)[0] == "OFFICIAL_WEB", url


def test_una_coordenada_sin_signo_no_es_argentina():
    """Argentina esta entera en el hemisferio sur y oeste. Con el menos
    opcional, el patron de WordPress tomaba pares como "50.774, 50.7708" -que
    no son coordenadas de nada- y ubicaba 752 propiedades fuera del pais."""
    fuente = (ROOT / "connectors" / "wordpress.py").read_text(encoding="utf-8")
    assert r"(-?[23456]\d\.\d{3,})" not in fuente
    assert r"(-[23456]\d\.\d{3,})" in fuente

    import re as _re
    patron = _re.compile(r"(-[23456]\d\.\d{3,})[\",\s]+(-[567]\d\.\d{3,})")
    assert patron.search('"-34.6037","-58.3816"')
    assert patron.search("-31.4201, -64.1888")
    assert not patron.search("50.774, 50.7708")
    assert not patron.search('"34.6037","58.3816"')
    # Y el par que ubicaba propiedades en Polonia deja de tomarse.
    assert not patron.search('"lat":"50.774","lng":"50.7708"')


def test_dos_enumeraciones_que_no_se_pisan_no_son_cien_bajas(tmp_path):
    """pitton.net enumero 5 propiedades en una corrida y otras 5 completamente
    distintas en la siguiente, sin declarar total: es el carrusel de destacados
    de la home, que Tokko rota. Contarlo como bajas daria de baja el catalogo
    entero de esa inmobiliaria en tres corridas sin que se cayera un aviso."""
    ck = B.Checkpoint(tmp_path / "ck.json")
    con = B.Connector(checkpoint=ck)
    f = B.Fuente(canonical_agency_id="a", agency_name="A",
                 official_url="https://a.com", inmobiliaria_id=1)
    est = ck.de("a")
    est["vistos"] = {f"h{i}": "fp" for i in range(5)}

    # Conjunto totalmente distinto: no es comparable, no cuenta.
    aus = con.identify_deleted_or_inactive(f, {f"n{i}" for i in range(5)},
                                           fuente_respondio=True)
    assert len(aus) == 5
    assert all(a["ausencias_consecutivas"] == 0 for a in aus)
    assert all(a["enumeracion_comparable"] is False for a in aus)
    assert all(a["estado"] == "SIN_EVIDENCIA_FUENTE_CAIDA" for a in aus)


def test_una_baja_real_sigue_contando():
    """El resguardo no puede tapar la baja de verdad: si el resto del
    inventario sigue ahi, la que falta cuenta."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ck = B.Checkpoint(Path(tmp) / "ck.json")
        con = B.Connector(checkpoint=ck)
        f = B.Fuente(canonical_agency_id="a", agency_name="A",
                     official_url="https://a.com", inmobiliaria_id=1)
        ck.de("a")["vistos"] = {f"h{i}": "fp" for i in range(10)}
        vistos = {f"h{i}" for i in range(10)} - {"h3"}
        aus = con.identify_deleted_or_inactive(f, vistos, fuente_respondio=True)
        assert [a["hash_dedup"] for a in aus] == ["h3"]
        assert aus[0]["ausencias_consecutivas"] == 1
        assert aus[0]["enumeracion_comparable"] is True


def test_canonicalizar_la_url_no_puede_producir_bajas_falsas():
    """El runner arma el conjunto "visto ahora" con la url ENUMERADA, pero el
    checkpoint guarda la clave de la url que devolvio normalize. Un connector
    que canonicaliza -Wasi sirve la misma propiedad bajo dos slugs- hacia que
    esas dos claves no coincidieran: 33 bajas falsas en la primera corrida de
    una sola fuente. Se comparan las dos formas."""
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    bloque = src[src.index("# --- ausencias"):src.index("identify_deleted_or_inactive")]
    assert "vistos |= {p.hash_dedup for p in objetos}" in bloque


# --------------------------------------- estabilidad de la huella de contenido
def _prop(**kw):
    base = dict(canonical_agency_id="x", source_listing_id="1",
                source_url="https://x.com/p/1", connector="tokko", precio=100.0)
    base.update(kw)
    return B.PropiedadNormalizada(**base)


def test_reordenar_la_descripcion_no_es_un_cambio():
    """Tokko arma la lista de servicios sin orden fijo: "Cloaca Internet" en un
    pedido y "Internet Cloaca" en el siguiente, mismas palabras y mismo largo.
    Como la descripcion entra en la huella, una propiedad sin tocar volvia
    MODIFICADA. Fue el 2,4% de un canary; a escala de 91.715 son ~2.200 cambios
    falsos por corrida, y MODIFICADA deja de significar nada."""
    a = _prop(descripcion="Cocina Cloaca Internet Calefaccion")
    b = _prop(descripcion="Internet Calefaccion Cocina Cloaca")
    assert a.fingerprint == b.fingerprint


# --------------------------------- fotos de la pagina vs fotos de la propiedad
def _con_fotos(i, imgs):
    return B.PropiedadNormalizada(
        canonical_agency_id="a", source_listing_id=str(i),
        source_url=f"https://a.com/p/{i}", connector="t", imagenes=imgs)


def test_el_icono_del_telefono_no_es_una_foto_de_la_propiedad():
    """El chinche del mapa, el icono del telefono y el boton de Pinterest salen
    en todas las fichas del sitio. Medido sobre las 18.474 propiedades de
    WordPress: 91.836 referencias de imagen -el 15,8%- eran esto. Ademas hacian
    ruido en el incremental, porque el sitio las rota y cada rotacion se leia
    como que la propiedad habia cambiado de fotos."""
    from scripts.run_rollout import descartar_imagenes_compartidas
    objs = [_con_fotos(i, [f"foto{i}.jpg", "https://a.com/ico-tel.png",
                           "https://pinterest.com/pin/create/button/"])
            for i in range(10)]
    assert descartar_imagenes_compartidas(objs) == 20
    assert objs[0].imagenes == ["foto0.jpg"]


def test_no_se_juzga_a_una_agencia_con_pocas_propiedades():
    """Con tres avisos del mismo edificio, la fachada compartida no es un
    icono."""
    from scripts.run_rollout import descartar_imagenes_compartidas
    objs = [_con_fotos(i, [f"f{i}.jpg", "https://a.com/comun.png"]) for i in range(5)]
    assert descartar_imagenes_compartidas(objs) == 0
    assert objs[0].imagenes == ["f0.jpg", "https://a.com/comun.png"]


def test_una_foto_compartida_por_pocas_propiedades_se_conserva():
    """Tres departamentos del mismo edificio pueden compartir la fachada. El
    umbral es la mitad del catalogo, no cualquier repeticion."""
    from scripts.run_rollout import descartar_imagenes_compartidas
    objs = [_con_fotos(i, [f"f{i}.jpg"] + (["fachada.jpg"] if i < 3 else []))
            for i in range(10)]
    assert descartar_imagenes_compartidas(objs) == 0
    assert "fachada.jpg" in objs[0].imagenes


def test_una_foto_es_una_foto_no_cuatro():
    """WordPress genera una copia por cada tamano que usa el tema. El 30% de las
    "fotos" eran variantes de la misma imagen: 146.876 entradas de mas en 9.672
    propiedades. Una que figuraba con 40 fotos solia tener diez."""
    from connectors.wordpress import _sin_variantes_de_tamano as colapsar
    urls = ["https://x.com/a-120x72.jpg", "https://x.com/a-768x1024.jpg",
            "https://x.com/a.jpg", "https://x.com/b-224x140.png",
            "https://x.com/b-800x600.png", "https://x.com/c.webp"]
    r = colapsar(urls)
    assert r == ["https://x.com/a.jpg",        # la original gana sobre cualquier tamano
                 "https://x.com/b-800x600.png",  # sin original, la mas grande
                 "https://x.com/c.webp"]


def test_colapsar_variantes_no_toca_fotos_distintas():
    """Tokko y el generico no usan variantes: el patron no puede tocarlos."""
    from connectors.wordpress import _sin_variantes_de_tamano as colapsar
    urls = ["https://static.tokkobroker.com/pictures/8636261_abc.jpg",
            "https://static.tokkobroker.com/pictures/8636261_def.jpg",
            "https://x.com/casa-2026.jpg"]
    assert colapsar(urls) == urls


def test_el_recorte_de_fotos_elige_siempre_las_mismas():
    """El 47% de las propiedades de WordPress llegan al tope de 40 y la fuente
    no devuelve la cola en el mismo orden: el subconjunto elegido cambiaba entre
    corridas y se leia como cambio de fotos. La primera si es estable -99,9%- y
    se respeta como principal."""
    urls = [f"foto{i:02}.jpg" for i in range(50)]
    a = B.recorte_estable_de_imagenes(urls, 40)
    # La misma lista en otro orden (salvo la principal) da el MISMO recorte.
    revuelto = [urls[0]] + list(reversed(urls[1:]))
    b = B.recorte_estable_de_imagenes(revuelto, 40)
    assert a == b
    assert len(a) == 40
    assert a[0] == "foto00.jpg"


def test_si_no_llega_al_tope_no_se_toca_el_orden():
    urls = ["principal.jpg", "z.jpg", "a.jpg"]
    assert B.recorte_estable_de_imagenes(urls, 40) == urls


def test_el_filtro_corre_antes_de_calcular_la_huella():
    """Si corriera despues, el checkpoint compararia contra una version de la
    propiedad que no existe en el artefacto."""
    src = (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8")
    i_filtro = src.index("descartar_imagenes_compartidas(objetos)")
    i_registrar = src.index("cambio = con.registrar(fuente, p)")
    assert i_filtro < i_registrar


def test_cambiar_la_formula_de_la_huella_no_es_un_cambio_comercial(tmp_path):
    """Paso dos veces: al cambiar que entra en la huella, el checkpoint anterior
    deja de ser comparable y TODO vuelve MODIFICADA -499 de 500 en una muestra
    real- sin que cambiara una letra. Con la version adentro esa corrida se
    informa como incompatible y la siguiente ya compara bien."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    p = norm()
    assert c.registrar(f, p) == "NUEVA"
    assert c.registrar(f, p) == "SIN_CAMBIOS"

    # Alguien cambia la formula: la huella guardada quedo con la version vieja.
    cp.de("ag-1")["huella_version"] = B.HUELLA_VERSION - 1
    c2 = conector(cp=cp)          # corrida nueva: connector nuevo
    assert c2.registrar(f, p) == B.BASELINE_INCOMPATIBLE
    # Y la corrida siguiente vuelve a comparar de verdad.
    assert conector(cp=cp).registrar(f, p) == "SIN_CAMBIOS"


def test_la_incompatibilidad_vale_para_TODA_la_fuente(tmp_path):
    """Se decide una vez por fuente. Leyendola del checkpoint en cada propiedad,
    la primera lo sella con la version nueva y las demas ya lo ven al dia: una
    corrida real informo 1 BASELINE_INCOMPATIBLE y 372 MODIFICADA cuando las 373
    eran el mismo cambio de version."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    f = fuente()
    est = cp.de("ag-1")
    est["huella_version"] = B.HUELLA_VERSION - 1
    est["vistos"] = {f"h{i}": "vieja" for i in range(5)}

    c = conector(cp=cp)
    salidas = []
    for i in range(5):
        p = norm()
        # Cada propiedad con su propia clave, como en una fuente real.
        object.__setattr__(p, "source_url", f"https://x.com/p/{i}")
        est["vistos"][p.hash_dedup] = "vieja"
        salidas.append(c.registrar(f, p))
    assert set(salidas) == {B.BASELINE_INCOMPATIBLE}, salidas


def test_la_huella_viaja_con_su_version_en_el_artefacto():
    """Sin la version guardada, una comparacion futura no puede distinguir
    "cambio el contenido" de "cambio la formula"."""
    d = norm().a_dict()
    assert d["fingerprint_version"] == B.HUELLA_VERSION


def test_la_fecha_que_declara_el_sitio_no_es_contenido():
    """WordPress mueve `modified` cuando re-guarda los posts en masa: 1.618
    propiedades cambiaron esa fecha entre dos corridas -varias con el mismo
    04:00:29, o sea un cron- sin que cambiara una letra del aviso. Con ella
    adentro, MODIFICADA pasa a significar "el sitio corrio su tarea nocturna"."""
    a = _prop(extra={"modificado_en_fuente": "2026-08-21T01:02:18", "cocheras": 1})
    b = _prop(extra={"modificado_en_fuente": "2026-08-24T04:00:29", "cocheras": 1})
    assert a.fingerprint == b.fingerprint
    # Pero un dato de verdad dentro de `extra` si cuenta.
    c = _prop(extra={"modificado_en_fuente": "2026-08-21T01:02:18", "cocheras": 2})
    assert a.fingerprint != c.fingerprint


def test_reordenar_las_fotos_tampoco():
    a = _prop(imagenes=["a.jpg", "b.jpg", "c.jpg"])
    b = _prop(imagenes=["c.jpg", "a.jpg", "b.jpg"])
    assert a.fingerprint == b.fingerprint


def test_pero_agregar_o_sacar_texto_si_es_un_cambio():
    """Si la huella se volviera ciega al contenido, el incremental dejaria de
    detectar ediciones reales, que es lo unico para lo que existe."""
    a = _prop(descripcion="Cocina Cloaca Internet")
    assert a.fingerprint != _prop(descripcion="Cocina Cloaca Internet Pileta").fingerprint
    assert a.fingerprint != _prop(descripcion="Cocina Cloaca").fingerprint
    assert a.fingerprint != _prop(descripcion="Cocina Cloaca Internet",
                                  precio=120.0).fingerprint
    assert a.fingerprint != _prop(descripcion="Cocina Cloaca Internet",
                                  imagenes=["a.jpg"]).fingerprint


def test_el_directorio_descubre_las_corridas_en_vez_de_listarlas():
    """Estaba fijo en ("1","2"): apenas aparecio una corrida 3 el directorio
    dejo de verla en silencio, que es exactamente el error que su propio
    comentario dice evitar."""
    src = (ROOT / "scripts" / "build_platform_directory.py").read_text(encoding="utf-8")
    assert 'for corrida in ("1", "2")' not in src
    assert 'base.glob("source_inventory_run*.jsonl")' in src


def test_regenerar_el_directorio_no_borra_la_reclasificacion():
    """El directorio se reconstruye fila por fila desde cero. Si la
    clasificacion de la url no se recalcula ahi, la regeneracion siguiente la
    pierde en silencio y "agencias con web propia" vuelve de 2.259 a 2.596,
    contando paginas de terceros como cobertura."""
    import importlib.util
    ruta = ROOT / "scripts" / "build_platform_directory.py"
    spec = importlib.util.spec_from_file_location("build_platform_directory", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "clasificar_web")
    assert mod.clasificar_web("https://www.todoprops.com/x")[0] == \
        "EXTERNAL_PORTAL_PROFILE"
    assert mod.clasificar_web("https://bartuccipropiedades.com")[0] == "OFFICIAL_WEB"
    # Y la fila que arma tiene que llevar el campo, no solo saber calcularlo.
    assert '"web_kind": tipo_web' in ruta.read_text(encoding="utf-8")


def test_la_reclasificacion_conserva_la_evidencia():
    """No se borran: son evidencia de que la inmobiliaria existe y opera, y
    sirven para buscar su sitio propio mas adelante."""
    ruta = Path(r"D:\INMO CAPITAL\PORTAL_RECLASSIFICATION.jsonl")
    if not ruta.exists():
        pytest.skip("todavia no se genero")
    filas = [json.loads(l) for l in ruta.open(encoding="utf-8") if l.strip()]
    assert filas
    for f in filas[:20]:
        assert f["url"] and f["host"] and f["motivo"]
        assert f["clasificacion_nueva"] in ("EXTERNAL_PORTAL_PROFILE",
                                            "OFFICIAL_OFFICE_PAGE")

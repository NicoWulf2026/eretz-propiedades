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
def test_una_sola_ausencia_no_da_de_baja(tmp_path):
    """Un 502 de diez minutos daria de baja el catalogo entero de golpe."""
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    c.registrar(f, norm())
    r = c.identify_deleted_or_inactive(f, set(), fuente_respondio=True)
    assert r[0]["estado"] == "AUSENTE_PROVISORIA"


def test_recien_a_las_tres_ausencias_seguidas_se_confirma(tmp_path):
    cp = B.Checkpoint(tmp_path / "cp.json")
    c = conector(cp=cp)
    f = fuente()
    c.registrar(f, norm())
    for _ in range(B.AUSENCIAS_PARA_BAJA):
        r = c.identify_deleted_or_inactive(f, set(), fuente_respondio=True)
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

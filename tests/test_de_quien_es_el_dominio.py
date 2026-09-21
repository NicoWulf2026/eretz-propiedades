# -*- coding: utf-8 -*-
"""Los casos reales donde contar menciones se equivocaba.

Cada test con nombre `MUERDE` es una url de las 15 pendientes. Si el criterio
del dominio no los resuelve, no sirve de nada: son exactamente los que el
intento anterior no pudo.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from scripts.de_quien_es_el_dominio import (  # noqa: E402
    DE_NADIE, DUENA, PARA_REVISAR, dictaminar, etiqueta_del_dominio, pajar,
    tokens_propios)


def test_MUERDE_remax_net_es_de_remax_net_y_no_de_remax_star():
    """El error mas claro del detector anterior: eligio `remax star`."""
    fallo = dictaminar("https://remax-net.com.ar", {
        "roomix:remax net": "RE/MAX Net",
        "roomix:remax star": "RE/MAX Star"})
    assert fallo["veredicto"] == DUENA
    assert fallo["duena"] == "roomix:remax net"
    assert fallo["retirar_de"] == ["roomix:remax star"]


def test_MUERDE_rodriguez_jurado_lo_decide_la_palabra_que_no_comparten():
    """Doce menciones cada una: el conteo empataba. `jurado` no empata."""
    fallo = dictaminar("https://rodriguezjurado.com.ar", {
        "roomix:rodriguez jurado propiedades": "Rodríguez Jurado Propiedades",
        "roomix:maqueira rodriguez propiedades": "Maqueira Rodríguez Propiedades"})
    assert fallo["duena"] == "roomix:rodriguez jurado propiedades"


def test_MUERDE_con_duena_la_url_se_le_retira_a_todas_las_demas():
    """Aunque la perdedora toque el dominio: `maqueira RODRIGUEZ` lo toca.

    Dejarsela mantiene armada la mina entera -dos agencias enumerando el
    mismo catalogo- que es justo lo que esto vino a desactivar. Que haya
    duena decidida es la condicion; el resto no conserva nada.
    """
    fallo = dictaminar("https://rodriguezjurado.com.ar", {
        "roomix:rodriguez jurado propiedades": "Rodríguez Jurado Propiedades",
        "roomix:maqueira rodriguez propiedades": "Maqueira Rodríguez Propiedades"})
    assert fallo["detalle"]["roomix:maqueira rodriguez propiedades"]["toca"]
    assert fallo["retirar_de"] == ["roomix:maqueira rodriguez propiedades"]


def test_MUERDE_el_ordinal_separa_dos_oficinas_de_la_misma_red():
    """`re max urbana` y `remax urbana iii` se diferencian solo en el `iii`.

    Sin contar el ordinal como token propio las dos explican el dominio y el
    grupo queda en revision para siempre.
    """
    fallo = dictaminar("https://www.remax-urbana.com.ar", {
        "roomix:re max urbana": "RE/MAX Urbana",
        "roomix:remax urbana iii": "RE/MAX Urbana III",
        "roomix:re max actitud": "RE/MAX Actitud",
        "roomix:re max time": "RE/MAX Time"})
    assert fallo["duena"] == "roomix:re max urbana"
    # Decidida la duena, las otras tres pierden la url — incluida `urbana iii`,
    # que toca el dominio pero no lo explica.
    assert fallo["retirar_de"] == ["roomix:re max actitud", "roomix:re max time",
                                   "roomix:remax urbana iii"]


def test_MUERDE_century21_identifica_la_oficina_por_la_ruta():
    """El host es de la franquicia; lo que nombra a la oficina es la ruta."""
    fallo = dictaminar(
        "https://century21.com.ar/v/oficina/133-franchi-la-plata-gba-sur-argentina",
        {"roomix:c21 franchi": "C21 Franchi",
         "roomix:contacto c21": "Contacto C21"})
    assert fallo["duena"] == "roomix:c21 franchi"


def test_MUERDE_fuera_de_una_plataforma_la_ruta_no_decide():
    """`urbanorosario.com.ar/servicios` no es de `servicios inmobiliarios`.

    Si la ruta contara, `/servicios` le daria el sitio a la agencia
    equivocada. El host ya es de alguien y eso manda.
    """
    fallo = dictaminar(
        "https://urbanorosario.com.ar/servicios",
        {"roomix:urbano inmobiliaria arquitectura": "Urbano Inmobiliaria Arquitectura",
         "roomix:servicios inmobiliarios rosario": "Servicios Inmobiliarios Rosario"},
        {"roomix:urbano inmobiliaria arquitectura": ["Rosario", "Santa Fe"],
         "roomix:servicios inmobiliarios rosario": ["Rosario", "Santa Fe"]})
    assert fallo["duena"] == "roomix:urbano inmobiliaria arquitectura"
    assert fallo["retirar_de"] == ["roomix:servicios inmobiliarios rosario"]


def test_MUERDE_un_directorio_no_es_de_ninguna():
    """`inmobiliariabertero` no es ni `arias` ni `dic`: no es de ellas."""
    fallo = dictaminar(
        "https://inmobiliariabertero.com.ar/provincia-de-buenos-aires/san-isidro",
        {"roomix:arias propiedades": "Arias Propiedades",
         "roomix:dic propiedades s a": "DIC Propiedades S.A."})
    assert fallo["veredicto"] == DE_NADIE
    assert fallo["duena"] is None
    assert fallo["retirar_de"] == ["roomix:arias propiedades",
                                   "roomix:dic propiedades s a"]


def test_MUERDE_dos_agencias_con_el_mismo_apellido_quedan_en_revision():
    """`leiva inmobiliaria` y `leiva propiedades` sobre `inmobiliarialeiva`.

    Es un empate real. Inventar un ganador aca seria exactamente lo que este
    trabajo vino a impedir.
    """
    fallo = dictaminar("https://www.inmobiliarialeiva.com.ar", {
        "roomix:leiva inmobiliaria": "Leiva Inmobiliaria",
        "roomix:leiva propiedades": "Leiva Propiedades"})
    assert fallo["veredicto"] == PARA_REVISAR
    assert fallo["duena"] is None
    assert fallo["retirar_de"] == []


def test_la_cobertura_desempata_cuando_una_explica_mas_del_dominio():
    """`jmizrahi`: `j mizrahi` lo explica entero, `mizrahi` solo una parte."""
    fallo = dictaminar("https://www.jmizrahi.com.ar", {
        "roomix:j mizrahi negocios inmobiliarios": "J. Mizrahi Negocios Inmobiliarios",
        "roomix:mizrahi real estate": "Mizrahi Real Estate"})
    assert fallo["duena"] == "roomix:j mizrahi negocios inmobiliarios"
    assert "cubre estrictamente mas" in fallo["motivo"]


def test_una_agencia_que_no_toca_el_dominio_se_retira_igual():
    """Aunque el grupo quede sin duena, esto si se puede afirmar.

    Es lo que desactiva la mina: dos oficinas enumerando el mismo catalogo.
    """
    fallo = dictaminar("https://remax-premium.com.ar", {
        "roomix:remax premium ii": "RE/MAX Premium II",
        "roomix:re max estilo": "RE/MAX Estilo"})
    assert fallo["veredicto"] == PARA_REVISAR
    assert fallo["retirar_de"] == ["roomix:re max estilo"]


def test_MUERDE_las_palabras_de_la_red_no_distinguen_oficinas():
    """Todas las oficinas llevan `remax`. Si contara, todas explicarian todo."""
    assert tokens_propios("RE/MAX Parque") == ["parque"]
    assert tokens_propios("C21 Franchi") == ["franchi"]
    assert tokens_propios("Rodríguez Jurado Propiedades") == ["rodriguez", "jurado"]


def test_MUERDE_un_apellido_que_tambien_es_una_ciudad_sigue_distinguiendo():
    """Zarate, Rodriguez y Martinez son ciudades Y apellidos.

    El primer intento descarto todo nombre de lugar del catalogo de GeoRef y
    se llevo puesto justo lo que distingue: `rodriguezjurado` se quedaba sin
    `rodriguez`. Lo que no distingue es la geografia DE ESA agencia, no la
    geografia en general.
    """
    assert tokens_propios("Zárate Gestión Inmobiliaria") == ["zarate"]
    assert tokens_propios("Rodríguez Jurado Propiedades") == ["rodriguez", "jurado"]
    # La misma palabra deja de distinguir cuando es donde esta registrada.
    assert tokens_propios("Zárate Propiedades", ["Zárate"]) == []


def test_un_nombre_hecho_solo_de_su_ciudad_no_explica_ningun_dominio():
    """No es un bug: ese nombre no la distingue de las otras de su ciudad."""
    assert tokens_propios("Rosario Propiedades", ["Rosario"]) == []


def test_la_etiqueta_del_dominio_junta_guiones_y_saca_sufijos():
    assert etiqueta_del_dominio("https://www.remax-net.com.ar/x?y=1") == "remaxnet"
    assert etiqueta_del_dominio("grupoplatino.com.ar") == "grupoplatino"
    assert etiqueta_del_dominio("https://proppies.app") == "proppies"


def test_el_pajar_ignora_la_ruta_salvo_en_plataformas():
    assert pajar("https://urbanorosario.com.ar/servicios") == "urbanorosario"
    assert "franchi" in pajar("https://century21.com.ar/v/oficina/133-franchi-la-plata")


def test_una_sola_candidata_que_no_toca_el_dominio_no_se_vuelve_duena():
    """Quedarse sola no es evidencia de nada."""
    fallo = dictaminar("https://crsargentina.com.ar", {
        "roomix:marcos wolberg propiedades": "Marcos Wolberg Propiedades"})
    assert fallo["veredicto"] == DE_NADIE
    assert fallo["duena"] is None


def test_un_grupo_sin_candidatas_no_explota():
    fallo = dictaminar("https://algo.com.ar", {})
    assert fallo["veredicto"] == DE_NADIE
    assert fallo["retirar_de"] == []


def test_los_acentos_no_impiden_reconocer_el_dominio():
    fallo = dictaminar("https://zaratepropiedades.com", {
        "roomix:zarate gestion": "Zárate Gestión Inmobiliaria",
        "roomix:otra": "Otra Cosa"})
    assert fallo["duena"] == "roomix:zarate gestion"


def test_la_cobertura_no_cuenta_dos_veces_el_mismo_pedazo():
    """`rodriguez` y `rodrig` se solapan: cubren nueve caracteres, no quince."""
    fallo = dictaminar("https://rodriguez.com.ar", {
        "roomix:x": "Rodriguez Rodrig"})
    assert fallo["detalle"]["roomix:x"]["cobertura"] == 9


def test_MUERDE_www_no_distingue_dos_sitios():
    """`crecer.com.ar` y `www.crecer.com.ar` son el mismo sitio.

    Sin plegar `www`, dos agencias apuntando al MISMO sitio no aparecen como
    url compartida: se esconden en la detección por host, que es la categoría
    menos grave —ahí cada una tiene su ruta y nadie se pisa, y éstas sí se
    pisan—. Eran cuatro grupos: `crecer.com.ar`, `red-inmobiliaria.com.ar`,
    `bustamantepropiedades.com` e `inmobiliariafotheringham.com.ar`.

    Y la herramienta de retiro tenía el mismo hueco: retiraba
    `https://crecer.com.ar`, dejaba intacta `https://www.crecer.com.ar/` y
    después informaba que no quedaba ninguna url compartida. Las dos
    normalizaciones tienen que plegar igual o una retira lo que la otra no ve.
    """
    import sys as _sys
    _sys.path.insert(0, str(RAIZ / "scripts"))
    from scripts.fuentes_compartidas import normalizar as n_detectar
    from scripts.retirar_fuente_compartida import normalizar as n_retirar
    for con, sin in (("https://www.crecer.com.ar/", "https://crecer.com.ar"),
                     ("https://WWW.Red-Inmobiliaria.com.ar", "https://red-inmobiliaria.com.ar"),
                     ("https://www.x.com/a/b", "https://x.com/a/b")):
        assert n_detectar(con) == n_detectar(sin), con
        assert n_retirar(con) == n_retirar(sin), con
        # Y las dos herramientas tienen que coincidir entre si.
        assert n_detectar(con) == n_retirar(con), con


def test_un_host_que_empieza_con_wwwalgo_no_se_recorta():
    """`wwwalgo.com` no es `algo.com`: el prefijo se saca con el punto."""
    from scripts.fuentes_compartidas import normalizar
    assert normalizar("https://wwwalgo.com") == "https://wwwalgo.com"
    assert "wwwalgo" in normalizar("https://wwwalgo.com/x")


# ---------------------------------------------------------------------------
# El titulo como segunda instancia, cuando el dominio no alcanza.
#
# El 2026-09-21 el dictamen por dominio marco 34 fuentes que «no nombran a la
# agencia» y varias eran abreviaturas legitimas. El titulo las resuelve, y
# resolvio las dos unicas que habian llegado a CERTIFIED_COMPLETE.

from scripts.de_quien_es_el_dominio import (el_titulo_la_nombra,  # noqa: E402
                                            titulo_de)


def test_titulo_de_saca_el_titulo_aplanado():
    assert titulo_de("<html><head><title>  Hola\n  Mundo </title></head>") == "Hola Mundo"
    assert titulo_de("<title lang='es'>Con <b>marcado</b></title>") == "Con marcado"


def test_sin_titulo_no_hay_titulo():
    assert titulo_de("<html><body>nada</body></html>") == ""
    assert titulo_de("") == ""


def test_MUERDE_el_caso_abril_abreviatura_legitima():
    """`ventasprop.com` no nombra a la agencia y es suyo: el titulo lo dice."""
    assert el_titulo_la_nombra(
        "Abril Negocios Inmobiliarios en venta y alquiler - Propiedades",
        "ABRiL Negocios Inmobiliarios") is True


def test_MUERDE_el_caso_fandino():
    assert el_titulo_la_nombra(
        "Fandino Propiedades - Inmobiliarias Banfield - Alquiler y Venta",
        "FANDINO PROPIEDADES") is True


def test_MUERDE_un_directorio_no_se_titula_con_el_nombre_de_la_agencia():
    """La diferencia con el intento viejo que fallo: un directorio nombra a
    docenas de agencias en su CUERPO y a ninguna en su TITULO."""
    assert el_titulo_la_nombra(
        "Empresas de Cordoba - Guia comercial de la provincia",
        "Cerro Inmobiliaria") is False


def test_MUERDE_sin_titulo_devuelve_None_y_no_False():
    """Sin evidencia no se afirma nada. Un `False` aca haria que una pagina
    sin titulo se leyera como «no es suya», que es inventar."""
    assert el_titulo_la_nombra("", "Cerro Inmobiliaria") is None


def test_un_nombre_sin_tokens_propios_no_decide():
    """`Inmobiliaria Propiedades` no tiene ninguna palabra que distinga: no se
    puede concluir nada del titulo."""
    assert el_titulo_la_nombra("Cualquier Cosa", "Inmobiliaria Propiedades") is None


def test_el_titulo_ignora_acentos_y_mayusculas():
    assert el_titulo_la_nombra("ACUNA PROPIEDADES - Inicio", "Acuña Propiedades") is True


# El titulo solo no alcanza: lo descubri usandolo sobre las 34 marcadas.

from scripts.de_quien_es_el_dominio import el_titulo_es_del_portal  # noqa: E402


def test_MUERDE_el_caso_cerro_un_directorio_titula_con_el_nombre_del_negocio():
    """Este es el falso positivo que el titulo INTRODUCE.

    `empresasdecordoba.com` titula cada pagina con el negocio que describe, y
    por eso `el_titulo_la_nombra` dice que si. Lo que lo delata es que el
    titulo TAMBIEN nombra al dominio.
    """
    titulo = "Cerro Inmobiliaria Miguel A Caceres - Empresas de Cordoba"
    url = "https://empresasdecordoba.com/pagina/Cerro-Inmobiliaria-Miguel-A-Caceres/"
    assert el_titulo_la_nombra(titulo, "Cerro Inmobiliaria") is True
    assert el_titulo_es_del_portal(titulo, url) is True


def test_MUERDE_el_caso_lujanprop():
    assert el_titulo_es_del_portal(
        "LujanProp | Arte Propiedades | Encontra tu proxima propiedad",
        "https://lujanprop.com.ar/inmobiliaria/arte") is True


def test_un_sitio_propio_no_se_nombra_dos_veces():
    """`fandiprop.com.ar` se titula «Fandino Propiedades»: la etiqueta del
    dominio no esta en el titulo, y eso es lo normal en un sitio propio."""
    assert el_titulo_es_del_portal(
        "Fandino Propiedades - Inmobiliarias Banfield",
        "https://fandiprop.com.ar") is False


def test_MUERDE_no_atrapa_al_portal_que_no_se_nombra():
    """Honestidad sobre el limite: `inmobusqueda.com` titula «ABALSAMO
    PROPIEDADES» a secas y esta regla no lo ve. Reduce el ruido, no lo
    elimina; si alguien cree que esto decide solo, se equivoca."""
    assert el_titulo_es_del_portal(
        "ABALSAMO PROPIEDADES",
        "https://www.inmobusqueda.com/abalsamopropiedades") is False


def test_sin_titulo_no_es_del_portal():
    assert el_titulo_es_del_portal("", "https://lujanprop.com.ar/x") is False

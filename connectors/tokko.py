#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Connector Tokko — implementacion numero uno.

Lo que el discovery encontro sobre 60 fuentes reales:

  - 88% corre "Tokko Front Web" (TFW), el sitio hospedado que Tokko sirve sobre
    el dominio de cada inmobiliaria. Mismo HTML, distinto tema.
  - El listado vive en /Propiedades (a veces /Venta o /venta) y trae 20 avisos.
  - La paginacion es scroll infinito: la propia pagina lleva escrito el $.ajax
    con TODOS los filtros y termina en "&p=". Se pagina poniendo el numero ahi.
    Inventar "?page=2" devuelve la pagina uno otra vez, sin error: por eso el
    query se lee del HTML en vez de construirse a mano.
  - La ficha es /p/<id>-<slug>, y ese <id> es el id de la propiedad en Tokko:
    sirve como source_listing_id estable.
  - Las fotos son static.tokkobroker.com/pictures/<id>_<hash>, con el mismo id
    adelante, asi que la asociacion foto-propiedad se puede verificar.

El 12% restante son frontends propios sobre Tokko. Este connector los detecta y
los reporta como variante no soportada en lugar de devolver cero en silencio,
que es la forma mas cara de fallar.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
from html import unescape
from typing import Any, Iterator

from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_entero, a_numero,
                   detectar_moneda, detectar_operacion, detectar_tipo, limpiar)

RUTAS_LISTADO = ("/Propiedades", "/propiedades", "/Venta", "/venta", "/Buscar")

# Un catalogo unificado ya trae venta, alquiler y emprendimientos juntos: si
# esta, con ese alcanza.
RUTAS_UNIFICADAS = ("/Propiedades", "/propiedades", "/Buscar")

# Muchos sitios NO tienen catalogo unificado: lo parten por operacion. Quedarse
# con el primero que aparece -siempre `/Venta`, porque encabeza la lista- deja
# afuera el resto del inventario, y la enumeracion se declara completa igual.
#
# Es el mismo error conceptual que la paginacion rota, en otra forma: la
# primera vez el catalogo terminaba donde terminaba la primera pagina, y aca
# termina donde termina el primer catalogo.
#
# Medido sobre 45 sitios tokko: 10 estan partidos asi. En los 11 casos donde se
# leyeron los totales declarados de cada ruta son 291 propiedades invisibles
# sobre 1.767, el 16,5%.
RUTAS_POR_OPERACION = ("/Venta", "/venta", "/Alquiler", "/alquiler",
                       "/Emprendimientos", "/emprendimientos",
                       "/Alquiler-Temporario", "/Temporario", "/temporario")
MAX_PAGINAS = 200          # 4.000 avisos: mas que el maximo observado (690)
POR_PAGINA = 20

RE_FICHA = re.compile(r"/p/(\d+)-([^\"'?#]*)")
RE_AJAX = re.compile(r"\$\.ajax\('([^']{20,900})'")

# El template TFW cambio: antes la url de paginacion era literal y ahora la
# arma un ayudante de JavaScript definido en la misma pagina.
#
#   antes:  $.ajax('/Propiedades?o=2,2&p=' + current_page)
#   ahora:  $.ajax(tfwListingUrl('', {o: '2,2', p: current_page}))
#
#   function tfwListingUrl(searchQuery, values) {
#     const params = new URLSearchParams(searchQuery);
#     Object.keys(values).forEach(k => params.set(k, String(values[k])));
#     return '?' + tfwRenderQuery(params);
#   }
#
# Sin url literal, `query_paginacion` quedaba en None y `fetch_listing` cortaba
# despues de la primera pagina: exactamente 20 avisos, que es `POR_PAGINA`.
# `aagaard` paso de 297 enumeradas el 2026-09-09 a 20 el 2026-09-20, y
# `abriola` dio el mismo 20. Comprobado contra la fuente que `?p=2` devuelve 20
# ids NUEVOS: la paginacion funciona, faltaba saber pedirla.
RE_AJAX_AYUDANTE = re.compile(
    r"\$\.ajax\(\s*tfwListingUrl\(\s*'([^']*)'\s*,\s*\{([^}]{0,400})\}")
# Pares `clave: 'valor'` o `clave: variable` dentro del objeto del ayudante.
RE_PAR_AYUDANTE = re.compile(r"(\w+)\s*:\s*(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z_]\w*))")
# La clave de pagina es la que recibe una VARIABLE, no un literal: el numero lo
# pone `fetch_listing` al concatenar.
CLAVES_DE_PAGINA = ("p", "page", "pagina")


def query_de_paginacion(html: str) -> str | None:
    """La query que hay que concatenarle el numero de pagina, o None.

    Primero la forma literal de siempre, que es la que usan la mayoria de las
    86 agencias Tokko que hoy cierran bien. Despues la forma nueva con
    ayudante. Si no hay ninguna de las dos no se inventa nada: pedir una
    paginacion equivocada devuelve cero, que es peor que quedarse en 20.
    """
    literal = RE_AJAX.search(html or "")
    if literal:
        return literal.group(1)
    ayudante = RE_AJAX_AYUDANTE.search(html or "")
    if not ayudante:
        return None
    busqueda, cuerpo = ayudante.group(1), ayudante.group(2)
    fijos: list[str] = []
    clave_pagina: str | None = None
    for clave, sim, dob, variable in RE_PAR_AYUDANTE.findall(cuerpo):
        if variable and clave.lower() in CLAVES_DE_PAGINA:
            clave_pagina = clave
            continue
        valor = sim or dob or variable
        fijos.append(f"{clave}={valor}")
    if clave_pagina is None:
        # Sin clave de pagina, concatenar el numero inventaria un parametro.
        return None
    partes = [p for p in ([busqueda] if busqueda else []) + fijos if p]
    if not partes:
        return f"?{clave_pagina}="
    return "?" + "&".join(partes + [f"{clave_pagina}="])


RE_TOTAL = re.compile(r"(\d[\d.]*)\s*Resultados", re.I)
RE_LOGO = re.compile(r"static\.tokkobroker\.com/logos/(\d+)/")
RE_FOTO = re.compile(r"https://static\.tokkobroker\.com/(?:pictures|thumbs)/[^\"'\s)]+")
RE_COORD = re.compile(r"(-?[23456]\d\.\d{3,})\s*,\s*(-?[567]\d\.\d{3,})")


def _tipo_propiedad(texto: str | None) -> str | None:
    """Tokko publica tipos con acentos; el vocabulario canonico no los usa."""
    if not texto:
        return None
    sin_acentos = "".join(
        char for char in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(char)
    )
    return detectar_tipo(sin_acentos)


def _texto_plano(html: str) -> str:
    """HTML a texto legible.

    El orden importa: primero se desescapan las entidades y despues se quitan
    las etiquetas, y hay que hacerlo dos veces. Muchas descripciones vienen con
    el markup escapado dentro del propio HTML -&lt;div&gt;&lt;br&gt;-, asi que
    limpiar primero y desescapar despues devuelve el markup al texto y lo deja
    dentro de la descripcion publicada.

    Desescapar tampoco es cosmetico en las etiquetas: varios temas escriben
    "Direcci&oacute;n", y sin traducirlo el campo sale vacio sin que nada falle.
    """
    # The closing-tag backreference used to contain a literal control byte
    # (``\x01``), so no script/style block was ever removed.  Besides leaking
    # JavaScript into descriptions, that also exposed unrelated numbers to the
    # attribute parser.
    t = re.sub(r"<(script|style)[^>]*>.*?</\1\s*>", " ", html, flags=re.S | re.I)
    t = unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = unescape(t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace(" ", " "))


# Etiquetas que Tokko usa en la ficha. Sirven de tope: el valor de un campo
# termina donde empieza la etiqueta siguiente. Hace falta la lista porque la
# cabecera escribe "Direccion Independencia al 300 Ubicacion Nueva Cordoba",
# sin dos puntos, y sin saber donde corta se leeria la ficha entera como
# direccion.
ETIQUETAS = (
    "Dirección", "Direccion", "Ubicación", "Ubicacion", "Ambientes",
    "Total construido", "Total terreno", "Superficie total",
    "Superficie cubierta", "Superficie", "Terreno", "Cubierta", "Total Built",
    "Dormitorios", "Baños", "Banos", "Toilettes", "Garages",
    "Suites", "Cocheras", "Plantas",
    "Apto profesional", "Condición", "Condicion", "Antigüedad", "Antiguedad",
    "Situación", "Situacion", "Expensas", "Orientación", "Orientacion",
    "Disposición", "Disposicion", "Crédito", "Credito", "Estado",
    "INFORMACIÓN BÁSICA", "INFORMACION BASICA", "SUPERFICIES", "REF.",
    # La ficha declara el tipo como campo propio. Sin esta etiqueta no era
    # frontera, asi que los valores vecinos podian arrastrarla adentro.
    "Tipo de Propiedad", "Tipo de propiedad",
    # Los avisos de pozo publican la entrega y no estaba en la lista, asi que
    # el valor seguia de largo hasta el tope de 70 caracteres y se llevaba el
    # rotulo y la fecha adentro:
    #
    #     barrio = 'Centro Fecha de entrega Diciembre 2027'
    #     barrio = 'Lanus Este Fecha de entrega Abril 2029'
    #
    # El barrio estaba bien; lo que sobraba era el campo siguiente. Medido
    # sobre el snapshot: de 1.715 barrios que son texto recortado, **1.243 -el
    # 72,5 %- contienen esta etiqueta**, y son todos recuperables cortando
    # aca. Los que quedan son otra cosa -listas de amenities y prosa de la
    # descripcion- y piden otra frontera, no esta.
    "Fecha de entrega", "Fecha de Entrega",
)
_STOP = "|".join(re.escape(e) for e in sorted(ETIQUETAS, key=len, reverse=True))


# El rastro de ubicacion que el tema pone debajo del titulo, con el partido
# entre parentesis al final. Ver el uso, mas abajo.
RE_RASTRO_DE_UBICACION = re.compile(
    r"<h2[^>]*>.{0,300}?</h2>\s*<p[^>]*>([^<]{0,200})</p>", re.S | re.I)


def _partido_del_rastro(html: str) -> str | None:
    """La ubicacion del rastro, cuando la ficha no trae el campo.

    El rastro viene en dos formas, y las dos aparecen en el mismo sitio:

      Los Puentes | Nordelta | Countries/B.Cerrado (Tigre)
      Loma Verde  | Escobar  | G.B.A. Zona Norte

    Cuando el ultimo tramo trae un parentesis, ahi esta el partido y es lo mas
    confiable que hay. Cuando no, se toma el PRIMER tramo, que es el lugar mas
    fino que el sitio nombra: `Loma Verde` es una localidad censal de Escobar,
    y afirmarla es mas preciso que subir un nivel.

    Nunca se afirma nada por esto: lo que sale de aca es un candidato y lo
    arbitra el catalogo. `Loma Verde` resuelve; `Los Puentes` -que es un barrio-
    no, y se queda donde estaba, que es lo correcto.
    """
    rastro = RE_RASTRO_DE_UBICACION.search(html or "")
    if not rastro:
        return None
    texto = rastro.group(1).strip()
    partido = re.search(r"\(([^)]{2,40})\)\s*$", texto)
    if partido:
        return limpiar(partido.group(1))
    tramos = [x.strip() for x in texto.split("|") if x.strip()]
    return limpiar(tramos[0]) if len(tramos) >= 2 else None


def _campo(texto: str, etiqueta: str) -> str | None:
    """Lee un campo de la ficha, con o sin dos puntos.

    El valor corta en la proxima etiqueta conocida. Confiar en 'la siguiente
    palabra con mayuscula' fallaria con "Nueva Cordoba" o "Villa Urquiza", que
    son valores legitimos con mayuscula adentro.
    """
    for valor in _valores_campo(texto, etiqueta):
        if valor.lower() in {"s", "si", "sí", "no", "-"} and etiqueta.lower() in {
                "dirección", "direccion", "ubicación", "ubicacion"}:
            return None
        return valor
    return None


def _valores_campo(texto: str, etiqueta: str) -> Iterator[str]:
    """Todos los candidatos; el titulo puede anticipar la misma etiqueta.

    Sin dos puntos, la etiqueta solo cuenta si viene capitalizada como rotulo.
    En minuscula es una palabra corriente de la descripcion: "por su ubicacion
    privilegiada, esta casa ofrece..." dejaba `barrio='privilegiada'`. Eran
    1.145 fichas con prosa guardada como ubicacion -"tranquila", "y",
    "residencial"-, un dato inventado que ademas parecia un barrio de verdad.
    """
    patron = (rf"\b({re.escape(etiqueta)})\s*(:?)\s+(.{{1,70}}?)"
              rf"\s*(?=(?:{_STOP})\b|$)")
    for match in re.finditer(patron, texto, re.I):
        rotulo, dos_puntos, crudo = match.groups()
        if not dos_puntos and rotulo[:1].islower():
            continue
        valor = limpiar(crudo)
        if valor:
            yield valor


def _cantidad(texto: str, *etiquetas: str) -> int | None:
    """Read one structured count from a labelled Tokko field.

    A value containing two numbers is deliberately rejected.  Tokko commonly
    renders ``3 baños + 1 toilette`` in the same visual block; stripping all
    non-digits used to turn that into 31.
    """
    for etiqueta in etiquetas:
        for raw in _valores_campo(texto, etiqueta):
            value = a_entero(raw)
            if value is not None:
                return value
    return None


def _descripcion(texto: str) -> str | None:
    """Descripcion propia sin cortar subtitulos internos como Caracteristicas."""
    match = re.search(
        r"DESCRIPCI[OÓ]N\s*(.{0,4000}?)\s*"
        r"(?=INFORMACI[OÓ]N|SUPERFICIES|Ubicaci[oó]n en el mapa|"
        r"Contactanos|Contacto|Compartir|"
        r"Consultar|Volver a Resultados|\Z)",
        texto, re.S | re.I)
    if not match:
        return None
    crudo = match.group(1)
    for marca in ("http", "REF.", "(REF", "Volver a", "Compartir"):
        indice = crudo.find(marca)
        if indice > 0:
            crudo = crudo[:indice]
    valor = limpiar(crudo)
    if valor and len(valor) >= 40 and len(valor.split()) >= 6:
        return valor
    return None


_NUMERO_EN_PALABRAS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def _cantidad_descriptiva(texto: str | None, etiqueta: str) -> int | None:
    """Fallback explicito y acotado para cantidades escritas en la descripcion."""
    if not texto:
        return None
    palabras = "|".join(_NUMERO_EN_PALABRAS)
    match = re.search(
        rf"\b(\d{{1,2}}|{palabras})\s+(?:{etiqueta})\b", texto, re.I)
    if not match:
        return None
    token = match.group(1).lower()
    return int(token) if token.isdigit() and int(token) > 0 else _NUMERO_EN_PALABRAS.get(token)


class TokkoConnector(Connector):
    nombre = "tokko"
    variantes_soportadas = ("TFW_ESTANDAR", "TFW_SIN_AJAX")

    # ---------------------------------------------------------------- discover
    def discover(self, fuente: Fuente) -> dict[str, Any]:
        base = self._base(fuente.official_url)
        html = self.descargador.bajar(fuente.official_url)

        plan: dict[str, Any] = {
            "base": base,
            "tokko_client_id": (RE_LOGO.search(html).group(1)
                                if RE_LOGO.search(html) else None),
            "usa_tfw": "static.tokkobroker.com/tfw/" in html,
        }

        propia = urllib.parse.urlparse(fuente.official_url).path or "/"
        rutas = self.rutas_del_catalogo(html, propia)
        plan["rutas_listado"] = rutas
        plan["ruta_listado"] = rutas[0] if rutas else None

        # Cada catalogo se mide por separado: tienen su propio total declarado
        # y pueden paginar distinto. Sumarlos antes de medirlos escondria que
        # uno de ellos no se puede paginar.
        plan["catalogos"] = [self._medir_catalogo(base, r, html if r == propia
                                                  else None)
                             for r in rutas]
        principal = plan["catalogos"][0] if plan["catalogos"] else {}
        listado = principal.get("html_listado", html)

        plan["query_paginacion"] = principal.get("query_paginacion")
        plan["pagina_por_query"] = bool(principal.get("pagina_por_query"))
        # El total del sitio es la suma de sus catalogos. Con un solo catalogo
        # da exactamente lo de antes; con varios, es contra este numero que la
        # enumeracion tiene que compararse para poder llamarse completa.
        totales = [c["total_declarado"] for c in plan["catalogos"]
                   if c["total_declarado"] is not None]
        plan["total_declarado"] = sum(totales) if totales else None
        plan["ids_primera_pagina"] = principal.get("ids_primera_pagina", 0)
        plan["html_listado"] = listado

        if plan["usa_tfw"] and plan["ids_primera_pagina"] and plan["pagina_por_query"]:
            plan["variante"] = "TFW_ESTANDAR"
        elif plan["ids_primera_pagina"]:
            plan["variante"] = "TFW_SIN_AJAX"
        elif "tokkobroker" in html:
            plan["variante"] = "TOKKO_FRONTEND_PROPIO"
        else:
            plan["variante"] = "SIN_MARCADOR"
        plan["soportada"] = plan["variante"] in self.variantes_soportadas
        plan["paginacion_imposible"] = self.paginacion_imposible(plan)
        return plan

    @staticmethod
    def rutas_del_catalogo(html: str, propia: str) -> list[str]:
        """Todos los catalogos del sitio, no el primero que aparece.

        Si hay uno unificado -`/Propiedades`- ese trae todo y se devuelve solo
        el. Si el sitio parte el inventario por operacion, se devuelven TODAS
        las rutas partidas que publica, en el orden de `RUTAS_POR_OPERACION`
        para que la principal siga siendo `/Venta` y nada de lo que ya
        dependia de `ruta_listado` cambie de significado.

        Quedarse con la primera era el defecto: `andrea gianfelice` declara 147
        en `/Venta`, 10 en `/Alquiler` y 7 en `/Emprendimientos`, y se
        certificaba contra 147.
        """
        unificada = next((r for r in RUTAS_UNIFICADAS if f'href="{r}"' in html),
                         None)
        if unificada:
            return [unificada]
        partidas = [r for r in RUTAS_POR_OPERACION if f'href="{r}"' in html]
        if partidas:
            return partidas
        # Sin ninguna ruta reconocible, la propia pagina es el listado si trae
        # fichas. Es el caso de los sitios de una sola pagina.
        return [propia] if RE_FICHA.search(html) else []

    def _medir_catalogo(self, base: str, ruta: str,
                        html_ya_bajado: str | None = None) -> dict[str, Any]:
        """Lo que hace falta saber de UN catalogo para recorrerlo entero."""
        listado = (html_ya_bajado if html_ya_bajado is not None
                   else self.descargador.bajar(base + ruta))
        query = query_de_paginacion(listado)
        mt = RE_TOTAL.search(listado)
        crudo = mt.group(1).replace(".", "") if mt else ""
        return {
            "ruta": ruta,
            "query_paginacion": query,
            "pagina_por_query": bool(
                query and query.rstrip().endswith(
                    ("&p=", "?p=", "&page=", "?page=", "&pagina=", "?pagina="))),
            "total_declarado": int(crudo) if crudo.isdigit() else None,
            "ids_primera_pagina": len(set(RE_FICHA.findall(listado))),
            "html_listado": listado}

    @staticmethod
    def paginacion_imposible(plan: dict[str, Any]) -> bool:
        """Este plan solo puede devolver la primera pagina.

        Un TFW con fichas en la primera pagina y SIN query de paginacion no
        tiene como pedir la segunda: `fetch_listing` cae en `else: break` y
        devuelve exactamente `POR_PAGINA` avisos. Se sabe aca, antes de bajar
        nada mas, y por eso se anota aca en vez de inferirlo despues.

        Cero fichas NO es un truncamiento: es otra cosa y tiene su propio
        defecto. Mezclarlos haria que "no pudimos paginar" y "no hay nada" se
        diagnostiquen igual.

        Con varios catalogos alcanza con que UNO no pueda paginar: ese queda
        truncado en 20 y el sitio no esta enumerado entero, aunque los demas
        anden bien.
        """
        catalogos = plan.get("catalogos") or [plan]
        return any(bool(c.get("ids_primera_pagina")
                        and not c.get("query_paginacion"))
                   for c in catalogos)

    def foto_verificable(self) -> bool:
        """La ruta del CDN de Tokko lleva el id de la propiedad adelante."""
        return True

    def foto_es_de(self, prop, url: str) -> bool:
        pid = prop.source_listing_id
        return f"/pictures/{pid}_" in url or f"/thumbs/{pid}_" in url

    @staticmethod
    def _base(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme}://{p.netloc}"

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        """Recorre el listado pagina por pagina y emite un aviso por propiedad.

        Corta cuando una pagina no aporta ningun id nuevo. Confiar solo en el
        total declarado seria fragil: algunas fuentes lo publican mal, y una
        pagina vacia es la senal que la propia paginacion da.
        """
        if not plan.get("soportada"):
            return
        base = plan["base"]
        vistos: set[str] = set()
        estado = self.resume(fuente)

        # Un sitio puede partir su inventario en varios catalogos. Se recorren
        # todos, compartiendo `vistos`: una propiedad listada en dos catalogos
        # se emite una sola vez.
        catalogos = plan.get("catalogos") or [{
            "ruta": plan.get("ruta_listado") or "/Propiedades",
            "query_paginacion": plan.get("query_paginacion"),
            "total_declarado": plan.get("total_declarado"),
            "html_listado": plan.get("html_listado")}]
        for catalogo in catalogos:
            yield from self._recorrer_catalogo(base, catalogo, vistos, estado)
        estado["completa"] = True

    def _recorrer_catalogo(self, base: str, catalogo: dict[str, Any],
                           vistos: set[str],
                           estado: dict[str, Any]) -> Iterator[dict]:
        """Un catalogo, pagina por pagina, hasta agotarlo."""
        ruta = catalogo.get("ruta") or "/Propiedades"
        query = catalogo.get("query_paginacion")
        declarado = catalogo.get("total_declarado")
        propias: set[str] = set()
        # Si la fuente declara un total, se sabe cuantas paginas hacen falta y
        # ese numero manda por encima de cualquier heuristica. Es el total de
        # ESTE catalogo: comparar contra la suma del sitio haria recorrer de
        # mas en cada uno.
        minimo_paginas = -(-declarado // POR_PAGINA) if declarado else 0

        # Tokko reordena el conjunto entre pedidos: dos barridos identicos
        # devuelven subconjuntos distintos, asi que una sola pasada deja afuera
        # entre un 6% y un 14% del inventario aunque recorra todas las paginas
        # que el total declarado implica. Se repite el barrido mientras siga
        # apareciendo material nuevo y el total siga sin alcanzarse.
        MAX_BARRIDOS = 4
        for barrido in range(1, MAX_BARRIDOS + 1):
            antes = len(propias)
            pagina, sin_nuevos = 1, 0
            while pagina <= MAX_PAGINAS:
                try:
                    if pagina == 1 and barrido == 1:
                        html = (catalogo.get("html_listado")
                                or self.descargador.bajar(base + ruta))
                    elif query:
                        html = self.descargador.bajar(base + ruta + query + str(pagina))
                    else:
                        break
                except ErrorPermanente:
                    # Varias fuentes devuelven 404 al pedir una pagina que ya no
                    # existe, en vez de una pagina vacia. Es el final del
                    # listado, no un fallo: sin atraparlo aca la excepcion subia
                    # y se perdian TODAS las propiedades ya enumeradas de esa
                    # inmobiliaria.
                    break
                except (ErrorTransitorio, Bloqueado):
                    # Cortar por red caida no es haber llegado al final.
                    self.paginacion_interrumpida = True
                    break

                hallados = RE_FICHA.findall(html)
                nuevos = 0
                for pid, slug in hallados:
                    # `propias` mide el avance DE ESTE catalogo; `vistos` evita
                    # emitir dos veces una propiedad que figura en dos. Si se
                    # usara solo `vistos`, un catalogo cuyas fichas ya salieron
                    # todas en otro pareceria no avanzar y cortaria antes de
                    # llegar a las suyas.
                    if pid not in propias:
                        propias.add(pid)
                        nuevos += 1
                    if pid in vistos:
                        continue
                    vistos.add(pid)
                    yield {"source_listing_id": pid,
                           "source_url": self.descargador.url_segura(
                               f"{base}/p/{pid}-{slug}"),
                           "pagina": pagina}

                if not hallados:
                    break
                if nuevos == 0:
                    sin_nuevos += 1
                    if sin_nuevos >= 2 and pagina >= minimo_paginas:
                        break
                else:
                    sin_nuevos = 0
                estado["ultima_pagina"] = pagina
                pagina += 1

            ganancia = len(propias) - antes
            estado["barridos"] = barrido
            if not declarado or len(propias) >= declarado or ganancia == 0:
                break

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        url = crudo["source_url"]
        try:
            html = self.descargador.bajar(url)
        except ErrorPermanente:
            return None
        except (ErrorTransitorio, Bloqueado) as e:
            self.anotar_error(fuente, "detalle", e)
            return None

        texto = _texto_plano(html)
        pid = crudo["source_listing_id"]

        titulo = None
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"', html)
        if m:
            titulo = limpiar(m.group(1))
        if not titulo:
            m = re.search(r"<title[^>]*>(.{1,200}?)</title>", html, re.S | re.I)
            titulo = limpiar(m.group(1)) if m else None

        # Precio y moneda: Tokko los escribe juntos, "VENTA USD55.000".
        precio = moneda = None
        mp = re.search(r"(VENTA|ALQUILER[A-ZÁ ]*|TEMPORARIO)\s*"
                       r"(USD|U\$S|US\$|\$)\s*([\d.,]{3,15})", texto, re.I)
        if mp:
            moneda = detectar_moneda(mp.group(2))
            precio = a_numero(mp.group(3))
        operacion = detectar_operacion(mp.group(1) if mp else titulo)

        # Solo las fotos de ESTA propiedad: la ruta lleva el id adelante, asi
        # que una foto de otra ficha no se cuela por estar en el mismo carrusel.
        imagenes, vistas = [], set()
        for u in RE_FOTO.findall(html):
            if f"/pictures/{pid}_" not in u and f"/thumbs/{pid}_" not in u:
                continue
            limpio = u.split("?")[0]
            if limpio not in vistas:
                vistas.add(limpio)
                imagenes.append(limpio)

        lat = lon = None
        mc = RE_COORD.search(html)
        if mc:
            lat, lon = float(mc.group(1)), float(mc.group(2))

        expensas = None
        me = re.search(r"Expensas\s*:?\s*\$?\s*([\d.,]{3,15})", texto, re.I)
        if me:
            expensas = a_numero(me.group(1))

        sup_cub = sup_tot = None
        ms = re.search(
            r"(?:Total construido|Superficie cubierta|Cubierta|Total Built)"
            r"\s*:?\s*([\d.,]+)\s*m", texto, re.I)
        if ms:
            sup_cub = a_numero(ms.group(1))
        # La unidad se lee, no se supone. Tokko publica el terreno en hectareas
        # cuando la propiedad es rural -`Terreno: 50.0 Ha`- y exigiendo `m` esas
        # fichas quedaban sin superficie y sin motivo anotado. Convertida, el
        # valor entra si es coherente con el tipo y lo descarta `coherencia` si
        # no lo es: un departamento con cincuenta hectareas de terreno no se
        # publica ni corregido ni como esta.
        ms = re.search(
            r"(?:Superficie total|Total terreno|Terreno)\s*:?\s*"
            r"([\d.,]+)\s*(ha|m)(?![a-z])", texto, re.I)
        if ms:
            sup_tot = a_numero(ms.group(1))
            if sup_tot is not None and ms.group(2).lower() == "ha":
                sup_tot *= 10_000

        direccion = _campo(texto, "Dirección") or _campo(texto, "Direccion")
        ubicacion = _campo(texto, "Ubicación") or _campo(texto, "Ubicacion")
        # Cuando la ficha no trae el campo, el rastro debajo del titulo:
        #
        #   <p> Los Puentes | Nordelta | Countries/B.Cerrado (Tigre) </p>
        #
        # `gruponortepropiedades.com.ar` no llena ubicacion y publica solo
        # esto: sus 192 propiedades quedaban sin geografia de ningun nivel.
        #
        # Se toma UNICAMENTE lo que va entre parentesis, que es el partido.
        # Los otros dos tramos son barrio y zona -"Los Puentes", "Nordelta"-
        # y ninguno es una localidad censal: guardarlos como ubicacion los
        # mandaria a competir con el catalogo por un lugar que no existe.
        # Esto es un CANDIDATO y lo arbitra el catalogo despues, igual que
        # el campo `Ubicacion`: `Tigre` resuelve, `Nordelta` no.
        if not ubicacion:
            ubicacion = _partido_del_rastro(html)

        # La descripcion esta en la ficha que ya se bajo: extraerla no cuesta
        # una peticion adicional. Se corta el encabezado y el pie, que repiten
        # el titulo y los datos de contacto en todas las fichas.
        descripcion = _descripcion(texto)

        extra = {k: v for k, v in {
            "expensas": expensas,
            "antiguedad": _campo(texto, "Antigüedad") or _campo(texto, "Antiguedad"),
            "condicion": _campo(texto, "Condición"),
            "orientacion": _campo(texto, "Orientación"),
            "disposicion": _campo(texto, "Disposición"),
            "situacion": _campo(texto, "Situación"),
            "apto_credito": "apto credito" in texto.lower() or "Apto crédito" in texto,
            "cocheras": a_entero(_campo(texto, "Cocheras")),
            "suites": a_entero(_campo(texto, "Suites")),
            "plantas": a_entero(_campo(texto, "Plantas")),
            "referencia": (re.search(r"REF\.\s*([A-Z0-9]{3,20})", texto).group(1)
                           if re.search(r"REF\.\s*([A-Z0-9]{3,20})", texto) else None),
            "tokko_client_id": crudo.get("tokko_client_id"),
            "imagenes_totales_en_pagina": len(set(RE_FOTO.findall(html))),
        }.items() if v not in (None, "", False)}

        dormitorios = (_cantidad(texto, "Dormitorios")
                        or _cantidad_descriptiva(descripcion, r"dormitorios?|habitaciones?"))
        banos = (_cantidad(texto, "Baños", "Banos")
                 or _cantidad_descriptiva(descripcion, r"ba[nñ]os?"))

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=pid,
            source_url=url,
            connector=self.nombre,
            titulo=titulo,
            descripcion=descripcion,
            precio=precio,
            moneda=moneda,
            operacion=operacion,
            # El titulo manda porque es lo que venia funcionando; el campo
            # entra solo donde el titulo no alcanzo. Eran 899 fichas sin tipo
            # -y sin tipo una propiedad no se puede publicar- teniendo la
            # fuente el dato declarado en la ficha.
            tipo_propiedad=(_tipo_propiedad(titulo)
                            or _tipo_propiedad(
                                _campo(texto, "Tipo de Propiedad"))),
            direccion=direccion,
            barrio=ubicacion,
            ciudad=None,
            provincia=None,
            latitud=lat,
            longitud=lon,
            dormitorios=dormitorios,
            banos=banos,
            ambientes=_cantidad(texto, "Ambientes"),
            superficie_total=sup_tot,
            superficie_cubierta=sup_cub,
            imagenes=imagenes,
            extra=extra,
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre,
                        "official_domain": self._base(fuente.official_url),
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "TOKKO",
                        "pagina_listado": crudo.get("pagina")},
        )

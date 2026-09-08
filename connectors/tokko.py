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
MAX_PAGINAS = 200          # 4.000 avisos: mas que el maximo observado (690)
POR_PAGINA = 20

RE_FICHA = re.compile(r"/p/(\d+)-([^\"'?#]*)")
RE_AJAX = re.compile(r"\$\.ajax\('([^']{20,900})'")
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
)
_STOP = "|".join(re.escape(e) for e in sorted(ETIQUETAS, key=len, reverse=True))


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

        ruta = next((r for r in RUTAS_LISTADO if f'href="{r}"' in html), None)
        propia = urllib.parse.urlparse(fuente.official_url).path or "/"
        if ruta is None and RE_FICHA.search(html):
            ruta = propia
        plan["ruta_listado"] = ruta

        listado = html
        if ruta and ruta != propia:
            listado = self.descargador.bajar(base + ruta)

        m = RE_AJAX.search(listado)
        plan["query_paginacion"] = m.group(1) if m else None
        plan["pagina_por_query"] = bool(m and m.group(1).rstrip().endswith("&p="))
        mt = RE_TOTAL.search(listado)
        crudo = mt.group(1).replace(".", "") if mt else ""
        plan["total_declarado"] = int(crudo) if crudo.isdigit() else None
        plan["ids_primera_pagina"] = len(set(RE_FICHA.findall(listado)))
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
        return plan

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
        base, ruta = plan["base"], plan.get("ruta_listado") or "/Propiedades"
        query = plan.get("query_paginacion")
        vistos: set[str] = set()

        estado = self.resume(fuente)
        declarado = plan.get("total_declarado")
        # Si la fuente declara un total, se sabe cuantas paginas hacen falta y
        # ese numero manda por encima de cualquier heuristica.
        minimo_paginas = -(-declarado // POR_PAGINA) if declarado else 0

        # Tokko reordena el conjunto entre pedidos: dos barridos identicos
        # devuelven subconjuntos distintos, asi que una sola pasada deja afuera
        # entre un 6% y un 14% del inventario aunque recorra todas las paginas
        # que el total declarado implica. Se repite el barrido mientras siga
        # apareciendo material nuevo y el total siga sin alcanzarse.
        MAX_BARRIDOS = 4
        for barrido in range(1, MAX_BARRIDOS + 1):
            antes = len(vistos)
            pagina, sin_nuevos = 1, 0
            while pagina <= MAX_PAGINAS:
                try:
                    if pagina == 1 and barrido == 1:
                        html = (plan.get("html_listado")
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
                    break

                hallados = RE_FICHA.findall(html)
                nuevos = 0
                for pid, slug in hallados:
                    if pid in vistos:
                        continue
                    vistos.add(pid)
                    nuevos += 1
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

            ganancia = len(vistos) - antes
            estado["barridos"] = barrido
            if not declarado or len(vistos) >= declarado or ganancia == 0:
                break
        estado["completa"] = True

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

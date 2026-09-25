#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verificador de identidad V2: primero qué es el sitio, después de quién es.

No toca nada con huella. Verificado empíricamente el 2026-09-15: modificar este
archivo recalcula idénticas las 18 estrategias.

### Por qué existe

El canario de 50 del 2026-09-14 dio 72 % de resolución cruda y ~36 % auditada.
Los falsos positivos no fueron casos raros: fueron un patrón único.

    BTS Propiedades     -> bts.com              una consultora de estrategia
    Cerullo Propiedades -> cerullo.com          un fabricante de butacas
    Mizrahi Real Estate -> mizrahi.com          un dominio parkeado
    Genzano             -> ww16.genzano.com     dominio expirado
    F. Brandolin        -> cuitonline.com       un buscador de CUIT
    Coldwell Paraguay   -> lanacion.com.py      una nota de diario
    REMAX RAICES        -> aspenbienesraices    OTRA inmobiliaria
    RE/MAX Focus        -> remax.com.uy/agent   un agente uruguayo
    Sol Llabres         -> puntoclick.com.ar    un portal
    RE/MAX GO           -> inmoup.com.ar/ficha  una ficha en un portal

El verificador V1 aceptaba un dominio porque **compartía un token con el
nombre**. Un fabricante de butacas llamado Cerullo satisface esa prueba. La
falla no estaba en el buscador: Brave devolvió lo que había.

### El principio

Dos condiciones SEPARADAS, y la primera manda:

    A. el sitio es del tipo correcto
    B. la identidad corresponde a esa inmobiliaria

Una coincidencia de nombre sola no alcanza nunca. `cerullo.com` falla en A y
nunca llega a B, que es exactamente donde V1 lo dejaba pasar.

### Preferir no resolver antes que resolver mal

Un falso negativo cuesta una búsqueda más. Un falso positivo le asigna a una
inmobiliaria el catálogo de otra, y eso contamina cientos de propiedades con
una identidad que después nadie distingue de la real.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# --------------------------------------------------------------------------
# Tipos de sitio (§3)
# --------------------------------------------------------------------------
REAL_ESTATE_OFFICIAL_SITE = "REAL_ESTATE_OFFICIAL_SITE"
NETWORK_OFFICE_PAGE = "NETWORK_OFFICE_PAGE"
NETWORK_DIRECTORY = "NETWORK_DIRECTORY"
EXTERNAL_PORTAL = "EXTERNAL_PORTAL"
PROPERTY_DETAIL_PAGE = "PROPERTY_DETAIL_PAGE"
BUSINESS_DIRECTORY = "BUSINESS_DIRECTORY"
NEWS_MEDIA = "NEWS_MEDIA"
SOCIAL_PROFILE = "SOCIAL_PROFILE"
PARKED_DOMAIN = "PARKED_DOMAIN"
UNRELATED_BUSINESS = "UNRELATED_BUSINESS"
DESCONOCIDO = "UNKNOWN"

# Sólo de estos dos puede salir una fuente oficial.
PUEDE_SER_OFICIAL = {REAL_ESTATE_OFFICIAL_SITE}
PUEDE_SER_OFICINA = {NETWORK_OFFICE_PAGE}

# --------------------------------------------------------------------------
# Confianza (§11)
# --------------------------------------------------------------------------
ALTA, MEDIA, BAJA = "HIGH", "MEDIUM", "LOW"

OFFICIAL_WEB = "OFFICIAL_WEB"
OFFICIAL_OFFICE_PAGE = "OFFICIAL_OFFICE_PAGE"
EXTERNAL_PORTAL_PROFILE = "EXTERNAL_PORTAL_PROFILE"
INACTIVE_SOURCE = "INACTIVE_SOURCE"
NO_OFFICIAL_WEB_FOUND = "NO_OFFICIAL_WEB_FOUND"
IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
BLOCKED = "BLOCKED"

# --------------------------------------------------------------------------
# Señales
# --------------------------------------------------------------------------
# Rubro (§4). No hace falta que estén todas; hace falta que haya alguna.
SENALES_RUBRO = (
    "inmobiliari", "propiedades", "inmueble", "bienes raices", "bienes raíces",
    "en venta", "en alquiler", "tasacion", "tasación", "departamento",
    "emprendimiento", "real estate", "corredor inmobiliario", "matricula",
    "matrícula", "cpi ", "alquiler temporario", "venta de casas",
)
# Rubros que NO son el nuestro. Sirven para separar "no habla de propiedades"
# de "habla de otra cosa", que es informacion distinta para el diagnostico.
SENALES_OTRO_RUBRO = (
    "butaca", "asiento", "seats", "consultora", "consulting", "strategy",
    "software", "indumentaria", "restaurant", "farmacia", "seguros",
    "automotor", "concesionaria", "turismo", "hotel",
)
# Dominio parkeado o expirado (§6). HTTP 200 no significa sitio vivo.
PARKING_HOST = re.compile(r"^(ww\d+|parking|sedo|parkingcrew)\.", re.I)
PARKING_TEXTO = re.compile(
    r"(?i)(this domain (is|may be) for sale|dominio (en venta|a la venta)|"
    r"buy this domain|parked (free )?(at|by)|sedoparking|related searches|"
    r"búsquedas relacionadas|renew (your )?domain|expired domain)")
PARKING_QUERY = re.compile(r"(?i)[?&](sub\d|dsparking|caf_)")

# Portales y directorios. La lista sirve para los conocidos; la heuristica de
# `_parece_agregador` para los que no estan.
PORTALES = (
    "zonaprop", "argenprop", "mercadolibre", "properati", "inmoup",
    "puntoclick", "buscainmueble", "inmobusqueda", "icasas", "lamudi",
    "remax.com", "century21", "coldwellbanker", "toctocventas", "navent",
    "clasificados", "yably", "slideprop", "comunidadinmobiliaria",
    "redinmosoft", "choza.ai", "agroads", "inmoclick",
    # Los tres que se colaron en la corrida de 250 del 2026-09-14, medidos:
    # `realedo.com` dos veces -es el portal uruguayo, y la url era
    # /uruguay/profile/agency/156-, y `mudafy.com.ar` una. Los tres se habian
    # declarado OFFICIAL_WEB, o sea "su sitio propio".
    "realedo", "mudafy", "apuntavamos",
    # 25-09: con identidad READY apuntando a un portal o directorio. Aca se
    # compara por subcadena: `propia`, `lujanprop` y `liderprop` atraparian
    # `inmobiliariapropia`, `lujanpropiedades`, `liderpropiedades`. Esos
    # quedan solo en `agency_web_discovery`, que compara el nombre entero.
    "proppies", "aspenbienesraices",
)
# No venden propiedades: publican avisos de empleo. Se mira aparte de
# PORTALES porque no son lo mismo, pero el desenlace es el mismo: NO es el
# sitio de la inmobiliaria. `FULLINMO SAS` resolvio a
# ar.computrabajo.com/trabajo-de-corredor-inmobiliario.
BOLSAS_DE_TRABAJO = ("computrabajo", "bumeran", "zonajobs", "indeed")
DIRECTORIOS = ("cuitonline", "dateas", "universidad", "paginasamarillas",
               "guiaempresas", "informacion-empresas", "opendata", "nosis",
               "einforma", "empresite")
MEDIOS = ("lanacion", "clarin", "infobae", "pagina12", "eldia", "lavoz",
          "perfil.com", "ambito.com", "cronista", "iprofesional", "telam",
          "diario", "noticias",
          # `ORIGO` resolvio a misionesonline.net/2024/03/21/origen-... , una
          # nota. El host no trae "diario" ni "noticias", asi que ninguna de
          # las dos reglas de arriba lo alcanzaba.
          "misionesonline", "elonce", "eldiarioar", "rosario3")
# Por dominio registrable, NO por substring: "x.com" como substring convierte
# a `remax.com.ar` en un perfil social, que fue exactamente el bug.
SOCIALES = {"facebook.com", "instagram.com", "twitter.com", "x.com",
            "linkedin.com", "youtube.com", "tiktok.com", "wa.me",
            "whatsapp.com", "pinterest.com"}

# Rutas que en el dominio de una red NO son la pagina de una oficina (§7).
#
# La distincion no es cosmetica. Un LISTADO es una superficie de busqueda y
# nunca es una oficina, por mas que la ruta siga: `/listings/buy` es el
# buscador de RE/MAX Uruguay. Un INDICE de oficinas, en cambio, puede
# continuar hacia una oficina concreta:
# `/offices/argentina/palermo/remax-premium/42` es UNA oficina.
RUTA_LISTADO = re.compile(
    r"(?i)/(listings?|buscar|search|resultados|properties|propiedades)(/|\?|$)")
RUTA_INDICE = re.compile(
    r"(?i)/(directorio|directory|oficinas|offices|agentes|agents|sucursales)(/|\?|$)")
# Rutas que son una ficha de propiedad, no un sitio (§3).
RUTA_FICHA = re.compile(
    r"(?i)/(propiedades?|inmuebles?|fichas?|listings?|property|properties)"
    r"[/-][^/]*\d|/ficha(/|$)")

# Rutas que ENUMERAN TERCEROS. Es la regla que reemplaza a media lista negra:
# un host que tiene una seccion de "inmobiliarias", de "anunciantes" o de
# "perfiles" no es una inmobiliaria — es el lugar donde varias se publican.
#
# Sale de cuatro falsos positivos del canario V2 que no compartian host pero si
# esta forma:
#   gopunta.uy/inmobiliarias/beba-paez-vilaro/...
#   infocasas.com.uy/inmobiliarias/perfil/17...
#   bullano.com.ar/anunciantes/tienda/SITUAR...
#   puntoclick.com.ar/empresa/sol-llabres-dts...
RUTA_DE_TERCEROS = re.compile(
    r"(?i)/(inmobiliarias?|anunciantes?|empresas?|agencias?|perfil(es)?|"
    r"tiendas?|comercios?|profesionales?|directorio)/[^/]")
# Rutas de nota periodistica. `0221.com.ar/nota/2022-1-11-...` no esta en
# ninguna lista de medios y aun asi es una nota.
RUTA_DE_NOTA = re.compile(
    r"(?i)/(nota|noticias?|articulo|blog|prensa|news)[/-]")

PAIS_AR = re.compile(
    r"(?i)argentin|buenos aires|c[oó]rdoba|rosario|mendoza|santa fe|"
    r"tucum[aá]n|salta|neuqu[eé]n|bariloche|mar del plata|la plata|\bCABA\b|"
    r"\+54\b|\b0800\b|\bCUIT\b|\bAFIP\b|\bCPI\b")
PAIS_OTRO = re.compile(
    r"(?i)\b(uruguay|montevideo|punta del este|paraguay|asunci[oó]n|"
    r"chile|santiago de chile|brasil|s[aã]o paulo|\+598|\+595|\+56|\+55)\b")

RUIDO = {
    "propiedades", "inmobiliaria", "inmobiliarias", "negocios", "inmobiliarios",
    "bienes", "raices", "raíces", "servicios", "consultora", "consultoria",
    "gestion", "gestión", "broker", "brokers", "estate", "real", "grupo",
    "estudio", "y", "de", "la", "el", "los", "las", "del", "sa", "srl",
}
REDES = ("re/max", "remax", "century 21", "century21", "c21", "coldwell banker",
         "keller williams", "century", "sotheby")


def _normalizar(texto: str) -> str:
    texto = (texto or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ñ", "n"), ("ü", "u")):
        texto = texto.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def tokens_distintivos(nombre: str) -> set[str]:
    """Lo que queda del nombre sacando las palabras del rubro y de la red.

    'RE/MAX Focus' deja {focus}: lo que distingue a esa oficina de las otras
    191 de la red. Sin esto, cualquier pagina de RE/MAX satisface a cualquier
    oficina de RE/MAX, que es como `RE/MAX Focus` termino apuntando al perfil
    de un agente uruguayo.
    """
    base = _normalizar(nombre)
    for red in ("re max", "remax", "century 21", "century21", "c21",
                "coldwell banker", "keller williams"):
        base = base.replace(red, " ")
    fuera = {t for t in base.split() if t not in RUIDO and len(t) > 2}
    if not fuera:
        # 'Century 21 MM Real Estate' deja solo 'mm'. Descartarlo por corto
        # dejaria a esa oficina sin nada que la distinga de las otras.
        fuera = {t for t in base.split() if t not in RUIDO and len(t) >= 2}
    return fuera


def registrable(host: str) -> str:
    host = (host or "").lower().removeprefix("www.")
    partes = host.split(".")
    if len(partes) >= 3 and partes[-2] in ("com", "net", "org", "gob", "edu"):
        return ".".join(partes[-3:])
    return ".".join(partes[-2:]) if len(partes) >= 2 else host


def red_de(nombre_o_url: str) -> str | None:
    t = _normalizar(nombre_o_url)
    for red in REDES:
        if _normalizar(red) in t:
            return red
    return None


@dataclass
class Sitio:
    """Lo que se pudo leer de una candidata. `texto` vacío = no se pudo abrir.

    `html_bytes` existe para separar dos cosas que se parecen y no lo son: un
    dominio parkeado sirve poco HTML y poco texto; una aplicación JavaScript
    sirve MUCHO HTML y poco texto, porque el contenido lo pone el navegador.
    Sin este dato, las páginas de las redes inmobiliarias —que son SPAs— se
    clasificaban como parkeadas.
    """
    url: str
    titulo: str = ""
    texto: str = ""
    http: int | None = None
    html_bytes: int = 0


@dataclass
class VeredictoV2:
    clase: str
    confianza: str = BAJA
    tipo_de_sitio: str = DESCONOCIDO
    url: str | None = None
    evidencias: list[str] = field(default_factory=list)
    contras: list[str] = field(default_factory=list)
    razon: str = ""


# --------------------------------------------------------------------------
# A. ¿Qué es este sitio? (§3, §4, §5, §6)
# --------------------------------------------------------------------------

def _parece_agregador(sitio: Sitio) -> bool:
    """Muchas empresas distintas en la misma pagina.

    Un portal o un directorio listan decenas de inmobiliarias; el sitio de una
    inmobiliaria habla de una sola. No hace falta conocer el host para verlo.
    """
    texto = sitio.texto or ""
    marcas = len(re.findall(r"(?i)\binmobiliaria\b", texto))
    empresas = len(set(re.findall(
        r"(?i)\b([A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]{2,})\s+(?:propiedades|inmobiliaria)\b",
        texto)))
    return marcas >= 8 or empresas >= 5


def clasificar_sitio(sitio: Sitio, entidad: dict | None = None) -> str:
    """Qué es el candidato, antes de preguntar de quién es."""
    if sitio.http is None:
        return DESCONOCIDO
    if sitio.http >= 400:
        return DESCONOCIDO
    # Un 2xx con el cuerpo VACIO no es una pagina: es un desafio anti-bot.
    # `global.remax.com` y `remax.com.ar` devuelven HTTP 202 con cero bytes a
    # cualquier cliente que no ejecute JavaScript. Llamarlas parkeadas —que es
    # lo que hacia la regla de texto corto— descartaba 100 oficinas con 20.919
    # avisos, o sea el grupo de mayor inventario del universo.
    #
    # La pagina existe y probablemente es correcta. Lo que no tenemos es una
    # forma de leerla sin navegador, y eso se dice asi.
    if not (sitio.texto or "").strip() and sitio.html_bytes == 0:
        return DESCONOCIDO

    partes = urlsplit(sitio.url or "")
    host = partes.netloc.lower().removeprefix("www.")
    ruta = partes.path or "/"
    completo = f"{sitio.titulo} {sitio.texto}"
    texto_norm = _normalizar(completo)

    # --- parkeado / expirado. Va primero: responde 200 y parece vivo.
    if PARKING_HOST.search(host) or PARKING_QUERY.search(sitio.url or ""):
        return PARKED_DOMAIN
    if PARKING_TEXTO.search(completo):
        return PARKED_DOMAIN
    if len((sitio.texto or "").strip()) < 120:
        # Poco texto tiene DOS causas distintas y confundirlas sale caro.
        #
        # `mizrahi.com` servia 2 KB con su propio dominio como titulo: eso es
        # un dominio parkeado. Las paginas de RE/MAX y Century 21 sirven 200 KB
        # de HTML con casi nada de texto porque el contenido lo pone
        # JavaScript: eso es una aplicacion que no pudimos ejecutar.
        #
        # Llamar parkeadas a las segundas descarto 129 oficinas con 35.710
        # avisos en la primera corrida de este validador.
        if sitio.html_bytes >= 50_000:
            return DESCONOCIDO
        return PARKED_DOMAIN

    reg = registrable(host)
    if reg in SOCIALES:
        return SOCIAL_PROFILE
    if any(s in reg for s in MEDIOS) or RUTA_DE_NOTA.search(ruta):
        return NEWS_MEDIA
    if any(s in reg for s in DIRECTORIOS):
        return BUSINESS_DIRECTORY

    # Un host con seccion de terceros no es una inmobiliaria: es donde varias
    # se publican. Se pregunta ANTES que la red, porque un portal puede hablar
    # de RE/MAX sin ser RE/MAX.
    if RUTA_DE_TERCEROS.search(ruta):
        return PROPERTY_DETAIL_PAGE if RUTA_FICHA.search(ruta) else EXTERNAL_PORTAL

    red_host = red_de(host)
    if red_host:
        # Dominio de una red: puede ser la pagina de UNA oficina o el indice.
        # El indice y la pagina de oficina comparten prefijo -/offices/...- asi
        # que lo que decide es si DESPUES del segmento de directorio queda algo
        # que identifique a una oficina concreta.
        if ruta in ("/", "") or RUTA_LISTADO.search(ruta):
            return NETWORK_DIRECTORY
        indice = RUTA_INDICE.search(ruta)
        if indice:
            # Despues del segmento de indice tiene que quedar algo que nombre a
            # una oficina. `/directorio` a secas es el indice; `/offices/.../
            # remax-premium/42` es una oficina.
            resto = ruta[indice.end():].strip("/")
            if not resto or resto.isdigit():
                return NETWORK_DIRECTORY
        return NETWORK_OFFICE_PAGE

    if any(p in host for p in BOLSAS_DE_TRABAJO):
        return EXTERNAL_PORTAL
    if any(p in host for p in PORTALES):
        return PROPERTY_DETAIL_PAGE if RUTA_FICHA.search(ruta) else EXTERNAL_PORTAL
    if RUTA_FICHA.search(ruta) and _parece_agregador(sitio):
        return PROPERTY_DETAIL_PAGE
    if _parece_agregador(sitio):
        return EXTERNAL_PORTAL

    # --- ¿habla de propiedades? (§4)
    del_rubro = sum(1 for s in SENALES_RUBRO if s in texto_norm.replace(" ", " "))
    otro_rubro = sum(1 for s in SENALES_OTRO_RUBRO if s in texto_norm)
    if del_rubro == 0:
        return UNRELATED_BUSINESS
    if otro_rubro and del_rubro < 2:
        # Menciona "venta" pero vende otra cosa.
        return UNRELATED_BUSINESS
    if del_rubro < 2:
        return DESCONOCIDO
    return REAL_ESTATE_OFFICIAL_SITE


# --------------------------------------------------------------------------
# B. ¿De quién es? (§8, §9, §10)
# --------------------------------------------------------------------------

def _evidencias_de_identidad(sitio: Sitio, entidad: dict) -> tuple[list[str], list[str]]:
    a_favor: list[str] = []
    en_contra: list[str] = []
    nombre = entidad.get("nombre_original") or ""
    toks = tokens_distintivos(nombre)
    host = urlsplit(sitio.url or "").netloc.lower().removeprefix("www.")
    hostplano = re.sub(r"[^a-z0-9]", "", registrable(host).split(".")[0])
    texto_norm = _normalizar(f"{sitio.titulo} {sitio.texto}")

    # El nombre cuenta UNA vez, aparezca en el dominio, en el titulo o en el
    # cuerpo. Contarlo dos veces convertia un nombre generico en "dos
    # evidencias independientes", que es lo contrario de lo que pide el §10.
    nombre_norm = _normalizar(nombre)
    en_dominio = bool(toks and any(t in hostplano for t in toks))
    en_pagina = bool(
        (nombre_norm and nombre_norm in texto_norm)
        or (toks and sum(1 for t in toks if t in texto_norm) >= max(1, len(toks) - 1)))
    if en_dominio or en_pagina:
        donde = "el dominio" if en_dominio else "la pagina"
        a_favor.append(f"el nombre coincide en {donde}")

    zonas = [_normalizar(z) for z in (entidad.get("zonas_observadas") or [])]
    coinciden = [z for z in zonas if z and z in texto_norm]
    if coinciden:
        a_favor.append(f"menciona la zona {coinciden[0]}")

    mats = [str(m) for m in (entidad.get("matricula") or [])]
    if any(m and m in texto_norm for m in mats):
        a_favor.append("la matricula coincide")

    # --- guarda de pais (§8)
    if PAIS_OTRO.search(f"{sitio.titulo} {sitio.texto}") and not PAIS_AR.search(
            f"{sitio.titulo} {sitio.texto}"):
        en_contra.append("el sitio habla de otro pais y no de Argentina")

    # --- guarda de identidad cruzada (§9)
    #
    # Se mira el TITULO y el HOST, nunca el cuerpo pegado al titulo. Pegarlos
    # fabrica frases que no existen en ninguno de los dos: el titulo "RE/MAX
    # Premium - Palermo Nuevo" seguido del cuerpo "Propiedades en venta..."
    # producia la marca fantasma "Nuevo Propiedades", y con ella la guarda
    # rechazaba una oficina legitima.
    titulo_norm = _normalizar(sitio.titulo)
    nuestro_en_titulo = bool(toks and any(t in titulo_norm for t in toks))
    otras = set(re.findall(
        r"(?i)\b([A-ZÁÉÍÓÚÑ][\w'ÁÉÍÓÚÑáéíóúñ]{3,})\s+"
        r"(?:propiedades|inmobiliaria|bienes ra[ií]ces)", sitio.titulo or ""))
    ajenas = {o for o in otras if _normalizar(o) not in toks}
    if toks and ajenas and not nuestro_en_titulo and not any(
            t in hostplano for t in toks):
        # Ni el host ni el titulo son de esta agencia, y el titulo nombra otra.
        en_contra.append(
            f"el sitio es de otra inmobiliaria ({sorted(ajenas)[0]})")
    return a_favor, en_contra


def _oficina_correcta(sitio: Sitio, entidad: dict) -> bool:
    """La pagina nombra ESA oficina, no la red (§7)."""
    toks = tokens_distintivos(entidad.get("nombre_original") or "")
    if not toks:
        return False
    ruta = _normalizar(urlsplit(sitio.url or "").path)
    titulo = _normalizar(sitio.titulo)
    return any(t in ruta for t in toks) or any(t in titulo for t in toks)


def verificar(entidad: dict, candidatas: list[Sitio]) -> VeredictoV2:
    """El veredicto. Sin candidata que pase A, no se evalua B."""
    nombre = entidad.get("nombre_original") or ""
    toks = tokens_distintivos(nombre)
    generico = len(toks) <= 1

    mejor: VeredictoV2 | None = None
    vistos: list[str] = []

    for sitio in candidatas:
        tipo = clasificar_sitio(sitio, entidad)
        vistos.append(f"{urlsplit(sitio.url).netloc}={tipo}")

        if tipo in (PARKED_DOMAIN, NEWS_MEDIA, BUSINESS_DIRECTORY,
                    SOCIAL_PROFILE, UNRELATED_BUSINESS, NETWORK_DIRECTORY):
            continue
        if tipo in (EXTERNAL_PORTAL, PROPERTY_DETAIL_PAGE):
            if mejor is None:
                mejor = VeredictoV2(
                    clase=EXTERNAL_PORTAL_PROFILE, confianza=MEDIA,
                    tipo_de_sitio=tipo, url=sitio.url,
                    razon="presencia en un portal ajeno, no sitio propio")
            continue

        a_favor, en_contra = _evidencias_de_identidad(sitio, entidad)
        if en_contra:
            mejor = mejor or VeredictoV2(
                clase=IDENTITY_AMBIGUOUS, confianza=BAJA, tipo_de_sitio=tipo,
                url=sitio.url, evidencias=a_favor, contras=en_contra,
                razon=en_contra[0])
            continue

        # §10: nombre unico -> 1 evidencia fuerte; generico -> 2 independientes.
        minimo = 2 if generico else 1
        if tipo == NETWORK_OFFICE_PAGE:
            if not _oficina_correcta(sitio, entidad):
                mejor = mejor or VeredictoV2(
                    clase=REVIEW_REQUIRED, confianza=MEDIA,
                    tipo_de_sitio=NETWORK_DIRECTORY, url=sitio.url,
                    razon="pagina de la red que no nombra a esta oficina")
                continue
            return VeredictoV2(
                clase=OFFICIAL_OFFICE_PAGE, confianza=ALTA,
                tipo_de_sitio=tipo, url=sitio.url, evidencias=a_favor,
                razon="pagina propia de la oficina dentro de la red")

        if len(a_favor) >= minimo:
            return VeredictoV2(
                clase=OFFICIAL_WEB, confianza=ALTA, tipo_de_sitio=tipo,
                url=sitio.url, evidencias=a_favor,
                razon="sitio inmobiliario con identidad corroborada")
        if a_favor:
            mejor = mejor or VeredictoV2(
                clase=REVIEW_REQUIRED, confianza=MEDIA, tipo_de_sitio=tipo,
                url=sitio.url, evidencias=a_favor,
                razon=f"sitio inmobiliario pero {len(a_favor)} evidencia(s) "
                      f"para un nombre {'generico' if generico else 'unico'}")

    if mejor:
        return mejor
    if any(clasificar_sitio(s) == PARKED_DOMAIN for s in candidatas):
        return VeredictoV2(clase=INACTIVE_SOURCE, confianza=MEDIA,
                           tipo_de_sitio=PARKED_DOMAIN,
                           razon="el dominio existe pero esta parkeado o vacio")
    return VeredictoV2(clase=NO_OFFICIAL_WEB_FOUND, confianza=MEDIA,
                       razon="ninguna candidata es un sitio inmobiliario propio; "
                             f"vistas: {', '.join(vistos[:4])}")


def es_portal_url(url: str) -> bool:
    """¿La url es de un portal, un directorio, un medio o una red?

    Existe para que otros pasos puedan descartar candidatas sin bajarlas. No
    reemplaza a `clasificar_sitio`, que necesita el contenido: esto mira la url
    y nada mas, y por eso solo se usa para NO gastar una peticion.
    """
    from urllib.parse import urlsplit
    partes = urlsplit(url if "://" in url else "https://" + url)
    host = partes.netloc.lower().removeprefix("www.")
    reg = registrable(host)
    if reg in SOCIALES:
        return True
    if any(s in reg for s in MEDIOS) or any(s in reg for s in DIRECTORIOS):
        return True
    if any(p in host for p in PORTALES) or any(p in host for p in BOLSAS_DE_TRABAJO):
        return True
    return bool(RUTA_DE_TERCEROS.search(partes.path or "")
                or RUTA_DE_NOTA.search(partes.path or ""))

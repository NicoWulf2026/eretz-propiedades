#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scoring de identidad explicable entre una inmobiliaria y un sitio web.

La regla que gobierna este modulo: una URL equivocada es peor que ninguna. Una
casilla vacia se nota y alguien la completa; una URL falsa parece un dato bueno
y contamina todo lo que venga despues.

Por eso el scoring no es una caja negra ni una suma de parecidos. Cada señal
tiene un peso y un motivo, y cada decision guarda por que se tomo, de forma que
dentro de seis meses se pueda auditar sin reconstruir nada.

Tres cosas que lo diferencian de comparar nombres:

  - Las señales fuertes son las que una entidad NO comparte con otra por
    casualidad: telefono, email, direccion, matricula. El nombre es una señal
    media, porque dos inmobiliarias pueden llamarse igual en dos provincias.

  - Las señales negativas restan de verdad. Un telefono distinto o una ciudad
    incompatible no se compensan con que el dominio tenga el nombre adentro.

  - Un sitio que claramente vende otra cosa se RECHAZA antes de puntuar. Es el
    caso de `inmobiliarialopez.com` resultando ser una tienda de ropa: tiene el
    nombre, responde 200, tiene SSL, y no es la inmobiliaria. Ninguna cantidad
    de coincidencia de nombre deberia poder salvar eso.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")

SCORING_VERSION = "identity_scoring_v1"

# Estados de rechazo/diagnostico que este modulo puede producir.
OTHER_ENTITY = "CANDIDATE_REJECTED_OTHER_ENTITY"
HISTORICAL_INVALID = "HISTORICAL_URL_INVALID"
HISTORICAL_REPLACED = "HISTORICAL_URL_REPLACED"

# Pesos. Fuertes: cosas que dos entidades distintas no comparten por azar.
PESOS = {
    "telefono": 45,
    "email": 45,
    "matricula": 50,
    "direccion": 35,
    "razon_social": 30,
    "pagina_franquicia": 40,
    # Medias: coherentes pero reproducibles por otra entidad.
    "nombre_exacto": 25,
    "localidad": 18,
    "agente": 15,
    # Debiles: nunca alcanzan solas.
    "nombre_parcial": 8,
    "provincia": 5,
    "rubro_inmobiliario": 6,
}
PENAS = {
    "es_una_nota": -100,   # rechazo: el sitio habla DE la inmobiliaria
    "telefono_distinto": -35,
    "localidad_incompatible": -30,
    "otro_rubro": -100,     # rechazo efectivo
    "portal": -100,
    "estacionado": -100,
    "sin_rastro_del_nombre": -25,
}

UMBRAL_VERIFIED = 70
UMBRAL_ALTA = 45

# Rubros que delatan que el sitio no es de una inmobiliaria. La lista no
# pretende ser exhaustiva: alcanza con que cubra los casos que aparecen cuando
# un dominio con nombre parecido pertenece a otro negocio.
OTROS_RUBROS = {
    "indumentaria": r"\b(indumentaria|ropa|calzoncillo|remera|jeans|talles?|"
                    r"vestido|calzado|zapatilla|moda|boutique de ropa)\b",
    "gastronomia": r"\b(restaurante|men[uú] del d[ií]a|pizzer[ií]a|cafeter[ií]a|"
                   r"delivery de comida|parrilla)\b",
    "salud": r"\b(consultorio|odontolog|kinesiolog|turnos m[eé]dicos|obra social)\b",
    "juridico": r"\b(estudio jur[ií]dico|abogad[oa]s?|derecho penal|sucesiones)\b",
    "automotor": r"\b(concesionaria|0km|autom[oó]viles|repuestos|neum[aá]ticos)\b",
    "ecommerce": r"\b(carrito de compras|agregar al carrito|env[ií]os a todo el pa[ií]s|"
                 r"medios de pago|talle)\b",
    "construccion": r"\b(corral[oó]n|materiales de construcci[oó]n|ferreter[ií]a)\b",
}
# Vocabulario que confirma que SI es una inmobiliaria.
RUBRO_INMOBILIARIO = re.compile(
    r"\b(inmobiliaria|propiedades|bienes ra[ií]ces|alquiler(es)?|venta de (casas|"
    r"departamentos|inmuebles)|tasaci[oó]n|corredor inmobiliario|matr[ií]cula|"
    r"emprendimientos inmobiliarios|departamentos?|locales? comercial)\b", re.I)


@dataclass
class Señal:
    clave: str
    peso: int
    detalle: str = ""


@dataclass
class Puntaje:
    total: int = 0
    positivas: list[Señal] = field(default_factory=list)
    negativas: list[Señal] = field(default_factory=list)
    rubro_detectado: str | None = None
    scoring_version: str = SCORING_VERSION

    @property
    def rechazado_por_rubro(self) -> bool:
        return any(s.clave in ("otro_rubro", "es_una_nota") for s in self.negativas)

    @property
    def explicacion(self) -> str:
        pos = ", ".join(f"{s.clave}(+{s.peso})" for s in self.positivas) or "ninguna"
        neg = ", ".join(f"{s.clave}({s.peso})" for s in self.negativas)
        return f"total={self.total} | a favor: {pos}" + (f" | en contra: {neg}" if neg else "")


def _digitos(v: str | None) -> str:
    n = re.sub(r"\D", "", v or "")
    n = re.sub(r"^0*54", "", n)
    n = re.sub(r"^9", "", n)
    n = re.sub(r"^0", "", n)
    return n[-10:] if len(n) >= 8 else ""


def telefonos_del_texto(texto: str) -> set[str]:
    """Telefonos argentinos plausibles dentro del contenido del sitio."""
    out = set()
    for m in re.finditer(r"(?:\+?54)?[\s\-\.\(\)]*(?:9)?[\s\-\.\(\)]*"
                         r"(\d[\d\s\-\.\(\)]{7,16}\d)", texto or ""):
        t = _digitos(m.group(0))
        if t:
            out.add(t)
    return out


def emails_del_texto(texto: str) -> set[str]:
    return {m.group(0).lower()
            for m in re.finditer(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", texto or "", re.I)}


def detectar_otro_rubro(texto: str, nombre_entidad: str = "") -> str | None:
    """Devuelve el rubro ajeno detectado, si el sitio es claramente de otra cosa.

    Se exige que el vocabulario ajeno aparezca y que el inmobiliario NO aparezca.
    Una inmobiliaria puede nombrar `local comercial` sin ser una ferreteria, y
    una ferreteria no habla de tasaciones.

    El nombre de la entidad se descuenta del texto antes de buscar vocabulario
    inmobiliario. Si no, una tienda de ropa llamada "Lopez Propiedades" se
    salvaria sola: la palabra `propiedades` de su propio nombre alcanzaria para
    hacerla pasar por inmobiliaria. El nombre prueba como se llama el sitio, no
    a que se dedica.
    """
    if not texto:
        return None
    sin_nombre = texto
    for tok in (nombre_entidad or "").split():
        if len(tok) > 2:
            sin_nombre = re.sub(re.escape(tok), " ", sin_nombre, flags=re.I)
    if RUBRO_INMOBILIARIO.search(sin_nombre):
        return None
    bajo = d.strip_accents(texto.lower())
    for rubro, patron in OTROS_RUBROS.items():
        if len(re.findall(patron, bajo, re.I)) >= 2:
            return rubro
    return None


# Un articulo vive en una ruta profunda con slug largo; la web de una
# inmobiliaria vive en la raiz de su dominio o a un nivel.
ARTICULO = re.compile(r"^/[^/]+/[^/]*-[^/]*-[^/]*-[^/]*-", re.I)


def es_articulo(url: str) -> bool:
    """La URL tiene forma de nota, no de home de inmobiliaria."""
    from urllib.parse import urlsplit
    camino = urlsplit(url if "://" in url else "https://" + url).path
    if ARTICULO.match(camino):
        return True
    # /2026/03/titulo-largo-de-la-nota
    return bool(re.match(r"^/(19|20)[0-9][0-9]/", camino))


def puntuar(entidad: dict, sitio: dict) -> Puntaje:
    """Compara una inmobiliaria contra el contenido de un sitio.

    `entidad` usa lo que ERETZ y Roomix saben; `sitio` es lo que se leyo de la
    pagina: texto, titulo, telefonos, emails.
    """
    p = Puntaje()
    texto = f"{sitio.get('titulo','')} {sitio.get('texto','')}"
    bajo = d.strip_accents(texto.lower())

    # --- rechazo: el sitio es una nota SOBRE la inmobiliaria ---
    url = sitio.get("url") or ""
    if url and es_articulo(url):
        p.negativas.append(Señal("es_una_nota", PENAS["es_una_nota"],
                                 "la URL tiene forma de articulo, no de sitio propio"))
        p.total = PENAS["es_una_nota"]
        return p

    # --- rechazo por rubro, antes de puntuar nada ---
    rubro = detectar_otro_rubro(texto, entidad.get("nombre_original") or "")
    if rubro:
        p.rubro_detectado = rubro
        p.negativas.append(Señal("otro_rubro", PENAS["otro_rubro"],
                                 f"el sitio es de {rubro}, no una inmobiliaria"))
        p.total = PENAS["otro_rubro"]
        return p

    # --- señales fuertes ---
    tel_ent = _digitos(entidad.get("telefono"))
    tels_sitio = telefonos_del_texto(texto)
    if tel_ent and tels_sitio:
        if tel_ent in tels_sitio:
            p.positivas.append(Señal("telefono", PESOS["telefono"], tel_ent))
        else:
            p.negativas.append(Señal("telefono_distinto", PENAS["telefono_distinto"],
                                     "el sitio publica otros telefonos"))

    mail_ent = (entidad.get("email") or "").strip().lower()
    if mail_ent and mail_ent in emails_del_texto(texto):
        p.positivas.append(Señal("email", PESOS["email"], mail_ent))

    for m in entidad.get("matricula") or []:
        if d.norm_name(m).replace(" ", "") in bajo.replace(" ", ""):
            p.positivas.append(Señal("matricula", PESOS["matricula"], m))
            break

    dire = d.norm_name(entidad.get("direccion") or "")
    if dire and len(dire) > 8 and dire in d.norm_name(texto):
        p.positivas.append(Señal("direccion", PESOS["direccion"], dire[:40]))

    if entidad.get("official_office_page"):
        p.positivas.append(Señal("pagina_franquicia", PESOS["pagina_franquicia"],
                                 "perfil oficial dentro del dominio de la red"))

    # --- señales medias ---
    wd = _load("agency_web_discovery")
    toks = wd.tokens_distintivos(entidad.get("nombre_original") or "")
    presentes = {t for t in toks if t in bajo}
    if toks and presentes == toks:
        p.positivas.append(Señal("nombre_exacto", PESOS["nombre_exacto"]))
    elif toks and len(presentes) / len(toks) >= 0.5:
        p.positivas.append(Señal("nombre_parcial", PESOS["nombre_parcial"],
                                 f"{len(presentes)}/{len(toks)} tokens"))
    elif toks:
        p.negativas.append(Señal("sin_rastro_del_nombre", PENAS["sin_rastro_del_nombre"]))

    ciudad = d.norm_name(entidad.get("ciudad") or "")
    zonas = [d.norm_name(z) for z in (entidad.get("zonas_observadas") or [])]
    localidades = [x for x in [ciudad] + zonas if x and len(x) > 3]
    if localidades:
        if any(loc in d.norm_name(texto) for loc in localidades):
            p.positivas.append(Señal("localidad", PESOS["localidad"], localidades[0]))
        elif sitio.get("localidades_detectadas"):
            # El sitio dice claramente otra ciudad: es el caso de las homonimas.
            p.negativas.append(Señal("localidad_incompatible", PENAS["localidad_incompatible"],
                                     "el sitio opera en otra localidad"))

    prov = d.norm_name(entidad.get("provincia") or "")
    if prov and len(prov) > 3 and prov in d.norm_name(texto):
        p.positivas.append(Señal("provincia", PESOS["provincia"], prov))

    sin_nombre = texto
    for tok in (entidad.get("nombre_original") or "").split():
        if len(tok) > 2:
            sin_nombre = re.sub(re.escape(tok), " ", sin_nombre, flags=re.I)
    if RUBRO_INMOBILIARIO.search(sin_nombre):
        p.positivas.append(Señal("rubro_inmobiliario", PESOS["rubro_inmobiliario"]))

    p.total = sum(s.peso for s in p.positivas) + sum(s.peso for s in p.negativas)
    return p


def clasificar(p: Puntaje) -> str:
    """Traduce el puntaje a decision.

    Los umbrales estan puestos de modo que ninguna combinacion de señales
    debiles alcance por si sola: nombre parcial + provincia + rubro suman 19,
    muy por debajo del umbral de alta confianza.
    """
    if p.rechazado_por_rubro:
        return OTHER_ENTITY
    if p.total >= UMBRAL_VERIFIED:
        return "VERIFIED"
    if p.total >= UMBRAL_ALTA:
        return "HIGH_CONFIDENCE"
    return "INSUFICIENTE"


def diagnosticar_url_historica(previa: str, cand: dict | None) -> dict:
    """Que paso con la URL que ERETZ venia usando y no funcionaba.

    La hipotesis por defecto NO es que el sitio sea imposible de scrapear: es
    que la URL dejo de ser la correcta. Eso se comprueba antes de culpar al
    parser.
    """
    wd = _load("agency_web_discovery")
    if not previa:
        return {"estado": "sin_url_previa"}
    if wd.es_portal(previa):
        return {"estado": HISTORICAL_INVALID,
                "detalle": "la fuente guardada era un portal, no la web de la inmobiliaria"}
    if cand is None or cand.get("http") is None:
        return {"estado": HISTORICAL_INVALID, "detalle": "el dominio ya no responde"}
    if cand.get("http", 0) >= 400:
        return {"estado": HISTORICAL_INVALID, "detalle": f"responde {cand['http']}"}

    final = cand.get("url") or previa
    if wd.dominio(final) != wd.dominio(previa):
        return {"estado": HISTORICAL_REPLACED, "detalle": "redirige a otro dominio",
                "nuevo_dominio": final}
    rubro = detectar_otro_rubro(f"{cand.get('titulo','')} {cand.get('texto','')}")
    if rubro:
        return {"estado": HISTORICAL_INVALID,
                "detalle": f"el dominio hoy pertenece a otro rubro ({rubro})"}
    return {"estado": "vigente", "detalle": "la URL sigue siendo de la inmobiliaria"}


# ------------------------------------------------------- scrapeability
SCRAPE_READY = "SCRAPE_SOURCE_READY"
SCRAPE_JS = "SCRAPE_SOURCE_REQUIRES_JS"
SCRAPE_BLOCKED = "SCRAPE_SOURCE_BLOCKED"
SCRAPE_UNKNOWN = "SCRAPE_SOURCE_UNKNOWN"
SCRAPE_NO_LISTINGS = "SCRAPE_SOURCE_NO_LISTINGS"


def diagnosticar_scrapeabilidad(sitio: dict) -> dict:
    """Diagnostico superficial. NO scrapea: solo mira lo que ya se bajo."""
    html = sitio.get("html") or sitio.get("texto") or ""
    bajo = html.lower()
    http = sitio.get("http")
    plataforma = None
    for nombre, patron in (("wordpress", "wp-content"), ("next.js", "__next_data__"),
                           ("react", "data-reactroot"), ("wix", "wix.com"),
                           ("tokko", "tokkobroker"), ("mediacore", "mediacore")):
        if patron in bajo:
            plataforma = nombre
            break
    if http in (403, 503) or "cloudflare" in bajo and "challenge" in bajo:
        estado = SCRAPE_BLOCKED
    elif plataforma in ("next.js", "react") and "propiedad" not in bajo:
        estado = SCRAPE_JS
    elif re.search(r"(propiedad|inmueble|ficha|listado|/venta/|/alquiler/)", bajo):
        estado = SCRAPE_READY
    elif http == 200:
        estado = SCRAPE_NO_LISTINGS
    else:
        estado = SCRAPE_UNKNOWN
    return {"scrapeability_status": estado, "plataforma": plataforma}

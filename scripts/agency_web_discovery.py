#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Descubrimiento y verificacion de la web oficial de cada inmobiliaria.

Roomix no publica la web del anunciante -verificado en la ficha: solo hay nombre
y logo-, asi que el dominio hay que encontrarlo afuera y despues demostrar que
es de esa inmobiliaria y no de otra.

El riesgo de esta fase no es no encontrar webs. Es asignar la equivocada. Un
apellido comun, dos inmobiliarias homonimas en provincias distintas, un dominio
abandonado que hoy vende otra cosa, o -el mas facil de cometer- poner
`remax.com.ar` como web de las 191 oficinas de la red. Todos esos casos producen
un dato que parece bueno y no lo es.

De ahi las tres reglas del modulo:

  - un portal nunca es web oficial. Zonaprop, Argenprop, Mercado Libre,
    Instagram y companiaortan EVIDENCIA para llegar al dominio, nunca lo
    sustituyen;
  - el dominio de una franquicia no es el dominio de una oficina. Si la oficina
    tiene perfil dentro del dominio de la red, eso es `official_office_page` y
    es algo distinto de `official_domain`;
  - un HTTP 200 no demuestra propiedad. Hace falta que el sitio hable de la
    misma entidad: nombre, localidad, telefono o matricula.

Ante duda: AMBIGUOUS. Nunca inventar.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


d = _load("eretz_dedupe")

VERIFIER_VERSION = "web_verifier_v1"

VERIFIED = "OFFICIAL_WEB_VERIFIED"
HIGH_CONFIDENCE = "OFFICIAL_WEB_HIGH_CONFIDENCE"
AMBIGUOUS = "OFFICIAL_WEB_AMBIGUOUS"
NOT_FOUND = "OFFICIAL_WEB_NOT_FOUND"
INACTIVE = "OFFICIAL_WEB_INACTIVE"
NO_SITE = "NO_INDEPENDENT_WEBSITE"
# Estados OPERATIVOS, no resultados. Existen para no mentir en el artefacto:
# NOT_FOUND significa "se busco y no hay", y usarlo por falta de credencial o
# por un fallo del proveedor convertiria una limitacion nuestra en un hecho
# sobre la inmobiliaria.
PENDING = "SEARCH_API_PENDING"
SEARCH_ERROR = "SEARCH_API_ERROR"
OPERATIVOS = (PENDING, SEARCH_ERROR)

# Nunca son web oficial de una inmobiliaria. Sirven como evidencia.
PORTALES = {
    "zonaprop.com.ar", "zonaprop.com", "argenprop.com", "mercadolibre.com.ar",
    "properati.com.ar", "properati.com", "inmuebles24.com", "roomix.ai",
    "inmoclick.com.ar", "clasificados.lavoz.com.ar", "plusvalia.com",
    "icasas.com.ar", "buscadorprop.com.ar", "demicasa.com", "puntopropiedad.com",
    "inmobusqueda.com.ar", "meridianoinmobiliario.com", "clasificadosrn.com.ar",
    # Secciones inmobiliarias de diarios: listan la inmobiliaria, no son suyas.
    "inmuebles.clarin.com", "clasificados.clarin.com", "inmuebles.lanacion.com.ar",
    # Agregadores que republican avisos de terceros.
    "trovitargentina.com.ar", "trovit.com.ar", "trovit.com", "mitula.com.ar",
    "nestoria.com.ar", "nuroa.com.ar", "hogar360.com.ar",
}
# Bolsas de trabajo: un aviso de empleo NOMBRA a la inmobiliaria, no es su web.
EMPLEO = {
    "computrabajo.com", "ar.computrabajo.com", "bumeran.com.ar", "zonajobs.com.ar",
    "indeed.com", "ar.indeed.com", "glassdoor.com", "jobatus.com.ar", "empleos.net",
}
# Medios. Publican SOBRE una inmobiliaria; su sitio no es el de ella.
MEDIOS = {
    "clarin.com", "lanacion.com.ar", "infobae.com", "pagina12.com.ar",
    "ambito.com", "cronista.com", "lavoz.com.ar", "losandes.com.ar",
    "rionegro.com.ar", "lacapital.com.ar", "eldia.com", "lagaceta.com.ar",
    "perfil.com", "iprofesional.com", "revistaareatres.com.ar", "arquitecturaydiseno.es",
}
REDES = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "wa.me", "api.whatsapp.com", "t.me",
}
AGREGADORES = {
    "google.com", "maps.google.com", "goo.gl", "maps.app.goo.gl",
    "paginasamarillas.com.ar", "cylex.com.ar", "yelp.com", "linktr.ee",
    "sites.google.com", "wixsite.com", "blogspot.com", "wordpress.com",
    # Directorios de empresas: describen a la inmobiliaria, no son suyos.
    "crunchbase.com", "zoominfo.com", "apollo.io", "rocketreach.co",
    "opencorporates.com", "dnb.com", "empresite.com", "informacion-empresas.co",
    "guiaempresas.com.ar", "nosis.com", "universidad-de-empresas.com",
    # Indices de los propios buscadores: Exa devolvio su pagina de la
    # organizacion como si fuera la web de la inmobiliaria.
    "exa.ai", "tavily.com", "jina.ai", "serper.dev", "perplexity.ai",
}
NO_OFICIALES = PORTALES | MEDIOS | EMPLEO | REDES | AGREGADORES

# Dominios de red: valen para la pagina de oficina, nunca como dominio propio.
DOMINIOS_FRANQUICIA = {
    "remax.com.ar": "RE/MAX", "remax.com": "RE/MAX",
    "century21.com.ar": "Century 21", "century21global.com": "Century 21",
    "coldwellbanker.com.ar": "Coldwell Banker", "coldwellbanker.com": "Coldwell Banker",
    "kwargentina.com": "Keller Williams", "kw.com": "Keller Williams",
    "toribioachaval.com": "Toribio Achaval", "interwin.com.ar": "Interwin",
}

# Sitio estacionado o en venta: responde 200 y no es la inmobiliaria.
ESTACIONADO = re.compile(
    r"(dominio en venta|domain (is )?for sale|parked (domain|free)|comprar este dominio|"
    r"sedo\.com|dan\.com|godaddy.*parking|en construccion|coming soon|proximamente)", re.I)


def dominio(url: str) -> str:
    """Dominio registrable, sin www."""
    if not url:
        return ""
    s = re.sub(r"^\w+://", "", url.strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    return re.sub(r"^www\.", "", s)


# Marcas de portal, comparadas contra CADA ETIQUETA del dominio y nunca como
# subcadena. La lista de arriba es de dominios exactos y se quedo corta:
# `buscainmueble.com` figuraba como web oficial de 4 agencias de la cola y
# produjo 295 «propiedades» que eran paginas de categoria del portal -las
# MISMAS 98 para tres agencias distintas-. `verificador_identidad_v2` ya lo
# conocia; esta lista, que es la que consulta el certificador, no. Otra vez
# la misma regla escrita en dos lugares que no se hablan, y por eso
# `test_MUERDE_las_dos_listas_de_portales_no_pueden_divergir` las compara.
#
# Por NOMBRE REGISTRABLE y no por subcadena: `navent` es la duena de Zonaprop
# e `inmobiliarianaventura.com.ar` es una inmobiliaria. Tampoco por cualquier
# etiqueta: `zonaprop.com.ar.official.test` no es Zonaprop, es un sitio de
# `official.test` que se llama asi -lo fija un test que ya existia-. Las
# redes de franquicia
# -RE/MAX, Century 21- no van aca: su pagina de oficina ES la casa de la
# inmobiliaria, y se tratan en `DOMINIOS_FRANQUICIA`.
PORTALES_POR_NOMBRE = {
    "zonaprop", "argenprop", "mercadolibre", "properati", "inmoup",
    "puntoclick", "buscainmueble", "inmobusqueda", "icasas", "lamudi",
    "toctocventas", "navent", "clasificados", "yably", "slideprop",
    "comunidadinmobiliaria", "redinmosoft", "choza", "agroads", "inmoclick",
    "realedo", "mudafy", "apuntavamos", "todoprops", "datoinmobiliario",
    # Medidos el 25-09 con identidad READY: `proppies` (842 fichas de
    # `benjamin ferreyra`), `propia` (portal de Rosario), y tres directorios.
    "proppies", "propia", "liderprop", "lujanprop", "aspenbienesraices",
}


def es_portal(url: str) -> bool:
    dom = dominio(url)
    if any(dom == p or dom.endswith("." + p) for p in NO_OFICIALES):
        return True
    return nombre_registrable(dom) in PORTALES_POR_NOMBRE


def nombre_registrable(dom: str) -> str:
    """`buscainmueble` de `www.buscainmueble.com`, `inmoup` de `inmoup.com.ar`.

    El mismo corte que `verificador_identidad_v2.registrable`, que queda
    fuera de la huella: por eso se escribe aca y no se importa, y
    `test_el_nombre_registrable_coincide_con_el_del_verificador` los compara.
    """
    partes = (dom or "").lower().removeprefix("www.").split(".")
    if len(partes) >= 3 and partes[-2] in ("com", "net", "org", "gob", "edu"):
        return partes[-3]
    return partes[-2] if len(partes) >= 2 else (dom or "")


def franquicia_de_dominio(url: str) -> str | None:
    dom = dominio(url)
    for base, marca in DOMINIOS_FRANQUICIA.items():
        if dom == base or dom.endswith("." + base):
            return marca
    return None


def es_pagina_de_oficina(url: str) -> bool:
    """URL dentro del dominio de la red que apunta a UNA oficina.

    `remax.com.ar` a secas es la red: vale para 191 oficinas y por eso no
    identifica a ninguna. `remax.com.ar/oficinas/ultra` si identifica.
    """
    if not franquicia_de_dominio(url):
        return False
    camino = urlsplit(url if "://" in url else "https://" + url).path.strip("/")
    return bool(camino) and camino not in ("es", "en", "ar")


@dataclass
class Candidata:
    url: str
    origen: str = "busqueda"
    titulo: str = ""
    texto: str = ""
    http: int | None = None
    redirects: list[str] = field(default_factory=list)


@dataclass
class Veredicto:
    estado: str
    official_web: str | None = None
    official_office_page: str | None = None
    senales: list[str] = field(default_factory=list)
    contras: list[str] = field(default_factory=list)
    confianza: float = 0.0
    razon: str = ""
    verifier_version: str = VERIFIER_VERSION


# Palabras del rubro: las comparten todas, no distinguen a nadie.
RUIDO = {
    "propiedades", "inmobiliaria", "inmobiliarias", "negocios", "inmobiliarios",
    "bienes", "raices", "servicios", "consultora", "consultoria", "gestion",
    "broker", "brokers", "estate", "real", "grupo", "estudio", "y", "de", "la",
    "el", "los", "las", "del",
}


def tokens_distintivos(nombre: str) -> set[str]:
    return {t for t in d.norm_name(nombre).split() if t not in RUIDO and len(t) > 2}


def verificar(entidad: dict, candidatas: list[Candidata]) -> Veredicto:
    """Decide el estado web de una entidad a partir de sus candidatas."""
    nombre = entidad.get("nombre_original") or ""
    red = entidad.get("red_franquicia")
    zonas = " ".join(entidad.get("zonas_observadas") or [])
    mats = set(entidad.get("matricula") or [])
    toks = tokens_distintivos(nombre)

    propias: list[tuple[float, Candidata, list[str]]] = []
    oficina: str | None = None
    contras: list[str] = []

    for c in candidatas:
        if not c.url:
            continue

        # La pagina de oficina dentro del dominio de la red se guarda aparte y
        # no compite como dominio propio.
        marca = franquicia_de_dominio(c.url)
        if marca:
            if es_pagina_de_oficina(c.url) and (not red or marca == red):
                oficina = oficina or c.url
            else:
                contras.append(f"dominio de red sin oficina ({dominio(c.url)})")
            continue

        if es_portal(c.url):
            continue  # evidencia, nunca web oficial

        if c.http is not None and c.http >= 400:
            contras.append(f"{dominio(c.url)} responde {c.http}")
            continue

        blob = d.strip_accents(f"{c.titulo} {c.texto}".lower())
        if ESTACIONADO.search(blob):
            contras.append(f"{dominio(c.url)} parece estacionado")
            continue

        senales: list[str] = []
        presentes = {t for t in toks if t in blob}
        cobertura = len(presentes) / len(toks) if toks else 0.0
        if toks and presentes == toks:
            senales.append("nombre completo en el sitio")
        elif cobertura >= 0.5:
            senales.append(f"nombre parcial en el sitio ({cobertura:.0%})")

        dom_txt = d.strip_accents(dominio(c.url).split(".")[0].replace("-", ""))
        if toks and any(t in dom_txt for t in toks if len(t) >= 4):
            senales.append("nucleo del nombre en el dominio")

        if zonas:
            zt = [z for z in d.norm_name(zonas).split() if len(z) > 3]
            if zt and any(z in blob for z in zt):
                senales.append("localidad coincide")

        for m in mats:
            if d.norm_name(m).replace(" ", "") in blob.replace(" ", ""):
                senales.append(f"matricula {m}")

        if not senales:
            continue
        fuerte = sum(1 for s in senales
                     if s.startswith(("matricula", "nombre completo", "nucleo del nombre")))
        puntaje = cobertura + 0.5 * fuerte + (0.3 if "localidad coincide" in senales else 0.0)
        propias.append((puntaje, c, senales))

    propias.sort(key=lambda x: -x[0])

    if not propias:
        if oficina:
            return Veredicto(NO_SITE, None, oficina,
                             ["perfil oficial dentro del dominio de la red"], contras, 0.6,
                             "sin dominio independiente; se conserva la pagina de oficina")
        if any("responde" in x for x in contras):
            return Veredicto(INACTIVE, None, None, [], contras, 0.3,
                             "el dominio parece de la entidad pero no responde")
        return Veredicto(NOT_FOUND, None, None, [], contras, 0.0,
                         "ninguna candidata resiste la verificacion")

    mejor, cand, senales = propias[0]

    # Dos dominios propios igualmente sostenidos: es el caso de las homonimas.
    # Elegir uno seria inventar.
    if len(propias) > 1 and propias[1][0] >= mejor - 0.15:
        return Veredicto(
            AMBIGUOUS, None, oficina, senales,
            contras + [f"otra candidata igual de fuerte: {dominio(propias[1][1].url)}"],
            0.4, "mas de un dominio plausible; hace falta revision humana")

    con_matricula = any(s.startswith("matricula") for s in senales)
    nombre_completo = any(s.startswith("nombre completo") for s in senales)
    localidad = "localidad coincide" in senales

    if con_matricula or (nombre_completo and localidad):
        return Veredicto(VERIFIED, cand.url, oficina, senales, contras,
                         min(0.95, 0.7 + mejor / 10),
                         "identidad confirmada por evidencia independiente del nombre")
    if mejor >= 0.8:
        return Veredicto(HIGH_CONFIDENCE, cand.url, oficina, senales, contras, 0.7,
                         "evidencia consistente pero sin confirmacion independiente")
    return Veredicto(AMBIGUOUS, None, oficina, senales, contras, 0.4,
                     "evidencia insuficiente para asignar el dominio")


def fila_de_salida(entidad: dict, v: Veredicto, candidatas: list[Candidata]) -> dict:
    """Fila del agency_web_directory. Determinista y reanudable."""
    return {
        "canonical_agency_id": entidad.get("stable_id"),
        "nombre": entidad.get("nombre_original"),
        "nombre_normalizado": entidad.get("nombre_normalizado"),
        "tipo": entidad.get("tipo"),
        "red_franquicia": entidad.get("red_franquicia"),
        "zonas_observadas": entidad.get("zonas_observadas"),
        "roomix_agent_ids": entidad.get("raw_agent_ids"),
        "eretz_status": entidad.get("clasificacion_eretz"),
        "current_eretz_web": entidad.get("current_eretz_web"),
        "discovered_domain": v.official_web,
        "official_office_page": v.official_office_page,
        "official_web_status": v.estado,
        "confidence": round(v.confianza, 3),
        "evidence": [{"url": c.url, "origen": c.origen, "http": c.http,
                      "redirects": c.redirects} for c in candidatas][:10],
        "senales": v.senales,
        "contras": v.contras,
        "reason": v.razon,
        "verifier_version": v.verifier_version,
    }


def cargar_hechas(salida: Path) -> set[str]:
    """Reanudable: una entidad ya resuelta no se vuelve a investigar."""
    if not salida.exists():
        return set()
    return {json.loads(l)["canonical_agency_id"]
            for l in salida.open(encoding="utf-8") if l.strip()}


# --------------------------------------------------------- auditoria ERETZ
CORRECTA = "correcta"
REDIRECT_OK = "redirect_valido"
MUERTA = "dominio_muerto"
OTRA_ENTIDAD = "otra_entidad"
PORTAL = "portal_generico"
FALTANTE = "missing"


def auditar_web_eretz(entidad: dict, cand: "Candidata | None") -> dict:
    """Estado de la web que ERETZ ya tenia cargada.

    No se asume que sea correcta. Una web vieja apuntando a otra entidad es peor
    que no tener ninguna: parece un dato y manda a la persona al lugar
    equivocado.
    """
    actual = (entidad.get("current_eretz_web") or "").strip()
    if not actual:
        return {"estado": FALTANTE, "detalle": "ERETZ no tiene web para esta entidad"}
    if es_portal(actual):
        return {"estado": PORTAL, "detalle": f"{dominio(actual)} es un portal, no un sitio propio"}
    if cand is None or cand.http is None:
        return {"estado": MUERTA, "detalle": "el dominio no responde"}
    if cand.http >= 400:
        return {"estado": MUERTA, "detalle": f"responde {cand.http}"}

    v = verificar(entidad, [cand])
    if v.estado in (VERIFIED, HIGH_CONFIDENCE):
        redirigio = bool(cand.redirects) and dominio(cand.url) != dominio(actual)
        return {"estado": REDIRECT_OK if redirigio else CORRECTA,
                "detalle": v.explicacion if hasattr(v, "explicacion") else v.razon,
                "destino": cand.url}
    return {"estado": OTRA_ENTIDAD,
            "detalle": "responde pero no hay evidencia de que sea esta inmobiliaria"}

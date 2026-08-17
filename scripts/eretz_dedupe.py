#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Motor de deduplicacion de inmobiliarias, reutilizable.

Nace de un problema concreto: el cruce de Agency Coverage decidia identidad
mirando una sola columna, `nombre_normalizado`. Eso fallo de dos maneras
distintas y ninguna de las dos era culpa del nombre. Primero, 1.983 de 7.003
filas de main tienen esa columna en NULL, asi que quedaban invisibles por mas
que el nombre coincidiera exactamente. Segundo, dos oficinas distintas de la
misma red normalizan casi igual y nada las separaba.

De ahi las dos decisiones de diseno de este modulo:

  - la clave nunca se lee de una columna, se CALCULA a partir del nombre, para
    que una fila sin normalizar valga lo mismo que una normalizada;
  - la identidad se decide con varias senales independientes, y una sola senal
    fuerte no alcanza para fusionar si otra senal la contradice.

El estado AMBIGUOUS existe para no fusionar. No es un fallo del motor: es el
motor negandose a adivinar.
"""
from __future__ import annotations

import html as _html
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

MATCHER_VERSION = "dedupe_v1"

# Sufijos de rubro: no distinguen una inmobiliaria de otra.
NOISE = (
    " propiedades ", " inmobiliaria ", " inmobiliarias ", " negocios ",
    " inmobiliarios ", " bienes ", " raices ", " servicios ", " consultora ",
    " consultoria ", " gestion ", " broker ", " brokers ", " estate ",
    " real ", " grupo ", " estudio ", " emprendimientos ", " desarrollos ",
)

# Dominios que no identifican a nadie: son portales o redes sociales.
DOMINIOS_GENERICOS = {
    "zonaprop.com.ar", "argenprop.com", "mercadolibre.com.ar", "properati.com.ar",
    "facebook.com", "instagram.com", "wa.me", "api.whatsapp.com", "linktr.ee",
    "sites.google.com", "wixsite.com", "blogspot.com", "roomix.ai",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_name(raw: str) -> str:
    """Clave conservadora para comparar. NUNCA reemplaza al raw.

    Identica a la de `agency_crosswalk.norm_name` a proposito: si el motor de
    dedupe normalizara distinto que el cruce, las dos etapas hablarian de
    entidades distintas con la misma palabra.
    """
    s = _html.unescape(raw or "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = strip_accents(s.lower())
    s = s.replace("&", " y ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+(sa|srl|sas|sh|scs)$", "", s)


def norm_core(raw: str) -> str:
    """Nucleo del nombre: quita sufijos de rubro. Solo para comparar."""
    s = " " + norm_name(raw) + " "
    for n in NOISE:
        s = s.replace(n, " ")
    return re.sub(r"\s+", " ", s).strip()


def dominio(web: str | None) -> str:
    """Dominio registrable, sin www ni subdominios de portal."""
    if not web:
        return ""
    s = re.sub(r"^\w+://", "", (web or "").strip().lower())
    s = s.split("/")[0].split("?")[0].split(":")[0]
    s = re.sub(r"^www\.", "", s)
    if not s or "." not in s:
        return ""
    return "" if any(s == g or s.endswith("." + g) for g in DOMINIOS_GENERICOS) else s


def telefono(valor: str | None) -> str:
    """Solo digitos, sin prefijos de pais ni el 9 de celular argentino.

    Sin esto `+54 9 11 4555-1234` y `011 4555-1234` se leen como telefonos
    distintos siendo el mismo.
    """
    d = re.sub(r"\D", "", valor or "")
    if not d:
        return ""
    d = re.sub(r"^0*54", "", d)
    d = re.sub(r"^9", "", d)
    d = re.sub(r"^0", "", d)
    return d[-10:] if len(d) >= 8 else ""


def email(valor: str | None) -> str:
    v = (valor or "").strip().lower()
    return v if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v) else ""


def localidad(ciudad: str | None, provincia: str | None) -> str:
    c, p = norm_name(ciudad or ""), norm_name(provincia or "")
    return f"{c}|{p}".strip("|")


# Matriculas argentinas embebidas en el nombre. Identifican con mucha fuerza.
MAT_RE = re.compile(
    r"\b(cucicba|cmcpsi|cmcpdjlp|cmcpdsn|cpi|cmcp[a-z]{0,6}|cscoc)\s*[nº#:\-]*\s*(\d{3,6})\b",
    re.I)


def matriculas(raw: str) -> frozenset[str]:
    return frozenset(f"{m.group(1).upper()} {m.group(2)}" for m in MAT_RE.finditer(raw or ""))


@dataclass(frozen=True)
class Entidad:
    """Una inmobiliaria vista desde cualquier tabla u origen."""
    ident: str
    nombre: str
    web: str | None = None
    telefono_raw: str | None = None
    email_raw: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    fuente: str | None = None
    # `nombre_normalizado` de la tabla, si existe. Se ACEPTA pero no se
    # necesita: la clave se recalcula igual. Una fila con NULL vale lo mismo.
    normalizado_guardado: str | None = None

    @property
    def norm(self) -> str:
        return self.normalizado_guardado.strip().lower() if (
            self.normalizado_guardado or "").strip() else norm_name(self.nombre)

    @property
    def norm_calculado(self) -> str:
        return norm_name(self.nombre)

    @property
    def core(self) -> str:
        return norm_core(self.nombre)

    @property
    def dom(self) -> str:
        return dominio(self.web)

    @property
    def tel(self) -> str:
        return telefono(self.telefono_raw)

    @property
    def mail(self) -> str:
        return email(self.email_raw)

    @property
    def loc(self) -> str:
        return localidad(self.ciudad, self.provincia)

    @property
    def mats(self) -> frozenset[str]:
        return matriculas(self.nombre)


EXACT = "EXACT"
HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
AMBIGUOUS = "AMBIGUOUS"
DISTINCT = "DISTINCT"
INSUFFICIENT = "INSUFFICIENT"


@dataclass
class Veredicto:
    estado: str
    senales: list[str] = field(default_factory=list)
    contras: list[str] = field(default_factory=list)
    similitud: float = 0.0
    matcher_version: str = MATCHER_VERSION

    @property
    def explicacion(self) -> str:
        a = " + ".join(self.senales) or "sin senales"
        return a if not self.contras else f"{a} / contra: {' + '.join(self.contras)}"


def _distinta_localidad(a: Entidad, b: Entidad) -> bool:
    """Solo cuenta como contradiccion si AMBAS tienen localidad cargada.

    Un dato ausente no es un desacuerdo. Tratarlo como tal fue lo que llevo a
    descartar coincidencias buenas contra filas historicas incompletas.
    """
    return bool(a.loc and b.loc and a.loc != b.loc)


def comparar(a: Entidad, b: Entidad) -> Veredicto:
    """Decide si dos entidades son la misma, y explica por que."""
    senales: list[str] = []
    contras: list[str] = []

    na, nb = a.norm_calculado, b.norm_calculado
    sim = SequenceMatcher(None, na, nb).ratio() if na and nb else 0.0

    if not na or not nb or min(len(na), len(nb)) < 4:
        return Veredicto(INSUFFICIENT, ["nombre demasiado corto o vacio"], [], sim)

    # --- senales fuertes, cada una suficiente por si sola para sospechar ---
    if a.mats and b.mats and a.mats & b.mats:
        senales.append(f"matricula compartida ({sorted(a.mats & b.mats)[0]})")
    if a.dom and a.dom == b.dom:
        senales.append(f"dominio ({a.dom})")
    if a.mail and a.mail == b.mail:
        senales.append("email")
    if a.tel and a.tel == b.tel:
        senales.append("telefono")

    nombre_igual = na == nb
    if nombre_igual:
        senales.append("nombre normalizado identico")
    elif a.core and a.core == b.core:
        senales.append(f"nucleo identico ({a.core})")
    elif sim >= 0.92:
        senales.append(f"nombre casi identico ({sim:.2f})")

    # --- contradicciones ---
    if a.dom and b.dom and a.dom != b.dom:
        contras.append(f"dominios distintos ({a.dom} vs {b.dom})")
    if a.mail and b.mail and a.mail != b.mail:
        contras.append("emails distintos")
    if _distinta_localidad(a, b):
        contras.append(f"localidades distintas ({a.loc} vs {b.loc})")

    fuertes = [s for s in senales if s.split(" ")[0] in ("matricula", "dominio", "email", "telefono")]

    if not senales:
        return Veredicto(DISTINCT, [], contras or ["ninguna senal en comun"], sim)

    # Nombre identico y ademas otra senal independiente: no queda margen.
    if nombre_igual and fuertes and not contras:
        return Veredicto(EXACT, senales, contras, sim)
    # Un dominio propio compartido es identidad por si solo: dos inmobiliarias
    # distintas no comparten sitio.
    if any(s.startswith("dominio") for s in senales) and not contras:
        return Veredicto(EXACT if nombre_igual else HIGH_CONFIDENCE, senales, contras, sim)

    if contras:
        # Una senal fuerte contra una contradiccion no se resuelve sola.
        return Veredicto(AMBIGUOUS if fuertes or nombre_igual else DISTINCT, senales, contras, sim)

    if nombre_igual:
        return Veredicto(HIGH_CONFIDENCE, senales, contras, sim)
    if fuertes:
        return Veredicto(HIGH_CONFIDENCE, senales, contras, sim)
    # Solo parecido de nombre, sin nada que lo respalde: no alcanza.
    return Veredicto(AMBIGUOUS, senales, contras, sim)


@dataclass
class Emparejamiento:
    izquierda: Entidad
    derecha: Entidad
    veredicto: Veredicto


def _bloques(entidades: Iterable[Entidad]) -> dict[str, list[Entidad]]:
    """Agrupa por claves baratas para no comparar todos contra todos.

    Sin esto el cruce de 11.798 staging contra 7.003 main serian 82 millones de
    comparaciones. Con bloques por nombre, nucleo, dominio y telefono, se
    comparan solo las que comparten al menos una senal.
    """
    idx: dict[str, list[Entidad]] = defaultdict(list)
    for e in entidades:
        for k in (f"n:{e.norm_calculado}", f"c:{e.core}",
                  f"d:{e.dom}" if e.dom else "", f"t:{e.tel}" if e.tel else ""):
            if k and not k.endswith(":"):
                idx[k].append(e)
    return idx


def cruzar(izquierda: Iterable[Entidad], derecha: Iterable[Entidad]) -> list[Emparejamiento]:
    """Cruza dos colecciones y devuelve todo par con alguna relacion."""
    idx = _bloques(derecha)
    vistos: set[tuple[str, str]] = set()
    out: list[Emparejamiento] = []
    for a in izquierda:
        candidatas: dict[str, Entidad] = {}
        for k in (f"n:{a.norm_calculado}", f"c:{a.core}",
                  f"d:{a.dom}" if a.dom else "", f"t:{a.tel}" if a.tel else ""):
            if not k or k.endswith(":"):
                continue
            for b in idx.get(k, ()):
                candidatas[b.ident] = b
        for b in candidatas.values():
            par = (a.ident, b.ident)
            if par in vistos:
                continue
            vistos.add(par)
            v = comparar(a, b)
            if v.estado != DISTINCT:
                out.append(Emparejamiento(a, b, v))
    return out


def cardinalidad(pares: Iterable[Emparejamiento]) -> dict[str, str]:
    """Etiqueta cada par como uno-a-uno, uno-a-muchos o muchos-a-uno.

    Importa porque un uno-a-uno se puede resolver y un muchos-a-uno casi nunca:
    si dos filas distintas apuntan al mismo destino, fusionar las dos borraria
    una entidad real.
    """
    pares = list(pares)
    por_izq: dict[str, int] = defaultdict(int)
    por_der: dict[str, int] = defaultdict(int)
    for p in pares:
        if p.veredicto.estado in (EXACT, HIGH_CONFIDENCE):
            por_izq[p.izquierda.ident] += 1
            por_der[p.derecha.ident] += 1
    out: dict[str, str] = {}
    for p in pares:
        clave = f"{p.izquierda.ident}->{p.derecha.ident}"
        i, d = por_izq[p.izquierda.ident], por_der[p.derecha.ident]
        if i <= 1 and d <= 1:
            out[clave] = "uno_a_uno"
        elif i > 1 and d <= 1:
            out[clave] = "uno_a_muchos"
        elif i <= 1 and d > 1:
            out[clave] = "muchos_a_uno"
        else:
            out[clave] = "muchos_a_muchos"
    return out


def resoluble(p: Emparejamiento, card: str) -> bool:
    """Un par solo se puede resolver sin intervencion humana si es de alta
    confianza Y uno-a-uno. Todo lo demas va a revision."""
    return p.veredicto.estado in (EXACT, HIGH_CONFIDENCE) and card == "uno_a_uno"

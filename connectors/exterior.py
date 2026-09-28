# -*- coding: utf-8 -*-
"""Propiedades publicadas FUERA de Argentina: se conservan y se marcan.

Agencias argentinas publican tambien alquileres en Miami, Punta del Este o la
costa amalfitana (`blanco`, `masar`, `farina`).

Politica decidida por el usuario el 2026-09-28 (durable): RECOLECCION si,
PRESERVACION si, PUBLICACION no. ERETZ publico es `ARGENTINA_ONLY`. Aca no se
borra ni se descarta nada -scraping, paquetes y canonico las guardan enteras,
con pais (codigo ISO en `pais_publicado`), lo publicado y la evidencia- y se
marca `PRESERVED_NOT_PUBLISHED`. Es la capa de publicacion (la snapshot de la
API) la que las deja afuera, con `publicable()`. Una expansion internacional
futura cambia esa politica sin volver a recolectarlas. Los paquetes anteriores
llevan la marca vieja `PRODUCT_DECISION_PENDING`, que se trata igual.

Lo que si se corrige es no inventarles geografia argentina. «CIUDAD DE MIAMI»
no resuelve como localidad y el pipeline la bajaba a `barrio`, con la provincia
de la plantilla del sitio -«Buenos Aires»- al lado: una propiedad en Miami
figuraba como un barrio de la provincia de Buenos Aires.

La deteccion es conservadora a proposito. Cuenta como evidencia SOLO:
  - `addressCountry` estructurado que no es Argentina;
  - el valor COMPLETO publicado como ciudad o barrio, si es un pais o un
    destino de la lista y no es una localidad argentina;
  - en el titulo, un destino Y su pais a la vez («Sorrento Italia Costa
    Amalfitana»). Un nombre solo no alcanza: medido sobre los paquetes,
    «en España y Hospitales» es un barrio de Rosario y «en Uruguay al 200»,
    «en Italia al 2700» son calles.
La lista deja afuera nombres que tambien son lugares argentinos: Florida
(Vicente Lopez), Colonia, Santiago, La Barra, Sorrento (barrio de Rosario).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

PRODUCT_DECISION_PENDING = "PRODUCT_DECISION_PENDING"  # marca anterior al 28-09
PRESERVED_NOT_PUBLISHED = "PRESERVED_NOT_PUBLISHED"
POLITICA_PUBLICA = "ARGENTINA_ONLY"


def publicable(extra: Any) -> bool:
    """¿La politica publica actual deja servir esta fila? Solo lo argentino."""
    if not isinstance(extra, dict):
        return True
    return not extra.get("publicacion_exterior")

PAISES = {
    "uruguay": "UY", "paraguay": "PY", "chile": "CL", "brasil": "BR", "brazil": "BR",
    "bolivia": "BO", "peru": "PE", "espana": "ES", "italia": "IT", "estados unidos": "US",
    "eeuu": "US", "usa": "US", "mexico": "MX", "colombia": "CO", "portugal": "PT",
    "francia": "FR",
}
DESTINOS = {
    "miami": "US", "orlando": "US", "miami beach": "US", "nueva york": "US",
    "new york": "US", "punta del este": "UY", "punta ballena": "UY",
    "jose ignacio": "UY", "montevideo": "UY", "piriapolis": "UY",
    "colonia del sacramento": "UY", "costa amalfitana": "IT",
    "madrid": "ES", "barcelona": "ES", "asuncion": "PY", "florianopolis": "BR",
    "buzios": "BR", "rio de janeiro": "BR", "sao paulo": "BR", "camboriu": "BR",
    "balneario camboriu": "BR",
}
LUGARES = {**PAISES, **DESTINOS}
ARGENTINA = {"ar", "arg", "argentina", "republica argentina"}


def plano(texto: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", texto)).strip()


def _lugar_completo(valor: Any) -> str | None:
    """«CIUDAD DE MIAMI», «Miami», «Punta del Este, Uruguay» -> codigo de pais."""
    texto = plano(valor)
    texto = re.sub(r"^(?:ciudad|localidad|departamento) de ", "", texto)
    if texto in LUGARES:
        return LUGARES[texto]
    partes = [p.strip() for p in re.split(r"\s*,\s*", str(valor or "")) if p.strip()]
    codigos = {LUGARES.get(plano(p)) for p in partes} - {None}
    if len(partes) > 1 and len(codigos) == 1 and all(
            plano(p) in LUGARES for p in partes):
        return codigos.pop()
    return None


def _destino_y_pais(titulo: Any) -> str | None:
    """Codigo de pais si el titulo nombra un destino Y su pais, que coinciden."""
    texto = f" {plano(titulo)} "
    destinos = {c for k, c in DESTINOS.items() if f" {k} " in texto}
    paises = {c for k, c in PAISES.items() if f" {k} " in texto}
    comunes = destinos & paises
    return comunes.pop() if len(comunes) == 1 else None


def evidencia_de_exterior(titulo: Any = None, ciudad: Any = None, barrio: Any = None,
                          pais: Any = None,
                          es_localidad_argentina=lambda _texto: False) -> dict | None:
    """Evidencia de que la ficha publica un inmueble fuera de Argentina, o None.

    `es_localidad_argentina` lo decide el catalogo geografico: un valor que
    resuelve como localidad argentina nunca es evidencia de exterior.
    """
    if pais and plano(pais) not in ARGENTINA:
        codigo = PAISES.get(plano(pais)) or str(pais).strip().upper()[:3]
        return {"pais": codigo, "evidencia": f"addressCountry={pais}"}
    for campo, valor in (("ciudad", ciudad), ("barrio", barrio)):
        codigo = _lugar_completo(valor)
        if codigo and not es_localidad_argentina(valor):
            return {"pais": codigo, "evidencia": f"{campo}={valor}"}
    codigo = _destino_y_pais(titulo)
    if codigo:
        return {"pais": codigo, "evidencia": f"titulo: {str(titulo)[:80]}"}
    return None

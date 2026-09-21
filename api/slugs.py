#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""URLs publicas de una propiedad, sin afirmar geografia que no se demostro.

Una URL es una afirmacion tan fuerte como el texto de la pagina, y ademas
queda indexada. `/venta/casa/rosario/...` le dice al buscador y a la persona
que la propiedad esta en Rosario. Si lo unico que sabemos es el municipio, esa
URL inventa la ciudad, y la inventa de forma permanente: cambiarla despues
rompe los enlaces y pierde el posicionamiento.

Por eso el segmento geografico sale de la MISMA regla que el resto del
sistema:

  localidad demostrada   se usa el nombre de la localidad
  cualquier otro nivel   se usa la PROVINCIA, que si esta demostrada, y el
                         nivel mas fino no aparece en la URL
  nada demostrado        no hay segmento geografico

Nunca el municipio en el lugar donde la gente lee una ciudad.

**El id va siempre.** Un slug puede repetirse -dos "casa en venta en centro"
del mismo barrio- y puede cambiar si la inmobiliaria corrige el titulo. El id
lo hace unico y estable, que es lo que una URL canonica necesita.

**`noindex` cuando no hay nada que indexar.** Una ficha sin titulo, sin
descripcion y sin fotos no le sirve a nadie que llegue desde un buscador, y
publicarla gasta presupuesto de rastreo en paginas que van a rebotar.

No escribe en ninguna base.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

SLUG_VERSION = "eretz_slug_v1"

# Cuanto del titulo entra en la URL. Mas largo no mejora nada y hace URLs que
# no se pueden compartir en un mensaje.
LARGO_DE_SLUG = 60


def _plegar(texto: Any) -> str:
    if not isinstance(texto, str):
        return ""
    sin = "".join(c for c in unicodedata.normalize("NFD", texto)
                  if unicodedata.category(c) != "Mn")
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", sin.lower())).strip("-")


def sin_acento(texto: Any) -> str:
    """Minusculas y sin acentos, CONSERVANDO los espacios.

    No sirve `_plegar` para esto: convierte todo en slug con guiones, y
    entonces `mar del` deja de ser prefijo de `mar del plata`. El
    autocompletado compara prefijos de lo que una persona escribe.

    `collate nocase` de SQLite solo pliega mayusculas ASCII y no toca los
    acentos, asi que sin esto `cordo` no encuentra `Cordoba`: la comparacion
    se rompe en la segunda letra.
    """
    if not isinstance(texto, str):
        return ""
    plano = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in plano if unicodedata.category(c) != "Mn")


def segmento_geografico(geo: dict[str, Any] | None) -> str:
    """Lo unico que la URL puede afirmar sobre donde esta la propiedad."""
    geo = geo or {}
    localidad = (geo.get("localidad") or {}).get("nombre")
    if localidad:
        return _plegar(localidad)
    # Ni municipio ni departamento: en una URL, el nivel no se puede aclarar
    # -no hay lugar para decir "municipio de"- y el lector va a leer ciudad.
    provincia = (geo.get("provincia") or {}).get("nombre")
    return _plegar(provincia) if provincia else ""


def slug_de(propiedad: dict[str, Any]) -> str:
    """El slug de la ficha, con el id al final para que sea unico y estable."""
    partes = [_plegar(propiedad.get("operacion")),
              _plegar(propiedad.get("tipo_propiedad")),
              segmento_geografico(propiedad.get("geo"))]
    titulo = _plegar(propiedad.get("titulo"))[:LARGO_DE_SLUG].strip("-")
    partes.append(titulo)
    ruta = "/".join(p for p in partes if p)
    return f"{ruta}/{propiedad.get('id')}" if ruta else str(propiedad.get("id"))


def canonica(propiedad: dict[str, Any], base: str) -> str:
    """La URL canonica. Una sola por propiedad, siempre la misma."""
    return f"{base.rstrip('/')}/propiedad/{slug_de(propiedad)}"


def indexable(propiedad: dict[str, Any]) -> tuple[bool, str | None]:
    """Si vale la pena que un buscador gaste una visita en esta ficha."""
    if not (propiedad.get("titulo") or propiedad.get("descripcion")):
        return False, "sin titulo ni descripcion: no hay nada que indexar"
    if not (propiedad.get("imagenes") or propiedad.get("descripcion")):
        return False, "sin fotos ni descripcion: la ficha va a rebotar"
    return True, None


def datos_estructurados(propiedad: dict[str, Any], base: str) -> dict[str, Any]:
    """schema.org, con los campos que se pueden sostener y ninguno mas.

    Un dato estructurado inventado es peor que ausente: el buscador lo muestra
    como si fuera nuestro y despues la persona llega y no coincide.
    """
    geo = propiedad.get("geo") or {}
    localidad = (geo.get("localidad") or {}).get("nombre")
    provincia = (geo.get("provincia") or {}).get("nombre")
    datos: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "RealEstateListing",
        "url": canonica(propiedad, base),
        "name": propiedad.get("titulo"),
        "description": propiedad.get("descripcion"),
    }
    if propiedad.get("precio") and propiedad.get("moneda"):
        # Un precio sin moneda no es un precio y no entra: schema.org exige
        # las dos cosas juntas y publicar una sin la otra es publicar un numero.
        datos["offers"] = {"@type": "Offer",
                           "price": propiedad["precio"],
                           "priceCurrency": propiedad["moneda"]}
    direccion = {k: v for k, v in (
        ("addressLocality", localidad),
        ("addressRegion", provincia),
        ("addressCountry", "AR" if provincia or localidad else None),
    ) if v}
    if direccion:
        datos["address"] = {"@type": "PostalAddress", **direccion}
    if propiedad.get("latitud") and propiedad.get("longitud"):
        datos["geo"] = {"@type": "GeoCoordinates",
                        "latitude": propiedad["latitud"],
                        "longitude": propiedad["longitud"]}
    if propiedad.get("imagenes"):
        datos["image"] = propiedad["imagenes"][:6]
    return {k: v for k, v in datos.items() if v not in (None, "", [], {})}

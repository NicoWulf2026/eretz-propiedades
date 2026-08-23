#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Connector Century 21 Argentina — implementacion numero tres.

La red publica en century21.com.ar sobre una plataforma llamada Viviendi, con
un backend Elasticsearch compartido por todas las oficinas. Eso la vuelve la
fuente mas barata de las tres: un solo conector cubre las 42 oficinas y devuelve
JSON tipado, sin parsear una linea de HTML.

Como se encontro: el listado por oficina parece vacio -650 KB de HTML sin un
solo enlace a ficha, todo renderizado en el cliente-, asi que el conector nunca
lo habria visto. Mirando lo que la pagina realmente pide en el navegador
aparecio que la MISMA url con `?json=true` devuelve el resultado completo.

  - directorio de oficinas: /oficinas
  - perfil de oficina:      /v/oficina/<id>-<slug>
  - inventario:             /v/resultados/oficina_<id>-<slug>_local
  - JSON:                   la misma url + `?json=true`
  - paginacion:             .../pagina_<N>?json=true, 100 por pagina
  - total declarado:        campo `totalHits`

Los parametros de query tipo `page=`, `from=` u `offset=` devuelven la primera
pagina otra vez, con HTTP 200: la paginacion va en la RUTA. Es la misma trampa
que Tokko, con otra forma.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Iterator

from .base import (Bloqueado, Connector, ErrorPermanente, ErrorTransitorio,
                   Fuente, PropiedadNormalizada, a_numero, detectar_operacion,
                   detectar_tipo, limpiar)

BASE = "https://century21.com.ar"
POR_PAGINA = 100
MAX_PAGINAS = 60

RE_PERFIL = re.compile(r"/v/(?:oficina|office)/(\d+)-([a-z0-9\-]+)", re.I)
# El enlace al inventario que la propia ficha de oficina publica. Hace falta
# leerlo: el slug del perfil ("revolution-s-a-rosario-santa-fe-argentina") NO es
# el del listado ("revolution-s-a"), asi que no se puede derivar uno del otro.
# La red sirve la misma pagina en dos idiomas y cambia AMBOS segmentos:
# /v/resultados/oficina_..._local  y  /v/results/office_..._local. Reconocer
# solo uno dejaba fuera a la mitad de las oficinas sin que nada fallara.
RE_LISTADO = re.compile(
    r"/v/(?:resultados|results)/((?:oficina|office)_\d+-[a-z0-9\-]+_local)", re.I)


class Century21Connector(Connector):
    nombre = "century21"
    variantes_soportadas = ("C21_JSON",)

    # ---------------------------------------------------------------- discover
    def discover(self, fuente: Fuente) -> dict[str, Any]:
        plan: dict[str, Any] = {"variante": "SIN_OFICINA", "soportada": False,
                                "total_declarado": None}
        url = fuente.official_url
        def _ruta(slug: str) -> str:
            seccion = "results" if slug.lower().startswith("office_") else "resultados"
            return f"{BASE}/v/{seccion}/{slug}"

        m = RE_LISTADO.search(url)
        if m:
            ruta = _ruta(m.group(1))
        else:
            # La url guardada puede ser el perfil de la oficina, su version en
            # ingles (/v/office/), o directamente la ficha de UNA propiedad: a
            # varias inmobiliarias se les adjudico un aviso suelto como si fuera
            # su web. En los tres casos la pagina enlaza al inventario de su
            # oficina, asi que en vez de deducir la ruta de la forma de la url
            # se la lee del HTML. Una sola peticion cubre las tres variantes.
            perfil = RE_PERFIL.search(url)
            if perfil:
                plan["oficina_id"] = perfil.group(1)
            try:
                html = self.descargador.bajar(url)
            except (ErrorTransitorio, ErrorPermanente, Bloqueado):
                return plan
            m = RE_LISTADO.search(html)
            if not m:
                return plan
            ruta = _ruta(m.group(1))
            plan["origen_url"] = ("perfil" if perfil else "ficha_suelta")
        plan["ruta"] = ruta

        try:
            datos = json.loads(self.descargador.bajar(ruta + "?json=true"))
        except (ValueError, ErrorTransitorio, ErrorPermanente, Bloqueado):
            return plan
        if not isinstance(datos, dict) or not isinstance(datos.get("results"), list):
            return plan

        total = datos.get("totalHits")
        plan.update({
            "variante": "C21_JSON", "soportada": True,
            "total_declarado": int(total) if str(total).isdigit() else None,
            "primera_pagina": datos["results"],
        })
        return plan

    # ----------------------------------------------------------- fetch_listing
    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        if not plan.get("soportada"):
            return
        ruta = plan["ruta"]
        vistos: set[str] = set()
        for pagina in range(1, MAX_PAGINAS + 1):
            if pagina == 1:
                items = plan.get("primera_pagina") or []
            else:
                try:
                    sufijo = "page" if "/results/" in ruta else "pagina"
                    datos = json.loads(self.descargador.bajar(
                        f"{ruta}/{sufijo}_{pagina}?json=true"))
                except (ValueError, ErrorPermanente):
                    break
                except (ErrorTransitorio, Bloqueado):
                    break
                items = datos.get("results") or []
            if not items:
                break
            nuevos = 0
            for it in items:
                lid = str(it.get("id") or "")
                if not lid or lid in vistos:
                    continue
                vistos.add(lid)
                nuevos += 1
                yield {"source_listing_id": lid, "pagina": pagina, "json": it,
                       "source_url": self._url_de(it, lid)}
            if nuevos == 0 or len(items) < POR_PAGINA:
                break

    @staticmethod
    def _url_de(it: dict, lid: str) -> str:
        """La url real de la ficha, que el propio JSON publica.

        Construir "/v/propiedad/<id>" a mano daba una url que no existe, y
        source_url entra en el hash de identidad: cada propiedad habria quedado
        registrada con una direccion inexistente, imposible de auditar despues.
        """
        for clave in ("urlCorrectaPropiedad", "url", "urlDetalle", "link"):
            v = it.get(clave)
            if isinstance(v, str) and v:
                return v if v.startswith("http") else urllib.parse.urljoin(BASE, v)
        return f"{BASE}/propiedad/{lid}"

    # --------------------------------------------------------------- normalize
    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        it = crudo.get("json") or {}
        lid = crudo["source_listing_id"]

        # Las fotos vienen como listas dentro de `fotos`. Se toman en el orden
        # que trae la fuente, sin reordenar: el primero suele ser la portada.
        imagenes, vistas = [], set()
        fotos = it.get("fotos") or {}
        if isinstance(fotos, dict):
            for clave in ("propiedadFoto", "propiedadThumbnail", "fotos", "urls"):
                v = fotos.get(clave)
                if isinstance(v, list):
                    for u in v:
                        if isinstance(u, str) and u.startswith("http") and u not in vistas:
                            vistas.add(u)
                            imagenes.append(u)

        titulo = limpiar(it.get("encabezado") or it.get("titulo"))
        operacion = detectar_operacion(
            f"{it.get('tipoOperacionTrans') or ''} {it.get('tipoOperacion') or ''} "
            f"{titulo or ''}")
        moneda = (it.get("moneda") or "").upper().strip() or None
        if moneda not in ("USD", "ARS", None):
            moneda = None

        # La direccion se arma solo con lo que la fuente publica. Si falta la
        # calle no se rellena con la colonia: son cosas distintas.
        calle = limpiar(it.get("calle"))
        barrio = limpiar(it.get("colonia") or it.get("coloniaWeb"))

        # lat/lon estan en la raiz del item, no anidados.
        def _num(*claves):
            """Numero de la fuente, tratando el cero como ausencia.

            C21 devuelve 0 en m2C y m2T cuando no conoce la superficie. Grabar
            ese cero lo convierte en una medicion: "casa de 0 m2 cubiertos"
            parece un dato verificado y ademas dispara la incoherencia de
            cubierta mayor que total. Un 19% del inventario entraba asi.
            """
            for c in claves:
                v = it.get(c)
                if v in (None, ""):
                    continue
                try:
                    n = float(str(v).replace(",", ""))
                except (TypeError, ValueError):
                    continue
                return n
            return None

        def _sup(*claves):
            """Superficie de la fuente, tratando el cero como ausencia.

            C21 devuelve 0 en m2C y m2T cuando no la conoce. Grabar ese cero lo
            convierte en una medicion: "casa de 0 m2 cubiertos" parece un dato
            verificado y ademas dispara la incoherencia de cubierta mayor que
            total. Un 19% del inventario entraba asi.

            El filtro va aparte de _num a proposito: las coordenadas argentinas
            son negativas y un ">0" generico las borraria todas.
            """
            v = _num(*claves)
            return v if v and v > 0 else None

        lat, lon = _num("lat"), _num("lon")
        if lat is not None and not (-56 <= lat <= -21):
            lat = None
        if lon is not None and not (-74 <= lon <= -53):
            lon = None

        extra = {k: v for k, v in {
            "oficina_c21": it.get("afiliadoNombre"),
            "asesor": it.get("asesorNombre"),
            "estacionamientos": it.get("estacionamientos"),
            "cuota_mantenimiento": it.get("cuotaMantenimiento"),
            "exclusiva": it.get("exclusiva"),
            "con_video": it.get("conVideo"),
            "fecha_alta": it.get("fechaAlta"),
            "modificado_en_fuente": it.get("fechaModificacion"),
            "total_fotos_fuente": (fotos or {}).get("totalFotos"),
            "estado_web": it.get("estadoWeb"),
            "matricula": it.get("matricula"),
            "mantenimiento": it.get("mantenimiento"),
            "recorrido_virtual": it.get("recorridoVirtual"),
            "sin_descripcion_en_listado": True,
        }.items() if v not in (None, "", [])}

        return PropiedadNormalizada(
            canonical_agency_id=fuente.canonical_agency_id,
            source_listing_id=lid,
            source_url=crudo["source_url"],
            connector=self.nombre,
            titulo=titulo,
            descripcion=limpiar(it.get("descripcion"))[:4000] if it.get("descripcion") else None,
            precio=a_numero(it.get("precio")),
            moneda=moneda,
            operacion=operacion,
            tipo_propiedad=detectar_tipo(
                f"{it.get('tipoPropiedadTrans') or it.get('tipoPropiedad') or ''} "
                f"{titulo or ''}"),
            direccion=calle,
            barrio=barrio,
            ciudad=limpiar(it.get("municipio") or it.get("municipioWeb")),
            provincia=limpiar(it.get("estado") or it.get("estadoWeb")),
            latitud=lat,
            longitud=lon,
            dormitorios=self._entero(it.get("recamaras")),
            banos=self._entero(it.get("banos")),
            ambientes=None,   # la fuente no publica ambientes; no se deduce
            superficie_total=_sup("m2T", "m2TSort"),
            superficie_cubierta=_sup("m2C", "m2CSort"),
            imagenes=imagenes[:40],
            extra=extra,
            inmobiliaria_id=fuente.inmobiliaria_id,
            provenance={"connector": self.nombre, "official_domain": BASE,
                        "agency_name": fuente.agency_name,
                        "canonical_agency_id": fuente.canonical_agency_id,
                        "source_platform": "CENTURY21_VIVIENDI",
                        "oficina_id": crudo.get("oficina_id"),
                        "pagina_listado": crudo.get("pagina")},
        )

    @staticmethod
    def _entero(v: Any) -> int | None:
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return None
        return n if 1 <= n <= 99 else None

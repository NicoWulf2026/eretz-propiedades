#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""La version mas fresca de cada propiedad, venga de donde venga.

La preingestion es del 3 de septiembre. Las certificaciones corren todos los
dias y producen propiedades normalizadas con el codigo de HOY, y hasta ahora
nadie las consumia: quedaban adentro del paquete de certificacion como
evidencia y nada mas.

El efecto de eso no era teorico. `agostini inmobiliaria` tiene 360 propiedades
con `operacion` en su certificacion y 9 en la preingestion: 350 arregladas que
el quality gate seguia contando como defecto nuestro, porque comparaba una foto
del 3 de septiembre contra la cobertura del 7.

Cada arreglo del extractor se veia como un defecto sin arreglar hasta que
alguien reconstruyera la preingestion entera.

**No se toca la base canonica.** Esto es una CAPA de lectura: dice cual es la
version mas fresca de cada propiedad. La preingestion sigue siendo la fuente de
verdad de que existe; el paquete, de como se ve hoy.

**Solo de certificaciones que cerraron bien.** Un paquete de una corrida que
fallo tiene datos parciales, y preferirlos a la preingestion cambiaria datos
completos por incompletos.

No escribe en ninguna base.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

FRESCURA_VERSION = "property_freshest_v3"

# Historical structural evidence can fill an unexplained extraction gap.
# A previous commercial value is not evidence of the current offer.
CAMPOS_VOLATILES = frozenset({'precio', 'moneda', 'operacion', 'titulo',
                              'descripcion', 'imagenes'})

# Estados en los que el inventario del paquete es confiable y completo.
CIERRES_CONFIABLES = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE")

# Los campos que se toman de la version mas fresca. La identidad no entra:
# `hash_dedup` y `source_url` definen a la propiedad y cambiarlos seria otra
# propiedad, no la misma mas nueva.
CAMPOS_FUSIONABLES = ("titulo", "descripcion", "operacion", "tipo_propiedad",
                      "precio", "moneda", "ciudad", "barrio", "provincia",
                      "direccion", "superficie_total", "superficie_cubierta",
                      "ambientes", "dormitorios", "banos", "latitud",
                      "longitud", "imagenes")



def _leer(ruta: Path) -> list[dict[str, Any]]:
    if not ruta.exists():
        return []
    fuera = []
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            fuera.append(json.loads(linea))
        except ValueError:
            continue
    return fuera


def mas_frescas(paquetes: Path) -> dict[str, dict[str, Any]]:
    """Por `hash_dedup`, la propiedad mas reciente de los paquetes.

    Si una propiedad aparece en dos paquetes -no deberia, pero el mundo no
    coopera- gana la certificacion mas nueva, que es la unica regla que no
    depende del orden en que se lean los archivos.
    """
    fuera: dict[str, dict[str, Any]] = {}
    if not paquetes.exists():
        return fuera
    for carpeta in paquetes.iterdir():
        certificacion = carpeta / "certification.json"
        if not certificacion.exists():
            continue
        try:
            paquete = json.loads(certificacion.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if paquete.get("status") not in CIERRES_CONFIABLES:
            continue
        cuando = paquete.get("checked_at") or ""
        for fila in (_leer(carpeta / "properties_run1.jsonl")
                     or _leer(carpeta / "properties_run2.jsonl")):
            h = fila.get("hash_dedup")
            if not h:
                continue
            previo = fuera.get(h)
            if previo is None or cuando >= previo.get("_certificado_en", ""):
                fuera[h] = dict(fila, _certificado_en=cuando)
    return fuera


def fusionar(vieja: dict[str, Any], fresca: dict[str, Any] | None,
             campos: tuple[str, ...]) -> dict[str, Any]:
    """La fresca manda, salvo donde no leyo nada y no dijo por que.

    Los dos lados son extractores DISTINTOS, no dos versiones del mismo: la
    preingestion la construye el pipeline legacy y los paquetes los connectors.
    Ninguno gana en todo. El refresco recupera 679 superficies y 503
    operaciones, y a la vez pierde 177 valores de `banos` en casas y
    departamentos, sin ningun motivo anotado.

    La regla (para campos estructurales):

      la fresca trae valor          gana la fresca, que corrio con codigo de hoy
      la fresca esta vacia y ANOTO  gana el vacio: la validacion lo rechazo y
      el rechazo                    volver al viejo desharia esa decision
      la fresca esta vacia y no     gana el viejo: no leerlo no es haberlo
      anoto nada                    leido y encontrado que no estaba

    Los campos comerciales/editoriales presentes pero vacíos en la nueva fila
    NO se recuperan de un anuncio histórico. Precio y moneda se reemplazan
    juntos: combinar el precio nuevo con una moneda vieja fabricaría una oferta.
    Una clave omitida en un parche parcial no equivale a un vacío explícito.
    """
    if not fresca:
        return vieja
    rechazados = set()
    descartes = (fresca.get("extra") or {}).get("atributos_descartados")
    if isinstance(descartes, str):
        for motivo in descartes.split(","):
            motivo = motivo.strip()
            if not motivo:
                continue
            rechazados.add(motivo.split("_en_un_")[0])
            rechazados.update(re.split(r"[>,]", motivo))
    # The allowlist must govern the actual merge, not only its documentation.
    # Starting from fresca used to replace source_url and agency identity too.
    salida = dict(vieja)
    for metadata in ('extra', '_certificado_en'):
        if metadata in fresca:
            salida[metadata] = fresca[metadata]
    for campo in campos:
        valor = fresca.get(campo)
        if (valor not in (None, "", []) or campo in rechazados
                or (campo in CAMPOS_VOLATILES and campo in fresca)):
            salida[campo] = valor
    if {'precio', 'moneda'} & set(campos) and {'precio', 'moneda'} & fresca.keys():
        for campo in ('precio', 'moneda'):
            if campo in campos:
                salida[campo] = fresca.get(campo)
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paquetes",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies")
    ap.add_argument("--db", default=None,
                    help="preingestion, para medir cuanto mejora el refresco")
    args = ap.parse_args()

    frescas = mas_frescas(Path(args.paquetes))
    resumen: dict[str, Any] = {
        "frescura_version": FRESCURA_VERSION,
        "propiedades_con_version_fresca": len(frescas),
        "database_writes": 0,
    }

    if args.db:
        import sqlite3
        campos = ("operacion", "tipo_propiedad", "precio", "moneda", "ciudad",
                  "barrio", "direccion", "superficie_total",
                  "superficie_cubierta", "ambientes", "dormitorios", "banos",
                  "latitud")
        conexion = sqlite3.connect(f"file:{Path(args.db).as_posix()}?mode=ro",
                                   uri=True)
        gana = {c: 0 for c in campos}
        pierde = {c: 0 for c in campos}
        comunes = 0
        for crudo, h in conexion.execute(
                "select row_json, hash_dedup from rows where status = 'CANDIDATE'"):
            fresca = frescas.get(h)
            if fresca is None:
                continue
            comunes += 1
            vieja = json.loads(crudo)
            for campo in campos:
                nuevo = fresca.get(campo) not in (None, "", [])
                anterior = vieja.get(campo) not in (None, "", [])
                if nuevo and not anterior:
                    gana[campo] += 1
                elif anterior and not nuevo:
                    pierde[campo] += 1
        resumen["propiedades_comparables"] = comunes
        resumen["campos_que_gana_el_refresco"] = {
            k: v for k, v in sorted(gana.items(), key=lambda x: -x[1]) if v}
        # Si el refresco PIERDE campos, no es mas fresco: es peor. Se informa.
        resumen["campos_que_pierde_el_refresco"] = {
            k: v for k, v in sorted(pierde.items(), key=lambda x: -x[1]) if v}

    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

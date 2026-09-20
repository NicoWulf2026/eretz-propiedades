#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que coordenadas de las candidatas se pueden creer. No escribe nada.

Una coordenada mal puesta es peor que una coordenada ausente: la propiedad
aparece en el mapa, en el lugar equivocado, y nadie se entera. Por eso ninguna
queda habilitada por defecto: hay que ganarse el permiso.

Se piden cuatro cosas, en orden:

  RANGO         el par tiene que ser un par -numeros finitos, lat en [-90,90],
                lon en [-180,180]- y no puede ser (0,0), que es lo que devuelve
                un geocodificador cuando no encontro nada.
  ARGENTINA     tiene que caer dentro del pais.
  NO_INVERTIDA  si el par falla y el par dado vuelta si entra, esta invertido.
                Se marca; no se corrige sola, porque adivinar es lo que estamos
                tratando de evitar.
  PROVINCIA     tiene que caer dentro de la provincia que la propia ficha
                declara. Sin poligonos, la caja de la provincia se arma con los
                centroides de sus localidades censales mas un margen: es
                permisiva -deja pasar algo de mas- pero nunca rechaza una
                coordenada que este bien adentro.

Si la ficha no declara provincia no hay con que contrastar: queda
SIN_PROVINCIA_QUE_CONTRASTAR, que NO es lo mismo que valida.
"""
from __future__ import annotations

import json
import math
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

GEO = Path(r"D:\INMO CAPITAL\ERETZ_GEO")
CANDIDATAS = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                  r"\DB_WRITE_ELIGIBLE.jsonl")
SALIDA = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY"
              r"\coordenadas_validadas.jsonl")

# El pais entero, con holgura. Incluye Tierra del Fuego y las islas del sur.
LAT_AR = (-55.20, -21.70)
LON_AR = (-73.65, -53.60)

# Cuanto se agranda la caja de cada provincia. Los centroides de localidad no
# llegan al borde, asi que sin margen se rechazarian coordenadas costeras o de
# zonas despobladas que estan bien.
MARGEN = 1.0


def sin_acentos(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).strip().lower()


def cajas_de_provincia() -> dict[str, tuple[float, float, float, float]]:
    """La caja de cada provincia, armada con los centroides de sus localidades."""
    puntos: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for archivo in ("localidades_censales.json", "localidades.json",
                    "municipios.json"):
        ruta = GEO / archivo
        if not ruta.exists():
            continue
        for fila in json.loads(ruta.read_text(encoding="utf-8")):
            prov = (fila.get("provincia") or {})
            nombre = prov.get("nombre") if isinstance(prov, dict) else prov
            c = fila.get("centroide") or {}
            if nombre and c.get("lat") is not None and c.get("lon") is not None:
                puntos[sin_acentos(nombre)].append((c["lat"], c["lon"]))

    cajas = {}
    for nombre, ps in puntos.items():
        lats = [p[0] for p in ps]
        lons = [p[1] for p in ps]
        cajas[nombre] = (min(lats) - MARGEN, max(lats) + MARGEN,
                         min(lons) - MARGEN, max(lons) + MARGEN)
    # Alias que usa el catalogo productivo y no el de georef.
    for alias, canonico in (("capital federal", "ciudad autonoma de buenos aires"),
                            ("caba", "ciudad autonoma de buenos aires"),
                            ("tierra del fuego", "tierra del fuego, antartida e "
                                                 "islas del atlantico sur")):
        if canonico in cajas and alias not in cajas:
            cajas[alias] = cajas[canonico]
    return cajas


def numero(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def en(v: float, minimo: float, maximo: float) -> bool:
    return minimo <= v <= maximo


def clasificar(lat, lon, provincia: str | None,
               cajas: dict[str, tuple[float, float, float, float]]) -> tuple[str, str]:
    la, lo = numero(lat), numero(lon)
    if la is None or lo is None:
        return "SIN_COORDENADA", "la ficha no publica el par"
    if not (en(la, -90, 90) and en(lo, -180, 180)):
        return "RANGO_IMPOSIBLE", f"lat={la} lon={lo} fuera del rango del mundo"
    if abs(la) < 0.001 and abs(lo) < 0.001:
        return "ORIGEN_NULO", "(0,0): el geocodificador no encontro nada"

    dentro = en(la, *LAT_AR) and en(lo, *LON_AR)
    if not dentro:
        if en(lo, *LAT_AR) and en(la, *LON_AR):
            return "INVERTIDA", f"lat y lon al reves: ({la},{lo})"
        return "FUERA_DE_ARGENTINA", f"({la},{lo}) cae fuera del pais"

    if not provincia:
        return "SIN_PROVINCIA_QUE_CONTRASTAR", "la ficha no declara provincia"
    caja = cajas.get(sin_acentos(provincia))
    if caja is None:
        return "PROVINCIA_DESCONOCIDA", f"'{provincia}' no esta en el catalogo"
    lat_min, lat_max, lon_min, lon_max = caja
    if en(la, lat_min, lat_max) and en(lo, lon_min, lon_max):
        return "VALIDA", f"dentro de {provincia}"
    return "CONTRADICE_LA_PROVINCIA", (
        f"({la},{lo}) no cae en {provincia}")


def main() -> int:
    cajas = cajas_de_provincia()
    print(f"provincias con caja: {len(cajas)}")

    clases = Counter()
    por_provincia = Counter()
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(CANDIDATAS, encoding="utf-8") as f, \
            open(SALIDA, "w", encoding="utf-8") as g:
        for linea in f:
            if not linea.strip():
                continue
            r: dict[str, Any] = json.loads(linea)
            clase, motivo = clasificar(r.get("latitud"), r.get("longitud"),
                                       r.get("provincia"), cajas)
            clases[clase] += 1
            if clase == "CONTRADICE_LA_PROVINCIA":
                por_provincia[r.get("provincia")] += 1
            g.write(json.dumps({
                "hash_dedup": r.get("hash_dedup"),
                "canonical_agency_id": r.get("canonical_agency_id"),
                "clase": clase, "motivo": motivo,
                "habilitada": clase == "VALIDA",
            }, ensure_ascii=False) + "\n")

    total = sum(clases.values())
    con_par = total - clases["SIN_COORDENADA"]
    print(f"\ncandidatas: {total}  |  con coordenada: {con_par}\n")
    for c, n in clases.most_common():
        print(f"  {c:32} {n:7}")
    print(f"\nHABILITADAS para una futura escritura: {clases['VALIDA']}"
          f" ({100*clases['VALIDA']/max(con_par,1):.1f} % de las que traen par)")
    print(f"BLOQUEADAS: {con_par - clases['VALIDA']}")
    if por_provincia:
        print("\nprovincias donde mas contradice:",
              ", ".join(f"{p}:{n}" for p, n in por_provincia.most_common(5)))
    print(f"\nartefacto: {SALIDA}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

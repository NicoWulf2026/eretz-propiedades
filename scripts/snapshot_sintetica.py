#!/usr/bin/env python
"""Snapshot SINTETICA de la API v2: para QA de API y de navegador sin el estado LOCAL.

Por que existe: la snapshot servida vive en la PC LOCAL (arquitectura hibrida,
29-09) y el repo es publico, asi que CLOUD y CI no tienen con que levantar la API
ni el frontend. Esta snapshot se genera desde el codigo, siempre igual, con el
MISMO esquema (`api_snapshot.ESQUEMA`) y el MISMO documento (`fila_de_api`,
`alcances`) que la real: si el contrato cambia, cambia aca tambien.

Que NO es: datos. Los lugares son nombres geograficos publicos (provincias,
localidades) con coordenadas aproximadas de su centro; las fichas, agencias,
precios y textos son inventados a proposito y lo dicen:
- `agency_id` = `sintetica:<nombre>` y `source_url` bajo `sintetica.invalid`
  (dominio reservado, RFC 2606: nunca resuelve);
- `snapshot_meta.sintetica = 1`: `desplegar_snapshot.py` se niega a servirla y la
  API la declara en `/readyz`.

Los casos estan elegidos por lo que la beta necesita ver: un area con sus tres
niveles (Cordoba provincia, municipio y localidad), una ciudad que NO es provincia
(Rosario), municipio sin localidad (La Calera), barrio de CABA, conflicto
geografico, ficha sin titulo (P9), sin precio, precio sin moneda, sin
coordenadas, alquiler temporario, y suficientes filas para paginar.
Los casos borde tienen nombre en `CASOS`; los tests los buscan por ahi.

    python scripts/snapshot_sintetica.py --salida _scratch/sintetica/ERETZ_API_SNAPSHOT.sqlite3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
if str(RAIZ / "scripts") not in sys.path:
    sys.path.insert(0, str(RAIZ / "scripts"))

from api.slugs import sin_acento  # noqa: E402
from scripts.api_contract import fila_de_api  # noqa: E402
from scripts.api_snapshot import ESQUEMA, INSERTAR_FILA  # noqa: E402
from scripts.property_contract import alcances  # noqa: E402

DOMINIO = "sintetica.invalid"
PREFIJO_AGENCIA = "sintetica:"

# (clave, provincia, departamento, municipio, localidad, barrio, lat, lon)
# Solo nombres publicos. `localidad` None = el caso «municipio sin localidad».
LUGARES: dict[str, tuple[str, str | None, str | None, str | None, str | None, float, float]] = {
    "cordoba": ("Córdoba", "Capital", "Córdoba", "Córdoba", "Nueva Córdoba", -31.4201, -64.1888),
    "la_calera": ("Córdoba", "Colón", "La Calera", None, "Chacra del Norte", -31.3439, -64.3353),
    "rosario": ("Santa Fe", "Rosario", "Rosario", "Rosario", "Centro", -32.9468, -60.6393),
    "palermo": ("Ciudad Autónoma de Buenos Aires", "Comuna 14", None,
                "Ciudad Autónoma de Buenos Aires", "Palermo", -34.5889, -58.4306),
    "san_isidro": ("Buenos Aires", "San Isidro", "San Isidro", "San Isidro", "Centro",
                   -34.4708, -58.5286),
    "mar_del_plata": ("Buenos Aires", "General Pueyrredón", "General Pueyrredón",
                      "Mar del Plata", "La Perla", -38.0055, -57.5426),
    "san_luis": ("San Luis", "Juan Martín de Pueyrredón", "San Luis", "San Luis", None,
                 -33.3017, -66.3378),
    "neuquen": ("Neuquén", "Confluencia", "Neuquén", "Neuquén", None, -38.9516, -68.0591),
    "mendoza": ("Mendoza", "Capital", "Mendoza", "Mendoza", None, -32.8895, -68.8458),
    "salta": ("Salta", "Capital", "Salta", "Salta", None, -24.7821, -65.4232),
}

# Departamento y venta pesan doble, como en el catalogo real: la e2e pide paginas
# completas (24) de `tipo=departamento` y de `operacion=venta`.
TIPOS = ("departamento", "casa", "departamento", "ph", "terreno", "departamento", "local",
         "departamento", "oficina", "cochera")
OPERACIONES = ("venta", "alquiler", "venta", "alquiler_temporario")


def id_sintetico(n: int) -> str:
    """32 hex, como los ids reales (el frontend y la e2e validan esa forma)."""
    return hashlib.sha256(f"eretz-sintetica:{n}".encode()).hexdigest()[:32]


# Los casos borde por nombre: los tests y la QA de navegador los buscan asi.
CASOS = {nombre: id_sintetico(n) for nombre, n in (
    ("sin_titulo", 9001), ("sin_titulo_ni_datos", 9002), ("sin_precio", 9003),
    ("sin_moneda", 9004), ("sin_coordenadas", 9005), ("conflicto", 9006),
    ("solo_provincia", 9007), ("combinado", 9010), ("municipio", 9011))}
AGENCIAS = ("alfa", "beta", "gamma", "delta")


def _geo(clave: str, *, nivel_forzado: str | None = None) -> dict[str, Any]:
    """Las dimensiones canonicas que el pipeline real dejaria en la cobertura geo."""
    provincia, departamento, municipio, localidad, barrio, _, _ = LUGARES[clave]
    if nivel_forzado == "PROVINCIA":
        departamento = municipio = localidad = None
    elif nivel_forzado == "MUNICIPIO":
        localidad = None
    if localidad:
        area = {"nivel": "LOCALIDAD", "nombre": localidad, "id": f"sint-{clave}", "origen": "localidad"}
    elif municipio:
        area = {"nivel": "MUNICIPIO", "nombre": municipio, "id": None, "origen": "municipio"}
    else:
        area = {"nivel": "PROVINCIA", "nombre": provincia, "id": None, "origen": "provincia"}
    return {
        "localidad_canonica": localidad,
        "localidad_id": f"sint-{clave}" if localidad else None,
        "municipio_canonico": municipio,
        "departamento_canonico": departamento,
        "provincia_canonica": provincia,
        "barrio_fuente": barrio,
        "procedencia_de_dimensiones": {"municipio": "SINTETICA", "departamento": "SINTETICA"},
        "area_busqueda": area,
        "estado_geografico": None,
    }


def filas() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """(fila cruda, geo) en orden determinista. Mismas entradas, misma snapshot."""
    salida: list[tuple[dict[str, Any], dict[str, Any]]] = []
    n = 0
    for clave in LUGARES:
        for _ in range(10 if clave in ("cordoba", "rosario", "palermo") else 6):
            n += 1
            tipo = TIPOS[(n * 7) % len(TIPOS)]  # 7 coprimo con 10: todos los tipos
            operacion = OPERACIONES[n % len(OPERACIONES)]
            moneda = "USD" if operacion == "venta" else "ARS"
            precio = (60_000 + 7_500 * n) if moneda == "USD" else (250_000 + 15_000 * n)
            _, _, _, localidad, barrio, lat, lon = LUGARES[clave]
            lugar = localidad or LUGARES[clave][2] or LUGARES[clave][0]
            fila = {
                "hash_dedup": id_sintetico(n),
                "source_url": f"https://{AGENCIAS[n % len(AGENCIAS)]}.{DOMINIO}/propiedad/{n}",
                "canonical_agency_id": PREFIJO_AGENCIA + AGENCIAS[n % len(AGENCIAS)],
                "titulo": f"{tipo.capitalize()} de prueba en {lugar}",
                "descripcion": (f"Ficha SINTETICA {n} para QA. {tipo} en {barrio or lugar}, "
                                "no es una propiedad real."),
                "operacion": operacion,
                "tipo_propiedad": tipo,
                "precio": float(precio),
                "moneda": moneda,
                "ambientes": None if tipo in ("terreno", "cochera") else 1 + n % 5,
                "dormitorios": None if tipo in ("terreno", "cochera", "local") else n % 4,
                "banos": None if tipo in ("terreno", "cochera") else 1 + n % 2,
                "superficie_total": float(40 + 13 * n),
                "superficie_cubierta": None if tipo == "terreno" else float(30 + 9 * n),
                "imagenes": [],
                # Dispersion chica y determinista alrededor del centro del lugar.
                "latitud": round(lat + ((n * 37) % 11 - 5) * 0.004, 6),
                "longitud": round(lon + ((n * 53) % 11 - 5) * 0.004, 6),
            }
            salida.append((fila, _geo(clave)))

    def caso(n: int, clave: str, **cambios: Any) -> None:
        fila, geo = dict(salida[0][0]), _geo(clave, nivel_forzado=cambios.pop("_nivel", None))
        _, _, _, _, _, lat, lon = LUGARES[clave]
        fila.update({"hash_dedup": id_sintetico(n), "source_url": f"https://alfa.{DOMINIO}/caso/{n}",
                     "canonical_agency_id": PREFIJO_AGENCIA + "alfa", "latitud": lat, "longitud": lon})
        estado = cambios.pop("_estado", None)
        fila.update(cambios)
        if estado:
            geo["estado_geografico"] = estado
        salida.append((fila, geo))

    # Casos borde, con ids fijos para que los tests los nombren.
    caso(9001, "rosario", titulo=None, tipo_propiedad="casa", operacion="venta",      # P9
         descripcion="Ficha SINTETICA sin titulo publicado: tipo, operacion y localidad reales.")
    caso(9002, "cordoba", titulo=None, tipo_propiedad=None, operacion=None,
         descripcion="Ficha SINTETICA sin titulo, tipo ni operacion.")               # P9 sin datos
    caso(9003, "mar_del_plata", precio=None, moneda=None)                             # sin precio
    caso(9004, "san_isidro", precio=180000.0, moneda=None)                            # sin moneda
    caso(9005, "palermo", latitud=None, longitud=None,                                # sin coordenadas
         titulo="Casa amplia en alquiler sin mapa", tipo_propiedad="casa", operacion="alquiler")
    caso(9006, "salta", _estado="GEO_CONFLICT")                                       # conflicto
    caso(9007, "cordoba", _nivel="PROVINCIA")                                         # solo provincia
    caso(9008, "san_luis", _nivel="PROVINCIA")
    caso(9011, "cordoba", _nivel="MUNICIPIO")                                         # municipio
    # Lo que la e2e de descubrimiento (frontend/e2e/test_api_v2_discovery.py)
    # afirma de la geografia real: Rosario es municipio y localidad pero NO
    # provincia; «San…» existe en los tres niveles; «Buenos Aires» es provincia.
    caso(9012, "rosario", _nivel="MUNICIPIO")
    caso(9013, "san_isidro", _nivel="MUNICIPIO")
    caso(9014, "san_isidro", _nivel="PROVINCIA")
    caso(9009, "mar_del_plata", operacion="alquiler_temporario", moneda="ARS", precio=90000.0)
    caso(9010, "cordoba", titulo="Casa de prueba con jardín en Córdoba", tipo_propiedad="casa",
         operacion="venta", moneda="USD", precio=145000.0, dormitorios=3, ambientes=5)  # combinado
    return salida


def construir(destino: Path) -> dict[str, Any]:
    """Escribe la snapshot en `destino` (lo reemplaza) y devuelve su resumen."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()
    con = sqlite3.connect(destino)
    try:
        con.executescript(ESQUEMA)
        # Mismo orden que el builder real (por id): `busqueda.rowid` alineado.
        for fila, geo in sorted(filas(), key=lambda par: par[0]["hash_dedup"]):
            scopes, _ = alcances(fila, geo)
            documento = fila_de_api(fila, geo, sorted(scopes))
            area = documento["geo"]["area_busqueda"] or {}
            cursor = con.execute(
                INSERTAR_FILA,
                (documento["id"], documento["agency_id"], documento["source_url"],
                 documento["titulo"], documento["descripcion"], documento["operacion"],
                 documento["tipo_propiedad"], documento["precio"], documento["moneda"],
                 documento["ambientes"], documento["dormitorios"], documento["banos"],
                 documento["superficie_total"], documento["superficie_cubierta"],
                 len(documento["imagenes"]), documento["latitud"], documento["longitud"],
                 documento["geo"]["localidad"]["nombre"], documento["geo"]["localidad"].get("id"),
                 documento["geo"]["municipio"]["nombre"], documento["geo"]["departamento"]["nombre"],
                 documento["geo"]["provincia"]["nombre"], documento["geo"]["barrio"]["nombre"],
                 area.get("nivel") or "SIN_AREA", area.get("nombre"),
                 sin_acento(area.get("nombre")), sin_acento(documento["geo"]["barrio"]["nombre"]),
                 documento["geo"].get("estado"),
                 json.dumps(documento["alcances"], ensure_ascii=False),
                 json.dumps(documento, ensure_ascii=False)))
            con.execute(
                "insert into busqueda (rowid, id, titulo, descripcion, barrio, area_nombre) "
                "values (?,?,?,?,?,?)",
                (cursor.lastrowid, documento["id"], documento["titulo"] or "",
                 documento["descripcion"] or "", documento["geo"]["barrio"]["nombre"] or "",
                 area.get("nombre") or ""))
        con.executemany("insert or replace into snapshot_meta values (?, ?)",
                        [("orden_de_filas", "id"), ("busqueda_rowid", "propiedades"),
                         ("sintetica", "1")])
        con.commit()
        total = con.execute("select count(*) from propiedades").fetchone()[0]
        integridad = con.execute("pragma integrity_check").fetchone()[0]
    finally:
        con.close()
    return {"snapshot": str(destino), "propiedades": total, "integrity": integridad,
            "sintetica": True}


def es_sintetica(ruta: Path) -> bool:
    """Si la snapshot se declara sintetica. Una que no se puede leer no se afirma sintetica."""
    try:
        con = sqlite3.connect(f"file:{Path(ruta).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        fila = con.execute("select valor from snapshot_meta where clave = 'sintetica'").fetchone()
    except sqlite3.Error:
        return False
    finally:
        con.close()
    return bool(fila and fila[0] == "1")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, required=True,
                    help="ruta del .sqlite3 a escribir (nunca la servida)")
    args = ap.parse_args()
    print(json.dumps(construir(args.salida), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

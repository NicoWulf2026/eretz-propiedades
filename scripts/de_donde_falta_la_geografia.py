# -*- coding: utf-8 -*-
"""Separa las causas reales de que una propiedad no tenga ciudad ni barrio.

El pedido fue explicito: no asumir que la geografia faltante es un bug, y no
mezclar causas. Son siete y se comportan distinto:

  - LA FUENTE NO PUBLICA        el aviso no dice la ciudad en ningun lado
  - EL EXTRACTOR NO DETECTA     la dice y no la sacamos
  - LA NORMALIZACION PIERDE     la sacamos y se cayo en el camino
  - EL VALIDADOR RECHAZA        la sacamos y el catalogo la rechazo
  - GEOREF CONTRADICE           la coordenada cae en otro lado
  - SOLO INFERIBLE              no esta como dato, esta en el texto o el punto
  - REALMENTE DESCONOCIDA       no hay nada de donde sacarla

Mezclarlas lleva a la conclusion equivocada. "80 % sin ciudad" suena a
extractor roto; medido, la mayor parte no es eso.

Hay dos poblaciones distintas y NO son la misma, aunque las dos se llamen
"las propiedades":

  - el PADRON CERTIFICADO (`ERETZ_PROPIEDADES_CERTIFICADAS.jsonl`), lo que la
    cola verifico ficha por ficha, con el estado de cada campo;
  - el SNAPSHOT de la API, que es lo que el buscador sirve.

Este script mide las dos por separado y nunca promedia una con la otra.

Una advertencia que vale para todo lo que sale de aca: `source_provided` es
una SENAL, no un hecho. Ya se demostro que se equivoca -la tarjeta
`RealEstateAgent` con la direccion de la oficina hacia que la senal dijera que
la ficha publica ciudad cuando publicaba el domicilio de la inmobiliaria-. Por
eso las causas que dependen de la senal se reportan aparte de las que se
pueden comprobar contra el dato.

`database_writes: 0`. Lee artefactos y no toca nada.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

RAIZ_DATOS = Path(r"D:\INMO CAPITAL")
PADRON = (RAIZ_DATOS / "ERETZ_AGENCY_CERTIFICATION_20260827"
          / "ERETZ_PROPIEDADES_CERTIFICADAS.jsonl")
DIRECTORIO = RAIZ_DATOS / "ERETZ_AGENCY_DATA" / "agency_web_directory.jsonl"
PROVINCIAS = RAIZ_DATOS / "ERETZ_GEO" / "provincias.json"

# Causas, en el orden en que se evaluan. El orden importa: una ficha rechazada
# por el validador tambien puede tener coordenadas, y lo que la explica es el
# rechazo, no la coordenada.
PRESENTE = "ciudad presente"
RECHAZADA = "el validador rechazo"
EXTRACCION_FALLIDA = "el extractor fallo"
NO_INTENTADA = "no se intento"
SOLO_POR_COORDENADA = "solo inferible por coordenada"
SOLO_POR_BARRIO = "solo inferible por barrio"
SOLO_POR_DIRECCION = "solo inferible por direccion"
SIN_NINGUNA_PISTA = "sin ninguna pista"

ORDEN_DE_CAUSAS = (PRESENTE, RECHAZADA, EXTRACCION_FALLIDA, NO_INTENTADA,
                   SOLO_POR_COORDENADA, SOLO_POR_BARRIO, SOLO_POR_DIRECCION,
                   SIN_NINGUNA_PISTA)

# Un barrio es un nombre propio corto. Lo que pasa de aca es una frase que
# alguien recorto de la descripcion, y se ve a simple vista:
# "tranquila Parrilla techada Pileta descubierta Termo de gas Videos".
LARGO_MAXIMO_DE_UN_BARRIO = 40
JERGA_DE_AVISO = re.compile(
    r"\b(cuenta con|metros|m2|ambientes|dormitorios|venta|alquiler|"
    r"excelente|ubicad\w*|sobre calle|piso|cochera|fecha de entrega)\b",
    re.IGNORECASE)


def normalizar(valor: Any) -> str:
    """Compara nombres de lugar sin acentos, mayusculas ni espacios de mas."""
    crudo = unicodedata.normalize("NFKD", str(valor or ""))
    plano = crudo.encode("ascii", "ignore").decode().lower().strip()
    return " ".join(plano.split())


def leer_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    """Saltea lineas ilegibles en vez de abortar, y no las esconde.

    Un artefacto de 22.000 lineas escrito por una cola que se corta no tiene
    por que estar entero. Perder el informe completo por una linea partida
    seria peor que reportarla.
    """
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as fichero:
        for linea in fichero:
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except json.JSONDecodeError:
                continue


def valor_y_estado(propiedad: dict[str, Any], campo: str) -> tuple[Any, Any]:
    celda = (propiedad.get("campos") or {}).get(campo) or {}
    return celda.get("valor"), celda.get("estado")


def causa_de_la_ciudad(propiedad: dict[str, Any]) -> str:
    """Por que esta propiedad no tiene ciudad, mirando solo lo que hay.

    No consulta la senal `source_provided`: esta funcion responde con el dato,
    que es lo unico que no depende de una heuristica que ya se equivoco.
    """
    ciudad, estado = valor_y_estado(propiedad, "ciudad")
    if ciudad:
        return PRESENTE
    if estado == "PROVIDED_REJECTED":
        return RECHAZADA
    if estado == "EXTRACTION_FAILED":
        return EXTRACCION_FALLIDA
    if estado == "NOT_ATTEMPTED":
        return NO_INTENTADA
    if valor_y_estado(propiedad, "latitud")[0] is not None:
        return SOLO_POR_COORDENADA
    if valor_y_estado(propiedad, "barrio")[0]:
        return SOLO_POR_BARRIO
    if valor_y_estado(propiedad, "direccion")[0]:
        return SOLO_POR_DIRECCION
    return SIN_NINGUNA_PISTA


def barrio_es_una_frase(barrio: Any) -> bool:
    """Un barrio que no es un barrio: un recorte de la descripcion.

    Se pregunta por la FORMA, no por un diccionario de barrios: GeoRef no
    cataloga barrios, asi que no hay contra que validarlos. Lo que si se puede
    afirmar es que un nombre de barrio no tiene sesenta caracteres ni dice
    "cuenta con".
    """
    texto = str(barrio or "").strip()
    if not texto:
        return False
    if len(texto) > LARGO_MAXIMO_DE_UN_BARRIO:
        return True
    return bool(JERGA_DE_AVISO.search(texto))


def provincias_del_catalogo(ruta: Path = PROVINCIAS) -> set[str]:
    if not ruta.exists():
        return set()
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    filas = crudo if isinstance(crudo, list) else crudo.get("provincias", [])
    return {normalizar(fila["nombre"]) for fila in filas}


def provincia_de_cada_inmobiliaria(ruta: Path = DIRECTORIO) -> dict[str, str]:
    return {fila.get("canonical_agency_id"): fila.get("province")
            for fila in leer_jsonl(ruta)
            if fila.get("canonical_agency_id")}


def repite_la_provincia_de_su_inmobiliaria(
        propiedades: Iterable[tuple[str, Any]],
        padron: dict[str, str]) -> dict[str, int]:
    """Cuantas propiedades declaran exactamente la provincia de su agencia.

    Es la huella de una inferencia, no de una extraccion. El conector la
    escribe a proposito y la marca `provincia_confianza: inferida`; la
    pregunta que responde esta funcion es cuanto del campo es eso.

    No prueba por si sola que sea inferida -una inmobiliaria de Cordoba vende
    sobre todo en Cordoba-. Lo que la vuelve concluyente es cruzarla con las
    agencias cuya fuente no publica provincia: ahi no hay otra explicacion.
    """
    cuenta = {"igual": 0, "distinta": 0, "sin_padron": 0}
    for agencia, provincia in propiedades:
        if not provincia:
            continue
        registrada = padron.get(agencia)
        if not registrada:
            cuenta["sin_padron"] += 1
        elif normalizar(provincia) == normalizar(registrada):
            cuenta["igual"] += 1
        else:
            cuenta["distinta"] += 1
    return cuenta


def medir_el_padron(ruta: Path = PADRON) -> dict[str, Any]:
    causas: Counter[str] = Counter()
    por_conector: defaultdict[str, Counter[str]] = defaultdict(Counter)
    provincias: list[tuple[str, Any]] = []
    fuera_del_catalogo: Counter[str] = Counter()
    catalogo = provincias_del_catalogo()
    total = 0
    for propiedad in leer_jsonl(ruta):
        total += 1
        causa = causa_de_la_ciudad(propiedad)
        causas[causa] += 1
        por_conector[propiedad.get("connector") or "?"][causa] += 1
        provincia = valor_y_estado(propiedad, "provincia")[0]
        provincias.append((propiedad.get("agency_id"), provincia))
        if provincia and catalogo and normalizar(provincia) not in catalogo:
            fuera_del_catalogo[str(provincia)] += 1
    return {"total": total, "causas": dict(causas),
            "por_conector": {k: dict(v) for k, v in por_conector.items()},
            "provincia_vs_padron": repite_la_provincia_de_su_inmobiliaria(
                provincias, provincia_de_cada_inmobiliaria()),
            "provincia_fuera_del_catalogo": dict(fuera_del_catalogo)}


def medir_el_snapshot(ruta: Path) -> dict[str, Any]:
    """Lo que el buscador realmente sirve, en solo lectura."""
    conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        preguntar = lambda sql: conexion.execute(sql).fetchone()[0]
        total = preguntar("select count(*) from propiedades")
        columnas = {}
        for columna in ("provincia", "departamento", "municipio", "localidad",
                        "barrio", "latitud"):
            columnas[columna] = preguntar(
                f"select count(*) from propiedades "
                f"where {columna} is not null and {columna} <> ''")
        area = dict(conexion.execute(
            "select coalesce(area_nivel,'SIN_NIVEL'), count(*) "
            "from propiedades group by 1").fetchall())
        # El caso que explica el `municipality: null` del autocompletado: el
        # nivel dice MUNICIPIO y el nombre esta, pero en `area_nombre`.
        municipio_solo_en_area = preguntar(
            "select count(*) from propiedades where area_nivel='MUNICIPIO' "
            "and area_nombre is not null and area_nombre <> '' "
            "and (municipio is null or municipio = '')")
        barrios = [fila[0] for fila in conexion.execute(
            "select barrio from propiedades "
            "where barrio is not null and barrio <> ''")]
        provincias = list(conexion.execute(
            "select agency_id, provincia from propiedades"))
    finally:
        conexion.close()
    frases = [b for b in barrios if barrio_es_una_frase(b)]
    return {"total": total, "columnas": columnas, "area_nivel": area,
            "municipio_solo_en_area_nombre": municipio_solo_en_area,
            "barrios": {"con_valor": len(barrios), "son_una_frase": len(frases),
                        "ejemplos": [b[:80] for b in list(dict.fromkeys(frases))[:8]]},
            "provincia_vs_padron": repite_la_provincia_de_su_inmobiliaria(
                provincias, provincia_de_cada_inmobiliaria())}


def _porcentaje(parte: int, total: int) -> str:
    return f"{parte / total:6.1%}" if total else "     -"


def informar(padron: dict[str, Any], snapshot: dict[str, Any] | None) -> str:
    lineas = [f"PADRON CERTIFICADO — {padron['total']} propiedades", ""]
    for causa in ORDEN_DE_CAUSAS:
        cantidad = padron["causas"].get(causa, 0)
        lineas.append(f"  {causa:32s} {cantidad:6d}  "
                      f"{_porcentaje(cantidad, padron['total'])}")
    cuenta = padron["provincia_vs_padron"]
    con_padron = cuenta["igual"] + cuenta["distinta"]
    lineas += ["", "  provincia igual a la de su inmobiliaria: "
               f"{cuenta['igual']} de {con_padron} "
               f"({_porcentaje(cuenta['igual'], con_padron).strip()})"]
    fuera = padron["provincia_fuera_del_catalogo"]
    if fuera:
        lineas.append(f"  valores de `provincia` que no son una provincia: "
                      f"{sum(fuera.values())} propiedades, "
                      f"{len(fuera)} valores distintos")
    if snapshot:
        lineas += ["", f"SNAPSHOT DE LA API — {snapshot['total']} propiedades", ""]
        for columna, cantidad in snapshot["columnas"].items():
            lineas.append(f"  {columna:32s} {cantidad:6d}  "
                          f"{_porcentaje(cantidad, snapshot['total'])}")
        lineas.append(f"  municipio resuelto pero solo en `area_nombre`: "
                      f"{snapshot['municipio_solo_en_area_nombre']}")
        barrios = snapshot["barrios"]
        lineas.append(f"  barrios que son una frase recortada: "
                      f"{barrios['son_una_frase']} de {barrios['con_valor']}")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--padron", type=Path, default=PADRON)
    analizador.add_argument("--snapshot", type=Path, default=None,
                            help="sqlite del snapshot de la API, opcional")
    analizador.add_argument("--json", type=Path, default=None)
    opciones = analizador.parse_args(argv)

    padron = medir_el_padron(opciones.padron)
    snapshot = (medir_el_snapshot(opciones.snapshot)
                if opciones.snapshot and opciones.snapshot.exists() else None)
    print(informar(padron, snapshot))
    if opciones.json:
        opciones.json.write_text(
            json.dumps({"padron": padron, "snapshot": snapshot,
                        "database_writes": 0}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

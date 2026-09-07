#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""API v2: el contrato de propiedad de ERETZ, servido desde datos reales.

Los endpoints de `main.py` consultan la tabla de produccion, que hoy responde
`PGRST002`. Estos sirven la MISMA forma que va a servir produccion, leyendo la
snapshot local con las 58.427 propiedades reales, para que el frontend se pueda
construir hoy contra datos verdaderos en vez de contra mocks.

Cuando produccion vuelva, cambia de donde sale la fila; la forma no.

**Dos reglas que la API hace cumplir, no el frontend.**

1. El area de busqueda SIEMPRE viaja con su nivel. Un municipio devuelto sin
   decir que es un municipio se lee como una ciudad, y ahi es donde se inventa
   geografia.
2. Una propiedad incompleta se devuelve igual. Lo que falta le quita ALCANCE,
   no existencia: el frontend esconde el filtro, nunca la propiedad.

Solo lee. `database_writes: 0`.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

CONTRATO = "eretz_api_property_v1"

SNAPSHOT = Path(os.environ.get(
    "ERETZ_API_SNAPSHOT",
    r"D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3"))

router = APIRouter(prefix="/v2", tags=["v2"])

# El orden de los niveles importa: si `PROVINCIA` compitiera de igual a igual
# con `LOCALIDAD`, la sugerencia mas util quedaria sepultada.
PRECISION_DE_NIVEL = {"LOCALIDAD": 0, "MUNICIPIO": 1, "DEPARTAMENTO": 2,
                      "PROVINCIA": 3, "SIN_AREA": 4}


def conexion() -> sqlite3.Connection:
    if not SNAPSHOT.exists():
        raise HTTPException(
            status_code=503,
            detail=f"la snapshot no esta generada: {SNAPSHOT.name}. "
                   f"Correr scripts/api_snapshot.py.")
    con = sqlite3.connect(f"file:{SNAPSHOT.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _filtros(operacion, tipo, moneda, precio_min, precio_max, area, nivel,
             localidad, barrio, agencia, ambientes,
             dormitorios) -> tuple[str, list[Any]]:
    """El WHERE y sus parametros. Nunca se interpola texto del usuario."""
    condiciones: list[str] = []
    valores: list[Any] = []
    for columna, valor in (("operacion", (operacion or "").lower() or None),
                           ("tipo_propiedad", (tipo or "").lower() or None),
                           ("moneda", (moneda or "").upper() or None),
                           ("area_nivel", (nivel or "").upper() or None),
                           ("agency_id", agencia),
                           ("ambientes", ambientes),
                           ("dormitorios", dormitorios)):
        if valor not in (None, ""):
            condiciones.append(f"{columna} = ?")
            valores.append(valor)
    # Un precio sin moneda no es un precio: filtrar por rango sin exigir
    # moneda mezclaria 90.000 dolares con 90.000 pesos.
    if precio_min is not None:
        condiciones.append("precio >= ? and moneda is not null")
        valores.append(precio_min)
    if precio_max is not None:
        condiciones.append("precio <= ? and moneda is not null")
        valores.append(precio_max)
    for columna, valor in (("area_nombre", area), ("localidad", localidad),
                           ("barrio", barrio)):
        if valor:
            condiciones.append(f"{columna} like ? collate nocase")
            valores.append(f"%{valor}%")
    return (" where " + " and ".join(condiciones) if condiciones else ""), valores


@router.get("/propiedades")
def listar(
    operacion: Optional[str] = Query(None, description="venta | alquiler"),
    tipo: Optional[str] = Query(None),
    moneda: Optional[str] = Query(None, description="USD | ARS"),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
    area: Optional[str] = Query(None, description="nombre del area de busqueda"),
    nivel: Optional[str] = Query(None, description="LOCALIDAD | MUNICIPIO | ..."),
    localidad: Optional[str] = Query(None),
    barrio: Optional[str] = Query(None),
    agencia: Optional[str] = Query(None),
    ambientes: Optional[int] = Query(None, ge=0),
    dormitorios: Optional[int] = Query(None, ge=0),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    donde, valores = _filtros(operacion, tipo, moneda, precio_min, precio_max,
                              area, nivel, localidad, barrio, agencia,
                              ambientes, dormitorios)
    con = conexion()
    try:
        total = con.execute(
            f"select count(*) from propiedades{donde}", valores).fetchone()[0]
        filas = con.execute(
            # Orden estable: sin un desempate por id, dos paginas consecutivas
            # pueden repetir o saltear una propiedad.
            f"select documento from propiedades{donde} "
            f"order by (precio is null), precio desc, id limit ? offset ?",
            valores + [limit, offset]).fetchall()
    finally:
        con.close()
    return {"contrato": CONTRATO, "total": total, "limit": limit,
            "offset": offset,
            "data": [json.loads(f["documento"]) for f in filas]}


@router.get("/propiedades/mapa")
def mapa(
    operacion: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=5000),
) -> dict[str, Any]:
    """Solo lo que el mapa necesita: sin descripciones ni galerias."""
    donde, valores = _filtros(operacion, tipo, None, None, None, None, None,
                              None, None, None, None, None)
    union = " and " if donde else " where "
    con = conexion()
    try:
        filas = con.execute(
            f"select id, latitud, longitud, precio, moneda, operacion, "
            f"tipo_propiedad, titulo from propiedades{donde}"
            f"{union}latitud is not null and longitud is not null limit ?",
            valores + [limit]).fetchall()
    finally:
        con.close()
    return {"contrato": CONTRATO, "total": len(filas),
            "data": [dict(f) for f in filas]}


@router.get("/propiedades/{propiedad_id}")
def detalle(propiedad_id: str) -> dict[str, Any]:
    con = conexion()
    try:
        fila = con.execute("select documento from propiedades where id = ?",
                           (propiedad_id,)).fetchone()
    finally:
        con.close()
    if not fila:
        raise HTTPException(status_code=404, detail="propiedad inexistente")
    return json.loads(fila["documento"])


@router.get("/areas")
def areas(
    q: Optional[str] = Query(None, description="texto parcial"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Las areas de busqueda disponibles, CADA UNA CON SU NIVEL.

    El nivel no es decorativo: es lo que impide que el frontend muestre un
    municipio como si fuera la ciudad de la propiedad.
    """
    con = conexion()
    try:
        if q:
            filas = con.execute(
                "select area_nivel, area_nombre, count(*) as n from propiedades "
                "where area_nombre is not null and area_nombre like ? "
                "collate nocase group by area_nivel, area_nombre",
                (f"%{q}%",)).fetchall()
        else:
            filas = con.execute(
                "select area_nivel, area_nombre, count(*) as n from propiedades "
                "where area_nombre is not null "
                "group by area_nivel, area_nombre").fetchall()
    finally:
        con.close()
    ordenadas = sorted(
        filas, key=lambda f: (PRECISION_DE_NIVEL.get(f["area_nivel"], 9), -f["n"]))
    return {"contrato": CONTRATO,
            "data": [{"nivel": f["area_nivel"], "nombre": f["area_nombre"],
                      "propiedades": f["n"]} for f in ordenadas[:limit]]}


@router.get("/barrios")
def barrios(q: Optional[str] = Query(None),
            limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Barrios tal como los publica la fuente.

    No estan canonizados y se dice: GeoRef no cataloga barrios, y el texto de
    la inmobiliaria es informacion real aunque no se pueda validar.
    """
    con = conexion()
    try:
        parametros: list[Any] = []
        filtro = "where barrio is not null"
        if q:
            filtro += " and barrio like ? collate nocase"
            parametros.append(f"%{q}%")
        filas = con.execute(
            f"select barrio, count(*) as n from propiedades {filtro} "
            f"group by barrio order by n desc limit ?",
            parametros + [limit]).fetchall()
    finally:
        con.close()
    return {"contrato": CONTRATO, "canonizado": False,
            "data": [{"nombre": f["barrio"], "propiedades": f["n"]}
                     for f in filas]}


@router.get("/filtros")
def filtros() -> dict[str, Any]:
    """Los valores que EXISTEN, con cuantas propiedades tiene cada uno.

    Un filtro que no dice cuantas propiedades hay detras invita a elegir una
    combinacion vacia. Y los que faltan importan tanto como los que estan: por
    eso viaja `sin_dato`.
    """
    con = conexion()
    try:
        def agrupar(columna: str) -> list[dict[str, Any]]:
            filas = con.execute(
                f"select {columna} as v, count(*) as n from propiedades "
                f"where {columna} is not null group by v order by n desc"
            ).fetchall()
            return [{"valor": f["v"], "propiedades": f["n"]} for f in filas]

        sin_dato = {
            columna: con.execute(
                f"select count(*) from propiedades where {columna} is null"
            ).fetchone()[0]
            for columna in ("operacion", "tipo_propiedad", "precio",
                            "localidad", "latitud")}
        rango = con.execute(
            "select moneda, min(precio) as minimo, max(precio) as maximo "
            "from propiedades where precio is not null and moneda is not null "
            "group by moneda").fetchall()
        datos = {"operacion": agrupar("operacion"),
                 "tipo_propiedad": agrupar("tipo_propiedad"),
                 "moneda": agrupar("moneda"),
                 "area_nivel": agrupar("area_nivel")}
    finally:
        con.close()
    return {"contrato": CONTRATO, "filtros": datos,
            "rango_de_precio": [dict(f) for f in rango],
            "sin_dato": sin_dato}


@router.get("/sugerencias")
def sugerencias(q: str = Query(..., min_length=2),
                limit: int = Query(8, ge=1, le=20)) -> dict[str, Any]:
    """Autocompletado sobre areas y barrios, con el nivel a la vista."""
    con = conexion()
    try:
        area = con.execute(
            "select area_nivel, area_nombre, count(*) as n from propiedades "
            "where area_nombre like ? collate nocase "
            "group by area_nivel, area_nombre order by n desc limit ?",
            (f"{q}%", limit)).fetchall()
        barrio = con.execute(
            "select barrio, count(*) as n from propiedades "
            "where barrio like ? collate nocase group by barrio "
            "order by n desc limit ?", (f"{q}%", limit)).fetchall()
    finally:
        con.close()
    salida = [{"tipo": "area", "nivel": f["area_nivel"], "nombre": f["area_nombre"],
               "propiedades": f["n"]} for f in area]
    salida += [{"tipo": "barrio", "nivel": None, "nombre": f["barrio"],
                "propiedades": f["n"]} for f in barrio]
    salida.sort(key=lambda s: -s["propiedades"])
    return {"contrato": CONTRATO, "data": salida[:limit]}


@router.get("/buscar")
def buscar(q: Optional[str] = Query(None),
           operacion: Optional[str] = Query(None),
           tipo: Optional[str] = Query(None),
           limit: int = Query(24, ge=1, le=100),
           offset: int = Query(0, ge=0)) -> dict[str, Any]:
    """Busqueda por texto sobre lo que una persona escribe.

    Mira titulo, descripcion, barrio y area. NO depende de la localidad
    canonica: solo el 16,5 % la tiene, y exigirla dejaria la busqueda vacia
    para cinco de cada seis propiedades.
    """
    donde, valores = _filtros(operacion, tipo, None, None, None, None, None,
                              None, None, None, None, None)
    if q:
        union = " and " if donde else " where "
        donde += (f"{union}(titulo like ? collate nocase or "
                  f"descripcion like ? collate nocase or "
                  f"barrio like ? collate nocase or "
                  f"area_nombre like ? collate nocase)")
        valores += [f"%{q}%"] * 4
    con = conexion()
    try:
        total = con.execute(
            f"select count(*) from propiedades{donde}", valores).fetchone()[0]
        filas = con.execute(
            f"select documento from propiedades{donde} "
            f"order by (precio is null), precio desc, id limit ? offset ?",
            valores + [limit, offset]).fetchall()
    finally:
        con.close()
    return {"contrato": CONTRATO, "consulta": q, "total": total,
            "limit": limit, "offset": offset,
            "data": [json.loads(f["documento"]) for f in filas]}


@router.get("/stats")
def stats() -> dict[str, Any]:
    con = conexion()
    try:
        total = con.execute("select count(*) from propiedades").fetchone()[0]
        por_nivel = con.execute(
            "select area_nivel, count(*) as n from propiedades "
            "group by area_nivel order by n desc").fetchall()
        con_localidad = con.execute(
            "select count(*) from propiedades where localidad is not null"
        ).fetchone()[0]
        conflictos = con.execute(
            "select count(*) from propiedades where geo_estado = 'GEO_CONFLICT'"
        ).fetchone()[0]
    finally:
        con.close()
    return {"contrato": CONTRATO, "propiedades": total,
            "con_localidad_canonica": con_localidad,
            "en_conflicto_geografico": conflictos,
            "area_de_busqueda_por_nivel": {f["area_nivel"]: f["n"]
                                           for f in por_nivel},
            "database_writes": 0}

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
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from api.ranking import RANKING_VERSION, ordenar
from api.models_v2 import AgencyResponse, BatchResponse, MapResponse, SearchResponse

CONTRATO = "eretz_api_property_v1"
SORTS = {"relevance", "price_asc", "price_desc"}
AREA_LEVELS = {"PROVINCIA", "DEPARTAMENTO", "MUNICIPIO", "LOCALIDAD", "SIN_AREA"}
OPERATIONS = {"venta", "alquiler", "alquiler_temporario"}
PROPERTY_TYPES = {"casa", "cochera", "departamento", "galpon", "local", "oficina", "terreno"}
CURRENCIES = {"ARS", "USD"}
MAX_BATCH_IDS = 100

# Cuantas filas se puntuan por cada una que se devuelve. Cinco alcanza para que
# el ranking mande sobre la pagina pedida sin traer la base entera a memoria.
VENTANA_DE_RANKING = 5

# Tope duro de la ventana. Sin el, la ventana crecia con el offset: pedir
# `limit=100&offset=5000` puntuaba 25.500 filas y tardaba diez segundos, lo que
# convierte la busqueda en un boton de denegacion de servicio para cualquiera
# que sepa escribir un numero grande.
TOPE_DE_VENTANA = 400

# Hasta donde se puede paginar una busqueda RANKEADA. Mas alla, el ranking
# dejaria de significar algo -habria que puntuar el resultado entero- y nadie
# va a la pagina cuarenta de una busqueda. La paginacion profunda tiene su
# lugar y es `/propiedades`, que ordena por indice y es estable.
TOPE_DE_OFFSET_RANKEADO = 200

# Lo que el ranking necesita leer de cada fila. Traer el documento completo de
# cuatrocientas filas para quedarse con veinticuatro es pagar el JSON de las
# otras trescientas setenta y seis.
COLUMNAS_DE_RANKING = (
    "id",
    "titulo",
    "descripcion",
    "barrio",
    "area_nombre",
    "area_nivel",
    "geo_estado",
    "precio",
    "operacion",
    "tipo_propiedad",
    "dormitorios",
    "superficie_cubierta",
    "imagenes_n",
)


def _para_rankear(fila) -> dict[str, Any]:
    """La forma minima que `api.ranking` sabe puntuar."""
    return {
        "id": fila["id"],
        "titulo": fila["titulo"],
        "descripcion": fila["descripcion"],
        "precio": fila["precio"],
        "operacion": fila["operacion"],
        "tipo_propiedad": fila["tipo_propiedad"],
        "dormitorios": fila["dormitorios"],
        "superficie_cubierta": fila["superficie_cubierta"],
        # El ranking solo cuenta cuantas fotos hay, no cuales.
        "imagenes": [None] * (fila["imagenes_n"] or 0),
        "geo": {
            "area_busqueda": {"nivel": fila["area_nivel"], "nombre": fila["area_nombre"]},
            "barrio": {"nombre": fila["barrio"]},
            "estado": fila["geo_estado"],
        },
    }


SNAPSHOT = Path(
    os.environ.get(
        "ERETZ_API_SNAPSHOT", r"D:\INMO CAPITAL\ERETZ_API_CONTRACT\ERETZ_API_SNAPSHOT.sqlite3"
    )
)

router = APIRouter(prefix="/v2", tags=["v2"])

# El orden de los niveles importa: si `PROVINCIA` compitiera de igual a igual
# con `LOCALIDAD`, la sugerencia mas util quedaria sepultada.
PRECISION_DE_NIVEL = {
    "LOCALIDAD": 0,
    "MUNICIPIO": 1,
    "DEPARTAMENTO": 2,
    "PROVINCIA": 3,
    "SIN_AREA": 4,
}


def conexion() -> sqlite3.Connection:
    if not SNAPSHOT.exists():
        raise HTTPException(
            status_code=503,
            detail=f"la snapshot no esta generada: {SNAPSHOT.name}. "
            f"Correr scripts/api_snapshot.py.",
        )
    con = sqlite3.connect(f"file:{SNAPSHOT.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tiene_busqueda() -> bool:
    """Si la snapshot trae el indice de texto.

    Una snapshot vieja no lo tiene, y sin este chequeo la busqueda falla con
    un `no such table` que no le dice a nadie que hacer.
    """
    con = conexion()
    try:
        return bool(con.execute("select 1 from sqlite_master where name = 'busqueda'").fetchone())
    finally:
        con.close()


def _termino(q: str) -> str:
    """Lo que la persona escribio, en algo que FTS5 pueda buscar.

    Se escapa cada palabra entre comillas: sin eso, un guion o un asterisco en
    la caja de busqueda se interpretan como sintaxis y la consulta falla con
    un error de sintaxis en vez de no encontrar nada.
    """
    palabras = [p for p in re.split(r"\W+", q, flags=re.UNICODE) if p]
    return " ".join(f'"{p}"' for p in palabras) or '""'


def _filtros(
    operacion=None,
    tipo=None,
    moneda=None,
    precio_min=None,
    precio_max=None,
    area=None,
    nivel=None,
    localidad=None,
    barrio=None,
    agencia=None,
    ambientes=None,
    dormitorios=None,
    banos=None,
    superficie_min=None,
    provincia=None,
    municipio=None,
    departamento=None,
) -> tuple[str, list[Any]]:
    """El WHERE y sus parametros. Nunca se interpola texto del usuario."""
    condiciones: list[str] = []
    valores: list[Any] = []
    for columna, valor in (
        ("operacion", (operacion or "").lower() or None),
        ("tipo_propiedad", (tipo or "").lower() or None),
        ("moneda", (moneda or "").upper() or None),
        ("area_nivel", (nivel or "").upper() or None),
        ("agency_id", agencia),
        ("provincia", provincia),
        ("municipio", municipio),
        ("departamento", departamento),
    ):
        if valor not in (None, ""):
            condiciones.append(f"propiedades.{columna} = ?")
            valores.append(valor)
    for columna, valor in (
        ("ambientes", ambientes),
        ("dormitorios", dormitorios),
        ("banos", banos),
    ):
        if valor is not None:
            condiciones.append(f"propiedades.{columna} >= ?")
            valores.append(valor)
    # Un precio sin moneda no es un precio: filtrar por rango sin exigir
    # moneda mezclaria 90.000 dolares con 90.000 pesos.
    if precio_min is not None:
        condiciones.append("propiedades.precio >= ? and propiedades.moneda is not null")
        valores.append(precio_min)
    if precio_max is not None:
        condiciones.append("propiedades.precio <= ? and propiedades.moneda is not null")
        valores.append(precio_max)
    for columna, valor in (("area_nombre", area), ("localidad", localidad), ("barrio", barrio)):
        if valor:
            condiciones.append(f"propiedades.{columna} like ? collate nocase")
            valores.append(f"%{valor}%")
    if superficie_min is not None:
        condiciones.append(
            "coalesce(propiedades.superficie_total, propiedades.superficie_cubierta) >= ?"
        )
        valores.append(superficie_min)
    return (" where " + " and ".join(condiciones) if condiciones else ""), valores


def _validar_contrato(
    sort: str,
    nivel: Optional[str],
    precio_min,
    precio_max,
    moneda: Optional[str],
    operacion: Optional[str] = None,
    tipo: Optional[str] = None,
) -> None:
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail=f"sort invalido: {sort}")
    if nivel and nivel.upper() not in AREA_LEVELS:
        raise HTTPException(status_code=400, detail=f"nivel geografico invalido: {nivel}")
    if operacion and operacion.lower() not in OPERATIONS:
        raise HTTPException(status_code=400, detail=f"operacion invalida: {operacion}")
    if tipo and tipo.lower() not in PROPERTY_TYPES:
        raise HTTPException(status_code=400, detail=f"tipo invalido: {tipo}")
    if moneda and moneda.upper() not in CURRENCIES:
        raise HTTPException(status_code=400, detail=f"moneda invalida: {moneda}")
    if (
        precio_min is not None or precio_max is not None or sort.startswith("price_")
    ) and not moneda:
        raise HTTPException(
            status_code=400, detail="los rangos y el orden por precio requieren moneda"
        )
    if precio_min is not None and precio_max is not None and precio_min > precio_max:
        raise HTTPException(status_code=400, detail="precio_min no puede superar precio_max")


def _tabla_y_where(q: Optional[str], donde: str, valores: list[Any]) -> tuple[str, str, list[Any]]:
    tabla = "propiedades"
    if q:
        if not _tiene_busqueda():
            raise HTTPException(
                status_code=503,
                detail="la snapshot no tiene el indice de busqueda; correr scripts/api_snapshot.py",
            )
        tabla = "propiedades join busqueda on busqueda.id = propiedades.id"
        donde += (" and " if donde else " where ") + "busqueda match ?"
        valores = valores + [_termino(q)]
    return tabla, donde, valores


class BatchRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=MAX_BATCH_IDS)


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
    donde, valores = _filtros(
        operacion,
        tipo,
        moneda,
        precio_min,
        precio_max,
        area,
        nivel,
        localidad,
        barrio,
        agencia,
        ambientes,
        dormitorios,
    )
    con = conexion()
    try:
        total = con.execute(f"select count(*) from propiedades{donde}", valores).fetchone()[0]
        filas = con.execute(
            # Orden estable: sin un desempate por id, dos paginas consecutivas
            # pueden repetir o saltear una propiedad.
            f"select documento from propiedades{donde} "
            f"order by (precio is null), precio desc, id limit ? offset ?",
            valores + [limit, offset],
        ).fetchall()
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": [json.loads(f["documento"]) for f in filas],
    }


@router.get("/propiedades/mapa", response_model=MapResponse)
def mapa(
    north: float = Query(..., ge=-90, le=90),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    west: float = Query(..., ge=-180, le=180),
    q: Optional[str] = Query(None, max_length=200),
    operacion: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    moneda: Optional[str] = Query(None),
    precio_min: Optional[float] = Query(None, ge=0),
    precio_max: Optional[float] = Query(None, ge=0),
    area: Optional[str] = Query(None, max_length=120),
    nivel: Optional[str] = Query(None),
    localidad: Optional[str] = Query(None, max_length=120),
    municipio: Optional[str] = Query(None, max_length=120),
    departamento: Optional[str] = Query(None, max_length=120),
    provincia: Optional[str] = Query(None, max_length=120),
    barrio: Optional[str] = Query(None, max_length=120),
    ambientes: Optional[int] = Query(None, ge=0),
    dormitorios: Optional[int] = Query(None, ge=0),
    banos: Optional[int] = Query(None, ge=0),
    superficie_min: Optional[float] = Query(None, ge=0),
    limit: int = Query(2000, ge=1, le=5000),
) -> dict[str, Any]:
    """Puntos dentro del viewport; clustering queda en Leaflet sobre un conjunto acotado."""
    if north <= south or east <= west:
        raise HTTPException(status_code=400, detail="viewport invalido")
    _validar_contrato("relevance", nivel, precio_min, precio_max, moneda, operacion, tipo)
    donde, valores = _filtros(
        operacion,
        tipo,
        moneda,
        precio_min,
        precio_max,
        area,
        nivel,
        localidad,
        barrio,
        None,
        ambientes,
        dormitorios,
        banos,
        superficie_min,
        provincia,
        municipio,
        departamento,
    )
    tabla, donde, valores = _tabla_y_where(q, donde, valores)
    total_matches_where = donde
    viewport = (
        "latitud is not null and longitud is not null and latitud != 0 and longitud != 0 "
        "and latitud <= ? and latitud >= ? and longitud <= ? and longitud >= ?"
    )
    viewport_where = donde + (" and " if donde else " where ") + viewport
    viewport_values = valores + [north, south, east, west]
    con = conexion()
    try:
        total_matches = con.execute(
            f"select count(*) from {tabla}{total_matches_where}", valores
        ).fetchone()[0]
        viewport_matches = con.execute(
            f"select count(*) from {tabla}{viewport_where}", viewport_values
        ).fetchone()[0]
        filas = con.execute(
            f"select propiedades.id, propiedades.latitud, propiedades.longitud, "
            f"propiedades.precio, propiedades.moneda, propiedades.operacion, "
            f"propiedades.tipo_propiedad, propiedades.titulo from {tabla}{viewport_where} "
            f"order by propiedades.id limit ?",
            viewport_values + [limit],
        ).fetchall()
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "total_matches": total_matches,
        "viewport_matches": viewport_matches,
        "returned_points": len(filas),
        "truncated": viewport_matches > len(filas),
        "limit": limit,
        "data": [dict(f) for f in filas],
    }


@router.get("/propiedades/{propiedad_id}")
def detalle(propiedad_id: str) -> dict[str, Any]:
    con = conexion()
    try:
        fila = con.execute(
            "select documento from propiedades where id = ?", (propiedad_id,)
        ).fetchone()
        if (
            not fila
            and con.execute("select 1 from sqlite_master where name='property_aliases'").fetchone()
        ):
            fila = con.execute(
                "select p.documento from property_aliases a join propiedades p on p.id=a.property_id "
                "where a.alias = ?",
                (propiedad_id,),
            ).fetchone()
    finally:
        con.close()
    if not fila:
        raise HTTPException(status_code=404, detail="propiedad inexistente")
    return json.loads(fila["documento"])


@router.get("/agencias/{agency_id}", response_model=AgencyResponse)
def agencia_detalle(agency_id: str) -> dict[str, Any]:
    if not agency_id or len(agency_id) > 200:
        raise HTTPException(status_code=400, detail="agency_id invalido")
    con = conexion()
    try:
        existe = con.execute(
            "select 1 from propiedades where agency_id = ? limit 1", (agency_id,)
        ).fetchone()
    finally:
        con.close()
    if not existe:
        raise HTTPException(status_code=404, detail="agencia inexistente")
    public_name = agency_id.split(":", 1)[-1].strip()
    return {
        "contrato": CONTRATO,
        "data": {
            "agency_id": agency_id,
            "name": public_name,
            "logo": None,
            "website": None,
            "contact": {"status": "UNAVAILABLE", "phone": None, "whatsapp": None, "email": None},
        },
    }


@router.post("/propiedades/batch", response_model=BatchResponse)
def propiedades_batch(payload: BatchRequest = Body(...)) -> dict[str, Any]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in payload.ids:
        value = raw.strip()
        if not value or len(value) > 200:
            raise HTTPException(status_code=400, detail="id invalido")
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    con = conexion()
    try:
        marks = ",".join("?" * len(ordered))
        rows = con.execute(
            f"select id, documento from propiedades where id in ({marks})", ordered
        ).fetchall()
        documents = {row["id"]: json.loads(row["documento"]) for row in rows}
        if con.execute("select 1 from sqlite_master where name='property_aliases'").fetchone():
            aliases = con.execute(
                f"select a.alias, p.documento from property_aliases a join propiedades p "
                f"on p.id=a.property_id where a.alias in ({marks})",
                ordered,
            ).fetchall()
            documents.update({row["alias"]: json.loads(row["documento"]) for row in aliases})
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "items": [documents[key] for key in ordered if key in documents],
        "missing_ids": [key for key in ordered if key not in documents],
        "requested_ids": ordered,
    }


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
                (f"%{q}%",),
            ).fetchall()
        else:
            filas = con.execute(
                "select area_nivel, area_nombre, count(*) as n from propiedades "
                "where area_nombre is not null "
                "group by area_nivel, area_nombre"
            ).fetchall()
    finally:
        con.close()
    ordenadas = sorted(filas, key=lambda f: (PRECISION_DE_NIVEL.get(f["area_nivel"], 9), -f["n"]))
    return {
        "contrato": CONTRATO,
        "data": [
            {"nivel": f["area_nivel"], "nombre": f["area_nombre"], "propiedades": f["n"]}
            for f in ordenadas[:limit]
        ],
    }


@router.get("/barrios")
def barrios(q: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
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
            parametros + [limit],
        ).fetchall()
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "canonizado": False,
        "data": [{"nombre": f["barrio"], "propiedades": f["n"]} for f in filas],
    }


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
            for columna in ("operacion", "tipo_propiedad", "precio", "localidad", "latitud")
        }
        rango = con.execute(
            "select moneda, min(precio) as minimo, max(precio) as maximo "
            "from propiedades where precio is not null and moneda is not null "
            "group by moneda"
        ).fetchall()
        datos = {
            "operacion": agrupar("operacion"),
            "tipo_propiedad": agrupar("tipo_propiedad"),
            "moneda": agrupar("moneda"),
            "area_nivel": agrupar("area_nivel"),
        }
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "filtros": datos,
        "rango_de_precio": [dict(f) for f in rango],
        "sin_dato": sin_dato,
    }


@router.get("/sugerencias")
def sugerencias(
    q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=20)
) -> dict[str, Any]:
    """Autocompletado sobre areas y barrios, con el nivel a la vista."""
    con = conexion()
    try:
        area = con.execute(
            "select area_nivel, area_nombre, count(*) as n from propiedades "
            "where area_nombre like ? collate nocase "
            "group by area_nivel, area_nombre order by n desc limit ?",
            (f"{q}%", limit),
        ).fetchall()
        barrio = con.execute(
            "select barrio, count(*) as n from propiedades "
            "where barrio like ? collate nocase group by barrio "
            "order by n desc limit ?",
            (f"{q}%", limit),
        ).fetchall()
    finally:
        con.close()
    salida = [
        {
            "tipo": "area",
            "nivel": f["area_nivel"],
            "nombre": f["area_nombre"],
            "propiedades": f["n"],
        }
        for f in area
    ]
    salida += [
        {"tipo": "barrio", "nivel": None, "nombre": f["barrio"], "propiedades": f["n"]}
        for f in barrio
    ]
    salida.sort(key=lambda s: -s["propiedades"])
    return {"contrato": CONTRATO, "data": salida[:limit]}


@router.get("/buscar", response_model=SearchResponse)
def buscar(
    q: Optional[str] = Query(None, max_length=200),
    operacion: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    moneda: Optional[str] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    area: Optional[str] = None,
    nivel: Optional[str] = None,
    localidad: Optional[str] = None,
    municipio: Optional[str] = None,
    departamento: Optional[str] = None,
    provincia: Optional[str] = None,
    barrio: Optional[str] = None,
    ambientes: Optional[int] = None,
    dormitorios: Optional[int] = None,
    banos: Optional[int] = None,
    superficie_min: Optional[float] = None,
    sort: Literal["relevance", "price_asc", "price_desc"] = "relevance",
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Busqueda por texto sobre lo que una persona escribe.

    Mira titulo, descripcion, barrio y area. NO depende de la localidad
    canonica: solo el 16,5 % la tiene, y exigirla dejaria la busqueda vacia
    para cinco de cada seis propiedades.
    """
    _validar_contrato(sort, nivel, precio_min, precio_max, moneda, operacion, tipo)
    donde, valores = _filtros(
        operacion,
        tipo,
        moneda,
        precio_min,
        precio_max,
        area,
        nivel,
        localidad,
        barrio,
        None,
        ambientes,
        dormitorios,
        banos,
        superficie_min,
        provincia,
        municipio,
        departamento,
    )
    otros_filtros = bool(donde)
    # FTS5 en vez de cuatro `LIKE '%...%'`. Medido sobre las 58.427: el scan
    # tardaba 299 ms y el indice tarda 3. Ademas el tokenizador ignora
    # acentos, asi que "cordoba" y "Cordoba" devuelven lo mismo sin que
    # ninguna regla lo trate como caso especial.
    tabla, donde, valores = _tabla_y_where(q, donde, valores)
    if sort == "relevance" and offset > TOPE_DE_OFFSET_RANKEADO:
        raise HTTPException(
            status_code=400,
            detail=f"la busqueda rankeada pagina hasta offset "
            f"{TOPE_DE_OFFSET_RANKEADO}. Para recorrer el catalogo "
            f"entero, /v2/propiedades ordena por indice y es estable.",
        )

    ventana = min(max(limit + offset, 1) * VENTANA_DE_RANKING, TOPE_DE_VENTANA)
    columnas = ", ".join(f"propiedades.{c}" for c in COLUMNAS_DE_RANKING)
    con = conexion()
    try:
        if q and not otros_filtros:
            # Contar con el JOIN cuesta 333 ms; contar sobre el indice de texto
            # solo, 2,2. Cuando la consulta es unicamente texto, la fila de
            # `propiedades` no aporta nada al conteo y unirla es pagar por
            # nada.
            total = con.execute(
                "select count(*) from busqueda where busqueda match ?", [valores[-1]]
            ).fetchone()[0]
        else:
            total = con.execute(f"select count(*) from {tabla}{donde}", valores).fetchone()[0]
        # Se puntua una ventana amplia y despues se pagina: ordenar solo la
        # pagina pedida rankearia 24 filas elegidas por otro criterio, que es
        # rankear cualquier cosa. Pero se puntua sobre una PROYECCION: traer el
        # documento completo de cuatrocientas filas para quedarse con
        # veinticuatro es pagar el JSON de las otras trescientas setenta y seis.
        if sort == "relevance":
            crudas = con.execute(
                f"select {columnas} from {tabla}{donde} limit ?", valores + [ventana]
            ).fetchall()
            pagina = ordenar([_para_rankear(f) for f in crudas], q or "")[offset : offset + limit]
        else:
            direction = "asc" if sort == "price_asc" else "desc"
            pagina = [
                dict(row)
                for row in con.execute(
                    f"select {columnas} from {tabla}{donde} order by precio {direction}, "
                    f"propiedades.id asc limit ? offset ?",
                    valores + [limit, offset],
                ).fetchall()
            ]
            for row in pagina:
                row["ranking"] = None
        # Recien ahora se hidrata: una consulta por la pagina que se devuelve.
        documentos = {}
        if pagina:
            marcas = ",".join("?" * len(pagina))
            documentos = {
                f["id"]: json.loads(f["documento"])
                for f in con.execute(
                    f"select id, documento from propiedades where id in ({marcas})",
                    [p["id"] for p in pagina],
                )
            }
    finally:
        con.close()
    data = []
    for p in pagina:
        completo = documentos.get(p["id"], {})
        completo["ranking"] = p["ranking"]
        data.append(completo)
    return {
        "contrato": CONTRATO,
        "ranking": RANKING_VERSION if sort == "relevance" else None,
        "sort": sort,
        "consulta": q,
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": data,
    }


@router.get("/stats")
def stats() -> dict[str, Any]:
    con = conexion()
    try:
        total = con.execute("select count(*) from propiedades").fetchone()[0]
        por_nivel = con.execute(
            "select area_nivel, count(*) as n from propiedades group by area_nivel order by n desc"
        ).fetchall()
        con_localidad = con.execute(
            "select count(*) from propiedades where localidad is not null"
        ).fetchone()[0]
        conflictos = con.execute(
            "select count(*) from propiedades where geo_estado = 'GEO_CONFLICT'"
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "contrato": CONTRATO,
        "propiedades": total,
        "con_localidad_canonica": con_localidad,
        "en_conflicto_geografico": conflictos,
        "area_de_busqueda_por_nivel": {f["area_nivel"]: f["n"] for f in por_nivel},
        "database_writes": 0,
    }

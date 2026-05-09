from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Inmolink API", version="1.0.0")

# CORS — permite que el frontend pueda llamar a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "propiedades")

HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
}


def supabase_get(params: dict) -> list:
    """Hace un GET a la API REST de Supabase con los parámetros dados."""
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        headers=HEADERS,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


@app.get("/")
def root():
    return {"status": "ok", "proyecto": "Inmolink API"}


@app.get("/propiedades")
def listar_propiedades(
    operacion: Optional[str] = Query(None, description="alquiler o venta"),
    tipo: Optional[str] = Query(None, description="casa, departamento, terreno, etc."),
    ciudad: Optional[str] = Query(None),
    barrio: Optional[str] = Query(None),
    precio_min: Optional[int] = Query(None),
    precio_max: Optional[int] = Query(None),
    moneda: Optional[str] = Query(None, description="ARS o USD"),
    ambientes: Optional[int] = Query(None),
    dormitorios: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    params = {
        "select": "*",
        "limit": limit,
        "offset": offset,
        "order": "calidad_score.desc",
    }

    if operacion:
        params["operacion"] = f"eq.{operacion.lower()}"
    if tipo:
        params["tipo_propiedad"] = f"eq.{tipo.lower()}"
    if ciudad:
        params["ciudad"] = f"ilike.*{ciudad}*"
    if barrio:
        params["barrio_normalizado"] = f"ilike.*{barrio}*"
    if moneda:
        params["moneda"] = f"eq.{moneda.upper()}"
    if ambientes:
        params["ambientes"] = f"eq.{ambientes}"
    if dormitorios:
        params["dormitorios"] = f"eq.{dormitorios}"
    if precio_min:
        params["precio"] = f"gte.{precio_min}"
    if precio_max:
        # Si ya hay precio_min, no podemos sobreescribir el key
        # Supabase acepta múltiples filtros en el mismo campo con and
        params["and"] = f"(precio.gte.{precio_min or 0},precio.lte.{precio_max})"
        params.pop("precio", None)

    data = supabase_get(params)
    return {"total": len(data), "offset": offset, "limit": limit, "data": data}


@app.get("/propiedades/mapa")
def propiedades_mapa(
    operacion: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    ciudad: Optional[str] = Query(None),
    precio_min: Optional[int] = Query(None),
    precio_max: Optional[int] = Query(None),
):
    """Retorna solo los campos necesarios para mostrar en el mapa."""
    params = {
        "select": "id,titulo,precio,moneda,latitud,longitud,tipo_propiedad,operacion,barrio_normalizado",
        "latitud": "not.is.null",
        "longitud": "not.is.null",
        "limit": 1000,
    }

    if operacion:
        params["operacion"] = f"eq.{operacion.lower()}"
    if tipo:
        params["tipo_propiedad"] = f"eq.{tipo.lower()}"
    if ciudad:
        params["ciudad"] = f"ilike.*{ciudad}*"
    if precio_min:
        params["precio"] = f"gte.{precio_min}"
    if precio_max:
        params["and"] = f"(precio.gte.{precio_min or 0},precio.lte.{precio_max})"
        params.pop("precio", None)

    data = supabase_get(params)
    return {"total": len(data), "data": data}


@app.get("/propiedades/{propiedad_id}")
def detalle_propiedad(propiedad_id: int):
    """Retorna el detalle completo de una propiedad por ID."""
    params = {
        "select": "*",
        "id": f"eq.{propiedad_id}",
        "limit": 1,
    }
    data = supabase_get(params)
    if not data:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Propiedad no encontrada")
    return data[0]


@app.get("/barrios")
def listar_barrios(ciudad: Optional[str] = Query(None)):
    """Lista todos los barrios disponibles para los filtros."""
    params = {
        "select": "barrio_normalizado",
        "barrio_normalizado": "not.is.null",
        "limit": 1000,
    }
    if ciudad:
        params["ciudad"] = f"ilike.*{ciudad}*"

    data = supabase_get(params)
    barrios = sorted(set(
        item["barrio_normalizado"]
        for item in data
        if item.get("barrio_normalizado")
    ))
    return {"total": len(barrios), "data": barrios}


@app.get("/stats")
def estadisticas():
    """Estadísticas generales de la base de datos."""
    total = supabase_get({"select": "id", "limit": 10000})
    alquileres = supabase_get({"select": "id", "operacion": "eq.alquiler", "limit": 10000})
    ventas = supabase_get({"select": "id", "operacion": "eq.venta", "limit": 10000})
    con_coords = supabase_get({
        "select": "id",
        "latitud": "not.is.null",
        "limit": 10000,
    })

    return {
        "total_propiedades": len(total),
        "alquileres": len(alquileres),
        "ventas": len(ventas),
        "con_coordenadas": len(con_coords),
    }
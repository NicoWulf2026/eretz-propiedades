"""
importar_excel.py
-----------------
Importa inmobiliarias desde Excel a inmobiliarias_scraping en Supabase.

Lógica:
  - Si el nombre ya existe → completa solo los campos que están vacíos/nulos
  - Si no existe → inserta como nuevo registro
"""

import os
import re
import sys
import unicodedata
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

EXCEL_FILE   = r"D:\Inmobiliairas .xlsx"
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
TABLA        = "inmobiliarias_scraping"

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("excel_import")

# =============================================================================
# HELPERS
# =============================================================================

def limpiar(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return " ".join(str(v).strip().split())

def normalizar_clave(texto: str) -> str:
    """Normaliza para comparar nombres: minúsculas, sin acentos, sin puntuación."""
    t = texto.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def normalizar_telefono(tel: str) -> Optional[str]:
    if not tel:
        return None
    digits = re.sub(r"\D", "", tel)
    if not digits or len(digits) < 7:
        return None
    if len(digits) == 10:
        return f"+54{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+54{digits[1:]}"
    if len(digits) == 12 and digits.startswith("54"):
        return f"+{digits}"
    return digits

# =============================================================================
# SUPABASE
# =============================================================================

def _headers(prefer: str = "return=minimal") -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }

def cargar_existentes() -> Dict[str, Dict]:
    """Carga todos los registros actuales de Supabase, indexados por nombre normalizado."""
    log.info("Cargando registros existentes de Supabase...")
    todos = []
    pagina = 0
    tam = 1000
    while True:
        desde = pagina * tam
        hasta = desde + tam - 1
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA}",
            headers={**_headers(), "Range": f"{desde}-{hasta}", "Range-Unit": "items"},
            params={"select": "id,nombre,telefono,direccion,ciudad,provincia,fuente"},
            timeout=30,
        )
        if resp.status_code == 416:
            break
        lote = resp.json()
        if not lote:
            break
        todos.extend(lote)
        if len(lote) < tam:
            break
        pagina += 1

    # Indexar por nombre normalizado
    indice = {}
    for r in todos:
        clave = normalizar_clave(r.get("nombre") or "")
        if clave:
            indice[clave] = r
    log.info(f"Registros existentes: {len(todos)}")
    return indice

def insertar(registro: Dict[str, Any]) -> bool:
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{TABLA}",
        headers=_headers(),
        json=registro,
        timeout=15,
    )
    if resp.status_code in (200, 201, 204):
        return True
    log.warning(f"  INSERT error {resp.status_code}: {registro.get('nombre')} — {resp.text[:100]}")
    return False

def completar(id_registro, campos: Dict[str, Any]) -> bool:
    """PATCH solo los campos indicados en el registro con ese id."""
    if not campos or not id_registro:
        return True
    resp = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{TABLA}?id=eq.{id_registro}",
        headers=_headers(),
        json=campos,
        timeout=15,
    )
    if resp.status_code in (200, 204):
        return True
    log.warning(f"  PATCH error {resp.status_code}: id={id_registro} — {resp.text[:100]}")
    return False

# =============================================================================
# MAIN
# =============================================================================

def run():
    log.info("=" * 55)
    log.info("IMPORTAR EXCEL → Supabase")
    log.info(f"Archivo : {EXCEL_FILE}")
    log.info(f"Tabla   : {TABLA}")
    log.info("=" * 55)

    if not SUPABASE_URL or not SUPABASE_KEY:
        log.error("Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env")
        return

    # Leer Excel (sin encabezados — primera fila es dato)
    df = pd.read_excel(EXCEL_FILE, header=None)
    df.columns = ["corredor", "inmobiliaria", "estado", "direccion", "telefono", "email", "localidad"]
    log.info(f"Filas en Excel: {len(df)}")

    # Cargar registros existentes de Supabase
    existentes = cargar_existentes()

    insertados = 0
    completados = 0
    sin_cambios = 0
    saltados = 0

    for _, row in df.iterrows():
        nombre = limpiar(row["inmobiliaria"])
        if not nombre:
            saltados += 1
            continue

        tel      = normalizar_telefono(limpiar(row["telefono"]))
        dir_     = limpiar(row["direccion"]) or None
        localidad = limpiar(row["localidad"]).title() if limpiar(row["localidad"]) else None

        clave = normalizar_clave(nombre)

        if clave in existentes:
            # Ya existe — completar solo campos vacíos
            existente = existentes[clave]
            patch = {}
            if tel and not existente.get("telefono"):
                patch["telefono"] = tel
            if dir_ and not existente.get("direccion"):
                patch["direccion"] = dir_
            if localidad and not existente.get("ciudad"):
                patch["ciudad"] = localidad
            if not existente.get("provincia"):
                patch["provincia"] = "Santa Fe"

            if patch:
                ok = completar(existente["id"], patch)
                if ok:
                    completados += 1
                    log.info(f"  [COMPLETADO] {nombre} → {list(patch.keys())}")
            else:
                sin_cambios += 1
        else:
            # No existe — insertar nuevo
            ok = insertar({
                "nombre":    nombre,
                "telefono":  tel,
                "direccion": dir_,
                "ciudad":    localidad,
                "provincia": "Santa Fe",
                "categoria": "corredor inmobiliario",
                "fuente":    "excel_propio",
            })
            if ok:
                insertados += 1
                # Agregar al índice para evitar duplicados dentro del mismo Excel
                existentes[clave] = {"id": None, "nombre": nombre,
                                     "telefono": tel, "direccion": dir_,
                                     "ciudad": localidad}

    log.info("=" * 55)
    log.info(f"Insertados nuevos      : {insertados}")
    log.info(f"Completados (con datos): {completados}")
    log.info(f"Sin cambios (completos): {sin_cambios}")
    log.info(f"Saltados (sin nombre)  : {saltados}")
    log.info("=" * 55)

if __name__ == "__main__":
    run()

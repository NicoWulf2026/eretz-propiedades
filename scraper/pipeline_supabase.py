"""
pipeline_supabase.py
---------------------
Pipeline robusto de carga, validación y rescrapeo para la tabla
inmobiliarias_scraping en Supabase.

Partes:
  1+2  Upsert con batching y retry automático
  3    Logs detallados (consola + archivo pipeline.log)
  4    Detección de registros faltantes (CSV vs Supabase)
  5    Análisis de cobertura por provincia / ciudad
  6    Rescrapeo automático de faltantes
  7    Robustez: el proceso no se rompe si falla un registro o un batch

Uso:
    python pipeline_supabase.py                  # pipeline completo
    python pipeline_supabase.py --solo-carga     # solo carga CSVs → Supabase
    python pipeline_supabase.py --solo-analisis  # solo reporte de cobertura
    python pipeline_supabase.py --rescraper      # detecta faltantes y reintenta
"""

from __future__ import annotations

import os
import sys
import csv
import json
import time
import random
import argparse
import traceback
import importlib.util
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re
import requests
from requests.exceptions import (
    SSLError,
    Timeout,
    ConnectionError as RequestsConnectionError,
)

try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if not os.path.exists(_env):
        _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=_env)
except ImportError:
    pass


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

SUPABASE_URL   = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY   = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY", "")
)
SUPABASE_TABLE = "inmobiliarias_scraping"

BATCH_SIZE      = 200   # registros por request
MAX_RETRIES     = 3     # intentos por batch antes de rendirse
BACKOFF_BASE    = 2     # segundos base (2^intento)
REQUEST_TIMEOUT = 30    # segundos por request HTTP
MAX_QUERIES_RESCRAPE = 50  # límite de queries en un ciclo de rescrapeo

script_dir  = os.path.dirname(os.path.abspath(__file__))
CSV_LUGARES = os.path.join(script_dir, "..", "google_lugares.csv")
CSV_SEARCH  = os.path.join(script_dir, "..", "google_search.csv")
LOG_FILE    = os.path.join(script_dir, "..", "pipeline.log")


# =============================================================================
# PARTE 3 — LOGGING
# =============================================================================

_log_fh: object = None


def _init_log():
    global _log_fh
    try:
        _log_fh = open(LOG_FILE, "a", encoding="utf-8")
        _log_fh.write(f"\n{'='*65}\n[{datetime.now()}] NUEVA EJECUCIÓN\n{'='*65}\n")
        _log_fh.flush()
    except Exception:
        pass


def log(msg: str, nivel: str = "INFO"):
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{nivel}] {msg}"
    print(linea, flush=True)
    if _log_fh:
        try:
            _log_fh.write(linea + "\n")
            _log_fh.flush()
        except Exception:
            pass


def log_ok(msg: str):   log(msg, " OK ")
def log_warn(msg: str): log(msg, "WARN")
def log_err(msg: str):  log(msg, "ERR ")


# =============================================================================
# ESTADÍSTICAS
# =============================================================================

@dataclass
class PipelineStats:
    procesados:   int = 0
    insertados:   int = 0
    actualizados: int = 0
    errores:      int = 0
    faltantes:    int = 0
    rescraped:    int = 0
    batches_ok:   int = 0
    batches_err:  int = 0

    def resumen(self) -> str:
        lineas = [
            "",
            "=" * 55,
            "  RESUMEN PIPELINE",
            "=" * 55,
            f"  Registros procesados : {self.procesados}",
            f"  Insertados (nuevos)  : {self.insertados}",
            f"  Actualizados         : {self.actualizados}",
            f"  Errores              : {self.errores}",
            f"  Faltantes detectados : {self.faltantes}",
            f"  Rescraped            : {self.rescraped}",
            f"  Batches exitosos     : {self.batches_ok}",
            f"  Batches fallidos     : {self.batches_err}",
            "=" * 55,
        ]
        return "\n".join(lineas)


STATS = PipelineStats()


# =============================================================================
# PARTE 1+2 — UPSERT CON BATCHING Y RETRY
# =============================================================================

def _supabase_headers(prefer_extra: str = "") -> dict:
    prefer = "resolution=merge-duplicates"
    if prefer_extra:
        prefer += f",{prefer_extra}"
    return {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        prefer,
    }


def upsert_batch(
    registros: list[dict],
    on_conflict: str = "web",
    max_intentos: int = MAX_RETRIES,
) -> tuple[bool, int, str]:
    """
    Hace upsert de un batch a Supabase con retry y backoff exponencial.

    on_conflict: columna usada para resolver duplicados.
        - "web"   → registros con URL única  (preferido)
        - "id"    → cuando el registro ya tiene id de Supabase

    Returns: (ok, count, mensaje)
    """
    if not registros:
        return True, 0, "batch vacío"

    # Strip id para no interferir con el PK autogenerado
    registros = [{k: v for k, v in r.items() if k != "id"} for r in registros]

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict={on_conflict}"

    for intento in range(1, max_intentos + 1):
        try:
            resp = requests.post(
                url,
                headers=_supabase_headers("return=minimal"),
                data=json.dumps(registros, default=str),
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code in (200, 201):
                return True, len(registros), "ok"

            # Conflicto 409: otro constraint secundario interfiere en el UPDATE.
            # Fallback a ignore-duplicates: inserta los nuevos, saltea los existentes.
            if resp.status_code == 409:
                log_warn(
                    f"    409 en on_conflict={on_conflict}. "
                    f"Cambiando a ignore-duplicates (solo inserta nuevos)..."
                )
                return _insertar_ignorando_duplicados(registros, on_conflict=on_conflict)

            # Error 500 — distinguir entre error PG y error de servidor
            if resp.status_code == 500:
                try:
                    pg_code = resp.json().get("code", "")
                except Exception:
                    pg_code = ""

                if pg_code == "21000":
                    # Duplicados internos en el batch → deduplicar y reintentar UNA vez
                    deduped = _deduplicar_batch(registros)
                    if len(deduped) < len(registros):
                        log_warn(
                            f"    21000: {len(registros) - len(deduped)} duplicados "
                            f"internos. Deduplicando y reintentando..."
                        )
                        return upsert_batch(deduped, on_conflict=on_conflict,
                                            max_intentos=1)
                    return False, 0, f"21000: duplicados pero sin reducción posible"

                # Otros 500 (error de servidor transitorio) → retry
                raise requests.HTTPError(f"HTTP 500: {resp.text[:200]}")

            # 502/503/504 → retry
            if resp.status_code in (502, 503, 504):
                raise requests.HTTPError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )

            # Error de schema (sin constraint) — no tiene sentido reintentar
            if resp.status_code == 400:
                try:
                    code = resp.json().get("code", "")
                    if code == "42P10":
                        return False, 0, "42P10:NO_CONSTRAINT"
                except Exception:
                    pass

            # Cualquier otro error no recuperable
            return False, 0, f"HTTP {resp.status_code}: {resp.text[:200]}"

        except (SSLError, Timeout, RequestsConnectionError) as e:
            espera = BACKOFF_BASE ** intento + random.uniform(0, 1)
            log_warn(
                f"    Red: {type(e).__name__} (intento {intento}/{max_intentos}). "
                f"Reintentando en {espera:.1f}s..."
            )
            time.sleep(espera)

        except requests.HTTPError as e:
            espera = BACKOFF_BASE ** intento
            log_warn(
                f"    HTTP error (intento {intento}/{max_intentos}): {e}. "
                f"Reintentando en {espera}s..."
            )
            time.sleep(espera)

        except Exception as e:
            log_err(f"    Error inesperado en batch: {e}")
            return False, 0, str(e)

    return False, 0, f"Fallido tras {max_intentos} intentos"


def cargar_registros(
    registros: list[dict],
    on_conflict: str = "web",
    batch_size: int = BATCH_SIZE,
) -> None:
    """
    Divide los registros en batches y los sube a Supabase con upsert.
    Actualiza STATS globalmente.
    """
    # Separar registros con y sin web para aplicar la estrategia correcta
    con_web    = [r for r in registros if r.get("web")]
    sin_web    = [r for r in registros if not r.get("web")]

    _cargar_grupo(con_web,  on_conflict="web",  batch_size=batch_size, label="con web")
    _cargar_grupo(sin_web,  on_conflict="nombre", batch_size=batch_size, label="sin web")


def _cargar_grupo(
    registros: list[dict],
    on_conflict: str,
    batch_size: int,
    label: str,
) -> None:
    if not registros:
        return

    # Deduplicar ANTES de armar los batches para evitar el error 21000
    antes = len(registros)
    registros = _deduplicar_batch(registros)
    if len(registros) < antes:
        log_warn(
            f"  Deduplicación previa ({label}): "
            f"{antes - len(registros)} duplicados eliminados del lote"
        )

    batches = [
        registros[i: i + batch_size]
        for i in range(0, len(registros), batch_size)
    ]
    log(
        f"  Cargando {len(registros)} registros ({label}) "
        f"en {len(batches)} batches — on_conflict={on_conflict}"
    )

    # Estado del modo pre-filtro (activado si la tabla no tiene UNIQUE constraint)
    modo_prefiltro     = False
    webs_existentes:   set = set()
    nombres_existentes: set = set()

    for n, batch in enumerate(batches, 1):

        if modo_prefiltro:
            ok, count, msg = _insertar_sin_constraint(
                batch, webs_existentes, nombres_existentes
            )
        else:
            ok, count, msg = upsert_batch(batch, on_conflict=on_conflict)

            # Primera vez que aparece el error de constraint → activar pre-filtro
            if not ok and msg == "42P10:NO_CONSTRAINT":
                log_warn("  ⚠  La tabla no tiene UNIQUE constraint en la columna solicitada.")
                log_warn("  ⚠  Ejecutar en Supabase SQL Editor para habilitar upsert real:")
                log_warn(f"     ALTER TABLE {SUPABASE_TABLE}")
                log_warn(f"       ADD CONSTRAINT uq_scraping_web UNIQUE (web);")
                log_warn("  →  Cambiando a modo inserción con pre-filtro (sin duplicar)...")
                modo_prefiltro = True

                # Traer estado actual de Supabase una sola vez
                existentes = obtener_registros_supabase(["nombre", "web"])
                webs_existentes = {
                    (r.get("web") or "").strip().rstrip("/").lower()
                    for r in existentes if r.get("web")
                }
                nombres_existentes = {
                    (r.get("nombre") or "").lower().strip()
                    for r in existentes if r.get("nombre")
                }
                # Reintentar este mismo batch en modo pre-filtro
                ok, count, msg = _insertar_sin_constraint(
                    batch, webs_existentes, nombres_existentes
                )

        STATS.procesados += len(batch)
        if ok:
            STATS.batches_ok += 1
            STATS.insertados += count
            modo = "pre-filtro" if modo_prefiltro else "upsert"
            log_ok(f"    Batch {n}/{len(batches)} ({label}/{modo}) — {count} registros")
        else:
            STATS.batches_err += 1
            STATS.errores     += len(batch)
            log_err(f"    Batch {n}/{len(batches)} ({label}) FALLÓ: {msg}")

        if n < len(batches):
            time.sleep(random.uniform(0.3, 0.7))


def _insertar_ignorando_duplicados(
    registros: list[dict],
    on_conflict: str = "web",
) -> tuple[bool, int, str]:
    """
    Fallback para cuando el upsert choca con un constraint secundario.
    Usa resolution=ignore-duplicates + on_conflict=web:
      - Si web ya existe → saltea el registro silenciosamente (no actualiza)
      - Si web no existe → inserta normalmente
    """
    # Nunca enviar id para evitar conflictos en PK
    limpios = [{k: v for k, v in r.items() if k != "id"} for r in registros]

    # on_conflict es necesario para que ignore-duplicates sepa qué constraint ignorar
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict={on_conflict}"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=ignore-duplicates,return=minimal",
    }
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=json.dumps(limpios, default=str),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return True, len(limpios), "ok (ignore-duplicates)"
            if resp.status_code in (500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            return False, 0, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except (SSLError, Timeout, RequestsConnectionError, requests.HTTPError) as e:
            espera = BACKOFF_BASE ** intento
            log_warn(f"    Red error ignore-dup (intento {intento}): {e}. Reintentando en {espera}s...")
            time.sleep(espera)
        except Exception as e:
            return False, 0, str(e)
    return False, 0, f"Fallido tras {MAX_RETRIES} intentos (ignore-duplicates)"


def _deduplicar_batch(registros: list[dict]) -> list[dict]:
    """
    Elimina duplicados dentro de un mismo lote antes de enviarlo a Supabase.
    Clave: web normalizada → nombre normalizado (fallback).
    Cuando hay duplicados se conserva el registro con más campos no-nulos.
    """
    vistos: dict = {}
    for r in registros:
        web    = (r.get("web")    or "").strip().rstrip("/").lower()
        nombre = (r.get("nombre") or "").lower().strip()
        clave  = web if web else nombre
        if not clave:
            continue
        if clave not in vistos:
            vistos[clave] = r
        else:
            # Quedarse con el registro más completo
            actual_score = sum(1 for v in vistos[clave].values() if v)
            nuevo_score  = sum(1 for v in r.values() if v)
            if nuevo_score > actual_score:
                vistos[clave] = r
    return list(vistos.values())


def deduplicar_lista(registros: list[dict]) -> list[dict]:
    """
    Deduplicación global de toda una lista (usada antes de enviar al pipeline).
    Idéntica lógica que _deduplicar_batch pero exportada para uso externo.
    """
    return _deduplicar_batch(registros)


def _insertar_sin_constraint(
    batch: list[dict],
    webs_existentes: set,
    nombres_existentes: set,
) -> tuple[bool, int, str]:
    """
    Fallback cuando la tabla no tiene UNIQUE constraint.
    Filtra manualmente los registros ya existentes y hace un INSERT limpio.
    Actualiza los conjuntos en-memoria para no duplicar dentro del mismo run.
    """
    nuevos = []
    for r in batch:
        web    = (r.get("web")    or "").strip().rstrip("/").lower()
        nombre = (r.get("nombre") or "").lower().strip()

        if web and web in webs_existentes:
            continue
        if nombre and nombre in nombres_existentes:
            continue

        nuevos.append(r)
        # Marcar como visto para los batches siguientes del mismo run
        if web:
            webs_existentes.add(web)
        if nombre:
            nombres_existentes.add(nombre)

    if not nuevos:
        return True, 0, "ok (todos ya existen)"

    # Nunca enviar id: evita conflictos en PK si el registro viene de una corrida anterior
    nuevos = [{k: v for k, v in r.items() if k != "id"} for r in nuevos]

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    for intento in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=json.dumps(nuevos, default=str),
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code in (200, 201):
                return True, len(nuevos), "ok"
            if resp.status_code in (500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            return False, 0, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except (SSLError, Timeout, RequestsConnectionError, requests.HTTPError) as e:
            espera = BACKOFF_BASE ** intento
            log_warn(f"    Red error pre-filtro (intento {intento}): {e}. Reintentando en {espera}s...")
            time.sleep(espera)
        except Exception as e:
            return False, 0, str(e)

    return False, 0, f"Fallido tras {MAX_RETRIES} intentos (pre-filtro)"


# =============================================================================
# CONTEO EN SUPABASE (para calcular inserts vs updates)
# =============================================================================

def obtener_conteo_supabase() -> int:
    """Devuelve el total de filas en la tabla. -1 si falla."""
    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?select=id"
    headers = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer":        "count=exact",
        "Range-Unit":    "items",
        "Range":         "0-0",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        cr = resp.headers.get("Content-Range", "")
        if "/" in cr:
            return int(cr.split("/")[1])
    except Exception:
        pass
    return -1


# =============================================================================
# LECTURA DE CSV Y NORMALIZACIÓN
# =============================================================================

def leer_csv(path: str) -> list[dict]:
    """Lee un CSV de scraping y devuelve lista de filas como dicts."""
    if not os.path.exists(path):
        log_warn(f"CSV no encontrado: {path}")
        return []
    registros = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                registros.append(dict(row))
    except Exception as e:
        log_err(f"Error leyendo {path}: {e}")
    log(f"  '{os.path.basename(path)}': {len(registros)} filas")
    return registros


def normalizar_para_supabase(row: dict) -> Optional[dict]:
    """
    Convierte una fila de CSV (o dict con claves del scraper) al esquema
    de la tabla inmobiliarias_scraping.
    Retorna None si la fila no tiene nombre (descartada).
    """
    nombre = (row.get("nombre") or "").strip()
    if not nombre:
        return None

    web = (row.get("web") or "").strip().rstrip("/") or None

    return {
        "nombre":             nombre,
        "web":                web,
        "telefono_principal": _first(row, "telefono", "telefono_principal") or None,
        "email_principal":    _first(row, "email", "email_principal")       or None,
        "direccion":          (row.get("direccion")  or "").strip() or None,
        "barrio":             (row.get("barrio")     or "").strip() or None,
        "ciudad":             (row.get("ciudad")     or "").strip() or None,
        "provincia":          (row.get("provincia")  or "").strip() or None,
        "pais":               (row.get("pais")       or "Argentina").strip() or "Argentina",
        "rating":             _to_float(row.get("rating")),
        "resenas":            _to_int(row.get("resenas")),
        "categoria":          (row.get("categoria")  or "").strip() or None,
        "fuente":             (row.get("fuente")     or "").strip() or None,
        "estado_scraping":    "ok",
        "ultimo_scrapeo":     _validar_timestamp(row.get("fecha_scrapeo")) or datetime.now().isoformat(),
        # created_at NO se incluye → Supabase lo pone solo en el INSERT
        # y al hacer upsert no se sobreescribe porque no está en el body
    }


def _first(row: dict, *keys: str) -> str:
    for k in keys:
        v = (row.get(k) or "").strip()
        if v:
            return v
    return ""


def _validar_timestamp(val) -> Optional[str]:
    """
    Devuelve el valor solo si parece un timestamp válido (empieza con YYYY-MM-DD).
    Evita que un email u otro string mal posicionado en el CSV llegue a Supabase.
    """
    if not val:
        return None
    s = str(val).strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s
    return None


def normalizar_desarrolladora(row: dict) -> Optional[dict]:
    """
    Convierte una fila del CSV de desarrolladoras al esquema de
    la tabla desarrolladoras_scraping.
    """
    nombre = (row.get("nombre") or "").strip()
    if not nombre:
        return None

    web = (row.get("web") or "").strip().rstrip("/") or None

    tiene_proy_raw = row.get("tiene_proyectos", "")
    if isinstance(tiene_proy_raw, bool):
        tiene_proyectos = tiene_proy_raw
    else:
        tiene_proyectos = str(tiene_proy_raw).strip().lower() in ("true", "1", "si", "sí", "yes")

    return {
        "nombre":             nombre,
        "nombre_normalizado": nombre.lower().strip(),
        "web":                web,
        "telefono_principal": _first(row, "telefono", "telefono_principal") or None,
        "email_principal":    _first(row, "email", "email_principal")       or None,
        "direccion":          (row.get("direccion")  or "").strip() or None,
        "ciudad":             (row.get("ciudad")     or "").strip() or None,
        "provincia":          (row.get("provincia")  or "").strip() or None,
        "pais":               (row.get("pais")       or "Argentina").strip() or "Argentina",
        "rating":             _to_float(row.get("rating")),
        "resenas":            _to_int(row.get("resenas")),
        "categoria":          (row.get("categoria")  or "").strip() or None,
        "fuente":             (row.get("fuente")     or "").strip() or None,
        "tiene_proyectos":    tiene_proyectos,
        "estado_scraping":    "ok",
        "updated_at":         datetime.now().isoformat(),
    }


def _to_float(val) -> Optional[float]:
    try:
        return float(str(val).replace(",", ".")) if val else None
    except Exception:
        return None


def _to_int(val) -> Optional[int]:
    try:
        return int(str(val).replace(".", "").replace(",", "")) if val else None
    except Exception:
        return None


# =============================================================================
# PARTE 4 — DETECCIÓN DE FALTANTES
# =============================================================================

def obtener_registros_supabase(
    columnas: list[str] | None = None,
) -> list[dict]:
    """
    Descarga todos los registros de Supabase paginando de a 1 000 filas.
    """
    columnas = columnas or ["id", "nombre", "web", "ciudad", "provincia"]
    select   = ",".join(columnas)
    headers  = {
        "apikey":        SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    todos   = []
    offset  = 0
    page    = 1000

    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}"
            f"?select={select}&limit={page}&offset={offset}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if not resp.ok:
                log_err(f"Error leyendo Supabase: HTTP {resp.status_code}")
                break
            chunk = resp.json()
            if not chunk:
                break
            todos.extend(chunk)
            if len(chunk) < page:
                break
            offset += page
        except Exception as e:
            log_err(f"Error al paginar Supabase: {e}")
            break

    log(f"  Supabase: {len(todos)} registros existentes")
    return todos


def detectar_faltantes(
    csv_records: list[dict],
    supabase_records: list[dict],
) -> list[dict]:
    """
    Devuelve los registros del CSV que NO están en Supabase.
    Clave primaria: web (preferido) → nombre normalizado (fallback).
    """
    webs_db    = {
        r["web"].strip().rstrip("/").lower()
        for r in supabase_records
        if r.get("web")
    }
    nombres_db = {
        r["nombre"].lower().strip()
        for r in supabase_records
        if r.get("nombre")
    }

    faltantes = []
    for r in csv_records:
        web    = (r.get("web")    or "").strip().rstrip("/").lower()
        nombre = (r.get("nombre") or "").lower().strip()

        if web and web in webs_db:
            continue
        if nombre and nombre in nombres_db:
            continue
        faltantes.append(r)

    STATS.faltantes = len(faltantes)
    log(
        f"  Faltantes: {len(faltantes)} de {len(csv_records)} registros CSV "
        f"no están en Supabase"
    )
    return faltantes


# =============================================================================
# PARTE 5 — ANÁLISIS DE COBERTURA
# =============================================================================

def analizar_cobertura(
    csv_records: list[dict],
    supabase_records: list[dict],
) -> dict:
    """
    Genera métricas de cobertura por provincia / ciudad.
    """
    webs_db    = {
        r["web"].strip().rstrip("/").lower()
        for r in supabase_records
        if r.get("web")
    }
    nombres_db = {
        r["nombre"].lower().strip()
        for r in supabase_records
        if r.get("nombre")
    }

    def en_db(r: dict) -> bool:
        web    = (r.get("web")    or "").strip().rstrip("/").lower()
        nombre = (r.get("nombre") or "").lower().strip()
        return (web and web in webs_db) or (nombre and nombre in nombres_db)

    zonas: dict = defaultdict(
        lambda: {"detectadas": 0, "cargadas": 0, "faltantes": 0}
    )
    for r in csv_records:
        zona = r.get("provincia") or r.get("ciudad") or "Sin clasificar"
        zonas[zona]["detectadas"] += 1
        if en_db(r):
            zonas[zona]["cargadas"] += 1
        else:
            zonas[zona]["faltantes"] += 1

    total_det  = len(csv_records)
    total_carg = sum(1 for r in csv_records if en_db(r))
    total_falt = total_det - total_carg
    pct        = round(total_carg / total_det * 100, 1) if total_det else 0

    return {
        "total_detectadas": total_det,
        "total_cargadas":   total_carg,
        "total_faltantes":  total_falt,
        "cobertura_pct":    pct,
        "por_zona":         dict(zonas),
    }


def imprimir_reporte(reporte: dict):
    log("=" * 65)
    log("  REPORTE DE COBERTURA")
    log("=" * 65)
    log(f"  Total detectadas : {reporte['total_detectadas']}")
    log(f"  Total cargadas   : {reporte['total_cargadas']}")
    log(f"  Total faltantes  : {reporte['total_faltantes']}")
    log(f"  Cobertura        : {reporte['cobertura_pct']}%")
    log("-" * 65)
    log(f"  {'ZONA':<36} {'DET':>5} {'CARG':>5} {'FALT':>5} {'%':>5}")
    log("-" * 65)

    for zona, d in sorted(
        reporte["por_zona"].items(),
        key=lambda x: x[1]["faltantes"],
        reverse=True,
    ):
        det  = d["detectadas"]
        carg = d["cargadas"]
        falt = d["faltantes"]
        pct  = round(carg / det * 100, 1) if det else 0
        log(f"  {zona:<36} {det:>5} {carg:>5} {falt:>5} {pct:>4}%")

    log("=" * 65)


# =============================================================================
# PARTE 6 — RESCRAPEO AUTOMÁTICO DE FALTANTES
# =============================================================================

def rescraper_faltantes(faltantes: list[dict]) -> int:
    """
    Genera queries dirigidas para los registros faltantes y los rescraping
    usando scraper_google_lugares.py, luego sube los nuevos registros a Supabase.

    Returns: cantidad de registros nuevos subidos.
    """
    if not faltantes:
        log("  Sin faltantes para rescraper.")
        return 0

    log(f"  Cargando scraper_google_lugares...")
    try:
        spec = importlib.util.spec_from_file_location(
            "scraper_gl",
            os.path.join(script_dir, "scraper_google_lugares.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        log_err(f"  No se pudo importar scraper: {e}")
        return 0

    queries = _generar_queries(faltantes)
    log(f"  Queries de rescrapeo: {len(queries)}")

    # Vistos = nombres ya conocidos (para no recuperar duplicados)
    vistos: set = {(r.get("nombre") or "").lower().strip() for r in faltantes}

    capturados_total: list[dict] = []

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx  = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1400, "height": 900},
                locale="es-AR",
            )
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            for i, query in enumerate(queries, 1):
                log(f"  [{i}/{len(queries)}] Rescrapeo: '{query}'")
                try:
                    capturados: list[dict] = []

                    # Parchear guardar() para capturar en memoria
                    _orig = mod.guardar
                    mod.guardar = lambda d: capturados.append(d)

                    mod.scrapear_query(page, query, vistos)

                    mod.guardar = _orig

                    if capturados:
                        capturados_total.extend(capturados)
                        log_ok(f"    {len(capturados)} nuevos en '{query}'")

                except Exception as e:
                    log_err(f"    Error en '{query}': {e}")

                time.sleep(random.uniform(3, 6))

            browser.close()

    except ImportError:
        log_err("  Playwright no disponible para rescrapeo.")
        return 0
    except Exception as e:
        log_err(f"  Error general en rescrapeo: {e}")
        log_err(traceback.format_exc())
        return 0

    if not capturados_total:
        log("  Rescrapeo completado: sin registros nuevos.")
        return 0

    log(f"  Subiendo {len(capturados_total)} registros rescraped a Supabase...")
    normalizados = [normalizar_para_supabase(r) for r in capturados_total]
    normalizados = [r for r in normalizados if r]
    cargar_registros(normalizados)
    STATS.rescraped += len(normalizados)

    return len(normalizados)


def _generar_queries(faltantes: list[dict]) -> list[str]:
    """
    Genera una query de búsqueda dirigida por cada registro faltante.
    Formato: "inmobiliaria {nombre} {ciudad|provincia}"
    Limitado a MAX_QUERIES_RESCRAPE para no extender demasiado la ejecución.
    """
    visto: set = set()
    queries: list[str] = []

    for r in faltantes:
        nombre    = (r.get("nombre")    or "").strip()
        ciudad    = (r.get("ciudad")    or "").strip()
        provincia = (r.get("provincia") or "").strip()

        if not nombre:
            continue

        ubicacion = ciudad or provincia or "argentina"
        q = f"inmobiliaria {nombre} {ubicacion}".lower()

        if q not in visto:
            visto.add(q)
            queries.append(q)

        if len(queries) >= MAX_QUERIES_RESCRAPE:
            break

    return queries


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def run_pipeline(
    solo_carga:     bool = False,
    solo_analisis:  bool = False,
    rescraper:      bool = False,
    desarrolladoras: bool = False,
) -> None:
    global SUPABASE_TABLE

    # Configurar modo según el tipo de entidad
    if desarrolladoras:
        SUPABASE_TABLE = "desarrolladoras_scraping"
        csv_files      = [os.path.join(script_dir, "..", "desarrolladoras.csv")]
        normalizar_fn  = normalizar_desarrolladora
        modo_label     = "DESARROLLADORAS"
    else:
        SUPABASE_TABLE = "inmobiliarias_scraping"
        csv_files      = [CSV_LUGARES, CSV_SEARCH]
        normalizar_fn  = normalizar_para_supabase
        modo_label     = "INMOBILIARIAS"

    _init_log()

    log("=" * 65)
    log(f"  PIPELINE SUPABASE — ERETZ Propiedades ({modo_label})")
    log(f"  Tabla   : {SUPABASE_TABLE}")
    log(f"  URL     : {SUPABASE_URL or '⚠ SUPABASE_URL no configurada'}")
    log(f"  Batch   : {BATCH_SIZE} | Retries: {MAX_RETRIES}")
    log("=" * 65)

    if not SUPABASE_URL or not SUPABASE_KEY:
        log_err("SUPABASE_URL o SUPABASE_KEY no configuradas. Verificar .env")
        return

    # ── Leer CSVs ─────────────────────────────────────────────────────────────
    log("\n[1/6] Leyendo CSVs...")
    filas_csv: list[dict] = []
    for path in csv_files:
        filas_csv.extend(leer_csv(path))

    if not filas_csv:
        log_warn("No se encontraron registros en los CSVs. Verificar rutas.")
        return

    log(f"  Total filas CSV: {len(filas_csv)}")

    normalizados = [normalizar_fn(r) for r in filas_csv]
    normalizados = [r for r in normalizados if r]

    # Deduplicar globalmente antes de cualquier operación
    antes = len(normalizados)
    normalizados = deduplicar_lista(normalizados)
    duplicados_globales = antes - len(normalizados)
    log(
        f"  Válidos para Supabase: {len(normalizados)}"
        + (f" ({duplicados_globales} duplicados eliminados)" if duplicados_globales else "")
    )

    # ── Carga con upsert ──────────────────────────────────────────────────────
    if not solo_analisis:
        log("\n[2/6] Carga upsert → Supabase...")
        conteo_antes = obtener_conteo_supabase()
        cargar_registros(normalizados)
        conteo_despues = obtener_conteo_supabase()

        if conteo_antes >= 0 and conteo_despues >= 0:
            nuevos = conteo_despues - conteo_antes
            STATS.insertados  = nuevos
            STATS.actualizados = max(0, STATS.procesados - nuevos)
            log_ok(
                f"  Conteo Supabase: {conteo_antes} → {conteo_despues} "
                f"(+{nuevos} nuevos, ~{STATS.actualizados} actualizados)"
            )

    # ── Estado actual de Supabase ─────────────────────────────────────────────
    log("\n[3/6] Descargando estado de Supabase...")
    supa_records = obtener_registros_supabase(
        columnas=["id", "nombre", "web", "ciudad", "provincia"]
    )

    # ── Detección de faltantes ────────────────────────────────────────────────
    log("\n[4/6] Detectando faltantes...")
    faltantes = detectar_faltantes(normalizados, supa_records)

    # ── Cobertura ─────────────────────────────────────────────────────────────
    log("\n[5/6] Análisis de cobertura...")
    reporte = analizar_cobertura(normalizados, supa_records)
    imprimir_reporte(reporte)

    if solo_carga or solo_analisis:
        log(STATS.resumen())
        return

    # ── Rescrapeo automático ──────────────────────────────────────────────────
    if rescraper and faltantes:
        log(f"\n[6/6] Rescrapeo automático: {len(faltantes)} faltantes")
        rescraper_faltantes(faltantes)
    elif faltantes:
        log(
            f"\n[6/6] Hay {len(faltantes)} registros faltantes. "
            f"Ejecutar con --rescraper para recuperarlos."
        )
    else:
        log("\n[6/6] Sin faltantes. Cobertura completa ✓")

    log(STATS.resumen())


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline Supabase robusto para ERETZ Propiedades",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--solo-carga",
        action="store_true",
        help="Solo carga los CSVs a Supabase (sin análisis ni rescrapeo)",
    )
    parser.add_argument(
        "--solo-analisis",
        action="store_true",
        help="Solo muestra el reporte de cobertura (sin cargar datos)",
    )
    parser.add_argument(
        "--rescraper",
        action="store_true",
        help="Detecta registros faltantes y los rescrapea automáticamente",
    )
    parser.add_argument(
        "--desarrolladoras",
        action="store_true",
        help="Operar sobre desarrolladoras_scraping en lugar de inmobiliarias_scraping",
    )
    args = parser.parse_args()

    run_pipeline(
        solo_carga=args.solo_carga,
        solo_analisis=args.solo_analisis,
        rescraper=args.rescraper,
        desarrolladoras=args.desarrolladoras,
    )

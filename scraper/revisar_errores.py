"""
revisar_errores.py
------------------
Muestra los registros con needs_manual_review = true y qué campo les falta.
También lista los que tienen datos claramente incorrectos.
"""

import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
TABLA        = "inmobiliarias_scraping"

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

def cargar(filtro_params: dict) -> list:
    todos, pagina, tam = [], 0, 1000
    while True:
        desde, hasta = pagina * tam, pagina * tam + tam - 1
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA}",
            headers={**_headers(), "Range-Unit": "items", "Range": f"{desde}-{hasta}"},
            params=filtro_params,
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
    return todos

def diagnostico(r: dict) -> list[str]:
    problemas = []
    nombre = (r.get("nombre") or "").strip()

    if not nombre:
        problemas.append("SIN NOMBRE")
    elif len(nombre) < 5:
        problemas.append(f"NOMBRE MUY CORTO: '{nombre}'")
    elif re.search(r"\d{4,}", nombre):
        problemas.append(f"NÚMERO EN NOMBRE: '{nombre}'")

    if not r.get("telefono"):
        problemas.append("sin teléfono")
    if not r.get("direccion"):
        problemas.append("sin dirección")
    if not r.get("ciudad"):
        problemas.append("sin ciudad")
    if not r.get("provincia"):
        problemas.append("sin provincia")
    if not r.get("web"):
        problemas.append("sin web")
    if r.get("confidence_score", 0) < 30:
        problemas.append(f"confidence bajo ({r.get('confidence_score')})")

    return problemas

def run():
    print("Cargando registros con needs_manual_review = true...")
    registros = cargar({
        "select": "id,nombre,telefono,direccion,ciudad,provincia,web,fuente,confidence_score",
        "needs_manual_review": "eq.true",
        "order": "confidence_score.asc",
    })

    if not registros:
        print("No hay registros para revisar.")
        return

    print(f"\nTotal a revisar: {len(registros)}\n")
    print(f"{'ID':<8} {'NOMBRE':<40} {'CONFI':<6} PROBLEMAS")
    print("-" * 100)

    # Agrupar por tipo de problema
    conteo = {}
    for r in registros:
        problemas = diagnostico(r)
        for p in problemas:
            clave = p.split(":")[0].split("(")[0].strip()
            conteo[clave] = conteo.get(clave, 0) + 1

        nombre = (r.get("nombre") or "—")[:38]
        conf   = r.get("confidence_score") or 0
        desc   = " | ".join(problemas) if problemas else "OK (revisión por conf<30)"
        print(f"{r['id']:<8} {nombre:<40} {conf:<6} {desc}")

    print("\n" + "=" * 60)
    print("RESUMEN DE PROBLEMAS:")
    for prob, cant in sorted(conteo.items(), key=lambda x: -x[1]):
        print(f"  {prob:<30} : {cant}")
    print("=" * 60)

if __name__ == "__main__":
    run()

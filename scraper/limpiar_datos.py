"""
limpiar_datos.py
----------------
1. Limpia nombres que tienen números de matrícula / colegiado
2. Elimina registros que no son inmobiliarias (barrios, loteos, edificios, etc.)
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

# =============================================================================
# PATRONES PARA LIMPIAR NOMBRES
# =============================================================================

_RUIDO_MATRICULA = [
    re.compile(r"\bC\.?P\.?I\.?\s*\d{3,6}\b", re.I),              # CPI 7968
    re.compile(r"\bC\.?U\.?C\.?I\.?C\.?B\.?A\.?\s*\d{3,6}\b", re.I),  # CUCICBA 9188
    re.compile(r"\bC\.?M\.?C\.?P\.?S\.?I\.?\s*\d{3,6}\b", re.I),      # CMCPSI 7178
    re.compile(r"\bC\.?S\.?I\.?\s*\d{3,6}\b", re.I),              # CSI 6250
    re.compile(r"\bmat\.?\s*\d{3,6}\b", re.I),                    # mat 0336
    re.compile(r"\bcol\.?\s*\d{3,6}\b", re.I),                    # col 2146
    re.compile(r"\breg\.?\s*\d{3,6}\b", re.I),                    # reg 2886
    re.compile(r"\bcolegiado\s*\d{3,6}\b", re.I),                 # colegiado 7577
    re.compile(r"\bmatr[íi]cula\s*\d{3,6}\b", re.I),              # matrícula 0336
    re.compile(r"\bdesde\s+\d{4}\b", re.I),                       # desde 1978
    re.compile(r"\(\s*\w{0,10}\s*\d{4,6}\s*\)", re.I),            # (CSI 6250) / (reg 2886)
    re.compile(r"\|\s*\d{1,2}\s*y\s*\d{1,2}\s*Ambientes?\b", re.I),   # | 1 y 2 Ambientes
    re.compile(r"\|\s*\w+\s*\d{3,5}\b", re.I),                    # | Mendoza 2196
]

def limpiar_nombre_matricula(nombre: str) -> str:
    n = nombre
    for patron in _RUIDO_MATRICULA:
        n = patron.sub("", n)
    n = re.sub(r"\s{2,}", " ", n)
    # Solo quitar espacios, guiones y puntos al principio/final — no paréntesis
    n = n.strip(" |-")
    # Quitar punto final solo si NO es parte de una abreviatura (S.A., S.R.L., etc.)
    n = re.sub(r"(?<![A-Z])\.$", "", n).strip()
    return n

# =============================================================================
# KEYWORDS PARA DETECTAR NO-INMOBILIARIAS
# =============================================================================

_NO_INMOBILIARIA_PREFIJOS = [
    r"barrio\s+(privado|abierto|cerrado|la|el|los|las|del|nuevo|san|santa)",
    r"^barrio\s+\w",           # "Barrio Ferreyra", "Barrio Castañares"
    r"^loteo\b",               # "Loteo Fincas del Rincón"
    r"^country\b",             # "Country El Mirador"
    r"^complejo\b",            # "Complejo Torres de Buenos Aires"
    r"^cabaña",                # "Cabaña Elisim"
    r"^caba[ñn]as\b",
    r"^quinta\b",              # "Quinta Santa Ana"
    r"^vivero\b",              # "Vivero Los Álamos"
    r"^apart\b",               # "Apart ..."
    r"^edificio\b",            # "Edificio Latino 8"
    r"^departamento\s+\d",     # "Departamento 1954..."
    r"^departamentos\s+(la|el|los|las|kairos|funes)",
    r"^torres\s+de\b",         # "Torres de Abasto"
    r"^parque\s+(juan|san|los|la)",
    r"^paseo\s+(del|de\s+la|marqu)",
    r"^centro\s+vecinal\b",
    r"^alquilo\b",             # "Alquilo para agro"
    r"^avenida\b",             # "Avenida Pasteur..."  (dirección como nombre)
    r"^calle\s+\d",            # "Calle 24 número 1256"
    r"^cosme\s+gorostiza\b",   # dirección como nombre
    r"^avellaneda\s+\d",       # dirección como nombre
    r"^aires\s+del\b",
    r"^fincas\s+de\b",
    r"^lotes\s+para\b",
    r"^villa\s+(ocampo|del\s+carmen|libertador|la\s+angostura)\b",
    r"^distrito\s+puerto\b",
    r"^república\s+la\b",
]

_NO_INMOBILIARIA_EXACTO = {
    "-", "0341", "casa", "easy", "belgrano", "soldini",
    "leonadr", "lucymoda", "tía maria", "tia maria",
    "metalcoldart",
}

_NO_INMOBILIARIA_CONTIENE = [
    "hamburgues",
    "materiales para la construc",
    "metalúrgica", "metalurgica",
    "vivero ",
    "barrio privado",
    "country club",
    "cabañas:",
    "bahía apart",
    "bahia apart",
]

def es_no_inmobiliaria(nombre: str) -> bool:
    n = nombre.strip().lower()
    if n in _NO_INMOBILIARIA_EXACTO:
        return True
    for kw in _NO_INMOBILIARIA_CONTIENE:
        if kw in n:
            return True
    for patron in _NO_INMOBILIARIA_PREFIJOS:
        if re.match(patron, n, re.I):
            return True
    return False

# =============================================================================
# SUPABASE
# =============================================================================

def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

def cargar_todos(campos="id,nombre,fuente,ciudad") -> list:
    todos, pagina, tam = [], 0, 1000
    while True:
        desde, hasta = pagina * tam, pagina * tam + tam - 1
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA}",
            headers={**_headers(), "Range-Unit": "items", "Range": f"{desde}-{hasta}"},
            params={"select": campos, "order": "id.asc"},
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

_SESSION = requests.Session()

def _patch(rid: int, payload: dict) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?id=eq.{rid}"
    for intento in range(4):
        try:
            resp = _SESSION.patch(url, headers=_headers(), json=payload, timeout=20)
            if resp.status_code in (200, 204):
                return True
            print(f"  PATCH {rid} → {resp.status_code}: {resp.text[:80]}")
            return False
        except Exception as e:
            if intento == 3:
                print(f"  PATCH {rid} error: {e}")
                return False
            import time; time.sleep(2 ** intento)
            _SESSION.close()
    return False

def patch_nombre(rid: int, nombre_limpio: str) -> bool:
    return _patch(rid, {"nombre_limpio": nombre_limpio})

def eliminar(rid: int) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/{TABLA}?id=eq.{rid}"
    for intento in range(4):
        try:
            resp = _SESSION.delete(url, headers=_headers(), timeout=20)
            if resp.status_code in (200, 204):
                return True
            print(f"  DELETE {rid} → {resp.status_code}: {resp.text[:80]}")
            return False
        except Exception as e:
            if intento == 3:
                print(f"  DELETE {rid} error: {e}")
                return False
            import time; time.sleep(2 ** intento)
            _SESSION.close()
    return False

# =============================================================================
# CORRECCIÓN DE nombre_limpio YA GUARDADOS
# =============================================================================

def corregir_nombre_limpio():
    """
    Compara nombre_limpio actual en BD con lo que la lógica actual produciría.
    Corrige solo los registros donde difieren.
    """
    print("Cargando registros con nombre_limpio para verificar...")
    registros = cargar_todos("id,nombre,nombre_limpio")

    a_corregir = []
    for r in registros:
        nombre       = (r.get("nombre") or "").strip()
        limpio_actual = r.get("nombre_limpio")
        if not nombre or limpio_actual is None:
            continue
        limpio_correcto = limpiar_nombre_matricula(nombre)
        # Solo reemplazar si hay matrícula que limpiar Y el resultado difiere
        if limpio_correcto != nombre and limpio_correcto != limpio_actual and len(limpio_correcto) >= 3:
            a_corregir.append((r["id"], limpio_actual, limpio_correcto))

    if not a_corregir:
        print("No hay registros que corregir.")
        return

    print(f"\nRegistros a corregir: {len(a_corregir)}")
    for rid, viejo, nuevo in a_corregir:
        print(f"  [{rid}] '{viejo}'")
        print(f"       → '{nuevo}'")

    confirmar = input(f"\n¿Confirmar corrección de {len(a_corregir)} registros? (s/n): ").strip().lower()
    if confirmar != "s":
        print("Cancelado.")
        return

    ok = 0
    for rid, _, nuevo in a_corregir:
        if patch_nombre(rid, nuevo):
            ok += 1
        else:
            print(f"  ERROR corrigiendo id={rid}")
    print(f"\nCorregidos: {ok}/{len(a_corregir)}")


# =============================================================================
# MAIN
# =============================================================================

def run():
    print("Cargando registros...")
    registros = cargar_todos()
    print(f"Total: {len(registros)}\n")

    a_limpiar  = []  # (id, nombre_original, nombre_limpio)
    a_eliminar = []  # (id, nombre)

    for r in registros:
        nombre = (r.get("nombre") or "").strip()
        if not nombre:
            continue

        # Primero: ¿es un no-inmobiliaria?
        if es_no_inmobiliaria(nombre):
            a_eliminar.append((r["id"], nombre))
            continue

        # Segundo: ¿tiene números de matrícula en el nombre?
        limpio = limpiar_nombre_matricula(nombre)
        if limpio != nombre and len(limpio) >= 3:
            a_limpiar.append((r["id"], nombre, limpio))

    # --- Mostrar lo que se va a hacer ---
    print(f"{'='*65}")
    print(f"NOMBRES A LIMPIAR: {len(a_limpiar)}")
    print(f"{'='*65}")
    for rid, orig, limpio in a_limpiar:
        print(f"  [{rid}] '{orig}'")
        print(f"       → '{limpio}'")

    print(f"\n{'='*65}")
    print(f"REGISTROS A ELIMINAR: {len(a_eliminar)}")
    print(f"{'='*65}")
    for rid, nombre in a_eliminar:
        print(f"  [{rid}] {nombre}")

    print(f"\n{'='*65}")
    confirmar = input("¿Confirmar ambas operaciones? (s/n): ").strip().lower()
    if confirmar != "s":
        print("Cancelado.")
        return

    # --- Ejecutar limpieza de nombres ---
    print("\nLimpiando nombres...")
    ok_limpiar = 0
    for rid, orig, limpio in a_limpiar:
        if patch_nombre(rid, limpio):
            ok_limpiar += 1
        else:
            print(f"  ERROR limpiando id={rid}")

    # --- Ejecutar eliminaciones ---
    print("Eliminando no-inmobiliarias...")
    ok_eliminar = 0
    for rid, nombre in a_eliminar:
        if eliminar(rid):
            ok_eliminar += 1
        else:
            print(f"  ERROR eliminando id={rid} '{nombre}'")

    print(f"\n{'='*65}")
    print(f"Nombres limpiados : {ok_limpiar}/{len(a_limpiar)}")
    print(f"Registros eliminados: {ok_eliminar}/{len(a_eliminar)}")
    print(f"{'='*65}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--corregir":
        corregir_nombre_limpio()
    else:
        run()

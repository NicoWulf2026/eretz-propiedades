"""
clasificar_ia.py
----------------
Usa la API de Claude (Anthropic) para analizar y corregir la tabla inmobiliarias_scraping.

Correcciones que realiza:
  1. Elimina entradas que no son inmobiliarias (barrios, loteos, hoteles, etc.)
  2. Limpia nombre_limpio (quita matrículas, símbolos, texto basura)
  3. Normaliza ciudad (abreviaciones, typos: "Cba" → "Córdoba")
  4. Completa/corrige provincia si está vacía o es inconsistente con la ciudad
  5. Detecta duplicados (los lista, no los borra automáticamente)
  6. Marca webs claramente inválidas
  7. Clasifica tipo de agencia: franquicia / independiente / martillero
  8. Detecta emails y teléfonos inválidos

Uso:
    python clasificar_ia.py              → procesa todos los registros
    python clasificar_ia.py --dry-run   → muestra cambios pero no toca nada
    python clasificar_ia.py --limit 100 → prueba con los primeros 100
    python clasificar_ia.py --reset     → borra el checkpoint y empieza de cero

Requiere en .env:
    ANTHROPIC_API_KEY=sk-ant-...
    SUPABASE_URL=...
    SUPABASE_SERVICE_ROLE_KEY=...
"""

import os
import re
import sys
import json
import time
import argparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIG
# =============================================================================

SUPABASE_URL    = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
TABLA           = "inmobiliarias_scraping"

MODEL           = "claude-haiku-4-5"   # rápido y barato (~$0.30 para todo)
ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
BATCH           = 20     # Claude maneja bien lotes más grandes
DELAY           = 1.5    # 1.5s entre llamadas — Claude tiene límites altos
CHECKPOINT_FILE = "clasificar_checkpoint.json"  # guarda progreso para retomar

# =============================================================================
# CHECKPOINT (para retomar si se interrumpe)
# =============================================================================

def cargar_checkpoint() -> set:
    """Retorna el conjunto de IDs ya procesados."""
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("procesados", []))
        except Exception:
            pass
    return set()

def guardar_checkpoint(procesados: set) -> None:
    """Guarda los IDs procesados al disco."""
    try:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump({"procesados": list(procesados)}, f)
    except Exception:
        pass

def borrar_checkpoint() -> None:
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("Checkpoint borrado. Empezando desde cero.")

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

def cargar_todos(limit: int = 0) -> list:
    todos, pagina, tam = [], 0, 1000
    while True:
        desde = pagina * tam
        hasta  = pagina * tam + tam - 1
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/{TABLA}",
            headers={**_headers(), "Range-Unit": "items", "Range": f"{desde}-{hasta}"},
            params={
                "select": "id,nombre,nombre_limpio,web,ciudad,provincia,fuente,categoria,email_principal,telefono_principal",
                "order": "id.asc",
            },
            timeout=30,
        )
        if resp.status_code == 416:
            break
        lote = resp.json()
        if not lote:
            break
        todos.extend(lote)
        if limit and len(todos) >= limit:
            todos = todos[:limit]
            break
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
            time.sleep(2 ** intento)
    return False

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
            time.sleep(2 ** intento)
    return False

# =============================================================================
# CLAUDE API
# =============================================================================

SYSTEM_PROMPT = """Analiza registros de inmobiliarias argentinas y devuelve JSON.

Para cada registro evalúa:
1. es_inmobiliaria: false SOLO si es barrio privado, loteo, country, hotel, óptica, ferretería, carpintería, vivero, cabaña, dirección de calle como nombre, o empresa sin relación con el sector. CONSERVAR: inmobiliarias, brokers, corredores, martilleros, desarrolladoras, constructoras de viviendas, empresas de inversión inmobiliaria, administradoras de propiedades. Ante la duda → true.
2. nombre_limpio: quita matrículas (CPI/CUCICBA/Mat/Reg + número), códigos, texto basura. null si ya está bien.
3. ciudad_corregida: normaliza abreviaciones ("Cba"→"Córdoba", "C1428 Cdad. Autónoma de Buenos Aires"→"Buenos Aires", "X5000 Córdoba"→"Córdoba", "M5500 Mendoza"→"Mendoza", "CABA"→"Buenos Aires"). null si ya está bien.
4. provincia_corregida: completa si vacía o corrige si inconsistente con la ciudad. Nombres completos. null si está bien.
5. categoria_nueva: "franquicia" (RE/MAX, Century 21, Coldwell Banker, Keller Williams, ERA, Tizado, Soldati, Engel & Völkers), "martillero", "independiente", o null si ya tiene categoria o no se puede determinar.
6. email_invalido: true si no es un email válido (teléfono, texto, URL, formato roto).
7. telefono_invalido: true si no es teléfono real (texto, email, menos de 7 dígitos).
8. web_invalida: true solo si claramente no es web de inmobiliaria (Instagram, email, texto suelto).
9. duplicado_de_id: ID del original si este registro es duplicado obvio de otro en el lote.

Responde SOLO con este JSON, sin texto adicional:
{"resultados":[{"id":0,"es_inmobiliaria":true,"razon_eliminacion":null,"nombre_limpio":null,"ciudad_corregida":null,"provincia_corregida":null,"categoria_nueva":null,"email_invalido":false,"telefono_invalido":false,"web_invalida":false,"duplicado_de_id":null}]}

Incluye TODOS los IDs recibidos. null = sin cambio."""


def clasificar_lote(registros: list) -> list:
    lineas = []
    for r in registros:
        nombre    = (r.get("nombre") or "").strip()
        web       = (r.get("web") or "").strip()
        ciudad    = (r.get("ciudad") or "").strip()
        provincia = (r.get("provincia") or "").strip()
        fuente    = (r.get("fuente") or "").strip()
        categoria = (r.get("categoria") or "").strip()
        email     = (r.get("email_principal") or "").strip()
        telefono  = (r.get("telefono_principal") or "").strip()
        lineas.append(
            f'ID={r["id"]} | nombre="{nombre}" | ciudad="{ciudad}" | provincia="{provincia}"'
            f' | web="{web}" | email="{email}" | telefono="{telefono}"'
            f' | categoria="{categoria}" | fuente="{fuente}"'
        )
    contenido = "\n".join(lineas)

    payload = {
        "model": MODEL,
        "max_tokens": 4000,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": (
                    f"Analiza y corrige estos {len(registros)} registros:\n\n"
                    f"{contenido}\n\n"
                    "Responde solo con el JSON, sin texto adicional."
                ),
            }
        ],
    }

    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    intento = 0
    while True:
        intento += 1
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=90)

            if resp.status_code == 429:
                # Respetar el retry-after real de Claude
                retry_after = int(resp.headers.get("retry-after", 60))
                print(f"\n  [!] Rate limit, esperando {retry_after}s...", flush=True)
                time.sleep(retry_after + 2)
                continue

            if resp.status_code == 529:
                # Sobrecarga temporal del servidor
                print(f"\n  [!] Servidor sobrecargado, esperando 30s...", flush=True)
                time.sleep(30)
                continue

            if resp.status_code != 200:
                print(f"\n  [!] Error API {resp.status_code}: {resp.text[:200]}")
                if intento >= 5:
                    return [{"id": r["id"], "es_inmobiliaria": True} for r in registros]
                time.sleep(10)
                continue

            # Extraer texto de la respuesta Claude
            content_blocks = resp.json().get("content", [])
            texto = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    texto = block["text"].strip()
                    break

            match = re.search(r'\{[\s\S]*\}', texto)
            if not match:
                raise ValueError(f"No se encontró JSON: {texto[:300]}")
            data = json.loads(match.group())
            return data.get("resultados", [])

        except (json.JSONDecodeError, ValueError) as e:
            print(f"\n  [!] Error parseando JSON (intento {intento}): {e}")
            if intento >= 5:
                return [{"id": r["id"], "es_inmobiliaria": True} for r in registros]
            time.sleep(5)

        except Exception as e:
            print(f"\n  [!] Error inesperado (intento {intento}): {e}")
            if intento >= 5:
                return [{"id": r["id"], "es_inmobiliaria": True} for r in registros]
            time.sleep(10)

# =============================================================================
# APLICAR CAMBIOS
# =============================================================================

def aplicar_cambios(
    a_eliminar, a_limpiar, a_ciudad, a_provincia,
    a_categoria, a_email_inv, a_tel_inv, a_web_inv,
    dry_run: bool,
):
    sep = "=" * 70
    print(f"\n{sep}")
    print("RESUMEN DE CORRECCIONES")
    print(sep)
    print(f"  No-inmobiliarias a eliminar : {len(a_eliminar)}")
    print(f"  Nombres a limpiar           : {len(a_limpiar)}")
    print(f"  Ciudades a corregir         : {len(a_ciudad)}")
    print(f"  Provincias a completar      : {len(a_provincia)}")
    print(f"  Categorías a asignar        : {len(a_categoria)}")
    print(f"  Emails inválidos            : {len(a_email_inv)}")
    print(f"  Teléfonos inválidos         : {len(a_tel_inv)}")
    print(f"  Webs inválidas              : {len(a_web_inv)}")
    print(sep)

    if dry_run:
        print("\nMODO DRY-RUN — no se aplica nada.")
        return

    confirmar = input("\n¿Aplicar todos los cambios? (s/n): ").strip().lower()
    if confirmar != "s":
        print("Cancelado.")
        return

    print("\nAplicando cambios...")

    ok = err = 0
    for x in a_eliminar:
        if eliminar(x["id"]):
            ok += 1
        else:
            err += 1
            print(f"  ERROR eliminando [{x['id']}] {x['nombre']}")
    print(f"  Eliminados   : {ok}/{len(a_eliminar)}  (errores: {err})")

    ok = err = 0
    for x in a_limpiar:
        if _patch(x["id"], {"nombre_limpio": x["limpio"]}):
            ok += 1
        else:
            err += 1
    print(f"  Nombres      : {ok}/{len(a_limpiar)}")

    ok = err = 0
    for x in a_ciudad:
        if _patch(x["id"], {"ciudad": x["nueva"]}):
            ok += 1
        else:
            err += 1
    print(f"  Ciudades     : {ok}/{len(a_ciudad)}")

    ok = err = 0
    for x in a_provincia:
        if _patch(x["id"], {"provincia": x["nueva"]}):
            ok += 1
        else:
            err += 1
    print(f"  Provincias   : {ok}/{len(a_provincia)}")

    ok = err = 0
    for x in a_categoria:
        if _patch(x["id"], {"categoria": x["categoria"]}):
            ok += 1
        else:
            err += 1
    print(f"  Categorías   : {ok}/{len(a_categoria)}")

    ok = err = 0
    for x in a_email_inv:
        if _patch(x["id"], {"email_principal": None}):
            ok += 1
        else:
            err += 1
    print(f"  Emails null  : {ok}/{len(a_email_inv)}")

    ok = err = 0
    for x in a_tel_inv:
        if _patch(x["id"], {"telefono_principal": None}):
            ok += 1
        else:
            err += 1
    print(f"  Teléfonos null: {ok}/{len(a_tel_inv)}")

    ok = err = 0
    for x in a_web_inv:
        if _patch(x["id"], {"web": None}):
            ok += 1
        else:
            err += 1
    print(f"  Webs null    : {ok}/{len(a_web_inv)}")

    print(f"\n{sep}")
    print("✅ Cambios aplicados.")
    print(sep)

# =============================================================================
# MAIN
# =============================================================================

def run(dry_run: bool = False, limit: int = 0):
    if not ANTHROPIC_KEY:
        print("ERROR: No se encontró ANTHROPIC_API_KEY en .env")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env")
        sys.exit(1)

    # Cargar checkpoint (IDs ya procesados)
    procesados = cargar_checkpoint()
    if procesados:
        print(f"♻️  Retomando desde checkpoint — {len(procesados)} registros ya procesados.")

    print("Cargando registros de Supabase...")
    registros = cargar_todos(limit=limit)
    total = len(registros)
    print(f"Total cargados: {total}")

    # Filtrar ya procesados
    pendientes = [r for r in registros if r["id"] not in procesados]
    saltados   = total - len(pendientes)
    if saltados:
        print(f"  Saltando {saltados} ya procesados → quedan {len(pendientes)}")

    if not pendientes:
        print("✅ Todos los registros ya fueron procesados.")
        return

    mapa = {r["id"]: r for r in registros}
    total_lotes = (len(pendientes) + BATCH - 1) // BATCH

    print(f"\nModelo : {MODEL} (Claude — Anthropic)")
    print(f"Lotes  : {total_lotes} × {BATCH} registros")
    print(f"Costo estimado: ~${total_lotes * 0.0004:.2f} USD")
    if dry_run:
        print("MODO DRY-RUN activado — no se realizará ningún cambio\n")
    else:
        print()

    a_eliminar  = []
    a_limpiar   = []
    a_ciudad    = []
    a_provincia = []
    a_categoria = []
    a_email_inv = []
    a_tel_inv   = []
    a_web_inv   = []
    a_duplicados = []

    t_inicio = time.time()

    for i in range(0, len(pendientes), BATCH):
        lote     = pendientes[i : i + BATCH]
        num_lote = i // BATCH + 1
        pct      = (len(procesados) + i) / total * 100
        elapsed  = time.time() - t_inicio
        # ETA
        if i > 0:
            rate = i / elapsed  # registros/s
            restantes = len(pendientes) - i
            eta_s = restantes / rate
            eta_str = f"  ETA ~{eta_s/60:.0f}min"
        else:
            eta_str = ""

        print(
            f"  Lote {num_lote:>3}/{total_lotes} ({pct:4.1f}%){eta_str} ...",
            end=" ", flush=True,
        )

        resultados = clasificar_lote(lote)
        cambios = 0

        for res in resultados:
            rid = res.get("id")
            if rid not in mapa:
                continue
            r = mapa[rid]
            nombre = (r.get("nombre") or "").strip()

            if not res.get("es_inmobiliaria", True):
                a_eliminar.append({
                    "id": rid, "nombre": nombre,
                    "razon": res.get("razon_eliminacion") or "no es inmobiliaria",
                })
                cambios += 1
                continue

            nl = (res.get("nombre_limpio") or "").strip()
            if nl and nl != nombre and len(nl) >= 3:
                a_limpiar.append({"id": rid, "original": nombre, "limpio": nl})
                cambios += 1

            cc = (res.get("ciudad_corregida") or "").strip()
            if cc and cc != (r.get("ciudad") or "").strip():
                a_ciudad.append({"id": rid, "nombre": nombre,
                                 "original": r.get("ciudad",""), "nueva": cc})
                cambios += 1

            pc = (res.get("provincia_corregida") or "").strip()
            if pc and pc != (r.get("provincia") or "").strip():
                a_provincia.append({"id": rid, "nombre": nombre,
                                    "original": r.get("provincia","") or "(vacía)", "nueva": pc})
                cambios += 1

            cat_nueva = (res.get("categoria_nueva") or "").strip()
            if cat_nueva and not (r.get("categoria") or "").strip():
                a_categoria.append({"id": rid, "nombre": nombre, "categoria": cat_nueva})
                cambios += 1

            if res.get("email_invalido") and (r.get("email_principal") or "").strip():
                a_email_inv.append({"id": rid, "nombre": nombre,
                                    "email": r.get("email_principal","")})
                cambios += 1

            if res.get("telefono_invalido") and (r.get("telefono_principal") or "").strip():
                a_tel_inv.append({"id": rid, "nombre": nombre,
                                  "telefono": r.get("telefono_principal","")})
                cambios += 1

            if res.get("web_invalida") and (r.get("web") or "").strip():
                a_web_inv.append({"id": rid, "nombre": nombre, "web": r.get("web","")})
                cambios += 1

            dup = res.get("duplicado_de_id")
            if dup and dup in mapa:
                a_duplicados.append({
                    "id_dup": rid, "nombre_dup": nombre,
                    "id_orig": dup, "nombre_orig": (mapa[dup].get("nombre") or "").strip(),
                })

        # Marcar como procesados y guardar checkpoint
        for r in lote:
            procesados.add(r["id"])
        guardar_checkpoint(procesados)

        print(
            f"{cambios} cambios  "
            f"[elim={len(a_eliminar)} nombres={len(a_limpiar)} "
            f"ciudad={len(a_ciudad)} prov={len(a_provincia)} "
            f"email={len(a_email_inv)} tel={len(a_tel_inv)} web={len(a_web_inv)}]"
        )

        time.sleep(DELAY)

    # Aplicar o mostrar resumen
    aplicar_cambios(
        a_eliminar, a_limpiar, a_ciudad, a_provincia,
        a_categoria, a_email_inv, a_tel_inv, a_web_inv,
        dry_run,
    )

    # Duplicados (solo info)
    if a_duplicados:
        print(f"\nDuplicados detectados ({len(a_duplicados)}):")
        for d in a_duplicados[:20]:
            print(f"  [{d['id_dup']}] '{d['nombre_dup']}' → duplicado de [{d['id_orig']}] '{d['nombre_orig']}'")
        if len(a_duplicados) > 20:
            print(f"  ... y {len(a_duplicados)-20} más")

    # Limpiar checkpoint al terminar exitosamente
    borrar_checkpoint()
    print("\n✅ Proceso completado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clasificador IA de inmobiliarias (Claude)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra cambios pero no toca la BD")
    parser.add_argument("--limit",   type=int, default=0,
                        help="Procesar solo N registros (para prueba)")
    parser.add_argument("--reset",   action="store_true",
                        help="Borrar checkpoint y empezar desde cero")
    args = parser.parse_args()

    if args.reset:
        borrar_checkpoint()

    run(dry_run=args.dry_run, limit=args.limit)

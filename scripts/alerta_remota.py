#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que un paro llegue al teléfono, no sólo a esta máquina. §18, §16, §100.14.

No escribe en la base. `database_writes: 0`. No contrata nada, no guarda
ningún secreto en el repositorio y **no manda nada hasta que el usuario elija
un canal**: este módulo queda preparado e inerte.

Por qué hace falta, medido
--------------------------
`tiempo_perdido_por_causa.py` midió 7 días reales: 102,8 h de cola parada en 58
episodios. La mediana de un episodio es de **8 minutos** —diagnosticar no es
caro— y 9 episodios (16%) se llevan **80% de las horas**, con máximos de 15, 17
y 18 h. Ocho de esos nueve **empezaron en horario de día**, entre las 9 y las
16. O sea: no es que pasen de noche y nadie esté; es que el aviso no llega a
donde está la persona. Ese es el agujero que tapa este módulo, y es el de mayor
retorno medido de todo el tablero.

Regla que no se negocia (§16)
-----------------------------
Persistir estado **antes** que notificar. Este módulo se llama último, con
tiempo de espera corto, y traga toda excepción: si el canal remoto falla, el
vigilante ya escribió su estado y la cola sigue. Un canal de aviso que puede
frenar la producción es peor que no tener canal.

Canales
-------
Ninguno se da por bueno sin comprobarlo. El §18 se escribió justamente porque
un canal que parece estar y no está es indistinguible de no avisar.

  ``ntfy``      empuje real al teléfono. Gratis, sin cuenta, sin servicio pago.
                Lo único que necesita es un tema, que elige el usuario y que se
                lee de un archivo **fuera del repositorio**. Sin ese archivo el
                canal queda apagado y este módulo no sale a la red.

  ``onedrive``  deja el aviso en una carpeta que sincroniza al teléfono. Se
                comprobó en esta máquina el 2026-09-16: la carpeta existe, está
                vacía y **el cliente de OneDrive no está corriendo**. Así que el
                canal se declara NO_DISPONIBLE en vez de escribir un archivo que
                no viaja a ninguna parte.

Uso:
    python scripts/alerta_remota.py --estado          ver qué canales hay
    python scripts/alerta_remota.py --probar          enviar una prueba
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

# Fuera del repositorio a propósito: lo que el usuario escriba acá no se
# commitea, no entra en un artefacto y no viaja en un prompt.
CONFIG = Path(os.environ.get("ERETZ_ALERTA_REMOTA_CONFIG")
              or Path.home() / ".eretz" / "alerta_remota.json")
BITACORA = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
                r"\ERETZ_ALERTA_REMOTA.log")
BUZON_ONEDRIVE = Path.home() / "OneDrive" / "ERETZ_ALERTAS.txt"

# Corto a propósito. El aviso es lo último y lo menos importante de la cadena.
ESPERA_SEGUNDOS = 8.0


def leer_config() -> dict[str, Any]:
    """La config puede no existir, y eso es un estado válido, no un error."""
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _anotar(linea: str) -> None:
    try:
        BITACORA.parent.mkdir(parents=True, exist_ok=True)
        with BITACORA.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {linea}\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# Canales. Cada uno contesta dos preguntas: ¿estás disponible? y ¿mandaste?
# --------------------------------------------------------------------------

def onedrive_disponible() -> tuple[bool, str]:
    """No alcanza con que exista la carpeta: tiene que estar sincronizando.

    Una carpeta `OneDrive` sin cliente corriendo acepta el archivo y no lo
    manda a ningún lado. El aviso parecería enviado y nadie lo recibiría, que
    es exactamente el modo de falla que el §18 pide evitar.
    """
    if not BUZON_ONEDRIVE.parent.is_dir():
        return False, "no hay carpeta OneDrive en este perfil"
    try:
        salida = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OneDrive.exe"],
                                capture_output=True, text=True, timeout=10)
        vivo = "OneDrive.exe" in (salida.stdout or "")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"no se pudo comprobar el cliente: {type(e).__name__}"
    if not vivo:
        return False, ("la carpeta existe pero el cliente de OneDrive no esta "
                       "corriendo: lo que se escriba ahi no sincroniza")
    return True, "carpeta presente y cliente corriendo"


def onedrive_enviar(titulo: str, cuerpo: str) -> bool:
    try:
        with BUZON_ONEDRIVE.open("a", encoding="utf-8") as fh:
            fh.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M')} · {titulo} ===\n"
                     f"{cuerpo}\n")
        return True
    except OSError:
        return False


def ntfy_disponible(config: dict[str, Any]) -> tuple[bool, str]:
    tema = (config.get("ntfy_topic") or "").strip()
    if not tema:
        return False, (f"sin tema configurado. El usuario elige uno y lo "
                       f"escribe en {CONFIG}")
    return True, f"tema configurado en {CONFIG}"


def ntfy_enviar(config: dict[str, Any], titulo: str, cuerpo: str) -> bool:
    tema = (config.get("ntfy_topic") or "").strip()
    servidor = (config.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
    if not tema:
        return False
    peticion = urllib.request.Request(
        f"{servidor}/{tema}", data=cuerpo.encode("utf-8"),
        headers={"Title": titulo.encode("utf-8").decode("latin-1", "replace"),
                 "Priority": "high", "Tags": "warning"})
    try:
        with urllib.request.urlopen(peticion, timeout=ESPERA_SEGUNDOS) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


def canales(config: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    config = leer_config() if config is None else config
    ntfy_ok, ntfy_por = ntfy_disponible(config)
    od_ok, od_por = onedrive_disponible()
    return {"ntfy": {"disponible": ntfy_ok, "porque": ntfy_por},
            "onedrive": {"disponible": od_ok, "porque": od_por}}


def avisar_remoto(titulo: str, cuerpo: str) -> dict[str, Any]:
    """Intenta todos los canales disponibles. Nunca levanta una excepción.

    Devuelve qué canal funcionó. No corta en el primero que anda: si el usuario
    configuró dos, que lleguen los dos —un aviso duplicado no cuesta nada y un
    aviso perdido costó 18 horas—.
    """
    resultado: dict[str, Any] = {"enviado": False, "vias": {}, "errores": {}}
    try:
        config = leer_config()
        estado = canales(config)
        for nombre, envio in (("ntfy", lambda: ntfy_enviar(config, titulo, cuerpo)),
                              ("onedrive", lambda: onedrive_enviar(titulo, cuerpo))):
            if not estado[nombre]["disponible"]:
                resultado["vias"][nombre] = False
                resultado["errores"][nombre] = estado[nombre]["porque"]
                continue
            try:
                ok = bool(envio())
            except Exception as e:  # noqa: BLE001 - el canal no puede romper nada
                ok = False
                resultado["errores"][nombre] = f"{type(e).__name__}: {e}"
            resultado["vias"][nombre] = ok
            resultado["enviado"] = resultado["enviado"] or ok
    except Exception as e:  # noqa: BLE001
        resultado["errores"]["general"] = f"{type(e).__name__}: {e}"
    _anotar(f"{'ENVIADO' if resultado['enviado'] else 'NO_ENVIADO'}  "
            f"{titulo[:60]}  vias={resultado['vias']}")
    return resultado


def texto_desde_estado(estado: dict[str, Any]) -> tuple[str, str]:
    """El mismo estado que ya escribe el vigilante, sin volver a calcular nada."""
    agencia = (estado.get("agency") or "").split(":")[-1] or "sin agencia"
    minutos = estado.get("minutes_paused")
    titulo = f"ERETZ: cola parada ({estado.get('stop_state')})"
    cuerpo = (f"{agencia}\n"
              f"firma: {estado.get('stop_signature') or 'sin firma'}\n"
              f"detenida hace: {minutos} min\n"
              f"workers vivos: {estado.get('workers_alive')}\n"
              f"diagnostico: {estado.get('diagnosis_state')}")
    return titulo, cuerpo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estado", action="store_true",
                    help="mostrar que canales hay, sin mandar nada")
    ap.add_argument("--probar", action="store_true",
                    help="mandar un aviso de prueba por los canales disponibles")
    args = ap.parse_args()

    estado = canales()
    print(f"config: {CONFIG}  {'(existe)' if CONFIG.exists() else '(no existe)'}\n")
    for nombre, dato in estado.items():
        marca = "OK " if dato["disponible"] else "-- "
        print(f"{marca}{nombre:12} {dato['porque']}")

    if not any(d["disponible"] for d in estado.values()):
        print("\n  Ningun canal remoto disponible: hoy el aviso llega solo a")
        print("  esta maquina. Para habilitar el empuje al telefono hace falta")
        print(f"  crear {CONFIG} con:")
        print('      {"ntfy_topic": "<un-nombre-que-elijas>"}')
        print("  y suscribirse a ese mismo nombre desde la app ntfy. Es gratis,")
        print("  no pide cuenta y no hay ningun secreto que guardar. No lo")
        print("  configuro yo: el tema es la unica cosa que protege el canal.")

    if args.probar:
        if not any(d["disponible"] for d in estado.values()):
            print("\nno hay nada por donde mandar la prueba")
            return 1
        r = avisar_remoto("ERETZ: prueba de canal remoto",
                          "Si ves esto, el canal remoto funciona.")
        print(f"\nprueba: {json.dumps(r, ensure_ascii=False)}")

    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

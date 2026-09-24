#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Hay un paro sin atender, y desde hace cuánto?

No escribe en la base. `database_writes: 0`. No relanza nada, no mata nada:
mira y dice.

El 2026-09-15 la cola paró a las 23:49 en `fenix inmobiliaria` y estuvo
**ocho horas** detenida. Nadie lo supo hasta que alguien fue a mirar los
cerrojos a mano. El paro estaba bien puesto —era un defecto transversal real y
diagnosticable— y no hay que relajarlo: lo que faltaba era que se viera.

Las cuatro marcas que el §12 pide salen todas de archivos que ya existen, sin
infraestructura nueva:

    STOP_SIGNATURE      del `AGENCY_CERTIFICATION_STOP.json`
    QUEUE_PAUSED_AT     de su campo `cuando`
    STOP_DETECTED_AT    de cuándo se corre esto
    DIAGNOSIS_STARTED_AT  de si esa agencia ya tiene una diferida escrita
                          después del paro

Uso:
    python scripts/vigilante_de_paros.py
    python scripts/vigilante_de_paros.py --umbral-minutos 20
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# El `.bat` corre `python scripts\vigilante_de_paros.py`, asi que `sys.path[0]`
# es la carpeta `scripts` y NO la raiz del repo: un `from scripts.x import y`
# revienta con ModuleNotFoundError. Paso el 2026-09-16 y el vigilante quedo dos
# horas fallando en silencio mientras la cola estaba parada.
#
# Se agregan las DOS: la raiz para los imports con prefijo y la carpeta propia
# para los sin prefijo, y asi da igual desde donde se lo invoque.
_AQUI = Path(__file__).resolve().parent
for _ruta in (str(_AQUI.parent), str(_AQUI)):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

# El import va ACA ARRIBA y no adentro de la rama que avisa.
#
# Estaba adentro, y por eso ningun test lo ejecutaba: todos pasan
# `--sin-alerta`, que saltea esa rama. El 2026-09-16 se rompio en produccion
# con quince tests en verde. Un import perezoso dentro de un `if` es codigo que
# solo corre cuando ya es tarde.
from alerta_de_cola import avisar  # noqa: E402

CERT = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
BANDERA = CERT / "AGENCY_CERTIFICATION_STOP.json"
DIFERIDOS = CERT / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
CERROJO = "AGENCY_CERTIFICATION_RUNNER.w{}.lock"
# El unico archivo que este script escribe. Es local, no es la base, y su
# contenido es lo que el propio script acaba de leer: si se borra, la siguiente
# corrida lo reconstruye igual. No lleva secretos ni datos de inmobiliarias.
ESTADO = CERT / "ERETZ_QUEUE_WATCH_STATUS.json"
# Solo TRANSICIONES. Un log con una linea cada 5 minutos es un log que nadie
# lee, y este tiene que poder leerse de un vistazo despues de un fin de semana.
BITACORA = CERT / "ERETZ_QUEUE_WATCH.log"

# Los dos estados que sacan a alguien de lo que esta haciendo. `PARO_RECIENTE`
# no alerta a proposito: todavia esta dentro del umbral y puede resolverse
# solo. `PARO_DIAGNOSTICADO` tampoco: ya tiene diferida escrita.
ALERTAN = ("PARO_DESATENDIDO", "CERO_WORKERS_SIN_BANDERA",
           "FAMILIA_DETENIDA")
# Cada cuanto se repite el aviso mientras el mismo paro siga sin resolver.
RECORDATORIO_MINUTOS = 60


def epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return time.mktime(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def workers_vivos() -> list[dict]:
    """Los cerrojos cuyo proceso propietario sigue existiendo.

    Un cerrojo huérfano no es un worker: si se contara como vivo, el vigilante
    diría que todo anda mientras la cola está parada, que es justo el error que
    viene a evitar.
    """
    fuera = []
    for i in (0, 1):
        ruta = CERT / CERROJO.format(i)
        if not ruta.exists():
            continue
        try:
            d = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pid = d.get("pid")
        if pid and _vive(pid):
            fuera.append({"worker": f"w{i}", **d})
    return fuera


def _vive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    # Sin ventana: la tarea corre con `pythonw.exe` desde el 2026-09-24 y
    # esto se llama en cada pasada, cada cinco minutos.
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                       capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return str(pid) in (r.stdout or "")


def diagnosticada_despues(agencia: str, desde: float | None) -> str | None:
    """¿Alguien ya escribió una diferida para esta agencia DESPUÉS del paro?"""
    if not DIFERIDOS.exists():
        return None
    mejor = None
    for linea in DIFERIDOS.read_text(encoding="utf-8",
                                     errors="replace").splitlines():
        if not linea.strip():
            continue
        try:
            f = json.loads(linea)
        except ValueError:
            continue
        if f.get("canonical_agency_id") != agencia:
            continue
        cuando = epoch(f.get("cuando"))
        if cuando is None:
            continue
        if desde is None or cuando >= desde:
            if mejor is None or cuando < mejor:
                mejor = cuando
    return (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mejor))
            if mejor else None)



# Una familia detenida no es tan urgente como la cola entera parada -el resto
# sigue certificando- pero tampoco puede quedarse ahi para siempre: sobre las
# 791 agencias de la cola `ready`, `generico` es el 46,3 % y `tokko` el 37,8 %.
UMBRAL_FAMILIA_HORAS = 12.0


def familias_detenidas() -> list[dict]:
    """Las familias que el relanzador dejo fuera y siguen sin firma.

    Se importa la funcion del relanzador en vez de releer el archivo aca: la
    regla de «esta atendido» ya esta escrita una vez y escribirla dos veces es
    como terminan divergiendo. Si el modulo no esta, se sigue sin esta vista
    en lugar de romper la vigilancia que ya funcionaba.
    """
    try:
        from relanzar_la_cola import familias_pendientes
    except Exception:  # noqa: BLE001
        return []
    try:
        return familias_pendientes(CERT)
    except Exception:  # noqa: BLE001
        return []


def horas_detenida(familia: dict, ahora: float) -> float | None:
    desde = epoch(familia.get("cuando"))
    return None if desde is None else (ahora - desde) / 3600


def mas_vieja(familias: list[dict], ahora: float) -> float | None:
    horas = [h for h in (horas_detenida(f, ahora) for f in familias)
             if h is not None]
    return max(horas) if horas else None


def clave_de_alerta(estado: dict) -> str | None:
    """Que identifica a ESTE paro y no a otro.

    La firma sola no alcanza: dos paros distintos pueden compartirla. La hora
    de pausa sola tampoco: el mismo paro la conserva. Las dos juntas
    identifican un episodio, y por eso cuando el paro se resuelve y aparece
    otro, la clave cambia y vuelve a avisar.
    """
    e = estado.get("stop_state")
    if e not in ALERTAN:
        return None
    if e == "FAMILIA_DETENIDA":
        # La clave es el conjunto de familias, no la hora: mientras sean las
        # mismas es el mismo episodio y alcanza con el recordatorio. Si se
        # suma otra familia, la clave cambia y vuelve a avisar.
        return f"FAMILIAS|{estado.get('stop_signature')}"
    if e == "CERO_WORKERS_SIN_BANDERA":
        # Sin bandera no hay firma ni hora: el episodio es "no hay nadie
        # certificando", y se deduplica como uno solo hasta que vuelva el OK.
        return "CERO_WORKERS"
    return f"{estado.get('stop_signature')}|{estado.get('paused_since')}"


def estado_previo() -> dict:
    if not ESTADO.exists():
        return {}
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def anotar(linea: str) -> None:
    """Una linea en la bitacora. Solo la llaman las transiciones."""
    try:
        with BITACORA.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {linea}\n")
    except OSError:
        pass


def decidir_alerta(estado: dict, previo: dict, ahora: float,
                   recordatorio: float) -> tuple[bool, str]:
    """¿Hay que avisar, y por que? Separado de avisar() para poder probarlo
    sin hacer sonar la maquina."""
    clave = clave_de_alerta(estado)
    if not clave:
        return False, "el estado no alerta"
    if previo.get("alert_key") != clave:
        return True, "paro nuevo"
    ultimo = _fecha_iso(previo.get("last_alert_at"))
    if ultimo is None:
        return True, "no hay registro de aviso anterior"
    minutos = (ahora - ultimo) / 60
    if minutos >= recordatorio:
        return True, f"recordatorio, {minutos:.0f} min desde el ultimo"
    return False, f"ya se aviso hace {minutos:.0f} min"


def _fecha_iso(iso: str | None) -> float | None:
    return epoch(iso)


def registrar_transicion(estado: dict, previo: dict) -> None:
    """Solo cuando cambia algo que a alguien le importa."""
    antes, ahora_e = previo.get("stop_state"), estado.get("stop_state")
    if antes == ahora_e:
        return
    agencia = (estado.get("agency") or "").split(":")[-1]
    if ahora_e == "OK" and antes:
        anotar(f"{antes} -> OK   la cola volvio a avanzar")
    elif ahora_e == "CERO_WORKERS_SIN_BANDERA":
        anotar("-> CERO_WORKERS   nadie certificando y ninguna bandera lo explica")
    elif ahora_e in ("PARO_RECIENTE", "PARO_OPERACIONAL"):
        anotar(f"{antes or '(inicio)'} -> {ahora_e}   {agencia}  "
               f"[{estado.get('stop_signature')}]")
    elif ahora_e == "PARO_DESATENDIDO":
        anotar(f"{antes or '(inicio)'} -> PARO_DESATENDIDO   {agencia}  "
               f"detenida hace {estado.get('minutes_paused')} min  "
               f"[{estado.get('stop_signature')}]")
    elif ahora_e == "FAMILIA_DETENIDA":
        anotar(f"{antes or '(inicio)'} -> FAMILIA_DETENIDA   "
               f"{estado.get('stop_signature')}  "
               f"detenida hace {estado.get('minutes_paused')} min")
    elif ahora_e == "PARO_DIAGNOSTICADO":
        anotar(f"{antes or '(inicio)'} -> DIAGNOSTICADO   {agencia}  "
               f"diferida escrita {estado.get('diagnosis_state')}")


def escribir_estado(d: dict) -> None:
    """Deja el estado por escrito para que no haya que estar mirando.

    Se escribe primero a un temporal y despues se renombra: si el proceso
    muere a la mitad, nadie lee un JSON cortado por la mitad y lo confunde con
    "no hay paro".
    """
    tmp = ESTADO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ESTADO)



def cerrar(estado: dict, previo: dict, ahora: float, args) -> None:
    """Decide el aviso, lo manda, anota la transicion y guarda el estado.

    El orden importa: el estado se guarda AL FINAL y con `last_alert_at` ya
    actualizado. Si se guardara antes, un fallo al notificar dejaria escrito
    que se aviso cuando no se aviso, y el recordatorio no volveria a salir.
    """
    hay_que, por_que = decidir_alerta(estado, previo, ahora,
                                      args.recordatorio_minutos)
    estado["alert_key"] = clave_de_alerta(estado)
    estado["last_alert_at"] = previo.get("last_alert_at")

    if hay_que and not args.sin_alerta:
        # Envuelto a proposito. Un fallo al NOTIFICAR no puede impedir que se
        # escriba el estado: el 2026-09-16 un ModuleNotFoundError aca dejo el
        # archivo congelado dos horas con la cola parada, que es exactamente lo
        # que este script existe para evitar. Avisar es lo deseable; dejar
        # constancia es lo obligatorio.
        try:
            vias = avisar(estado)
            estado["last_alert_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            estado["last_alert_vias"] = vias
            anotar(f"AVISO   {estado.get('stop_state')}  "
                   f"{(estado.get('agency') or '').split(':')[-1]}  "
                   f"({por_que})  vias={vias}")
            print(f"\nAVISO ENVIADO — {por_que}  vias={vias}")
        except Exception as e:
            # No se toca `last_alert_at`: si no se aviso, el proximo chequeo
            # tiene que volver a intentarlo en vez de creer que ya aviso.
            estado["alert_error"] = f"{type(e).__name__}: {e}"
            anotar(f"FALLO EL AVISO   {type(e).__name__}: {e}   "
                   f"-- el estado igual queda escrito")
            print(f"\nFALLO EL AVISO: {type(e).__name__}: {e}")
    elif hay_que:
        estado["last_alert_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        print(f"\n(--sin-alerta) habria avisado: {por_que}")
    else:
        print(f"\nsin aviso: {por_que}")

    # Cuando vuelve el OK se limpia la clave, y por eso un paro NUEVO
    # -aunque tenga la misma firma- vuelve a avisar.
    if estado.get("stop_state") == "OK":
        estado["alert_key"] = None
        estado["last_alert_at"] = None

    registrar_transicion(estado, previo)
    if not args.sin_estado:
        escribir_estado(estado)
        print(f"estado -> {ESTADO.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-alerta", action="store_true",
                    help="no notificar; solo escribir estado y bitacora")
    ap.add_argument("--recordatorio-minutos", type=float,
                    default=RECORDATORIO_MINUTOS,
                    help="cada cuanto repetir el aviso de un paro sin resolver")
    ap.add_argument("--sin-estado", action="store_true",
                    help="no escribir ERETZ_QUEUE_WATCH_STATUS.json")
    ap.add_argument("--umbral-familia-horas", type=float,
                    default=UMBRAL_FAMILIA_HORAS,
                    help="a partir de cuantas horas una familia detenida sin "
                         "diferida firmada se reporta como FAMILIA_DETENIDA")
    ap.add_argument("--umbral-minutos", type=float, default=30,
                    help="a partir de cuántos minutos un paro sin atender "
                         "se reporta como PARO_DESATENDIDO")
    ap.add_argument("--log", default=None,
                    help="escribir la salida en este archivo (modo tarea, sin "
                         "consola). Ver `relanzar_la_cola.escribir_en_el_log`.")
    args = ap.parse_args()
    if args.log:
        # La misma razon y el mismo mecanismo que el relanzador: con consola
        # las pasadas morian con 0xC000013A sin dejar rastro.
        from relanzar_la_cola import escribir_en_el_log
        escribir_en_el_log(Path(args.log))

    ahora = time.time()
    previo = estado_previo()
    vivos = workers_vivos()
    bandera = None
    if BANDERA.exists():
        try:
            bandera = json.loads(BANDERA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bandera = {"canonical_agency_id": "(bandera ilegible)"}

    print(f"STOP_DETECTED_AT      {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print(f"WORKERS_VIVOS         {len(vivos)}")
    for w in vivos:
        print(f"   {w['worker']}  pid={w.get('pid')}  "
              f"{w.get('current_agency')}  latido={w.get('heartbeat')}")

    estado = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "workers_alive": len(vivos),
        "workers": [{"worker": w["worker"], "pid": w.get("pid"),
                     "current_agency": w.get("current_agency"),
                     "heartbeat": w.get("heartbeat")} for w in vivos],
        "stop_state": None, "stop_signature": None,
        "paused_since": None, "minutes_paused": None,
        "diagnosis_state": None, "agency": None,
    }

    familias = familias_detenidas()
    if familias:
        estado["detained_families"] = [
            {"conector": f.get("conector"),
             "agencia": f.get("canonical_agency_id"),
             "desde": f.get("cuando"),
             "horas": round(horas_detenida(f, ahora) or 0, 1)}
            for f in familias]
        print(f"\nFAMILIAS_DETENIDAS    {len(familias)}")
        for f in estado["detained_families"]:
            print(f"   {str(f['conector']):12s} desde {f['desde']}  "
                  f"({f['horas']} h)  por "
                  f"{str(f['agencia']).split(':')[-1][:32]}")

    if not bandera:
        vieja = mas_vieja(familias, ahora)
        if vivos and vieja is not None and vieja >= args.umbral_familia_horas:
            # La cola avanza, pero una familia entera lleva horas sin tocarse.
            #
            # Sin esto el acotamiento por familia se comeria su propia
            # vigilancia: el relanzador consume la bandera, el vigilante ve
            # workers vivos y dice OK, y una familia -hasta el 35 % de la
            # cola, si es `generico`- se queda detenida sin que nadie se
            # entere. Seria el 2026-09-21 otra vez, mas silencioso.
            peor = max(familias, key=lambda f: horas_detenida(f, ahora) or 0)
            estado.update({
                "stop_state": "FAMILIA_DETENIDA",
                "stop_signature": "familia " + ", ".join(sorted(
                    {str(f.get("conector")) for f in familias})),
                "paused_since": peor.get("cuando"),
                "minutes_paused": round(vieja * 60),
                "agency": peor.get("canonical_agency_id"),
                "diagnosis_state": "SIN_DIAGNOSTICO"})
            print(f"\nESTADO: FAMILIA_DETENIDA — {vieja:.1f} h sin diagnostico.")
            print("   El resto de la cola avanza, pero esta familia no se")
            print("   toca hasta que su paro tenga diferida firmada.")
            cerrar(estado, previo, ahora, args)
            print("\ndatabase_writes: 0")
            return 0
        estado["stop_state"] = "OK" if vivos else "CERO_WORKERS_SIN_BANDERA"
        if vivos:
            print("\nESTADO: OK — la cola avanza y no hay bandera de paro.")
        else:
            print("\nESTADO: CERO_WORKERS_SIN_BANDERA")
            print("   Nadie esta certificando y no hay un paro que lo explique.")
            print("   Puede ser un arranque pendiente o una caida sin rastro:")
            print("   mirar w0.err y w1.err antes de relanzar.")
        cerrar(estado, previo, ahora, args)
        print("\ndatabase_writes: 0")
        return 0

    agencia = bandera.get("canonical_agency_id") or "(sin id)"
    pausado = epoch(bandera.get("cuando"))
    minutos = (ahora - pausado) / 60 if pausado else None
    diag = diagnosticada_despues(agencia, pausado)

    print(f"\nSTOP_SIGNATURE        {bandera.get('componente')} / "
          f"{bandera.get('radio')}")
    print(f"QUEUE_PAUSED_AT       {bandera.get('cuando')}")
    print(f"AGENCIA               {agencia}")
    print(f"DIAGNOSIS_STARTED_AT  {diag or '(todavia nadie)'}")
    if minutos is not None:
        print(f"MINUTOS_DETENIDA      {minutos:.0f}")

    # Una bandera de operacion no es un defecto: se puso a proposito para
    # relanzar. No debe disparar la misma alarma.
    estado.update({"stop_signature": f"{bandera.get('componente')} / {bandera.get('radio')}",
                   "paused_since": bandera.get("cuando"),
                   "minutes_paused": round(minutos) if minutos is not None else None,
                   "agency": agencia,
                   "diagnosis_state": diag or "SIN_DIAGNOSTICO"})
    if str(bandera.get("radio")) == "OPERACION":
        estado["stop_state"] = "PARO_OPERACIONAL"
        print("\nESTADO: PARO_OPERACIONAL — lo pedimos nosotros para relanzar.")
    elif diag:
        estado["stop_state"] = "PARO_DIAGNOSTICADO"
        print("\nESTADO: PARO_DIAGNOSTICADO — ya tiene diferida escrita.")
        print("   Si los workers no estan vivos, falta relanzarlos.")
    elif minutos is not None and minutos > args.umbral_minutos:
        estado["stop_state"] = "PARO_DESATENDIDO"
        print(f"\nESTADO: PARO_DESATENDIDO — {minutos:.0f} min sin diagnostico.")
        print("   Esto es lo que el 2026-09-15 duro OCHO HORAS.")
        print("   El paro NO se relaja: hay que diagnosticarlo contra la")
        print("   fuente, escribir la diferida con firma, y recien ahi")
        print("   relanzar. Empezar por:")
        print(f"      {bandera.get('evidencia', '')[:160]}")
    else:
        estado["stop_state"] = "PARO_RECIENTE"
        print("\nESTADO: PARO_RECIENTE — todavia dentro del umbral.")

    cerrar(estado, previo, ahora, args)
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

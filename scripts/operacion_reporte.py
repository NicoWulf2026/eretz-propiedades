#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El estado de ERETZ en una pantalla, para poder operarlo sin auditarlo entero.

Hoy saber como viene la corrida exige abrir seis artefactos y cruzarlos a mano.
Eso funciona una vez; no funciona todos los dias, y un sistema que necesita una
auditoria completa cada manana no esta terminado.

**Alertas, no ruido.** Solo se enciende lo que pide una accion humana. Que una
inmobiliaria este bloqueada no es una alerta: es un hecho conocido del mundo.
Que la cola este parada por un defecto transversal SI lo es, porque nadie mas
la va a reabrir.

Se lee todo de artefactos locales. No consulta produccion ni la red.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REPORTE_VERSION = "operacion_reporte_v2"

# El universo canonico. Se lee del checkpoint cuando esta; esto es el
# respaldo para cuando no.
UNIVERSO_CANONICO = 6597

# Terminal de verdad: la agencia no vuelve a la cola. `NEEDS_FIX` NO esta,
# porque vuelve cuando vence su diferida.
TERMINALES_DE_VERDAD = frozenset({
    "CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
    "NO_INVENTORY_CONFIRMED", "BLOCKED_EXTERNAL",
})

# El mismo umbral que usa el runner para decidir si un cerrojo quedo huerfano.
LATIDO_VENCIDO = 3600.0

# Estados que cierran una inmobiliaria. `NEEDS_FIX` NO es uno.
TERMINALES = ("CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
              "NO_INVENTORY_CONFIRMED", "BLOCKED_EXTERNAL", "IDENTITY_PENDING",
              "INACTIVE")


def _jsonl(ruta: Path) -> list[dict[str, Any]]:
    if not ruta.exists():
        return []
    fuera = []
    for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
        if linea.strip():
            try:
                fuera.append(json.loads(linea))
            except ValueError:
                # Una linea rota no puede tapar el resto del reporte, pero
                # tampoco se ignora en silencio: se cuenta abajo.
                fuera.append({"_ilegible": True})
    return fuera


def _proceso_existe(pid: Any) -> bool | None:
    """Si ese pid esta corriendo. `None` cuando no se puede saber.

    Sin esto, el reporte decidia por la edad del latido y llamaba huerfano a un
    worker vivo. La distincion importa porque la accion que sigue -liberar el
    cerrojo- pone un segundo runner sobre la misma particion.
    """
    if not isinstance(pid, int):
        return None
    try:
        import psutil
    except ImportError:
        # Sin la libreria no se inventa una respuesta: se dice que no se sabe
        # y el latido decide, que es lo que habia antes.
        return None
    try:
        return psutil.pid_exists(pid)
    except Exception:  # noqa: BLE001 - saber esto nunca puede tumbar el reporte
        return None


def _json(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def estado_de_la_cola(salida: Path) -> dict[str, Any]:
    resultados: dict[str, dict[str, Any]] = {}
    ilegibles = 0
    for fila in _jsonl(salida / "AGENCY_CERTIFICATION_RESULTS.jsonl"):
        if fila.get("_ilegible"):
            ilegibles += 1
            continue
        resultados[fila["canonical_agency_id"]] = fila

    # Lo que corre lo dice el LATIDO, no el archivo de progreso: un progreso
    # que quedo de una corrida muerta sigue nombrando una agencia, y contarlo
    # como runner activo hace ver dos procesos donde no hay ninguno.
    corriendo = []
    cerrojos = []
    for cerrojo in sorted(salida.glob("AGENCY_CERTIFICATION_RUNNER*.lock")):
        datos = _json(cerrojo)
        edad = time.time() - float(datos.get("heartbeat_epoch") or 0)
        proceso = _proceso_existe(datos.get("pid"))
        # El PID manda sobre el latido. Un latido viejo con el proceso VIVO es
        # un worker atascado en una inmobiliaria lenta, no un huerfano, y
        # liberar su cerrojo pondria un segundo runner sobre su particion.
        # Paso de verdad: `abriola propiedades` llevaba una hora y catorce
        # minutos con el proceso corriendo y ya figuraba vencido.
        vivo = proceso if proceso is not None else edad < LATIDO_VENCIDO
        cerrojos.append({"archivo": cerrojo.name, "pid": datos.get("pid"),
                         "latido_hace_s": round(edad),
                         "proceso_existe": proceso,
                         "vivo": vivo})
        if vivo:
            corriendo.append({"cerrojo": cerrojo.name,
                              "agencia": datos.get("current_agency"),
                              "latido_hace_s": round(edad)})
    estados = Counter(r.get("status") for r in resultados.values())
    return {
        "agencias_con_resultado": len(resultados),
        "por_estado": dict(estados.most_common()),
        "terminales": sum(estados[e] for e in TERMINALES),
        "needs_fix_abiertos": estados.get("NEEDS_FIX", 0),
        "lineas_ilegibles": ilegibles,
        "cerrojos": cerrojos,
        "cerrojos_huerfanos": [c["archivo"] for c in cerrojos if not c["vivo"]],
        "en_curso": corriendo,
        "paro_pedido": _json(salida / "AGENCY_CERTIFICATION_STOP.json") or None,
    }


def estado_de_los_datos(gate: Path, cobertura: Path) -> dict[str, Any]:
    resumen = _json(gate)
    geo = _json(cobertura)
    return {
        "propiedades": resumen.get("propiedades_evaluadas"),
        "publicables": resumen.get("publicables"),
        "perdidas_por_incompletitud": (
            (resumen.get("propiedades_evaluadas") or 0)
            - (resumen.get("publicables") or 0)),
        "por_alcance": resumen.get("por_alcance"),
        "area_por_nivel": resumen.get("area_de_busqueda_por_nivel"),
        "conflictos_geograficos": resumen.get("propiedades_en_conflicto_geografico"),
        "localidad_canonica_pct": geo.get("localidad_canonica_pct"),
        "extraccion_fallida_por_campo": dict(
            list((resumen.get("extraccion_fallida_por_campo") or {}).items())[:8]),
    }



# El vigilante corre cada 5 minutos por tarea programada. Si deja de escribir su
# estado, la cola puede estar parada y nadie enterarse: eso ya paso el
# 2026-09-16, cuando el vigilante fallo dos horas en silencio.
#
# Se comprueba contra el archivo que EL escribe, no contra la tarea: una tarea
# que arranca y revienta figura como "corrio". Lo que importa es si el estado
# esta fresco.
VIGILANTE_VENCIDO = 20 * 60


def salud_del_vigilante(salida: Path) -> dict[str, Any]:
    """§33. Sin infinitos vigilantes vigilando vigilantes: una sola pregunta.

    ¿Cuando fue la ultima vez que el vigilante dejo constancia?
    """
    estado = _json(salida / "ERETZ_QUEUE_WATCH_STATUS.json")
    if not estado:
        return {"estado": "WATCHDOG_SIN_ARTEFACTO",
                "detalle": "nunca escribio su archivo de estado"}
    visto = estado.get("checked_at")
    try:
        edad = time.time() - time.mktime(
            time.strptime(str(visto)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return {"estado": "WATCHDOG_UNHEALTHY",
                "detalle": f"fecha ilegible en el estado: {visto!r}"}
    sano = edad <= VIGILANTE_VENCIDO
    return {
        "estado": "OK" if sano else "WATCHDOG_UNHEALTHY",
        "ultimo_chequeo": visto,
        "edad_minutos": round(edad / 60, 1),
        "umbral_minutos": VIGILANTE_VENCIDO / 60,
        "stop_state": estado.get("stop_state"),
        "ultimo_aviso": estado.get("last_alert_at"),
        "error_al_avisar": estado.get("alert_error"),
        "detalle": None if sano else (
            f"el vigilante no deja constancia hace {edad/60:.0f} min. "
            f"Puede estar fallando en silencio: mirar vigilante.log"),
    }


def rendimiento(certificacion: Path, horas: float = 24.0) -> dict[str, Any]:
    """§52 y §53. Tres caudales distintos, que no son el mismo numero.

    Confundirlos lleva a optimizar lo que no importa: una agencia puede tardar
    tres horas y aportar 800 propiedades, y otra tardar diez minutos y aportar
    cero. `agencias/hora` sola premia a la segunda.
    """
    return _rendimiento_filas(
        _jsonl(certificacion / 'AGENCY_CERTIFICATION_RESULTS.jsonl'), horas, time.time())


def _rendimiento_filas(filas: list[Any], horas: float, ahora: float) -> dict[str, Any]:
    """Pure window calculation over one captured log and one observation clock."""
    if type(horas) not in (int, float) or not math.isfinite(horas) or horas <= 0:
        raise ValueError('La ventana de rendimiento debe ser positiva y finita')
    corte = ahora - horas * 3600
    exitos = {"CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE", "NO_INVENTORY_CONFIRMED"}
    vistas: set[str] = set()
    cerradas: set[str] = set()
    corridas = nuevas = exitos_nuevos = 0
    props_nuevas = 0
    segundos = 0.0
    sin_duracion = ilegibles = sin_inventario = 0
    observaciones = []
    for r in filas:
        if not isinstance(r, dict):
            ilegibles += 1
            continue
        a = r.get("canonical_agency_id")
        if not isinstance(a, str) or not a.strip():
            ilegibles += 1
            continue
        try:
            fecha = r.get('checked_at')
            if not isinstance(fecha, str) or 'T' not in fecha:
                raise ValueError('Fecha ausente')
            # Historical naive records retain the existing local-time meaning;
            # explicit offsets are respected instead of being truncated.
            cuando = datetime.fromisoformat(fecha).timestamp()
            if cuando > ahora:
                raise ValueError('Fecha futura')
        except (ValueError, TypeError, OverflowError, OSError):
            ilegibles += 1
            continue
        observaciones.append((cuando, a, r))
    for cuando, a, r in sorted(observaciones, key=lambda item: item[0]):
        primera = a not in vistas
        vistas.add(a)
        status = r.get('status')
        exito = isinstance(status, str) and status in exitos
        primer_exito = exito and a not in cerradas
        if exito:
            cerradas.add(a)
        if cuando < corte:
            continue
        corridas += 1
        metricas = r.get('operational_metrics')
        duracion = metricas.get('duration_seconds') if isinstance(metricas, dict) else None
        if type(duracion) in (int, float) and math.isfinite(duracion) and duracion >= 0:
            segundos += duracion
        else:
            sin_duracion += 1
        if primera:
            nuevas += 1
        if primer_exito:
            exitos_nuevos += 1
            audit = r.get('enumeration_audit')
            cantidad = audit.get('enumerated') if isinstance(audit, dict) else None
            if type(cantidad) is int and cantidad >= 0:
                props_nuevas += cantidad
            else:
                sin_inventario += 1
    return {
        "ventana_horas": horas,
        # Cuantas veces corrimos algo. Incluye repeticiones.
        "raw_throughput_corridas_por_hora": round(corridas / horas, 1),
        "new_attempt_throughput_agencias_por_hora": round(nuevas / horas, 2),
        # First recorded successful closure, not first attempt or external block.
        "certified_throughput_agencias_nuevas_por_hora": round(exitos_nuevos / horas, 2),
        # Compatibility key: enumerated in reported successes, NOT published rows.
        "useful_throughput_propiedades_por_hora": round(props_nuevas / horas, 1),
        "agencias_nuevas": nuevas,
        "agencias_con_primer_cierre_exitoso": exitos_nuevos,
        "corridas": corridas,
        "propiedades_nuevas": props_nuevas,
        "horas_de_worker_gastadas": round(segundos / 3600, 1),
        "corridas_sin_duracion_verificada": sin_duracion,
        "cierres_sin_inventario_verificado": sin_inventario,
        "registros_ilegibles_o_sin_fecha_valida": ilegibles,
        "eta_eligible": ilegibles == 0,
        "evidence_basis": "reported_status_not_current_certification_or_publication",
        "nota": ("`raw` incluye repeticiones. Intentos nuevos no son certificados. "
                 "`certified` cuenta primeros cierres exitosos registrados; no verifica "
                 "vigencia de código, fuente ni calidad. `useful` suma inventario "
                 "enumerado de esos cierres, NO propiedades publicadas. Horas de "
                 "worker suman sólo duraciones conocidas; no son un total si faltan."),
    }


def eta(cola: dict[str, Any], rend: dict[str, Any]) -> dict[str, Any]:
    """§52: ETA dinamica, calculada con el caudal de AHORA.

    No se guarda una fecha historica: si el ritmo cambia, la fecha cambia, y
    una ETA que no se mueve cuando el ritmo se derrumba es peor que ninguna.
    """
    # Lo que falta NO es "las que estan en la cola de hoy": es el universo
    # canonico menos lo que ya llego a un estado terminal. Usar la cola actual
    # daria una fecha optimista que ignora las 6.000 que todavia no entraron.
    if rend.get('eta_eligible') is False:
        return {'estado': 'SIN_ETA', 'porque': 'el historial contiene registros sin fecha válida'}
    UNIVERSO = 6597
    pendientes = max(0, UNIVERSO - (cola.get("terminales") or 0))
    por_hora = rend.get("certified_throughput_agencias_nuevas_por_hora") or 0
    if not pendientes or por_hora <= 0:
        return {"estado": "SIN_ETA",
                "porque": ("no hay avance medible en la ventana: con cero "
                           "agencias nuevas por hora, cualquier fecha seria "
                           "inventada")}
    horas = pendientes / por_hora
    return {
        "pendientes": pendientes,
        "agencias_nuevas_por_hora": por_hora,
        "horas_estimadas": round(horas, 1),
        "fecha_estimada": time.strftime(
            "%Y-%m-%d", time.localtime(time.time() + horas * 3600)),
        "eta_6h": round(por_hora * 6, 1),
        "eta_24h": round(por_hora * 24, 1),
        "nota": "calculada con el caudal de las ultimas horas, no con una "
                "cifra guardada",
    }


def caudal_por_ventana(certificacion: Path,
                       horas: tuple[int, ...] = (6, 12, 24, 48, 168),
                       ) -> dict[str, float]:
    """Primeros cierres exitosos registrados por hora, no primeras corridas.

    Reutiliza exactamente la frontera de rendimiento para que las fechas de
    ETA no sigan usando una métrica de intentos tras corregir el panel.
    Una ventana con historial ilegible no aporta un ritmo para estimar.
    """
    filas = _jsonl(certificacion / 'AGENCY_CERTIFICATION_RESULTS.jsonl')
    ahora = time.time()
    ventanas = {f'{h}h': _rendimiento_filas(filas, h, ahora) for h in horas}
    return {key: value['certified_throughput_agencias_nuevas_por_hora']
            if value['eta_eligible'] else 0.0 for key, value in ventanas.items()}


def eta_por_poblacion(certificacion: Path, datos_dir: Path,
                      rend: dict[str, Any]) -> dict[str, Any]:
    """§70: no una fecha para 6.597 agencias que no están en la misma cola.

    La ETA agregada que este mismo archivo venía dando —una sola fecha para
    `universo − terminales`— es la que el §70 pide dejar de dar, y no por
    prolijidad. Medido hoy:

        universo canónico                     6.597
        con entrada en el registro de fuentes 2.330
        **sin registro de fuentes**           4.267

    Esas 4.267 no esperan caudal de scraping: esperan que alguien les descubra
    una fuente, que es otro proceso, con otro ritmo, que hoy no está corriendo.
    Dividirlas por `agencias certificadas por hora` produce una fecha que no
    significa nada, y peor, que se mueve cuando mejora un caudal que no las
    toca.

    Lo mismo con las `IDENTITY_PENDING`: están frenadas antes del scraping, en
    la resolución de identidad.

    Donde no hay un proceso midiéndose, la respuesta honesta es `SIN_ETA` con
    el motivo, no una fecha.
    """
    por_hora = (rend.get("certified_throughput_agencias_nuevas_por_hora") or 0
                if rend.get('eta_eligible') is not False else 0)

    resultados = _jsonl(certificacion / "AGENCY_CERTIFICATION_RESULTS.jsonl")
    ultimo: dict[str, dict] = {}
    for fila in resultados:
        agencia = fila.get("canonical_agency_id")
        if agencia:
            ultimo[agencia] = fila
    registro = {f.get("canonical_agency_id")
                for f in _jsonl(datos_dir / "scrape_source_technology_map.jsonl")
                if f.get("canonical_agency_id")}
    progreso = _json(certificacion / "AGENCY_CERTIFICATION_PROGRESS.json")

    universo = progreso.get("universe") or UNIVERSO_CANONICO
    con_fuente = len(registro)
    terminales = {a for a, r in ultimo.items()
                  if r.get("status") in TERMINALES_DE_VERDAD}
    identidad = {a for a, r in ultimo.items()
                 if r.get("status") == "IDENTITY_PENDING"}
    navegador = {f.get("canonical_agency_id")
                 for f in _jsonl(datos_dir / "scrape_source_technology_map.jsonl")
                 if f.get("requires_js") is True and f.get("canonical_agency_id")}

    # El caudal medido en varias ventanas, porque varía mucho y una sola fecha
    # esconde esa variación.
    #
    # Medido el 2026-09-17: 2,67 nuevas/h en las últimas 6 h, 2,83 en 12 h,
    # 1,54 en 24 h, 1,04 en 48 h y 1,12 en 7 días. Dos veces y media de
    # diferencia según qué ventana se mire, y no es ruido: las ventanas cortas
    # son con alguien relanzando la cola después de cada paro, y las largas
    # incluyen las horas en que estuvo detenida sin que nadie mirara.
    #
    # Dar una sola fecha con ese spread es la falsa precisión que el §33 pide
    # evitar. Se da un rango, y el rango mismo dice cuánto vale atender la cola.
    ritmos = (caudal_por_ventana(certificacion)
              if rend.get('eta_eligible') is not False else {})

    def fechar(pendientes: int) -> dict[str, Any]:
        if pendientes <= 0:
            return {"pendientes": 0, "estado": "COMPLETA"}
        utiles = [r for r in ritmos.values() if r and r > 0]
        if not utiles:
            return {"pendientes": pendientes, "estado": "SIN_ETA",
                    "porque": "cero agencias nuevas por hora en toda ventana"}
        rapido, lento = max(utiles), min(utiles)
        return {
            "pendientes": pendientes,
            "ritmos_por_ventana": ritmos,
            "fecha_optimista": time.strftime(
                "%Y-%m-%d",
                time.localtime(time.time() + pendientes / rapido * 3600)),
            "fecha_pesimista": time.strftime(
                "%Y-%m-%d",
                time.localtime(time.time() + pendientes / lento * 3600)),
            "nota": (f"entre {lento:.2f} y {rapido:.2f} agencias nuevas por "
                     f"hora segun la ventana. Las ventanas cortas son con "
                     f"alguien relanzando tras cada paro; las largas incluyen "
                     f"las horas detenida sin que nadie mirara"),
        }

    en_cola = progreso.get("queue_size") or 0
    pendientes_cola = progreso.get("pending_count")
    if pendientes_cola is None:
        pendientes_cola = max(0, en_cola - len(terminales))

    listas_estaticas = max(0, con_fuente - len(terminales) - len(identidad)
                           - len(navegador))

    return {
        "por_que_separadas": ("una sola fecha para 6.597 agencias mezcla "
                              "poblaciones que esperan procesos distintos"),
        "agencias_nuevas_por_hora": por_hora,
        "ETA_CURRENT_BULK": {**fechar(pendientes_cola),
                             "poblacion": en_cola,
                             "que_es": "la cola de esta corrida"},
        "ETA_READY_STATIC": {**fechar(listas_estaticas),
                             "que_es": "con fuente registrada, sin navegador y "
                                       "sin bloqueo de identidad"},
        "ETA_READY_BROWSER": {
            "pendientes": len(navegador), "estado": "SIN_ETA",
            "que_es": "requires_js=True",
            "porque": ("no hay ventana de navegador abierta: el §25 la prohibe "
                       "con bulk activo, asi que su ritmo es cero por decision "
                       "y no por falta de capacidad")},
        "ETA_IDENTITY_BACKLOG": {
            "pendientes": len(identidad), "estado": "SIN_ETA",
            "que_es": "cerraron IDENTITY_PENDING",
            "porque": ("estan frenadas ANTES del scraping, en la resolucion de "
                       "identidad. El caudal de certificacion no las mueve")},
        "ETA_FULL_UNIVERSE": {
            "pendientes": max(0, universo - len(terminales)),
            "sin_registro_de_fuente": max(0, universo - con_fuente),
            "estado": "SIN_ETA",
            "porque": (f"{max(0, universo - con_fuente)} agencias del universo "
                       f"no tienen entrada en el registro de fuentes. No "
                       f"esperan caudal de scraping: esperan descubrimiento de "
                       f"fuente, que hoy no esta corriendo. Dividirlas por "
                       f"agencias/hora daria una fecha inventada")},
    }


def capacidad_de_reinicio() -> dict[str, Any]:
    """¿Existe algo que vuelva a levantar la cola cuando se cae?

    Sólo lee el Programador de tareas. **No crea ni modifica nada**, y la
    contención es deliberada: ponerle un disparador a estas tareas equivale a
    reiniciar la cola después de **cualquier** parada, incluida una no
    diagnosticada, y eso está explícitamente prohibido —un STOP nuevo se avisa,
    no se reinicia—.

    Lo que se descubrió el 2026-09-16: `ERETZ_cola_w0` y `ERETZ_cola_w1`
    existen, apuntan a `.bat` que funcionan, **tienen disparador** —la primera
    lectura dijo que no y era mía, no del sistema— y sin embargo su
    `NextRunTime` está **vacío**: no vuelven a correr nunca. Su último arranque
    fue el 2026-09-09, a mano, con código 2. `ERETZ_cola_certificacion` sí tiene
    próxima ejecución, para septiembre de **2027**.

    Por eso lo que se mira acá es la próxima ejecución y no la existencia de un
    disparador: contar disparadores daba verde sobre un sistema que no se
    reinicia solo.

    O sea que hoy la cola avanza únicamente mientras alguien la relanza. Eso
    explica el mecanismo detrás del número que más duele del tablero: 9 de 58
    paros se llevaron el 80% de las horas perdidas, con máximos de 15, 17 y 18
    horas. No es que el diagnóstico tarde —la mediana es de 8 minutos—: es que
    después de resolverlo hay que estar para volver a encenderla.

    Es un hecho para decidir, no para arreglar solo.
    """
    tareas = ("ERETZ_cola_w0", "ERETZ_cola_w1", "ERETZ_cola_certificacion")
    guion = (
        "$r=@(); foreach($n in @('" + "','".join(tareas) + "')){"
        " try{ $t=Get-ScheduledTask -TaskName $n -ErrorAction Stop;"
        " $i=Get-ScheduledTaskInfo -TaskName $n;"
        " $r+=[pscustomobject]@{nombre=$n; disparadores=@($t.Triggers).Count;"
        " ultima=[string]$i.LastRunTime; resultado=$i.LastTaskResult;"
        " proxima=[string]$i.NextRunTime} }catch{"
        " $r+=[pscustomobject]@{nombre=$n; disparadores=-1} } };"
        " $r | ConvertTo-Json -Compress")
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", guion],
            capture_output=True, text=True, timeout=30)
        filas = json.loads(salida.stdout or "[]")
    except Exception as e:  # noqa: BLE001 - saber esto no puede tumbar el reporte
        return {"estado": "NO_SE_PUDO_COMPROBAR",
                "detalle": f"{type(e).__name__}: {e}"}
    if isinstance(filas, dict):
        filas = [filas]

    # Lo que decide NO es si la tarea tiene disparador: las tres lo tienen.
    # Decide si hay una PROXIMA EJECUCION. `ERETZ_cola_w0` y `w1` tienen
    # disparador y `NextRunTime` vacio -no vuelve a correr nunca-, y
    # `ERETZ_cola_certificacion` lo tiene para septiembre de 2027.
    #
    # La primera version de esta funcion miraba la cantidad de disparadores y
    # concluia "OK". Estaba mirando el campo equivocado y por eso daba verde
    # sobre un sistema que no se reinicia solo.
    def _programada(fila: dict[str, Any]) -> bool:
        proxima = str(fila.get("proxima") or "").strip()
        if not proxima:
            return False
        # Una proxima ejecucion a mas de un mes no es un reinicio: es un
        # disparador olvidado.
        for formato in ("%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                cuando = time.mktime(time.strptime(proxima, formato))
            except ValueError:
                continue
            return (cuando - time.time()) < 30 * 24 * 3600
        return False

    sin_programar = [f for f in filas if not _programada(f)]
    ausentes = [f for f in filas if f.get("disparadores") == -1]
    return {
        "estado": ("SIN_REINICIO_AUTOMATICO"
                   if len(sin_programar) >= 2 else "OK"),
        "tareas": filas,
        "sin_proxima_ejecucion": [f["nombre"] for f in sin_programar],
        "ausentes": [f["nombre"] for f in ausentes],
        "que_significa": ("la cola avanza solo mientras alguien la relanza a "
                          "mano: las tareas tienen disparador pero ninguna "
                          "tiene una proxima ejecucion util"),
        "por_que_no_se_arregla_aca": ("ponerle un disparador reiniciaria la "
                                      "cola despues de CUALQUIER parada, "
                                      "incluida una no diagnosticada, y eso "
                                      "esta prohibido: un STOP nuevo se avisa, "
                                      "no se reinicia. Es una decision, no un "
                                      "arreglo"),
    }


def integridad(certificacion: Path) -> dict[str, Any]:
    """Dos defectos que ya sabemos que existen y que nadie vería si no se miran.

    Los dos comparten forma: son **silenciosos**. No detienen la cola, no
    ensucian un log y no bajan ningún número visible. Aparecen sólo si se los
    busca, y por eso entran al reporte en vez de quedar en un artefacto que hay
    que acordarse de abrir.

    El primero: agencias donde el id estable colapsa. `baron inmobiliaria`
    tiene el id `300` en 36 propiedades distintas —el extractor lo sacó del
    número de calle del slug— y el campo `identity_collisions` del mismo
    registro declara 0.

    El segundo: agencias terminales buenas con la calidad degradada. Hoy se
    publican como si estuvieran enteras, que es lo que el §32 pide dejar de
    hacer.
    """
    resumen: dict[str, Any] = {}

    colisiones = _json(certificacion / "ERETZ_COLISION_DE_IDS.json")
    if colisiones:
        resumen["ids_estables_colapsados"] = {
            "agencias": colisiones.get("agencias_con_ids_colapsados"),
            "de_esas_certified_complete":
                colisiones.get("de_esas_certified_complete"),
            "de_esas_con_identity_collisions_cero":
                colisiones.get("de_esas_con_identity_collisions_cero"),
            "nota": "el inventario NO esta afectado -enumerated cuenta urls-; "
                    "lo que esta roto es la señal",
        }

    gates = _jsonl(certificacion / "ERETZ_GATES_INDEPENDIENTES.jsonl")
    if gates:
        desacuerdos = [g for g in gates if g.get("shadow_disagreement")]
        resumen["calidad_degradada_en_terminales_buenas"] = {
            "agencias": len(desacuerdos),
            "de": len(gates),
            "modo": "SHADOW: la regla observa y no decide",
            "nota": "falsos positivos SIN medir: hay verdad de campo sobre una "
                    "sola agencia",
        }
    return resumen


def alertas(cola: dict[str, Any], datos: dict[str, Any]) -> list[dict[str, str]]:
    """Solo lo que pide una accion humana."""
    fuera: list[dict[str, str]] = []
    if cola.get("paro_pedido"):
        fuera.append({"nivel": "ALTA",
                      "que": "la cola esta parada por un defecto transversal",
                      "detalle": json.dumps(cola["paro_pedido"], ensure_ascii=False),
                      "accion": "diagnosticar contra la fuente real y arreglar "
                                "antes de reabrir"})
    if cola.get("lineas_ilegibles"):
        fuera.append({"nivel": "ALTA",
                      "que": f"{cola['lineas_ilegibles']} lineas ilegibles en "
                             f"los resultados de certificacion",
                      "accion": "revisar si hubo dos procesos escribiendo el "
                                "mismo artefacto"})
    if datos.get("perdidas_por_incompletitud"):
        fuera.append({"nivel": "ALTA",
                      "que": f"{datos['perdidas_por_incompletitud']} propiedades "
                             f"reales quedaron fuera por incompletitud",
                      "accion": "es la regla que no se negocia: revisar el "
                                "quality gate"})
    if cola.get("cerrojos_huerfanos"):
        fuera.append({"nivel": "MEDIA",
                      "que": f"cerrojo sin proceso vivo: "
                             f"{', '.join(cola['cerrojos_huerfanos'])}",
                      "accion": "el pid ya se comprobo muerto: se puede "
                                "liberar el cerrojo"})
    vig = datos.get("_vigilante") or {}
    if vig.get("estado") not in (None, "OK"):
        fuera.append({"nivel": "ALTA",
                      "que": f"el vigilante de paros no esta sano: "
                             f"{vig.get('estado')}",
                      "detalle": vig.get("detalle") or "",
                      "accion": "sin vigilante sano, un paro puede dormir "
                                "horas. Mirar vigilante.log y LastTaskResult"})
    if vig.get("error_al_avisar"):
        fuera.append({"nivel": "MEDIA",
                      "que": "el vigilante detecto pero NO pudo avisar",
                      "detalle": str(vig.get("error_al_avisar")),
                      "accion": "el estado igual quedo escrito; revisar el "
                                "canal de notificacion"})
    if not cola.get("en_curso") and not cola.get("paro_pedido"):
        fuera.append({"nivel": "MEDIA",
                      "que": "no hay ningun runner en curso",
                      "accion": "correr el preflight y reabrir si esta limpio"})
    fallidos = datos.get("extraccion_fallida_por_campo") or {}
    if fallidos:
        campo, cuantas = next(iter(fallidos.items()))
        if cuantas >= 1000:
            fuera.append({"nivel": "MEDIA",
                          "que": f"`{campo}` falla en {cuantas} propiedades que "
                                 f"la fuente si publica",
                          "accion": "agrupar por connector y atacar el patron"})
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--certificacion",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    ap.add_argument("--gate",
                    default=r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                            r"\PROPERTY_QUALITY_GATE_SUMMARY.json")
    ap.add_argument("--cobertura",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT_SUMMARY.json")
    ap.add_argument("--datos",
                    default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_OPERACION")
    args = ap.parse_args()

    cola = estado_de_la_cola(Path(args.certificacion))
    datos = estado_de_los_datos(Path(args.gate), Path(args.cobertura))
    vigilante = salud_del_vigilante(Path(args.certificacion))
    rend = rendimiento(Path(args.certificacion))
    datos["_vigilante"] = vigilante
    reporte = {
        "reporte_version": REPORTE_VERSION,
        "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cola": cola,
        "datos": {k: v for k, v in datos.items() if k != "_vigilante"},
        "vigilante": vigilante,
        "rendimiento": rend,
        "eta_agregada": {**eta(cola, rend),
                         "advertencia": "mezcla poblaciones que esperan "
                                        "procesos distintos; usar "
                                        "`eta_por_poblacion` (§70)"},
        "eta_por_poblacion": eta_por_poblacion(
            Path(args.certificacion), Path(args.datos), rend),
        "integridad": integridad(Path(args.certificacion)),
        "capacidad_de_reinicio": capacidad_de_reinicio(),
        "alertas": alertas(cola, datos),
        "database_writes": 0,
    }
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "ERETZ_OPERACION.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(reporte, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

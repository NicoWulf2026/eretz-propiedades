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
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPORTE_VERSION = "operacion_reporte_v1"

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
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_OPERACION")
    args = ap.parse_args()

    cola = estado_de_la_cola(Path(args.certificacion))
    datos = estado_de_los_datos(Path(args.gate), Path(args.cobertura))
    reporte = {
        "reporte_version": REPORTE_VERSION,
        "generado_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cola": cola,
        "datos": datos,
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

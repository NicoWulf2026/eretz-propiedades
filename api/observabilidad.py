"""Observabilidad minima de la API para la beta (P16/P21): un evento por pedido.

Mismo formato que el frontend (`frontend/src/lib/observability/route.ts`,
`event: "http_request"`), para que los dos lados se lean con la misma consulta:
una linea JSON por pedido en stdout, que es lo que recoge cualquier plataforma
de contenedores.

Privacidad: del pedido se registran SOLO las claves de los parametros, nunca los
valores. Lo que alguien busca («casa en Palermo con pileta») no es un dato
operativo y no se guarda.

Ademas:
- `x-request-id`: el que manda el cliente si tiene forma razonable, o uno nuevo.
  Viaja en la respuesta para cruzar un error del navegador con su linea de log.
- Encabezados de seguridad: `nosniff`, `noindex` (la API no se indexa nunca:
  P23), `no-referrer`.
- Una excepcion no atrapada responde 500 con el request id, sin detalle interno.
"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

ID_VALIDO = re.compile(r"[A-Za-z0-9_-]{8,64}")
MENSAJE_500 = "error interno de la API"
ENCABEZADOS = {
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, nofollow",
    "referrer-policy": "no-referrer",
}


def _desenlace(status: int) -> str:
    if status >= 500:
        return "server_error"
    if status >= 400:
        return "client_error"
    return "ok"


def _emitir(evento: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(evento, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


async def registrar_pedido(request: Request, call_next: Callable) -> Response:
    entrante = request.headers.get("x-request-id") or ""
    request_id = entrante if ID_VALIDO.fullmatch(entrante) else str(uuid.uuid4())
    inicio = time.perf_counter()
    error = None
    try:
        respuesta = await call_next(request)
    except Exception as exc:  # el cliente recibe un 500 limpio; el log dice que fue
        error = type(exc).__name__
        respuesta = JSONResponse({"error": MENSAJE_500, "requestId": request_id}, status_code=500)
    ruta = getattr(request.scope.get("route"), "path", None) or "sin_ruta"
    claves = sorted(set(request.query_params.keys()))
    status = respuesta.status_code
    desenlace = _desenlace(status)
    _emitir({
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": "error" if desenlace == "server_error" else "warn" if desenlace == "client_error" else "info",
        "event": "http_request", "service": "eretz-api",
        "requestId": request_id, "route": ruta, "method": request.method,
        "status": status, "outcome": desenlace,
        "durationMs": round((time.perf_counter() - inicio) * 1000, 1),
        "paramCount": len(claves), "paramKeys": claves,
        **({"errorName": error} if error else {}),
    })
    respuesta.headers["x-request-id"] = request_id
    for clave, valor in ENCABEZADOS.items():
        respuesta.headers.setdefault(clave, valor)
    return respuesta

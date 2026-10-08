#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Almacen de paginas: cada ficha y cada listado que la cola baja queda guardado, crudo y fechado.

Mision 08-10 (`docs/agent/MISION_PADRON_COMPLETO.md`, puntos 4 y 6). Medido: 286 horas-worker en octubre
para 1.372 certificaciones y ~2/3 de la capacidad se va en recertificar porque cambiar un extractor obliga
a volver a BAJAR todo. Con las paginas guardadas, un extractor nuevo se prueba y se aplica re-extrayendo
desde aca (replay), y la red queda para lo que de verdad cambio.

Diseno:
- direccionado por contenido: `blobs/<aa>/<sha256>.html.gz`; la misma pagina bajada dos veces ocupa una;
- un indice JSONL por worker y por dia (`indice/AAAA-MM-DD.<worker>.jsonl`): dos procesos nunca escriben el
  mismo archivo (las escrituras concurrentes ya rompieron `MASTER_PROGRESS.jsonl`);
- escritura atomica del blob (tmp + os.replace); el indice se escribe con una linea por llamada;
- NUNCA rompe a quien lo usa: cualquier error se cuenta y se traga. Guardar es un efecto lateral.

No cambia la semantica de extraccion ni la huella: se engancha desde el runner (`enganchar`), no desde el
certificador.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

VERSION = "almacen_de_paginas_v1"


class AlmacenDePaginas:
    def __init__(self, raiz: Path, worker: str = "w0") -> None:
        self.raiz = Path(raiz)
        self.worker = worker
        self.contexto: dict[str, Any] = {}
        self.guardadas = 0
        self.repetidas = 0
        self.errores = 0
        self._lock = threading.Lock()

    def _ruta_blob(self, sha: str) -> Path:
        return self.raiz / "blobs" / sha[:2] / f"{sha}.html.gz"

    def guardar(self, url: str, cuerpo: str) -> str | None:
        """Guarda la pagina y anota la descarga. Devuelve el sha256 o None si algo fallo."""
        try:
            datos = (cuerpo or "").encode("utf-8", "ignore")
            sha = hashlib.sha256(datos).hexdigest()
            blob = self._ruta_blob(sha)
            if blob.exists():
                with self._lock:
                    self.repetidas += 1
            else:
                blob.parent.mkdir(parents=True, exist_ok=True)
                tmp = blob.with_name(f"{blob.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                with gzip.open(tmp, "wb", compresslevel=6) as fh:
                    fh.write(datos)
                os.replace(tmp, blob)
                with self._lock:
                    self.guardadas += 1
            fila = {"url": url, "sha256": sha, "bytes": len(datos),
                    "bajada_en": time.strftime("%Y-%m-%dT%H:%M:%S"), "worker": self.worker,
                    **self.contexto}
            indice = self.raiz / "indice" / f"{time.strftime('%Y-%m-%d')}.{self.worker}.jsonl"
            indice.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, indice.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            return sha
        except Exception:  # noqa: BLE001 - guardar nunca puede romper una certificacion
            with self._lock:
                self.errores += 1
            return None

    def leer(self, sha: str) -> str | None:
        blob = self._ruta_blob(sha)
        if not blob.exists():
            return None
        with gzip.open(blob, "rb") as fh:
            return fh.read().decode("utf-8", "ignore")


def envolver(bajar: Callable[..., str], almacen: AlmacenDePaginas) -> Callable[..., str]:
    """Un `bajar` que ademas guarda lo bajado. Errores de red se propagan igual que antes."""
    def bajar_y_guardar(self, url: str, *args: Any, **kwargs: Any) -> str:
        cuerpo = bajar(self, url, *args, **kwargs)
        almacen.guardar(url, cuerpo)
        return cuerpo
    bajar_y_guardar.__wrapped__ = bajar  # type: ignore[attr-defined]
    return bajar_y_guardar


def enganchar(clase: type, almacen: AlmacenDePaginas) -> None:
    """Engancha el almacen al `bajar` de una clase de descargador (idempotente)."""
    actual = clase.bajar
    if getattr(actual, "__wrapped__", None) is not None:
        return
    clase.bajar = envolver(actual, almacen)

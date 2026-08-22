#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Proveedores de busqueda adicionales: Exa y Jina.

Viven aparte de `search_provider.py` solo por tamano; implementan la misma
interfaz `Proveedor` y el runner los usa sin distinguirlos. No hay pipeline
paralelo: es la misma cadena con dos motores mas.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "search_provider", ROOT / "scripts" / "search_provider.py")
sp = importlib.util.module_from_spec(_spec)
sys.modules["search_provider"] = sp
_spec.loader.exec_module(sp)

Proveedor = sp.Proveedor
Resultado = sp.Resultado
ConsultaInvalida = sp.ConsultaInvalida
ProveedorAgotado = sp.ProveedorAgotado
redactar = sp.redactar


class Exa(Proveedor):
    """Exa Search normal. Solo `search`: nada de deep search, agent ni contents.

    La respuesta trae `costDollars`, asi que el gasto se mide y no se estima.
    El corte es por cantidad de requests Y por presupuesto: lo que llegue
    primero. Un tope que solo cuenta requests no protege de una consulta cara.
    """
    nombre = "exa"
    ENDPOINT = "https://api.exa.ai/search"
    ENV = "EXA_API_KEY"

    def __init__(self, pausa: float = 0.3, reintentos: int = 3, tope: int = 2700,
                 presupuesto_usd: float = 18.90):
        self.pausa = pausa
        self.reintentos = reintentos
        self.tope = tope
        self.presupuesto_usd = presupuesto_usd
        self.emitidas = 0
        self.gasto_usd = 0.0
        self.sin_creditos = False
        self._ultimo = 0.0

    def _key(self) -> str:
        return (os.environ.get(self.ENV) or "").strip()

    def disponible(self) -> bool:
        return bool(self._key())

    @property
    def agotado(self) -> bool:
        return (self.sin_creditos or self.emitidas >= self.tope
                or self.gasto_usd >= self.presupuesto_usd)

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 8) -> list:
        key = self._key()
        if not key:
            raise RuntimeError("EXA_API_KEY ausente")
        if self.agotado:
            raise ProveedorAgotado("exa: tope o presupuesto alcanzado")

        espera = self.pausa - (time.time() - self._ultimo)
        if espera > 0:
            time.sleep(espera)

        cuerpo = json.dumps({"query": consulta,
                             "numResults": max(1, min(cantidad, 10)),
                             "type": "auto"}).encode("utf-8")
        req = urllib.request.Request(
            self.ENDPOINT, data=cuerpo, method="POST",
            headers={"Content-Type": "application/json", "x-api-key": key})

        demora = 2.0
        datos = None
        for intento in range(1, self.reintentos + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self._ultimo = time.time()
                    self.emitidas += 1
                    datos = json.loads(r.read().decode("utf-8", "ignore"))
                break
            except urllib.error.HTTPError as e:
                self._ultimo = time.time()
                if e.code in (401, 402, 403, 429):
                    self.sin_creditos = True
                    raise ProveedorAgotado(
                        redactar("exa sin creditos HTTP " + str(e.code), key)) from None
                if e.code in (400, 413, 422):
                    raise ConsultaInvalida(
                        redactar("exa rechazo la consulta HTTP " + str(e.code), key)) from None
                if e.code >= 500 and intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar("exa HTTP " + str(e.code), key)) from None
            except Exception as e:
                self._ultimo = time.time()
                if intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar("exa: " + type(e).__name__, key)) from None
        if datos is None:
            raise RuntimeError("exa: sin respuesta tras reintentos")

        costo = (datos.get("costDollars") or {}).get("total")
        if isinstance(costo, (int, float)):
            self.gasto_usd += float(costo)

        ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
        salida = []
        for i, r in enumerate(datos.get("results") or [], 1):
            salida.append(Resultado(
                url=r.get("url") or "", titulo=r.get("title") or "",
                resumen=(r.get("text") or r.get("summary") or "")[:400],
                rank=i, provider=self.nombre, fetched_at=ahora))
        return salida


class Jina(Proveedor):
    """Busqueda web de Jina (s.jina.ai).

    Este endpoint descuenta tokens del saldo de la API key, igual que Reader.
    NO es un endpoint gratuito: es saldo gratuito de alta. Por eso el runner
    exige una consulta de prueba y la lectura del consumo antes del lote.

    Se pide `no-content` a proposito: bajar el texto completo de cada pagina
    multiplicaria los tokens sin aportar nada, porque el verificador baja la
    pagina por su cuenta igual.
    """
    nombre = "jina"
    ENDPOINT = "https://s.jina.ai/"
    ENV = "JINA_API_KEY"

    def __init__(self, pausa: float = 1.2, reintentos: int = 3, tope: int = 2000):
        self.pausa = pausa
        self.reintentos = reintentos
        self.tope = tope
        self.emitidas = 0
        self.tokens_consumidos = 0
        self.sin_creditos = False
        self._ultimo = 0.0

    def _key(self) -> str:
        return (os.environ.get(self.ENV) or "").strip()

    def disponible(self) -> bool:
        return bool(self._key())

    @property
    def agotado(self) -> bool:
        return self.sin_creditos or self.emitidas >= self.tope

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 8) -> list:
        key = self._key()
        if not key:
            raise RuntimeError("JINA_API_KEY ausente")
        if self.agotado:
            raise ProveedorAgotado("jina: tope alcanzado")

        espera = self.pausa - (time.time() - self._ultimo)
        if espera > 0:
            time.sleep(espera)

        url = self.ENDPOINT + "?" + urllib.parse.urlencode({"q": consulta})
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "X-Respond-With": "no-content",
            "X-Locale": idioma + "-" + pais,
        })

        demora = 2.0
        datos = None
        cabeceras = {}
        for intento in range(1, self.reintentos + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self._ultimo = time.time()
                    self.emitidas += 1
                    cabeceras = {k.lower(): v for k, v in dict(r.headers).items()}
                    datos = json.loads(r.read().decode("utf-8", "ignore"))
                break
            except urllib.error.HTTPError as e:
                self._ultimo = time.time()
                if e.code in (401, 402, 403, 429):
                    self.sin_creditos = True
                    raise ProveedorAgotado(
                        redactar("jina sin saldo HTTP " + str(e.code), key)) from None
                if e.code in (400, 413, 422):
                    raise ConsultaInvalida(
                        redactar("jina rechazo la consulta HTTP " + str(e.code), key)) from None
                if e.code >= 500 and intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar("jina HTTP " + str(e.code), key)) from None
            except Exception as e:
                self._ultimo = time.time()
                if intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar("jina: " + type(e).__name__, key)) from None
        if datos is None:
            raise RuntimeError("jina: sin respuesta tras reintentos")

        for h in ("x-tokens-used", "x-total-tokens", "x-token-usage"):
            if h in cabeceras:
                try:
                    self.tokens_consumidos += int(cabeceras[h])
                except (TypeError, ValueError):
                    pass
                break

        ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
        crudos = datos.get("data") if isinstance(datos, dict) else datos
        salida = []
        for i, r in enumerate(crudos or [], 1):
            if not isinstance(r, dict):
                continue
            salida.append(Resultado(
                url=r.get("url") or "", titulo=r.get("title") or "",
                resumen=(r.get("description") or r.get("content") or "")[:400],
                rank=i, provider=self.nombre, fetched_at=ahora))
        return salida

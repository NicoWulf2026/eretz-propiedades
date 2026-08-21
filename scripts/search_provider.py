#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Capa de busqueda web programatica, con proveedor intercambiable.

El metodo de dominios derivados del nombre encuentra `vanzini.com.ar` a partir
de "Vanzini Propiedades", pero no encuentra nada para "Inmobiliaria Lopez" si su
sitio se llama distinto. Para esas hace falta buscar de verdad.

El verificador de identidad ya existe y no se toca: esta capa solo consigue
candidatas mejores para alimentarlo. Por eso el proveedor esta detras de una
interfaz -hoy Brave, manana Serper o Google CSE- y cambiarlo no obliga a
reescribir la parte que decide.

Sobre la API key: se lee del entorno, nunca se escribe en disco, nunca se
imprime y nunca sale en un mensaje de error. `redactar()` existe para que un
traceback inesperado tampoco la filtre.

Sin key el pipeline NO se detiene: las entidades que necesitan busqueda quedan
en SEARCH_API_PENDING, que es un estado operativo. NOT_FOUND significa "se
busco y no hay", y usarlo por falta de credencial seria mentir en el artefacto.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

PENDING = "SEARCH_API_PENDING"
ERROR = "SEARCH_API_ERROR"


class ConsultaInvalida(RuntimeError):
    """El proveedor rechazo ESTA consulta. No dice nada del resto del lote.

    Existe para separar dos cosas que no son lo mismo: una consulta que el
    proveedor no acepta, y un proveedor que dejo de atender. Confundirlas hizo
    que un unico HTTP 400 cerrara una corrida con 5.500 entidades por delante.
    """


class ProveedorAgotado(RuntimeError):
    """Sin creditos o limitado. Aca si corresponde cerrar el lote."""


@dataclass
class Resultado:
    """Solo lo necesario para rankear y despues verificar. La pagina completa se
    baja despues, y solo para las candidatas que valen la pena."""
    url: str
    titulo: str = ""
    resumen: str = ""
    rank: int = 0
    provider: str = ""
    fetched_at: str = ""


def redactar(texto: str, *secretos: str) -> str:
    """Saca cualquier secreto de un texto antes de que se muestre o se guarde."""
    out = texto or ""
    for s in secretos:
        if s and len(s) >= 8:
            out = out.replace(s, "<redacted>")
    # Por si el proveedor devuelve la key en un eco del request.
    for patron in ("X-Subscription-Token", "api_key", "apiKey", "token="):
        idx = out.find(patron)
        if idx >= 0:
            out = out[:idx + len(patron)] + " <redacted>"
    return out


class Proveedor:
    """Interfaz. Cambiar de buscador no debe tocar al verificador."""

    nombre = "base"

    def disponible(self) -> bool:
        raise NotImplementedError

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 10) -> list[Resultado]:
        raise NotImplementedError


class Brave(Proveedor):
    nombre = "brave"
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    ENV = "BRAVE_SEARCH_API_KEY"

    def __init__(self, pausa: float = 1.1, reintentos: int = 3):
        # Brave limita por segundo en los planes bajos; una pausa por defecto
        # mayor a un segundo evita pelear con el 429 en vez de esperarlo.
        self.pausa = pausa
        self.reintentos = reintentos
        self._ultimo = 0.0

    def _key(self) -> str:
        return (os.environ.get(self.ENV) or "").strip()

    def disponible(self) -> bool:
        return bool(self._key())

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 10) -> list[Resultado]:
        key = self._key()
        if not key:
            raise RuntimeError(f"{self.ENV} ausente")

        espera = self.pausa - (time.time() - self._ultimo)
        if espera > 0:
            time.sleep(espera)

        params = urllib.parse.urlencode({
            "q": consulta, "country": pais, "search_lang": idioma,
            "count": max(1, min(cantidad, 20)), "safesearch": "off",
        })
        req = urllib.request.Request(
            f"{self.ENDPOINT}?{params}",
            headers={"Accept": "application/json", "X-Subscription-Token": key})

        demora = 2.0
        for intento in range(1, self.reintentos + 1):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    self._ultimo = time.time()
                    datos = json.loads(r.read().decode("utf-8", "ignore"))
                break
            except urllib.error.HTTPError as e:
                self._ultimo = time.time()
                # 429 y 5xx son transitorios: se espera y se reintenta. Un 401
                # o un 403 son de credencial y reintentar no los arregla.
                if e.code in (429, 500, 502, 503, 504) and intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar(f"brave HTTP {e.code}", key)) from None
            except Exception as e:
                self._ultimo = time.time()
                if intento < self.reintentos:
                    time.sleep(demora)
                    demora *= 2
                    continue
                raise RuntimeError(redactar(f"brave: {type(e).__name__}", key)) from None
        else:
            raise RuntimeError("brave: sin respuesta tras reintentos")

        ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
        out = []
        for i, r in enumerate((datos.get("web") or {}).get("results") or [], 1):
            out.append(Resultado(url=r.get("url") or "", titulo=r.get("title") or "",
                                 resumen=r.get("description") or "", rank=i,
                                 provider=self.nombre, fetched_at=ahora))
        return out


class Tavily(Proveedor):
    """Tavily, en modo basic. Una consulta = un credito.

    Se usa con tope duro de consumo: la corrida se detiene sola antes de agotar
    el saldo gratuito, y nunca habilita facturacion. Un limite que depende de que
    alguien mire el contador no es un limite.
    """
    nombre = "tavily"
    ENDPOINT = "https://api.tavily.com/search"
    ENV = "TAVILY_API_KEY"

    def __init__(self, pausa: float = 0.6, reintentos: int = 3, tope: int = 1450):
        self.pausa = pausa
        self.reintentos = reintentos
        self.tope = tope
        self.emitidas = 0
        # Bandera separada del contador: marcarse agotado subiendo `emitidas`
        # al tope falsea el numero de consultas realmente emitidas, que es
        # justo el dato que hay que reportar con exactitud.
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
               cantidad: int = 8) -> list[Resultado]:
        key = self._key()
        if not key:
            raise RuntimeError(f"{self.ENV} ausente")
        if self.agotado:
            raise RuntimeError(f"tope de {self.tope} consultas alcanzado")

        espera = self.pausa - (time.time() - self._ultimo)
        if espera > 0:
            time.sleep(espera)

        cuerpo = json.dumps({
            "query": consulta, "search_depth": "basic",
            "max_results": max(1, min(cantidad, 10)),
            "include_answer": False, "include_raw_content": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.ENDPOINT, data=cuerpo, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})

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
                # 432/433 son "sin creditos" en Tavily: no se reintenta, se corta.
                if e.code in (400, 413, 422):
                    raise ConsultaInvalida(redactar(f"tavily rechazo la consulta (HTTP {e.code})", key)) from None
                if e.code in (402, 429, 432, 433):
                    self.sin_creditos = True
                    raise ProveedorAgotado(redactar(f"tavily sin creditos o limitado (HTTP {e.code})", key)) from None
                if e.code >= 500 and intento < self.reintentos:
                    time.sleep(demora); demora *= 2
                    continue
                raise RuntimeError(redactar(f"tavily HTTP {e.code}", key)) from None
            except Exception as e:
                self._ultimo = time.time()
                if intento < self.reintentos:
                    time.sleep(demora); demora *= 2
                    continue
                raise RuntimeError(redactar(f"tavily: {type(e).__name__}", key)) from None
        if datos is None:
            raise RuntimeError("tavily: sin respuesta tras reintentos")

        ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
        return [Resultado(url=r.get("url") or "", titulo=r.get("title") or "",
                          resumen=r.get("content") or "", rank=i,
                          provider=self.nombre, fetched_at=ahora)
                for i, r in enumerate(datos.get("results") or [], 1)]


class Serper(Proveedor):
    """Serper, sobre resultados de Google. Una consulta = un credito.

    A diferencia de Tavily, cada respuesta trae el saldo restante en el campo
    `credits`, asi que el tope no depende solo de nuestro contador: si la cuenta
    informa menos de lo que creiamos, el limite se ajusta solo hacia abajo.
    """
    nombre = "serper"
    ENDPOINT = "https://google.serper.dev/search"
    ENV = "SERPER_API_KEY"

    def __init__(self, pausa: float = 0.35, reintentos: int = 3, tope: int = 2400):
        self.pausa = pausa
        self.reintentos = reintentos
        self.tope = tope
        self.emitidas = 0
        self.sin_creditos = False
        self.creditos_consumidos = 0
        self._ultimo = 0.0

    def _key(self) -> str:
        return (os.environ.get(self.ENV) or "").strip()

    def disponible(self) -> bool:
        return bool(self._key())

    @property
    def agotado(self) -> bool:
        return self.sin_creditos or self.emitidas >= self.tope

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 10) -> list[Resultado]:
        key = self._key()
        if not key:
            raise RuntimeError(f"{self.ENV} ausente")
        if self.agotado:
            raise RuntimeError(f"tope de {self.tope} consultas alcanzado")

        espera = self.pausa - (time.time() - self._ultimo)
        if espera > 0:
            time.sleep(espera)

        cuerpo = json.dumps({"q": consulta, "gl": pais.lower(), "hl": idioma,
                             "num": max(1, min(cantidad, 10))}).encode("utf-8")
        req = urllib.request.Request(
            self.ENDPOINT, data=cuerpo, method="POST",
            headers={"Content-Type": "application/json", "X-API-KEY": key})

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
                # 402/429 en Serper: cuota agotada o limitada. No se reintenta.
                if e.code in (401, 402, 403, 429):
                    self.sin_creditos = True
                    raise ProveedorAgotado(redactar(f"serper sin creditos o limitado (HTTP {e.code})", key)) from None
                if e.code in (400, 413, 422):
                    raise ConsultaInvalida(redactar(f"serper rechazo la consulta (HTTP {e.code})", key)) from None
                if e.code >= 500 and intento < self.reintentos:
                    time.sleep(demora); demora *= 2
                    continue
                raise RuntimeError(redactar(f"serper HTTP {e.code}", key)) from None
            except Exception as e:
                self._ultimo = time.time()
                if intento < self.reintentos:
                    time.sleep(demora); demora *= 2
                    continue
                raise RuntimeError(redactar(f"serper: {type(e).__name__}", key)) from None
        if datos is None:
            raise RuntimeError("serper: sin respuesta tras reintentos")

        # `credits` en la respuesta es lo que COSTO esta consulta, no el saldo
        # que queda. Leerlo como saldo mata el lote en la primera consulta, que
        # es exactamente lo que paso: devolvio 1 y el runner se dio por agotado.
        # El saldo no viaja en la respuesta de busqueda; el agotamiento se
        # detecta por HTTP 402/429 y por el tope duro.
        cred = datos.get("credits")
        if isinstance(cred, int):
            self.creditos_consumidos += cred

        ahora = time.strftime("%Y-%m-%dT%H:%M:%S")
        return [Resultado(url=r.get("link") or "", titulo=r.get("title") or "",
                          resumen=r.get("snippet") or "", rank=r.get("position") or i,
                          provider=self.nombre, fetched_at=ahora)
                for i, r in enumerate(datos.get("organic") or [], 1)]


def normalizar_consulta(consulta: str) -> str:
    """Clave de cache. Dos consultas que solo difieren en espacios o
    mayusculas no deberian pagarse dos veces."""
    return " ".join((consulta or "").lower().split())


@dataclass
class ConCache(Proveedor):
    """Envuelve un proveedor y no vuelve a pagar una consulta ya hecha.

    Importa para poder reanudar: una corrida interrumpida a mitad de camino no
    debe volver a gastar las consultas que ya resolvio.
    """
    interno: Proveedor
    ruta: Path
    cache: dict = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def __post_init__(self):
        self.nombre = self.interno.nombre
        if self.ruta.exists():
            for linea in self.ruta.open(encoding="utf-8"):
                if linea.strip():
                    reg = json.loads(linea)
                    self.cache[reg["clave"]] = reg["resultados"]

    def disponible(self) -> bool:
        return self.interno.disponible()

    def buscar(self, consulta: str, pais: str = "AR", idioma: str = "es",
               cantidad: int = 10) -> list[Resultado]:
        clave = f"{self.interno.nombre}|{normalizar_consulta(consulta)}"
        if clave in self.cache:
            self.hits += 1
            return [Resultado(**r) for r in self.cache[clave]]
        self.misses += 1
        res = self.interno.buscar(consulta, pais, idioma, cantidad)
        self.cache[clave] = [r.__dict__ for r in res]
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"clave": clave, "consulta": consulta,
                                 "resultados": self.cache[clave]},
                                ensure_ascii=False) + "\n")
        return res


def consultas_para(entidad: dict) -> list[str]:
    """Consultas progresivas, de la mas especifica a la mas amplia.

    Se emiten de a una y se corta apenas hay evidencia suficiente: cada consulta
    cuesta, y la primera resuelve la mayoria.
    """
    nombre = (entidad.get("nombre_original") or "").strip()
    if not nombre:
        return []
    zonas = entidad.get("zonas_observadas") or []
    zona = zonas[0].replace("-", " ") if zonas else ""
    red = entidad.get("red_franquicia")
    mats = entidad.get("matricula") or []

    out = []
    if red:
        # Para una oficina, el perfil dentro del dominio de la red suele ser la
        # respuesta correcta, y acotar el sitio evita traer las otras 190.
        out.append(f'"{nombre}" inmobiliaria')
        dominio = {"RE/MAX": "remax.com.ar", "Century 21": "century21.com.ar",
                   "Coldwell Banker": "coldwellbanker.com.ar",
                   "Keller Williams": "kwargentina.com"}.get(red)
        if dominio:
            out.append(f'"{nombre}" site:{dominio}')
    else:
        out.append(f'"{nombre}" {zona}'.strip() if zona else f'"{nombre}" inmobiliaria')
        out.append(f'"{nombre}" inmobiliaria {zona}'.strip())
    if mats:
        out.append(f'"{nombre}" {mats[0]}')
    # Sin duplicados y sin consultas vacias.
    vistas, limpio = set(), []
    for c in out:
        c = " ".join(c.split())
        if c and c not in vistas:
            vistas.add(c)
            limpio.append(c)
    return limpio[:3]

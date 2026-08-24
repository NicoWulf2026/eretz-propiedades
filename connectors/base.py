#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Arquitectura comun de connectors de ingesta directa.

Un connector traduce UNA fuente -la web oficial de una inmobiliaria- a la misma
representacion normalizada que el resto del pipeline ya entiende. El pipeline no
sabe que existe Tokko: Tokko es la implementacion numero uno, no el modelo.

Tres decisiones que valen mas que el codigo:

  - La identidad de una propiedad NO se inventa aca. Se reusa `hash_dedup` del
    pipeline existente, que es SHA256 de "{inmobiliaria_id}|url|{url_norm}".
    Esta acotado por inmobiliaria, asi que dos agencias no pueden colisionar por
    construccion, y una segunda corrida produce exactamente el mismo hash.
  - Un campo ausente es None, nunca un valor inferido. Una superficie inventada
    contamina el dataset de una forma que no se detecta despues.
  - Una propiedad que hoy no aparece NO es una baja. Puede ser un timeout, un
    502 o un sitio caido. La baja necesita varias corridas coincidentes.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import os
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

CONNECTOR_API_VERSION = "connector_v1"

# Claves de `extra` que NO son contenido y por lo tanto no entran en la huella.
# `modificado_en_fuente` es la fecha que declara el propio sitio, y WordPress la
# mueve cuando re-guarda los posts en masa: 1.618 propiedades cambiaron esa
# fecha entre dos corridas -varias con el mismo 04:00:29, o sea un cron- sin que
# cambiara una sola letra del aviso. Con ella adentro, MODIFICADA deja de
# significar "cambio algo" y pasa a significar "el sitio corrio su tarea nocturna".
NO_SON_CONTENIDO = ("raw_html_len", "fetched_at", "modificado_en_fuente")

# --------------------------------------------------------------------------
# Reuso del pipeline existente: la identidad de propiedad y los vocabularios
# validos viven en scraper/models.py y no se duplican aca. Si el algoritmo de
# hash cambia alla, esta capa lo hereda; una copia se desincronizaria en
# silencio y empezaria a crear duplicados.
# --------------------------------------------------------------------------
RUTA_PIPELINE = Path(os.environ.get(
    "ERETZ_PIPELINE_ROOT", r"D:\INMO CAPITAL\Inmo-Capital-main"))


def _cargar_modelos():
    ruta = RUTA_PIPELINE / "scraper" / "models.py"
    if not ruta.exists():
        return None
    spec = importlib.util.spec_from_file_location("eretz_models", ruta)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


_MODELOS = _cargar_modelos()

if _MODELOS is not None:
    normalizar_url = _MODELOS._normalize_url_for_hash
    calcular_hash_dedup = _MODELOS._compute_hash_dedup
    TIPOS_VALIDOS = set(_MODELOS.ALLOWED_PROPERTY_TYPES)
    MONEDAS_VALIDAS = set(_MODELOS.ALLOWED_MONEDAS)
    OPERACIONES_VALIDAS = set(_MODELOS.ALLOWED_OPERACIONES)
    REUSA_PIPELINE = True
else:  # pragma: no cover - solo si el repo del pipeline no esta montado
    REUSA_PIPELINE = False
    TIPOS_VALIDOS = {"casa", "departamento", "terreno", "local", "oficina",
                     "cochera", "galpon", "otro"}
    MONEDAS_VALIDAS = {"ARS", "USD"}
    OPERACIONES_VALIDAS = {"venta", "alquiler", "alquiler_temporario",
                           "consultar", "venta_y_alquiler"}

    def normalizar_url(url: Any) -> str:
        return re.sub(r"^https?://(www\.)?", "", str(url or "").strip().lower()).rstrip("/")

    def calcular_hash_dedup(inmobiliaria_id: Any, url: Any) -> str:
        clave = normalizar_url(url)
        base = f"{inmobiliaria_id}|url|{clave}" if clave else f"{inmobiliaria_id}|sin_identidad|"
        return hashlib.sha256(base.encode()).hexdigest()[:32]


# --------------------------------------------------------------------------
# Representacion normalizada comun
# --------------------------------------------------------------------------
@dataclass
class PropiedadNormalizada:
    """Lo que TODO connector produce, venga de donde venga.

    Los campos que el schema de ERETZ ya tiene como columna van arriba; los que
    la fuente publica y el schema guarda en `datos_extra` van en `extra`. No se
    agregan columnas nuevas: el pipeline actual las ignoraria.
    """
    # --- identidad ---
    canonical_agency_id: str
    source_listing_id: str
    source_url: str
    connector: str
    # --- lo que el schema tiene como columna ---
    titulo: str | None = None
    descripcion: str | None = None
    precio: float | None = None
    moneda: str | None = None
    operacion: str | None = None
    tipo_propiedad: str | None = None
    direccion: str | None = None
    barrio: str | None = None
    ciudad: str | None = None
    provincia: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    dormitorios: int | None = None
    banos: int | None = None
    ambientes: int | None = None
    superficie_total: float | None = None
    superficie_cubierta: float | None = None
    imagenes: list[str] = field(default_factory=list)
    # --- lo que va a datos_extra ---
    extra: dict[str, Any] = field(default_factory=dict)
    # --- procedencia ---
    source_status: str = "activa"
    inmobiliaria_id: int | None = None
    scraped_at: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scraped_at:
            self.scraped_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if self.operacion:
            self.operacion = self.operacion.lower().strip()
        if self.moneda:
            self.moneda = self.moneda.upper().strip()

    @property
    def hash_dedup(self) -> str:
        """Identidad estable. La clave de agencia entra en el hash, asi que dos
        inmobiliarias distintas nunca colisionan aunque compartan la URL."""
        clave = self.inmobiliaria_id if self.inmobiliaria_id is not None \
            else self.canonical_agency_id
        return calcular_hash_dedup(clave, self.source_url)

    @property
    def fingerprint(self) -> str:
        """Huella del CONTENIDO, para detectar cambios sin volver a bajar todo.

        Deja afuera scraped_at a proposito: si entrara, cada corrida veria
        cambios donde no los hubo y el incremental no serviria de nada.

        Por la misma razon el ORDEN no cuenta en la descripcion ni en las
        fotos. Tokko arma la lista de servicios sin orden fijo -"Cloaca
        Internet" en un pedido, "Internet Cloaca" en el siguiente: mismas
        palabras, mismo largo-, y como la descripcion entra en la huella, una
        propiedad sin tocar volvia MODIFICADA. Fue el 2,4% de un canary; a
        escala de 91.715 son ~2.200 cambios falsos por corrida, que dejarian a
        MODIFICADA sin significado.

        Reordenar no es un cambio. Agregar o sacar texto si, y eso se sigue
        detectando porque cambia el conjunto de palabras.
        """
        campos = {k: v for k, v in asdict(self).items()
                  if k not in ("scraped_at", "provenance", "extra")}
        campos["extra"] = {k: v for k, v in self.extra.items()
                           if k not in NO_SON_CONTENIDO}
        if isinstance(campos.get("descripcion"), str):
            campos["descripcion"] = " ".join(sorted(campos["descripcion"].split()))
        if isinstance(campos.get("imagenes"), list):
            campos["imagenes"] = sorted(str(x) for x in campos["imagenes"])
        crudo = json.dumps(campos, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(crudo.encode()).hexdigest()[:32]

    def problemas(self) -> list[str]:
        """Chequeos de coherencia. No corrige nada: informa."""
        p: list[str] = []
        if not self.source_listing_id:
            p.append("sin source_listing_id")
        if not self.source_url or not self.source_url.startswith("http"):
            p.append("source_url invalida")
        if self.moneda and self.moneda not in MONEDAS_VALIDAS:
            p.append(f"moneda fuera de vocabulario: {self.moneda}")
        if self.operacion and self.operacion not in OPERACIONES_VALIDAS:
            p.append(f"operacion fuera de vocabulario: {self.operacion}")
        if self.tipo_propiedad and self.tipo_propiedad not in TIPOS_VALIDOS:
            p.append(f"tipo fuera de vocabulario: {self.tipo_propiedad}")
        if self.precio is not None and self.precio <= 0:
            p.append("precio no positivo")
        if self.precio is not None and not self.moneda:
            p.append("precio sin moneda")
        if self.latitud is not None and not (-56 <= self.latitud <= -21):
            p.append("latitud fuera de Argentina")
        if self.longitud is not None and not (-74 <= self.longitud <= -53):
            p.append("longitud fuera de Argentina")
        return p

    def a_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hash_dedup"] = self.hash_dedup
        d["fingerprint"] = self.fingerprint
        d["problemas"] = self.problemas()
        return d


# --------------------------------------------------------------------------
# Red: limite de ritmo, reintentos y errores distinguibles
# --------------------------------------------------------------------------
class ErrorTransitorio(RuntimeError):
    """Fallo que puede desaparecer solo: timeout, 5xx, corte de red.

    Se separa de la ausencia real porque confundirlos es lo que convierte una
    caida de diez minutos en cientos de propiedades dadas de baja por error.
    """


class ErrorPermanente(RuntimeError):
    """404 o 410: la fuente dice explicitamente que eso ya no esta."""


class Bloqueado(RuntimeError):
    """403 o 429: el sitio nos esta pidiendo que paremos."""


class LimitadorDeRitmo:
    """Un pedido cada `intervalo` segundos por host, compartido entre hilos.

    El objetivo no es maximizar velocidad sino no molestar: son webs chicas de
    inmobiliarias, no infraestructura preparada para que la golpeen.
    """

    def __init__(self, intervalo: float = 1.5):
        self.intervalo = intervalo
        self._ultimo: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._maestro = threading.Lock()

    def _lock_de(self, host: str) -> threading.Lock:
        with self._maestro:
            return self._locks.setdefault(host, threading.Lock())

    def esperar(self, host: str) -> None:
        """Espera lo que le falte a ESTE host, sin frenar a los demas.

        Un lock unico para todos los hosts convertiria el limite de cortesia en
        un limite global: con 8 fuentes en paralelo, cada una esperando el turno
        de las otras, el paralelismo desaparece y el rollout completo pasaria de
        horas a dias. Cortesia por host, concurrencia entre hosts: son cosas
        distintas y no deben compartir cerrojo.
        """
        with self._lock_de(host):
            ahora = time.monotonic()
            falta = self.intervalo - (ahora - self._ultimo.get(host, 0.0))
            if falta > 0:
                time.sleep(falta)
                ahora = time.monotonic()
            self._ultimo[host] = ahora


class Descargador:
    """Descarga cortes: identificado, con backoff y sin insistir cuando molesta."""

    UA = "Mozilla/5.0 (compatible; ERETZ-PropertyBot/1.0; +contacto@eretz)"

    def __init__(self, limitador: LimitadorDeRitmo | None = None,
                 timeout: int = 25, reintentos: int = 3, limite_bytes: int = 800_000):
        self.limitador = limitador or LimitadorDeRitmo()
        self.timeout = timeout
        self.reintentos = reintentos
        self.limite_bytes = limite_bytes
        self.pedidos = 0
        self.bytes_bajados = 0
        self._lock = threading.Lock()

    @staticmethod
    def url_segura(url: str) -> str:
        """Codifica la URL para que urllib pueda pedirla.

        Los slugs de las fichas llevan acentos y enes, y urllib arma el pedido
        en ASCII: una URL con "Centrico" acentuado levanta UnicodeEncodeError.
        No es un caso raro -es una de cada cinco fichas en castellano-, y como
        el error aparece recien al abrir la conexion se confunde facil con una
        falla del sitio.

        La identidad no se altera: el hash del pipeline hace unquote antes de
        normalizar, asi que la forma codificada y la legible dan el mismo hash.
        """
        p = urllib.parse.urlsplit(url)
        return urllib.parse.urlunsplit((
            p.scheme, p.netloc,
            urllib.parse.quote(p.path, safe="/%:@&=+$,~()!*'"),
            urllib.parse.quote(p.query, safe="=&%+"), ""))

    def bajar(self, url: str) -> str:
        url = self.url_segura(url)
        host = urllib.parse.urlparse(url).netloc.lower()
        demora = 2.0
        ultimo: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            self.limitador.esperar(host)
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(url, headers={
                    "User-Agent": self.UA, "Accept-Encoding": "gzip",
                    "Accept": "text/html,application/xhtml+xml,application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as r:
                    crudo = r.read(self.limite_bytes)
                    if r.headers.get("Content-Encoding") == "gzip":
                        try:
                            crudo = gzip.decompress(crudo)
                        except (OSError, EOFError):
                            # Un gzip truncado -pasa cuando se corta la lectura
                            # por el limite de bytes- levanta EOFError, que no
                            # es OSError. Sin atraparlo, la excepcion sube y se
                            # lleva la fuente entera.
                            pass
                    juego = "utf-8"
                    m = re.search(r"charset=([\w-]+)", r.headers.get("Content-Type") or "", re.I)
                    if m:
                        juego = m.group(1)
                    with self._lock:
                        self.pedidos += 1
                        self.bytes_bajados += len(crudo)
                    return crudo.decode(juego, "ignore")
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    raise Bloqueado(f"http {e.code}") from None
                if e.code in (404, 410):
                    raise ErrorPermanente(f"http {e.code}") from None
                ultimo = ErrorTransitorio(f"http {e.code}")
            except Exception as e:
                ultimo = ErrorTransitorio(type(e).__name__)
            if intento < self.reintentos:
                # Con ruido, para no sincronizar los reintentos de varios hilos
                # contra el mismo servidor.
                time.sleep(demora + random.uniform(0, 0.5))
                demora *= 2
        raise ultimo or ErrorTransitorio("sin respuesta")


# --------------------------------------------------------------------------
# Checkpoint: reanudar sin volver a bajar lo ya bajado
# --------------------------------------------------------------------------
# Version del formato del checkpoint. Cambio cuando la clave de `vistos` paso
# de source_listing_id a hash_dedup: comparar entradas de formatos distintos no
# da "todo cambio", da basura, y ademas hace aparecer como ausente todo lo
# anterior. Una corrida contra un checkpoint viejo se trata como linea base.
ESQUEMA_CHECKPOINT = 2


class Checkpoint:
    """Estado por fuente, en disco, fuera del repo.

    Guarda el fingerprint de cada propiedad para que la segunda corrida sepa
    distinguir "cambio real" de "vuelvo a ver lo mismo".
    """

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.datos: dict[str, Any] = {"fuentes": {}}
        if self.ruta.exists():
            try:
                self.datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self.datos = {"fuentes": {}}

    def de(self, agency_id: str) -> dict[str, Any]:
        est = self.datos["fuentes"].setdefault(
            agency_id, {"vistos": {}, "corridas": 0, "ausencias": {},
                        "ultima_pagina": 0, "completa": False,
                        "esquema": ESQUEMA_CHECKPOINT})
        if est.get("esquema") != ESQUEMA_CHECKPOINT:
            # Las claves viejas no se pueden traducir -no guardaban la url, y el
            # hash la necesita-, asi que se descartan y esta corrida vale como
            # linea base. Conservarlas produciria ausencias falsas para todo el
            # inventario anterior.
            est["vistos_previos_descartados"] = len(est.get("vistos") or {})
            est["vistos"] = {}
            est["ausencias"] = {}
            est["esquema"] = ESQUEMA_CHECKPOINT
            est["linea_base"] = True
        return est

    def guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.ruta)


# Cuantas corridas seguidas sin ver una propiedad hacen falta para bajarla.
# Una sola ausencia no alcanza: un 502 de diez minutos daria de baja el catalogo
# entero de una inmobiliaria.
AUSENCIAS_PARA_BAJA = 3

# Cuanto tiene que pisarse la enumeracion de esta corrida con la anterior para
# que la comparacion signifique algo. Por debajo de esto no estamos viendo bajas
# sino dos vistas distintas del mismo sitio -tipicamente el carrusel de
# destacados de la home, que rota-.
SOLAPAMIENTO_MINIMO = 0.5


def clasificar_ausencia(estado_fuente: dict, listing_id: str,
                        fuente_respondio: bool) -> str:
    """Que significa que una propiedad no aparezca en esta corrida.

    Si la fuente entera no respondio, no significa nada: no se puede concluir
    una baja de un sitio que no contesto.
    """
    if not fuente_respondio:
        return "SIN_EVIDENCIA_FUENTE_CAIDA"
    n = estado_fuente.get("ausencias", {}).get(listing_id, 0)
    if n >= AUSENCIAS_PARA_BAJA:
        return "BAJA_CONFIRMADA"
    return "AUSENTE_PROVISORIA"


# --------------------------------------------------------------------------
# Interfaz
# --------------------------------------------------------------------------
@dataclass
class Fuente:
    """Una web oficial a ingerir, con la identidad de su inmobiliaria."""
    canonical_agency_id: str
    agency_name: str
    official_url: str
    inmobiliaria_id: int | None = None
    detected_platform: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Connector:
    """Contrato que cumple toda fuente, sea Tokko, WordPress o una API propia.

    El pipeline solo conoce estos metodos. Agregar una plataforma nueva no
    deberia tocar ni una linea fuera de su propio modulo.
    """

    nombre = "base"

    def __init__(self, descargador: Descargador | None = None,
                 checkpoint: Checkpoint | None = None):
        self.descargador = descargador or Descargador()
        self.checkpoint = checkpoint
        self.errores: list[dict[str, Any]] = []

    # --- ciclo de vida -----------------------------------------------------
    def discover(self, fuente: Fuente) -> dict[str, Any]:
        """Averigua como esta fuente publica su inventario. No baja fichas."""
        raise NotImplementedError

    def fetch_listing(self, fuente: Fuente, plan: dict[str, Any]) -> Iterator[dict]:
        """Emite los avisos crudos, paginando hasta agotar el inventario."""
        raise NotImplementedError

    def normalize(self, crudo: dict, fuente: Fuente) -> PropiedadNormalizada | None:
        """Traduce un aviso crudo a la representacion comun."""
        raise NotImplementedError

    def identify_deleted_or_inactive(self, fuente: Fuente, vistos_ahora: set[str],
                                     fuente_respondio: bool) -> list[dict[str, Any]]:
        """Que dejo de estar, y con cuanta confianza.

        `vistos_ahora` son hash_dedup, la misma clave con la que registra el
        checkpoint: comparar contra ids de la fuente daria falsas ausencias
        cada vez que dos rutas comparten numero.
        """
        if self.checkpoint is None:
            return []
        est = self.checkpoint.de(fuente.canonical_agency_id)
        if est.get("linea_base"):
            # Primera corrida con este formato de checkpoint: no hay con que
            # comparar, y decir que todo esta ausente seria inventar 19.000
            # bajas que no ocurrieron.
            return []

        # Dos enumeraciones que casi no se pisan no son "todo lo anterior se
        # dio de baja": son dos vistas distintas del mismo sitio. Pasa cuando
        # el connector solo alcanza el carrusel de destacados de la home, que
        # Tokko rota: pitton.net enumero 5 propiedades en la corrida 2 y otras
        # 5 completamente distintas en la 3, sin declarar total. Contarlo como
        # bajas daria de baja el catalogo entero de esa inmobiliaria en tres
        # corridas, sin que se hubiera caido un solo aviso.
        previos = set(est.get("vistos", {}))
        comparable = True
        if previos and fuente_respondio:
            solapamiento = len(previos & vistos_ahora) / len(previos)
            comparable = solapamiento >= SOLAPAMIENTO_MINIMO
            est["ultimo_solapamiento"] = round(solapamiento, 4)
        salida = []
        for lid in list(est.get("vistos", {})):
            if lid in vistos_ahora:
                est.setdefault("ausencias", {}).pop(lid, None)
                continue
            # El contador solo avanza cuando la ausencia significa algo. Si no
            # avanza, la propiedad nunca llega a las tres corridas que hacen
            # falta para una baja.
            cuenta = fuente_respondio and comparable
            if cuenta:
                est.setdefault("ausencias", {})[lid] = \
                    est.get("ausencias", {}).get(lid, 0) + 1
            salida.append({"hash_dedup": lid,
                           "source_listing_id": est.get("ids", {}).get(lid),
                           "estado": clasificar_ausencia(est, lid, cuenta),
                           "ausencias_consecutivas": est.get("ausencias", {}).get(lid, 0),
                           "enumeracion_comparable": comparable})
        return salida

    # --- reanudacion -------------------------------------------------------
    def resume(self, fuente: Fuente) -> dict[str, Any]:
        if self.checkpoint is None:
            return {"vistos": {}, "corridas": 0}
        return self.checkpoint.de(fuente.canonical_agency_id)

    def registrar(self, fuente: Fuente, prop: PropiedadNormalizada) -> str:
        """Anota la propiedad y dice si es NUEVA, MODIFICADA o SIN_CAMBIOS.

        La clave es `hash_dedup`, no `source_listing_id`. El id de la fuente
        sirve para rastrear la ficha de origen, pero no siempre es unico: en los
        sitios propios se deriva de la url y dos rutas distintas pueden dar el
        mismo numero. Con esa clave el checkpoint pisaba una propiedad con otra
        y la corrida siguiente las reportaba como modificadas sin que nada
        hubiera cambiado.
        """
        if self.checkpoint is None:
            return "NUEVA"
        est = self.checkpoint.de(fuente.canonical_agency_id)
        clave = prop.hash_dedup
        previo = est["vistos"].get(clave)
        est["vistos"][clave] = prop.fingerprint
        est.setdefault("ids", {})[clave] = prop.source_listing_id
        if previo is None:
            return "NUEVA"
        return "SIN_CAMBIOS" if previo == prop.fingerprint else "MODIFICADA"

    def foto_verificable(self) -> bool:
        """Si el connector puede probar que una foto es de ESTA propiedad.

        Tokko puede: la ruta del CDN lleva el id de la propiedad adelante.
        WordPress no: las imagenes son adjuntos con nombre libre. Contar
        "fotos ajenas" en una plataforma que no permite verificarlo produce
        miles de falsos positivos y esconde los casos reales.
        """
        return False

    def foto_es_de(self, prop: "PropiedadNormalizada", url: str) -> bool:
        return True

    def completar_ubicacion(self, prop: "PropiedadNormalizada",
                            fuente: Fuente) -> None:
        """Completa provincia desde el padron de la inmobiliaria.

        Solo provincia. El campo `city` del padron parece ciudad y no lo es:
        guarda zonas observadas -"centro", "recoleta", "palermo", "belgrano"-,
        que son barrios, y ademas trae valores con acentos perdidos. Copiarlo a
        `ciudad` llenaria el dataset de barrios disfrazados de ciudades, que es
        peor que dejar el campo vacio porque nadie lo notaria despues.

        La provincia si es un vocabulario limpio de 23 valores reales. Se
        escribe solo donde la ficha no dijo nada -una ubicacion explicita nunca
        se pisa con una inferencia- y queda marcada como inferida, porque la
        provincia de la inmobiliaria no es necesariamente la del inmueble.
        """
        padron = fuente.extra or {}
        provincia = padron.get("province")
        if provincia and not prop.provincia:
            prop.provincia = provincia
            prop.extra["provincia_origen"] = "padron_inmobiliaria"
            prop.extra["provincia_confianza"] = "inferida"
        zona = padron.get("city")
        if zona:
            # Se guarda como rastro, no como ubicacion: sirve para auditar de
            # donde salio una propiedad sin contaminar los campos de ubicacion.
            prop.extra["zona_padron"] = zona

    def anotar_error(self, fuente: Fuente, etapa: str, error: Exception) -> None:
        self.errores.append({
            "canonical_agency_id": fuente.canonical_agency_id,
            "official_url": fuente.official_url, "etapa": etapa,
            "clase": type(error).__name__, "detalle": str(error)[:200],
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S")})


# --------------------------------------------------------------------------
# Utilidades de normalizacion compartidas por todos los connectors
# --------------------------------------------------------------------------
_MONEDAS = {"usd": "USD", "u$s": "USD", "us$": "USD", "dolares": "USD",
            "dólares": "USD", "dolar": "USD", "ars": "ARS", "$": "ARS",
            "pesos": "ARS", "peso": "ARS"}

_OPERACIONES = {"venta": "venta", "vender": "venta", "sale": "venta",
                "alquiler": "alquiler", "alquilar": "alquiler", "rent": "alquiler",
                "alquiler temporario": "alquiler_temporario",
                "temporario": "alquiler_temporario", "temporal": "alquiler_temporario"}

_TIPOS = {
    "casa": "casa", "chalet": "casa", "quinta": "casa", "duplex": "casa",
    "departamento": "departamento", "depto": "departamento", "ph": "departamento",
    "loft": "departamento", "monoambiente": "departamento",
    "terreno": "terreno", "lote": "terreno", "campo": "terreno", "fraccion": "terreno",
    "local": "local", "fondo de comercio": "local",
    "oficina": "oficina", "consultorio": "oficina",
    "cochera": "cochera", "garage": "cochera",
    "galpon": "galpon", "deposito": "galpon", "nave industrial": "galpon",
}


def limpiar(texto: Any) -> str | None:
    if texto is None:
        return None
    t = re.sub(r"\s+", " ", str(texto)).strip()
    return t or None


def a_numero(texto: Any) -> float | None:
    """Numero de un texto en formato argentino: 1.234.567,89 -> 1234567.89.

    Devuelve None ante la duda. Un precio mal parseado es peor que uno ausente:
    el ausente se ve, el equivocado se publica.

    El signo se conserva cuando el menos ABRE el texto. Se perdia: el filtro de
    caracteres se llevaba el "-" y "-34.6690485" volvia 34.6690485, una
    latitud del hemisferio norte. Tokko no lo sufrio porque convierte sus
    coordenadas con float() directo, pero el connector de Wasi si, y lo delato
    su propio chequeo de coherencia. Exigir que el menos abra el texto evita
    volver negativo un rango como "55.000-60.000".
    """
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    crudo = str(texto).strip()
    negativo = crudo.startswith("-")
    # Un rango no es un numero. "55.000-60.000" perdia el guion y se pegaba en
    # 5.500.060.000: un precio absurdo pero bien formado, que se publica igual.
    if re.search(r"\d\s*[-–a]\s*\d", crudo[1:] if negativo else crudo):
        return None
    t = re.sub(r"[^\d.,]", "", crudo)
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rindex(",") > t.rindex(".") \
            else t.replace(",", "")
    elif "," in t:
        entero, _, dec = t.partition(",")
        t = f"{entero}.{dec}" if len(dec) <= 2 and dec else t.replace(",", "")
    elif t.count(".") >= 1:
        entero, _, dec = t.rpartition(".")
        if len(dec) == 3 or not dec:
            t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if negativo else v


def a_entero(texto: Any) -> int | None:
    v = a_numero(texto)
    if v is None:
        return None
    return int(v) if 0 <= v < 1000 else None


def detectar_moneda(texto: Any) -> str | None:
    if not texto:
        return None
    t = str(texto).lower()
    for clave, val in _MONEDAS.items():
        if clave in t:
            return val
    return None


def detectar_operacion(texto: Any) -> str | None:
    if not texto:
        return None
    t = str(texto).lower()
    if "temporario" in t or "temporal" in t:
        return "alquiler_temporario"
    for clave, val in _OPERACIONES.items():
        if clave in t:
            return val
    return None


def detectar_tipo(texto: Any) -> str | None:
    if not texto:
        return None
    t = re.sub(r"\s+", " ", str(texto).lower())
    for clave, val in _TIPOS.items():
        if re.search(rf"\b{re.escape(clave)}", t):
            return val
    return None

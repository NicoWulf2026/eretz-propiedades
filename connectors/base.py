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
import unicodedata
import ssl
from html import unescape
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .coherencia import revisar

CONNECTOR_API_VERSION = "connector_v1"

# Claves de `extra` que NO son contenido y por lo tanto no entran en la huella.
# `modificado_en_fuente` es la fecha que declara el propio sitio, y WordPress la
# mueve cuando re-guarda los posts en masa: 1.618 propiedades cambiaron esa
# fecha entre dos corridas -varias con el mismo 04:00:29, o sea un cron- sin que
# cambiara una sola letra del aviso. Con ella adentro, MODIFICADA deja de
# significar "cambio algo" y pasa a significar "el sitio corrio su tarea nocturna".
NO_SON_CONTENIDO = ("raw_html_len", "fetched_at", "modificado_en_fuente",
                    # Geografia DERIVADA: se calcula a partir de campos que ya
                    # entran en la huella. Ver HUELLA_VERSION 5.
                    "geo", "ciudad_publicada", "ciudad_match",
                    "ciudad_provenance", "ciudad_campo_de_origen",
                    "localidad_id", "localidad_fuente")

# Version de lo que se COMPARA. Se sube cada vez que cambia que entra en la
# huella o que se guarda: excluir un campo, ordenar una lista, normalizar un
# valor, o filtrar datos que antes se guardaban.
#
# Existe porque el mismo error se cometio dos veces. Al cambiar la formula, la
# huella guardada en el checkpoint deja de ser comparable y TODO el inventario
# vuelve MODIFICADA -499 de 500 en una muestra- sin que haya cambiado una letra.
# Con la version adentro, esa corrida se informa como BASELINE_INCOMPATIBLE en
# vez de inventar una ola de cambios comerciales, y la siguiente ya compara bien.
#
#   1  formula original
#   2  se ignora el ORDEN de descripcion y fotos
#   3  se ignora `modificado_en_fuente`
#   4  se descartan las imagenes de la PAGINA: las que aparecen en la mitad o
#      mas del catalogo de la inmobiliaria y por lo tanto no son de ninguna
#      propiedad -iconos, botones, banners: el 15,8% de las referencias-
#   5  la geografia DERIVADA sale de la huella de contenido. Sus insumos
#      -ciudad, barrio, provincia, lat, lon- ya estan hasheados, asi que
#      agregarla no aporta informacion sobre si la FUENTE cambio, y en cambio
#      hacia que cualquier mejora del resolver devolviera el inventario entero
#      como MODIFICADA. Que cambie el resolver es asunto de la huella de
#      estrategia y de la recertificacion, no del incremental.
HUELLA_VERSION = 5

# Lo que devuelve `registrar` cuando la huella guardada se calculo con otra
# formula: no se puede afirmar que cambio ni que no cambio.
BASELINE_INCOMPATIBLE = "BASELINE_INCOMPATIBLE"

# --------------------------------------------------------------------------
# Geografia canonica: dimensiones separadas y una capa de busqueda aparte
# --------------------------------------------------------------------------
# La regla que ordena todo: NO INVENTAR GEOGRAFIA. Un municipio puede servir
# para descubrir una propiedad, pero no puede fingir ser una localidad.
#
# Un solo campo `ciudad` no podia sostener a la vez "esto es una localidad
# censal demostrada" y "esto es lo que escribio la inmobiliaria": con el campo
# plano, `Villa del Parque` -barrio de CABA- contaba igual que una localidad.
DIMENSIONES_GEO = ("provincia", "departamento", "municipio", "localidad",
                   "barrio")

# Procedencias, de mas fuerte a mas debil.
GEO_SOURCE_STRUCTURED = "SOURCE_STRUCTURED"   # la fuente lo publica en su campo
GEO_SOURCE_TEXT = "SOURCE_TEXT"               # lo leimos de su texto
GEO_CANONICAL = "CANONICAL_NORMALIZED"        # resuelto contra el catalogo
GEO_GEOMETRY = "GEOMETRY"                     # resuelto por geometria oficial
GEO_UNKNOWN = "UNKNOWN"                       # no se pudo demostrar

# Niveles del area de busqueda, de mas preciso a menos. El nivel viaja SIEMPRE
# junto al valor: sin el, un municipio en la caja de busqueda se lee como una
# ciudad, que es justamente lo que no se quiere.
AREA_LOCALIDAD = "LOCALIDAD"
AREA_MUNICIPIO = "MUNICIPIO"
AREA_DEPARTAMENTO = "DEPARTAMENTO"
AREA_PROVINCIA = "PROVINCIA"
AREA_SIN = "SIN_AREA"

# Cuando la coordenada y lo que publico la fuente se contradicen, no se elige:
# una de las dos esta mal y quedarse con cualquiera seria decidir sin
# evidencia. Se declara el conflicto y se conservan las dos.
GEO_CONFLICT = "GEO_CONFLICT"


def dimension_geo(valor=None, *, id=None, procedencia=GEO_UNKNOWN,
                  confianza=None, evidencia=None, rechazo=None) -> dict:
    """Una dimension geografica con todo lo que hace falta para auditarla.

    `rechazo` es la mitad que suele faltar. Sin ella, "no se pudo demostrar" y
    "nunca se intento" se ven iguales, y confundir esas dos ausencias es como
    se escribe geografia inventada.
    """
    return {"id": id, "nombre": valor, "procedencia": procedencia,
            "confianza": confianza, "evidencia": evidencia, "rechazo": rechazo}

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


def geografia(*args, **kwargs):
    """Catalogo geografico canonico, cargado la primera vez que se usa.

    El import va diferido para que importar `base` no lea el snapshot: hay
    scripts que solo necesitan las estructuras y no la geografia.
    """
    from connectors.geografia import geografia as _geografia
    return _geografia(*args, **kwargs)


GEO_NO_ENCONTRADA = "NOT_FOUND"
GEO_CONTRADICHA = "CONTRADICTED_BY_COORDINATES"
GEO_AMBIGUA = "AMBIGUOUS"


# --------------------------------------------------------------------------
# Representacion normalizada comun
# --------------------------------------------------------------------------
# Lo que mira la aritmetica de inmuebles. Se declara aca y no se deduce del
# modulo: si `coherencia` agrega una regla sobre un campo nuevo, que falle al
# leerlo es mejor que aplicarla a medias sin que nadie se entere.
CAMPOS_DE_COHERENCIA = (
    "tipo_propiedad", "superficie_total", "superficie_cubierta",
    "dormitorios", "ambientes", "banos", "latitud", "longitud",
    "precio", "moneda",
)

# `imagenes` queda AFUERA a proposito, y no por olvido.
#
# `coherencia` tiene un filtro de imagenes que no es una foto -logo, avatar,
# placeholder-, y resulta que nunca corrio: `generico` llama a `revisar` con un
# diccionario que no incluye `imagenes`. Al aplicarlo aca por primera vez se vio
# lo que hacia: borro `WhatsApp-Image-depto.jpg`, que es la foto de un
# departamento subida desde el telefono, porque el patron incluye "whatsapp"
# para atrapar el icono de compartir.
#
# Y no compra nada: sobre 1.271.000 urls de imagen de las 58.427 propiedades el
# patron no saca ni una sola. Los connectors ya filtran lo suyo -Wasi descarta
# `/empresas/`, `/perfiles/` y `/publicidad/`- y la snapshot descarta lo que se
# repite en cinco o mas fichas de la misma inmobiliaria.
#
# Activarlo de arrastre, adentro de un arreglo sobre superficies, seria meter un
# cambio de comportamiento que nadie pidio y que empeora el dato.


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
    # Las cinco dimensiones canonicas, cada una con procedencia, confianza,
    # evidencia y rechazo, mas el area de busqueda derivada. Un solo campo
    # anidado en vez de veinticinco sueltos: la forma la fija `dimension_geo`
    # y se puede versionar entera.
    geo: dict[str, Any] = field(default_factory=dict)
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
        self._aplicar_coherencia()

    def _aplicar_coherencia(self) -> None:
        """Descartar lo que no puede ser cierto, venga del connector que venga.

        `revisar` vivia SOLO adentro de `generico.py`. Tokko, Wasi, WordPress y
        Century21 nunca pasaban por ahi, asi que certificaban combinaciones
        imposibles sin que nada las mirara: `aagaard.com.ar` cerro
        CERTIFIED_COMPLETE con un departamento de 95 m2 cubiertos y 50.000.000
        m2 de terreno -cincuenta kilometros cuadrados-, y otras dos fichas con
        180 y 50 hectareas sobre 180 y 45 metros construidos.

        Va en la construccion y no en cada connector por la misma razon por la
        que la guardia de `discover` se movio al runner: cada connector tiene
        sus caminos -century21 tiene cuatro salidas tempranas- y una guardia
        por connector deja justo el que nadie miro. Aca no hay construccion que
        la esquive, y los connectors que se escriban despues la heredan.

        Es idempotente: `generico` la sigue llamando antes de construir, y
        sobre datos ya limpios `revisar` no descarta nada.
        """
        campos = {c: getattr(self, c) for c in CAMPOS_DE_COHERENCIA}
        fuera = revisar(campos)
        if not fuera:
            return
        for nombre, valor in campos.items():
            setattr(self, nombre, valor)
        # El motivo viaja con el dato. Sin el, la propiedad aparece sin
        # superficie y no se puede distinguir de una que la fuente no publica.
        previos = [x for x in
                   str(self.extra.get("atributos_descartados") or "").split(",") if x]
        self.extra["atributos_descartados"] = ",".join(
            previos + [x for x in fuera if x not in previos])

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
        # `geo` queda afuera por la misma razon que `scraped_at`: es DERIVADO.
        # Sus insumos -ciudad, barrio, provincia, lat, lon- ya estan aca, asi
        # que no agrega informacion sobre si la fuente cambio, y si entrara,
        # cualquier mejora del resolver devolveria el inventario entero como
        # MODIFICADA. Ver HUELLA_VERSION 5.
        campos = {k: v for k, v in asdict(self).items()
                  if k not in ("scraped_at", "provenance", "extra", "geo")}
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
        # Queda en el artefacto para que una comparacion futura pueda distinguir
        # "cambio el contenido" de "cambio la formula de la huella".
        d["fingerprint_version"] = HUELLA_VERSION
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

    # Tope de cortesia. Un sitio que sigue cortando a 30 s por pedido no esta
    # pidiendo ritmo: esta diciendo que no. Sin tope, un solo host podria
    # dejar la corrida sin final.
    INTERVALO_MAXIMO = 30.0

    def __init__(self, intervalo: float = 1.5):
        self.intervalo = intervalo
        self._ultimo: dict[str, float] = {}
        self._intervalos: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._maestro = threading.Lock()

    def _lock_de(self, host: str) -> threading.Lock:
        with self._maestro:
            return self._locks.setdefault(host, threading.Lock())

    def intervalo_de(self, host: str) -> float:
        """El intervalo vigente para ESTE host."""
        return self._intervalos.get(host, self.intervalo)

    def ceder_ritmo(self, host: str, factor: float) -> float:
        """Baja la velocidad para un host, sin tocar a los demas.

        El limitador es uno solo y lo comparten todos los hilos, asi que un
        `self.intervalo *= factor` frenaria tambien a las inmobiliarias que no
        se quejaron, y con varias fuentes bloqueadas en paralelo compondria
        cuatro veces por cada una. La queja es de un host: la respuesta
        tambien.
        """
        with self._maestro:
            nuevo = min(self.intervalo_de(host) * factor, self.INTERVALO_MAXIMO)
            self._intervalos[host] = nuevo
            return nuevo

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
            falta = self.intervalo_de(host) - (ahora - self._ultimo.get(host, 0.0))
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
        # Hosts de los que se pudo leer aunque sea una respuesta. Sirve para
        # distinguir "el sitio dice que no tiene nada" de "no se pudo hablar
        # con el sitio", que es la diferencia entre NO_INVENTORY_CONFIRMED y
        # BLOCKED_EXTERNAL.
        self._hosts_leidos: set[str] = set()
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

    def hubo_contacto(self, url: str) -> bool:
        """Si alguna vez se leyo algo de este host en esta corrida.

        No haber podido leer NADA de un sitio no es haber leido que el sitio
        no tiene nada. Los connectors devolvian `SIN_INVENTARIO` en las dos
        situaciones, y `aguirreinmobiliaria.com.ar` -que publica 38
        propiedades- figuro con inventario cero por sesenta segundos malos:
        el triage lo leyo como perdida sistematica de radio FAMILIA y paro
        las dos colas durante diez horas.

        `NO_INVENTORY_CONFIRMED` y `BLOCKED_EXTERNAL` son estados terminales
        distintos, y esta es la pregunta que los separa.
        """
        host = urllib.parse.urlparse(self.url_segura(url)).netloc.lower()
        return host in self._hosts_leidos

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
                        self._hosts_leidos.add(host)
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
                        "esquema": ESQUEMA_CHECKPOINT,
                        "huella_version": HUELLA_VERSION})
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
        # Si el baseline de cada fuente es comparable con la version de huella
        # de hoy. Se decide una vez por fuente, no una vez por propiedad.
        self._version_evaluada: dict[str, bool] = {}

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

        Si la huella guardada se calculo con OTRA formula, no se puede afirmar
        que cambio ni que no cambio: se devuelve BASELINE_INCOMPATIBLE. Sin eso,
        cambiar la formula pinta el inventario entero de MODIFICADA -499 de 500
        en una muestra real- y esa ola falsa se lee como cambio comercial.
        """
        if self.checkpoint is None:
            return "NUEVA"
        est = self.checkpoint.de(fuente.canonical_agency_id)
        # La incompatibilidad se decide UNA vez por fuente y se recuerda en
        # memoria. Leerla del checkpoint en cada propiedad no funciona: la
        # primera lo sella con la version nueva y las demas ya lo ven al dia,
        # asi que una corrida informaba 1 BASELINE_INCOMPATIBLE y 372
        # MODIFICADA cuando las 373 eran el mismo cambio de version.
        cid = fuente.canonical_agency_id
        if cid not in self._version_evaluada:
            previa = est.get("huella_version")
            self._version_evaluada[cid] = (previa is not None
                                           and previa != HUELLA_VERSION)
            est["huella_version"] = HUELLA_VERSION
        incompatible = self._version_evaluada[cid]

        clave = prop.hash_dedup
        previo = est["vistos"].get(clave)
        est["vistos"][clave] = prop.fingerprint
        est.setdefault("ids", {})[clave] = prop.source_listing_id
        if previo is None:
            return "NUEVA"
        if incompatible:
            # La huella queda actualizada arriba, asi que la corrida siguiente
            # ya compara contra la formula nueva y esto no se repite.
            return BASELINE_INCOMPATIBLE
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
        self._resolver_geografia(prop)

    @staticmethod
    def _marcar_descartado(prop: "PropiedadNormalizada", campo: str) -> None:
        """Deja constancia de que un valor se rechazo, no de que falto.

        `EXTRACTION_FAILED` es un defecto nuestro y bloquea la certificacion;
        `REJECTED_BY_VALIDATION` es la validacion haciendo su trabajo.
        """
        descartados = prop.extra.get("atributos_descartados") or ""
        partes = [x for x in str(descartados).split(",") if x]
        if campo not in partes:
            partes.append(campo)
        prop.extra["atributos_descartados"] = ",".join(partes)

    @staticmethod
    def _resolver_geografia(prop: "PropiedadNormalizada") -> None:
        """Pone la ciudad y el barrio en la dimension que les corresponde.

        Barrio y localidad son cosas distintas, y GeoRef no cataloga barrios.
        Eso convierte al catalogo en el arbitro: una cadena que resuelve a una
        localidad censal ES una ciudad; una que no resuelve es, muy
        probablemente, un barrio.

        Sirve en los dos sentidos, y los dos aparecen en los datos reales:

          - `ciudad = "Palermo"` contamina la faceta principal de busqueda con
            una localidad que no existe. Se mueve a `barrio`.
          - `barrio = "Mar Del Plata"` esconde una ciudad de verdad donde nadie
            la va a buscar. Son 11.440 propiedades de Tokko, que publica la
            ubicacion en un solo campo sin decir de que nivel es.

        Nunca se inventa: si no resuelve, el texto se conserva donde estaba y
        `ciudad` queda vacia. Y la propiedad nunca desaparece por esto.
        """
        desde_barrio = not prop.ciudad
        publicada = prop.ciudad or prop.barrio
        if not publicada:
            return
        try:
            catalogo = geografia()
        except (OSError, ValueError):
            # Sin snapshot no se normaliza, pero no se rompe nada ni se pierde
            # lo que la fuente publico.
            return

        resolucion = catalogo.resolver_localidad(
            publicada, provincia=prop.provincia,
            lat=prop.latitud, lon=prop.longitud)
        prop.extra["ciudad_publicada"] = publicada
        prop.extra["ciudad_match"] = resolucion.certeza
        prop.extra["ciudad_provenance"] = resolucion.provenance
        prop.extra["ciudad_campo_de_origen"] = ("barrio" if desde_barrio
                                                else "ciudad")

        if resolucion.resuelta:
            entidad = resolucion.entidad
            prop.ciudad = entidad.official_name
            prop.extra["localidad_id"] = entidad.official_id
            prop.extra["localidad_fuente"] = entidad.fuente
            Connector._escribir_dimensiones(prop, entidad, resolucion,
                                            desde_barrio, publicada)
            if desde_barrio:
                # Era una ciudad, no un barrio: dejarla duplicada en `barrio`
                # afirmaria un barrio que no existe.
                #
                # Y vaciarlo no es haber fallado al extraerlo. El valor se
                # validó contra el catalogo y se rechazo COMO BARRIO, que es
                # una decision de validacion. Sin decirlo, la certificacion lee
                # "Cordoba Capital" promovida a ciudad como si hubieramos
                # perdido el barrio de esa ficha.
                prop.barrio = None
                Connector._marcar_descartado(prop, "barrio")
            if not prop.provincia:
                # La provincia de una localidad resuelta es un hecho del
                # catalogo, no una inferencia nuestra.
                prop.provincia = entidad.provincia
            return

        # Negarse a afirmar NO es lo mismo que fallar al extraer, y la
        # certificacion los trata distinto: `EXTRACTION_FAILED` es un defecto
        # nuestro y bloquea, `REJECTED_BY_VALIDATION` es la validacion haciendo
        # su trabajo. Aca la validacion funciono: azpropiedades publica
        # "Caseros" en 11 avisos del Gran Buenos Aires, y la unica Caseros del
        # catalogo esta en Entre Rios, a 238 km. Afirmarla los habria mandado a
        # otra provincia.
        # No afirmar una ciudad es distinto de no haberla podido leer, y la
        # certificacion los trata distinto: uno bloquea y el otro no.
        #
        # Se marca cuando la fuente publico una ciudad y la vaciamos, y tambien
        # cuando el texto venia en `barrio` pero la evidencia lo desmiente o lo
        # deja ambiguo: ahi la pagina si nombra una localidad y nos negamos a
        # afirmarla. Un barrio que simplemente no esta en el catalogo no marca
        # nada, porque no habia ninguna ciudad publicada que rechazar.
        if not desde_barrio or resolucion.certeza in (GEO_CONTRADICHA,
                                                      GEO_AMBIGUA):
            Connector._marcar_descartado(prop, "ciudad")

        if desde_barrio:
            # No resolvio: es lo que decia ser, un barrio. Se queda donde esta.
            Connector._escribir_dimensiones(prop, None, resolucion,
                                            desde_barrio, publicada)
            return
        prop.ciudad = None
        if resolucion.certeza == GEO_NO_ENCONTRADA and not prop.barrio:
            prop.barrio = publicada
        Connector._escribir_dimensiones(prop, None, resolucion,
                                        desde_barrio, publicada)

    @staticmethod
    def _escribir_dimensiones(prop: "PropiedadNormalizada", entidad,
                              resolucion, desde_barrio: bool,
                              publicada: str) -> None:
        """Llena las cinco dimensiones y deriva el area de busqueda.

        Ninguna dimension se rellena con otra. Si la localidad no se puede
        demostrar queda en UNKNOWN aunque haya municipio: el municipio se
        guarda en SU campo, donde no engana a nadie.
        """
        geo: dict[str, Any] = {}

        if entidad is not None:
            geo["localidad"] = dimension_geo(
                entidad.official_name, id=entidad.official_id,
                procedencia=GEO_CANONICAL, confianza=resolucion.certeza,
                evidencia=f"'{publicada}' resolvio contra {entidad.fuente}")
            # Los ids de GeoRef son jerarquicos -`06` provincia, `06280`
            # departamento, `06280040` localidad-, asi que el departamento no
            # se deduce: viene adentro del id de la localidad.
            geo["departamento"] = dimension_geo(
                getattr(entidad, "departamento", None),
                id=getattr(entidad, "departamento_id", None),
                procedencia=(GEO_CANONICAL
                             if getattr(entidad, "departamento_id", None)
                             else GEO_UNKNOWN),
                evidencia="derivado del id de la localidad")
            geo["municipio"] = dimension_geo(
                getattr(entidad, "municipio", None),
                id=getattr(entidad, "municipio_id", None),
                procedencia=(GEO_CANONICAL
                             if getattr(entidad, "municipio_id", None)
                             else GEO_UNKNOWN),
                rechazo=(None if getattr(entidad, "municipio_id", None)
                         else "el catalogo no declara gobierno local"))
        else:
            geo["localidad"] = dimension_geo(
                None, procedencia=GEO_UNKNOWN,
                rechazo=f"'{publicada}' no se pudo demostrar: "
                        f"{resolucion.certeza}")
            geo["departamento"] = dimension_geo(None)
            geo["municipio"] = dimension_geo(None)

        provincia = prop.provincia or getattr(entidad, "provincia", None)
        geo["provincia"] = dimension_geo(
            provincia,
            id=getattr(entidad, "provincia_id", None),
            procedencia=(GEO_SOURCE_TEXT if prop.provincia
                         else (GEO_CANONICAL if provincia else GEO_UNKNOWN)))

        # Barrio es una dimension propia y NO se resuelve contra el catalogo de
        # localidades: GeoRef no cataloga barrios. El texto que publico la
        # fuente se conserva aunque no se pueda canonizar, porque una persona
        # que busca en Villa del Parque reconoce el nombre y esconderlo pierde
        # informacion real sin ganar nada.
        barrio_fuente = prop.barrio if not desde_barrio else publicada
        geo["barrio"] = dimension_geo(
            barrio_fuente,
            procedencia=GEO_SOURCE_TEXT if barrio_fuente else GEO_UNKNOWN,
            rechazo=(None if not barrio_fuente else
                     "no se canoniza: el catalogo de localidades no cataloga "
                     "barrios"))

        geo["area_busqueda"] = Connector._area_de_busqueda(geo)
        prop.geo = geo

    @staticmethod
    def _area_de_busqueda(geo: dict[str, Any]) -> dict[str, Any]:
        """La capa de descubrimiento, derivada y con el nivel explicito.

        Baja de nivel hasta encontrar algo demostrado, y NUNCA rellena
        `localidad` al hacerlo: son dos caminos que no se tocan. Uno afirma
        donde esta la propiedad; el otro permite encontrarla.
        """
        for nivel, dimension in ((AREA_LOCALIDAD, "localidad"),
                                 (AREA_MUNICIPIO, "municipio"),
                                 (AREA_DEPARTAMENTO, "departamento"),
                                 (AREA_PROVINCIA, "provincia")):
            dato = geo.get(dimension) or {}
            if dato.get("nombre") and dato.get("procedencia") != GEO_UNKNOWN:
                return {"nivel": nivel, "nombre": dato["nombre"],
                        "id": dato.get("id"), "origen": dimension}
        return {"nivel": AREA_SIN, "nombre": None, "id": None, "origen": None}

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
    "departamento": "departamento", "depto": "departamento",
    "dpto": "departamento", "ph": "departamento",
    "loft": "departamento", "monoambiente": "departamento",
    "terreno": "terreno", "lote": "terreno", "campo": "terreno", "fraccion": "terreno",
    "local": "local", "fondo de comercio": "local",
    "oficina": "oficina", "consultorio": "oficina",
    "cochera": "cochera", "garage": "cochera",
    "galpon": "galpon", "deposito": "galpon", "nave industrial": "galpon",
}


def recorte_estable_de_imagenes(urls: list[str], tope: int) -> list[str]:
    """Recorta la lista de fotos eligiendo SIEMPRE las mismas.

    El 47% de las propiedades de WordPress llegan al tope de 40, y la fuente no
    devuelve la cola siempre en el mismo orden: el subconjunto elegido cambiaba
    entre corridas y se leia como que la propiedad habia cambiado de fotos -335
    casos en una sola corrida-.

    La primera SI es estable -se mantiene igual en el 99,9% de los casos-, asi
    que es la principal y se respeta. El resto se ordena antes de recortar, que
    es lo unico que vuelve reproducible la seleccion.
    """
    if not urls or len(urls) <= tope:
        return list(urls or [])
    principal = urls[0]
    resto = sorted(u for u in dict.fromkeys(urls[1:]) if u != principal)
    return [principal] + resto[:tope - 1]


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
    """Parse a single integer token, never a concatenation of several values.

    ``a_numero`` is intentionally permissive for prices and surfaces, where
    punctuation is meaningful.  Counts are different: ``"3 baños + 1
    toilette"`` must not become ``31`` and ``"1 + 1"`` must not become
    ``11``.  A count with more than one numeric token is ambiguous and fails
    closed.
    """
    if texto is None or isinstance(texto, bool):
        return None
    if isinstance(texto, int):
        return texto if 0 <= texto < 1000 else None
    if isinstance(texto, float):
        return int(texto) if texto.is_integer() and 0 <= texto < 1000 else None
    tokens = re.findall(r"(?<![\d.,])\d+(?![\d.,])", str(texto))
    if len(tokens) != 1:
        return None
    value = int(tokens[0])
    return value if 0 <= value < 1000 else None


def detectar_moneda(texto: Any) -> str | None:
    if not texto:
        return None
    t = str(texto).lower()
    for clave, val in _MONEDAS.items():
        if clave in t:
            return val
    return None


# Parametros con los que un proxy de imagenes lleva la foto REAL adentro de la
# query. Son cuatro nombres y los usa media web moderna: /api/img?u=...,
# /_next/image?url=..., /cdn-cgi/image/...?src=...
PROXY_DE_IMAGEN = ("u", "url", "src", "image", "img")


def identidad_de_imagen(u: str) -> str:
    """La imagen que una url representa, no la url con la que se pide.

    Un sitio servia sus 12 fotos por un proxy propio -/api/img?u=<foto>- y
    quitar la query, que es lo correcto para descartar variantes de tamano,
    dejaba las 12 reducidas a "/api/img": la ficha parecia tener una sola foto
    y el guardian la descartaba entera. Adentro de la query estaba la foto de
    verdad.
    """
    if "?" not in u:
        return u
    base, _, consulta = u.partition("?")
    try:
        campos = urllib.parse.parse_qs(consulta)
    except ValueError:
        return base
    for clave in PROXY_DE_IMAGEN:
        for valor in campos.get(clave, []):
            adentro = urllib.parse.unquote(valor)
            if not re.search(r"\.(?:jpe?g|png|webp|avif)", adentro, re.I):
                continue
            if adentro.startswith("http"):
                return identidad_de_imagen(adentro)
            if adentro.startswith("/"):
                # Next.js pasa la foto como ruta: /_next/image?url=%2Ffotos%2Fa.jpg
                return urllib.parse.urljoin(base, adentro)
    return base


RE_ENLACE_CON_IMAGEN = re.compile(
    r'<a\b[^>]*?href="([^"]+)"[^>]*>(?:(?!</a>).)*?<img\b(?:(?!</a>).)*?</a>',
    re.I | re.S)
RE_ARCHIVO_DE_IMAGEN = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)$", re.I)


def sin_fichas_vecinas(html: str, url_propia: Any) -> str:
    """Saca los bloques que enlazan a OTRA ficha y muestran su foto.

    azpropiedades.com pone al pie un carrusel de propiedades relacionadas: cada
    una es un `<a href="/propiedad/OTRO_ID/">` con su miniatura adentro.
    Extraer imagenes del documento entero le pegaba a cada aviso las fotos de
    sus vecinos -84.378 imagenes ajenas en 5.903 propiedades- y ademas rompia
    la idempotencia, porque el sitio rota ese bloque y cada rotacion se leia
    como que la propiedad habia cambiado de fotos.

    Mostrarle a alguien la foto de otra casa es peor que no mostrarle ninguna.

    La regla es estructural y no depende del nombre del archivo: una imagen
    envuelta en un enlace a otra PAGINA no es de esta propiedad. Las galerias
    con lightbox no se tocan, porque ahi el href es el archivo de imagen y no
    una ficha.
    """
    ruta_propia = urllib.parse.urlparse(
        str(url_propia or "")).path.rstrip("/") or None

    def decidir(coincidencia: "re.Match[str]") -> str:
        destino = unescape(coincidencia.group(1)).strip()
        if not destino or destino.startswith(
                ("javascript:", "mailto:", "tel:", "#")):
            return coincidencia.group(0)
        if RE_ARCHIVO_DE_IMAGEN.search(destino.split("?")[0]):
            return coincidencia.group(0)
        ruta = urllib.parse.urlparse(destino).path.rstrip("/")
        if ruta_propia and ruta and ruta == ruta_propia:
            return coincidencia.group(0)
        return " "

    return RE_ENLACE_CON_IMAGEN.sub(decidir, html or "")


def imagenes_de_fichas_vecinas(html: str, url_propia: Any) -> set[str]:
    """Las urls de imagen que viven dentro de un enlace a OTRA ficha.

    Se devuelven en vez de recortar el html porque el guardian de forma exige
    fotos para aceptar una pagina como propiedad: si el filtro corriera antes,
    una ficha real cuyas unicas imagenes visibles son las del carrusel de
    relacionadas quedaria descartada por una limpieza nuestra. Se limpia lo que
    se guarda, no lo que se usa para decidir.
    """
    ajenas: set[str] = set()
    recortado = sin_fichas_vecinas(html, url_propia)
    if recortado == (html or ""):
        return ajenas
    patron = re.compile(r'src="([^"]+)"|src=' + chr(39) + r'([^' + chr(39)
                        + r']+)' + chr(39), re.I)
    for bloque in RE_ENLACE_CON_IMAGEN.finditer(html or ""):
        if bloque.group(0) in recortado:
            continue
        for coincidencia in patron.finditer(bloque.group(0)):
            valor = coincidencia.group(1) or coincidencia.group(2)
            if valor:
                ajenas.add(unescape(valor.strip()))
    return ajenas


def detectar_operacion(texto: Any) -> str | None:
    if not texto:
        return None
    t = str(texto).lower()
    if "temporario" in t or "temporal" in t:
        return "alquiler_temporario"
    for clave, val in _OPERACIONES.items():
        if clave in t:
            return val
    # Formas verbales. Se consultan solo cuando nada de lo anterior dijo algo,
    # asi que no pueden cambiar ninguna deteccion que ya funcionaba. Van con
    # limite de palabra porque "vende" es parte de "vendedor". Titulos como
    # "Se vende terreno en Colastine" o "INMOBILIARIA LEAL VENDE CASA"
    # declaraban la operacion y quedaban sin ella, que es el campo que mas
    # define un aviso: sin el, la propiedad no se puede publicar.
    venta = re.search(r"\b(vende|venden|vendemos)\b", t)
    alquiler = re.search(r"\b(alquila|alquilan|alquilamos|arrienda|arriendan)\b",
                         t)
    if venta and not alquiler:
        return "venta"
    if alquiler and not venta:
        return "alquiler"
    # Si el aviso nombra las dos, la fuente no declaro una sola operacion.
    # Elegir cualquiera seria inventar la mitad del anuncio.
    return None


def _palabras(valor: Any) -> set[str]:
    plano = unicodedata.normalize("NFKD", str(valor or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return set(re.sub(r"[^a-z0-9]+", " ", plano).split())


def ficha_sin_contenido(prop: "PropiedadNormalizada") -> bool:
    """Ficha que no trajo ningun dato Y cuyo titulo es el nombre del sitio.

    Cuando la pagina devuelve el cascaron -sin renderizar, un error blando, un
    limite de tasa- lo unico que sobrevive es el <title> del sitio, y el tipo
    se termina adivinando del slug de la url: quedaron guardados "Ferraro
    Propiedades" como un terreno, "Lincoln Negocios Inmobiliarios" como un
    departamento y "CASAS EN ALQUILER | ARRAMBIDE PROPIEDADES" como una casa.
    La ausencia convertida en afirmacion.

    Las dos condiciones son necesarias, y eso se midio. Sin datos no alcanza:
    254 lotes y terrenos reales publican solo titulo y fotos -sin precio, sin
    ambientes, sin superficie, sin direccion- y descartarlos perderia
    inventario que la fuente si ofrece. El titulo solo tampoco alcanza: una
    inmobiliaria puede nombrarse en el titulo de un aviso legitimo.

    No se miran `operacion` ni `tipo_propiedad` ni `provincia`: el cascaron de
    alder los tenia los tres, sacados del slug de la url y del padron, no de la
    ficha. Tampoco las imagenes, que en ese caso eran una sola y generica.
    """
    publicados = (prop.precio, prop.descripcion, prop.dormitorios,
                  prop.ambientes, prop.banos, prop.superficie_total,
                  prop.superficie_cubierta, prop.direccion, prop.barrio,
                  prop.ciudad, prop.latitud, prop.longitud, prop.moneda)
    if any(valor not in (None, "", 0) for valor in publicados):
        return False
    titulo = _palabras(prop.titulo)
    agencia = _palabras(str(prop.canonical_agency_id or "").split(":", 1)[-1])
    if not titulo or not agencia:
        return False
    return titulo <= agencia or agencia <= titulo


def detectar_tipo(texto: Any) -> str | None:
    if not texto:
        return None
    t = re.sub(r"\s+", " ", str(texto).lower())
    for clave, val in _TIPOS.items():
        if re.search(rf"\b{re.escape(clave)}", t):
            return val
    return None

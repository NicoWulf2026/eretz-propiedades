"""Geografia canonica de ERETZ sobre el snapshot oficial de GeoRef.

El problema que resuelve es concreto. Una ficha publica `Ubicacion: Alberdi` y
otra `Ubicacion: Cordoba Capital`, en el MISMO lugar del aviso. La primera es un
barrio de la ciudad de Cordoba; la segunda es la ciudad. Sin catalogo, las dos
son una cadena y tratarlas igual llena el dataset de ciudades que no existen.

La prueba de que hace falta un catalogo, y no una tabla de excepciones: en
GeoRef no hay ninguna localidad llamada `Alberdi`. Hay `Alberdi Viejo`,
`Colonia Alberdi`, `Villa Alberdi` y dos `Juan Bautista Alberdi`. El unico
`Alberdi` exacto es un Paraje en Chaco. **GeoRef no cataloga barrios**, asi que
una cadena que no matchea ninguna localidad es, muy probablemente, un barrio: la
respuesta correcta es no afirmar ciudad.

Decisiones de modelado, tomadas sobre los datos y no supuestas:

  - El nivel canonico de "ciudad" es `localidades_censales` (4.023), la
    localidad censal del INDEC. NO `asentamientos`, que son las mismas mas
    10.425 parajes: usarlo triplicaria la ambiguedad de nombres -de 270 nombres
    repetidos a 1.545- y haria matchear el Paraje Alberdi de Chaco con una
    propiedad de Cordoba. NO `municipios`, que son division administrativa y no
    coinciden con la ciudad.
  - CABA no existe como localidad: esta partida en quince comunas
    (`CABA - Comuna 4`). Para una propiedad portena la ciudad es la provincia,
    no la comuna, asi que se resuelve por alias contra la provincia.
  - El nombre solo NUNCA alcanza: `san pedro` son trece localidades censales
    distintas.

Las coordenadas solo desempatan candidatas que el nombre ya trajo. Nunca
inventan una ciudad que la fuente no nombro. Y desempatan sin radio absoluto,
porque la separacion entre homonimas es bimodal: o estan a menos de un
kilometro -son la misma cosa partida en dos registros- o a cientos. Se exige que
la mas cercana lo sea por un margen amplio; en el primer regimen eso nunca se
cumple y queda ambigua, que es la respuesta correcta.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.geo_reference import verified_rows

DIRECTORIO_POR_DEFECTO = Path(r"D:\INMO CAPITAL\ERETZ_GEO")
FUENTE = "georef:localidades_censales"

# Certeza de la resolucion.
EXACTA = "EXACT_CANONICAL"
POR_ALIAS = "ALIAS_MATCH"
POR_CONTEXTO = "CONTEXT_MATCH"
POR_COORDENADA = "COORDINATE_SUPPORTED"
AMBIGUA = "AMBIGUOUS"
NO_ENCONTRADA = "NOT_FOUND"
CONTRADICHA = "CONTRADICTED_BY_COORDINATES"

# De donde salio el dato.
DE_LA_FUENTE_ESTRUCTURADA = "SOURCE_STRUCTURED"
DE_TEXTO_DE_LA_FUENTE = "SOURCE_TEXT"
NORMALIZADA_CANONICA = "CANONICAL_NORMALIZED"
APOYADA_EN_COORDENADA = "COORDINATE_SUPPORTED"
DESCONOCIDA = "UNKNOWN"
PROVINCE_CONFLICT_REASON = "la provincia declarada contradice al catalogo"
DEPARTAMENTO_REASON = "nombra un departamento de la provincia declarada, no una localidad"
CABA_POR_POLIGONO_REASON = ("provincia declarada 'Buenos Aires' desempatada: la "
                            "coordenada cae dentro del poligono oficial de CABA (IGN)")


def geografia_publicable(geo: dict[str, Any] | None) -> dict[str, Any]:
    """Never turn a detected source/geometry conflict into public assertions.

    Operates on the geo coverage artifact, preserving both pieces of evidence.
    It does not choose coordinates over the source, nor discard the property.
    Legacy artifacts may still contain canonical dimensions despite conflict.
    """
    result = dict(geo or {})
    if result.get('estado_geografico') != 'GEO_CONFLICT':
        return result
    for field in ('provincia_canonica', 'departamento_canonico',
                  'municipio_canonico', 'localidad_canonica', 'localidad_id'):
        result[field] = None
    result['area_busqueda'] = {
        'nivel': 'SIN_AREA', 'nombre': None, 'id': None, 'origen': 'sin_area',
    }
    return result


def geografia_de_fila_publicable(fila: dict[str, Any], geo: dict[str, Any] | None) -> dict[str, Any]:
    """A newly recorded row conflict overrides an older coverage artifact."""
    extra = fila.get('extra')
    conflict = extra.get('geo_conflicto') if isinstance(extra, dict) else None
    if isinstance(conflict, dict) and conflict:
        geo = dict(geo or {}, estado_geografico='GEO_CONFLICT', conflicto=conflict)
    return geografia_publicable(geo)

# Caja de Argentina continental mas el sector antartico e islas. Sirve para
# descartar coordenadas invertidas o de otro pais, no para afirmar precision.
CAJA_ARGENTINA = (-90.0, -21.0, -74.0, -53.0)

# Cuanto mas cerca tiene que estar la mejor candidata que la siguiente para que
# la coordenada decida. No es un radio: es un margen relativo, y sale de que la
# separacion entre homonimas es bimodal (p5 = 0,8 km contra mediana de 400 km).
# Con este margen, dos registros del mismo lugar nunca desempatan.
MARGEN_DE_DESEMPATE = 10.0

# A partir de cuantos kilometros una coordenada contradice a la ciudad que la
# fuente publico. No es una tuerca: la aglomeracion urbana mas grande del pais
# -el Gran Buenos Aires- ronda los 40 km de radio, asi que al doble y medio de
# eso la propiedad no esta en esa localidad.
#
# Ataja un defecto real y frecuente: argentinasothebysrealty.com publica
# `ciudad = Ciudad Autonoma de Buenos Aires` en avisos cuyas coordenadas caen a
# 3,7 km de Lago Moreno, Rio Negro. El campo tiene la oficina de la
# inmobiliaria, no la propiedad; sin este chequeo esas casas de Bariloche
# quedaban afirmadas como porteñas.
CONTRADICE_A_KM = 100.0


def normalizar(valor: Any) -> str:
    """Nombre comparable: sin acentos, sin puntuacion, en minusculas."""
    plano = unicodedata.normalize("NFKD", str(valor or "").lower())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plano).strip()


@dataclass(frozen=True)
class Entidad:
    """Una entidad territorial oficial, con su jerarquia y su procedencia."""

    official_id: str
    official_name: str
    normalized_name: str
    provincia_id: str
    provincia: str
    departamento_id: str | None
    departamento: str | None
    municipio_id: str | None
    municipio: str | None
    lat: float | None
    lon: float | None
    fuente: str

    def a_dict(self) -> dict[str, Any]:
        return {
            "official_id": self.official_id,
            "official_name": self.official_name,
            "normalized_name": self.normalized_name,
            "provincia": self.provincia,
            "departamento": self.departamento,
            "municipio": self.municipio,
            "coordinates": None if self.lat is None else {"lat": self.lat,
                                                          "lon": self.lon},
            "source": self.fuente,
        }


@dataclass(frozen=True)
class Resolucion:
    """Que se resolvio, con cuanta certeza y con que evidencia."""

    entidad: Entidad | None
    certeza: str
    provenance: str
    candidatas: int
    motivo: str

    @property
    def resuelta(self) -> bool:
        return self.entidad is not None

    def a_dict(self) -> dict[str, Any]:
        return {
            "locality": self.entidad.official_name if self.entidad else None,
            "locality_id": self.entidad.official_id if self.entidad else None,
            "province": self.entidad.provincia if self.entidad else None,
            "department": self.entidad.departamento if self.entidad else None,
            "match": self.certeza,
            "provenance": self.provenance,
            "candidates": self.candidatas,
            "reason": self.motivo,
        }


def _en_argentina(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    sur, norte, oeste, este = CAJA_ARGENTINA
    return sur <= lat <= norte and oeste <= lon <= este


def _distancia(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Kilometros entre dos puntos."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    dfi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dfi / 2) ** 2
         + math.cos(fi1) * math.cos(fi2) * math.sin(dlambda / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


class Geografia:
    """Indice local del snapshot oficial.

    Se carga una vez y se consulta en memoria: la normalizacion corre sobre
    cientos de miles de propiedades y una consulta remota por propiedad seria
    inaceptable para el pipeline y descortes con un servicio publico.
    """

    def __init__(self, directorio: Path | str = DIRECTORIO_POR_DEFECTO) -> None:
        self.directorio = Path(directorio)
        self.entidades: list[Entidad] = []
        self.por_nombre: dict[str, list[Entidad]] = {}
        self.provincias: dict[str, str] = {}
        self.alias: dict[str, list[Entidad]] = {}
        self.alias_de_aglomerado: dict[str, Entidad] = {}
        self._cargar()

    # ------------------------------------------------------------- carga
    def _leer(self, archivo: str) -> list[dict[str, Any]]:
        ruta = self.directorio / archivo
        if not ruta.exists():
            raise FileNotFoundError(
                f"falta el snapshot {ruta}. Se baja con scripts/geo_snapshot.py")
        return verified_rows(self.directorio, ruta.stem)

    def _cargar(self) -> None:
        self.provincia_entidad: dict[str, Entidad] = {}
        for fila in self._leer("provincias.json"):
            self.provincias[fila["id"]] = fila["nombre"]
            centro = fila.get("centroide") or {}
            self.provincia_entidad[normalizar(fila["nombre"])] = Entidad(
                official_id=str(fila["id"]),
                official_name=fila["nombre"],
                normalized_name=normalizar(fila["nombre"]),
                provincia_id=str(fila["id"]),
                provincia=fila["nombre"],
                departamento_id=None, departamento=None,
                municipio_id=None, municipio=None,
                lat=centro.get("lat"), lon=centro.get("lon"),
                fuente="georef:provincias")

        for fila in self._leer("localidades_censales.json"):
            centro = fila.get("centroide") or {}
            entidad = Entidad(
                official_id=str(fila["id"]),
                official_name=fila["nombre"],
                normalized_name=normalizar(fila["nombre"]),
                provincia_id=str((fila.get("provincia") or {}).get("id") or ""),
                provincia=(fila.get("provincia") or {}).get("nombre") or "",
                departamento_id=str((fila.get("departamento") or {}).get("id")
                                    or "") or None,
                departamento=(fila.get("departamento") or {}).get("nombre"),
                municipio_id=str((fila.get("municipio") or {}).get("id")
                                 or "") or None,
                municipio=(fila.get("municipio") or {}).get("nombre"),
                lat=centro.get("lat"),
                lon=centro.get("lon"),
                fuente=FUENTE,
            )
            self.entidades.append(entidad)
            self.por_nombre.setdefault(entidad.normalized_name, []).append(
                entidad)

        self._cargar_alias()

    def _cargar_alias(self) -> None:
        """Alias apuntando a entidades canonicas, nunca creando nuevas.

        El unico alias estructural sale de una diferencia real del catalogo:
        CABA no tiene localidad censal propia, esta partida en quince comunas.
        Nadie publica "CABA - Comuna 4" como ciudad de un aviso, asi que las
        formas comerciales de la ciudad apuntan a sus comunas y la resolucion
        queda a nivel provincia.
        """
        caba = self.provincia_entidad.get(
            "ciudad autonoma de buenos aires")
        if caba is None:
            return
        # Se resuelve a la PROVINCIA, no a una comuna: nadie publica
        # "CABA - Comuna 4" como ciudad de un aviso, y elegir una comuna
        # inventaria una precision que la fuente no dio.
        for forma in ("caba", "ciudad autonoma de buenos aires",
                      "capital federal", "ciudad de buenos aires"):
            self.alias[forma] = [caba]
        self._cargar_alias_de_aglomerados()

    def _cargar_alias_de_aglomerados(self) -> None:
        """Cada parte de una localidad censal compuesta nombra a esa localidad.

        GeoRef cataloga algunos aglomerados con el nombre de todas sus partes:
        «Necochea - Quequen», «Mar del Tuyu - Mar de Aje - San Bernardo». Nadie
        publica eso como ciudad; publica «Necochea», y quedaba NOT_FOUND (91
        fichas medidas el 29-09).

        Solo si el nombre de la parte NO es ya una localidad en ningun lado y
        es parte de UN solo aglomerado: «Bella Vista» (de «Iglesia - Bella
        Vista», San Juan) tiene sus propias localidades y no se toca. Las
        comunas de CABA no entran: CABA se resuelve a la provincia.

        Y solo dentro de su provincia: «Parque Norte» es parte de un aglomerado
        de Cordoba y tambien un barrio en otras provincias; con otra provincia
        declarada sigue sin resolverse, no pasa a ser una contradiccion.
        El separador puede venir como «?»: asi trae el snapshot de GeoRef la
        raya de «Necochea - Quequen».
        """
        partes: dict[str, list[Entidad]] = {}
        for entidad in self.entidades:
            if not re.search(r"\s[-\u2013\u2014?]\s", entidad.official_name):
                continue
            if normalizar(entidad.provincia) == "ciudad autonoma de buenos aires":
                continue
            for parte in re.split(r"\s[-\u2013\u2014?]\s", entidad.official_name):
                clave = normalizar(parte)
                if len(clave) < 4 or clave.startswith("comuna"):
                    continue
                partes.setdefault(clave, []).append(entidad)
        for clave, entidades in partes.items():
            if (len(entidades) == 1 and clave not in self.por_nombre
                    and clave not in self.alias
                    and clave not in self.provincia_entidad):
                self.alias_de_aglomerado[clave] = entidades[0]

    # ---------------------------------------------------------- resolucion
    def _filtrar_por_contexto(self, candidatas: list[Entidad], *,
                              provincia: str | None,
                              departamento: str | None) -> list[Entidad]:
        if provincia:
            objetivo = normalizar(provincia)
            porprov = [e for e in candidatas
                       if normalizar(e.provincia) == objetivo]
            # Si la provincia contradice a TODAS, no se elige ninguna: el
            # contexto es evidencia, no una sugerencia que se pueda ignorar.
            candidatas = porprov
        if departamento and len(candidatas) > 1:
            objetivo = normalizar(departamento)
            pordepto = [e for e in candidatas
                        if normalizar(e.departamento or "") == objetivo]
            if pordepto:
                candidatas = pordepto
        return candidatas

    def _desempatar_por_coordenada(self, candidatas: list[Entidad],
                                   lat: float, lon: float) -> Entidad | None:
        conmedida = [(e, _distancia(lat, lon, e.lat, e.lon))
                     for e in candidatas if e.lat is not None]
        if len(conmedida) < 2:
            return conmedida[0][0] if conmedida else None
        conmedida.sort(key=lambda par: par[1])
        mejor, segunda = conmedida[0], conmedida[1]
        if mejor[1] <= 0:
            return mejor[0]
        if segunda[1] / mejor[1] >= MARGEN_DE_DESEMPATE:
            return mejor[0]
        return None

    def _capital_de(self, provincia: str | None) -> Entidad | None:
        """La ciudad capital de una provincia, sacada del catalogo.

        "Cordoba Capital" es como se publica comercialmente la ciudad de
        Cordoba. No hace falta una tabla a mano: en GeoRef la capital es la
        localidad del departamento `Capital` de esa provincia, salvo CABA, que
        no tiene departamentos con ese nombre y ya resuelve por alias.
        """
        if not provincia:
            return None
        objetivo = normalizar(provincia)
        if objetivo not in self.provincia_entidad:
            return None
        de_la_provincia = [e for e in self.entidades
                           if normalizar(e.provincia) == objetivo]

        # La capital suele llamarse como su provincia: "Cordoba Capital" es la
        # localidad Cordoba de Cordoba, "Santa Fe Capital" la de Santa Fe.
        homonimas = [e for e in de_la_provincia
                     if e.normalized_name == objetivo]
        if len(homonimas) == 1:
            return homonimas[0]

        # Donde no coincide el nombre, manda el departamento capital. Solo 12
        # de las 24 provincias lo llaman asi -Santa Fe usa "La Capital"- por eso
        # esta regla no alcanza sola y va segunda.
        del_departamento = [e for e in de_la_provincia
                            if normalizar(e.departamento or "")
                            in ("capital", "la capital")]
        if len(del_departamento) == 1:
            return del_departamento[0]
        return None

    def provincia_declarada(self, texto: Any) -> tuple[str | None, str | None]:
        """Que provincia nombra lo que la fuente escribio en `provincia`.

        Devuelve `(provincia canonica, zona sobrante)`.

        Hay fuentes que rotulan una ZONA como provincia. No es un error de
        extraccion: la ficha de `dardopropiedades` publica, con todas las
        letras, `Provincia: Bs.As. Costa Atlantica`, y el resto de su
        geografia esta bien -`Ciudad: Mar del Plata`, `Direccion: Moreno
        2568`-. Es la taxonomia de otra plataforma debajo de la misma
        etiqueta. Medido: 612 propiedades del padron tienen en `provincia`
        algo que no es una provincia, y 567 son de esta forma.

        La regla NO adivina: se queda con la provincia **que el propio texto
        nombra**. `Bs.As. Costa Atlantica` empieza diciendo Buenos Aires, y
        `Buenos Aires Interior` tambien. Lo que sobra se devuelve aparte, como
        zona, porque es informacion real de la fuente y tirarla seria perder
        evidencia para no publicar un campo mal.

        Lo que no nombra una provincia devuelve `(None, None)`. `San Salvador`
        -una ciudad de Jujuy escrita en el campo provincia- queda sin
        resolver, que es la respuesta correcta: la fuente se equivoco de
        nivel y nosotros no sabemos cual quiso decir.

        La comparacion es por PALABRAS ENTERAS y no por prefijo de caracteres.
        En este proyecto la suposicion de limite de palabra ya fallo cinco
        veces; aca un prefijo suelto haria que `Cordobes` empiece por
        `Cordoba`.
        """
        palabras = normalizar(texto).split()
        if not palabras:
            return None, None
        # De la frase mas larga a la mas corta: `tierra del fuego` tiene que
        # ganarle a `tierra`, si alguna vez existiera esa provincia.
        for corte in range(len(palabras), 0, -1):
            candidata = " ".join(palabras[:corte])
            canonica = self._provincia_por_nombre(candidata)
            if canonica:
                resto = " ".join(palabras[corte:])
                return canonica, (resto or None)
        return None, None

    def _provincia_por_nombre(self, normalizada: str) -> str | None:
        """El nombre oficial de una provincia, o None.

        Acepta las formas que las fuentes escriben de verdad y que el catalogo
        no trae: la abreviatura `bs as`, los nombres comerciales de CABA, y
        `tierra del fuego` a secas -el catalogo la llama `Tierra del Fuego,
        Antartida e Islas del Atlantico Sur`-. No se inventan provincias: cada
        alias apunta a una entidad que ya existe.
        """
        entidad = self.provincia_entidad.get(normalizada)
        if entidad is not None:
            return entidad.provincia
        for alias, oficial in (
                ("bs as", "buenos aires"),
                ("pcia de buenos aires", "buenos aires"),
                ("provincia de buenos aires", "buenos aires"),
                ("caba", "ciudad autonoma de buenos aires"),
                ("capital federal", "ciudad autonoma de buenos aires"),
                ("ciudad de buenos aires", "ciudad autonoma de buenos aires"),
                ("tierra del fuego", "tierra del fuego antartida e islas "
                                     "del atlantico sur")):
            if normalizada == alias:
                destino = self.provincia_entidad.get(oficial)
                if destino is not None:
                    return destino.provincia
        return None

    def resolver_compuesta(self, texto: Any, *, provincia: str | None = None,
                           lat: float | None = None, lon: float | None = None
                           ) -> tuple[Resolucion, str | None] | None:
        """«Parte, Parte, Partido, Region»: la localidad que la cadena nombra.

        Fuentes que publican la ubicacion como una cadena jerarquica que entera
        no resuelve (medido el 28-09, ~590 fichas sin ciudad): «Rosario, Santa
        Fe» (`ferrari` 152), «Olivos, Vicente López, G.B.A. Zona Norte»
        (`d'aria`), «Morón, Bs.As. G.B.A. Oeste», «Belgrano, CABA», «NORDELTA,
        TIGRE». Devuelve `(resolucion, barrio)` o None si no se puede afirmar:

          - la provincia sale de la propia cadena («Santa Fe», «Bs.As. G.B.A.
            Oeste», «G.B.A. Zona Norte») y no puede contradecir la declarada;
          - se acepta la primera parte que resuelve en ese contexto, y si otra
            parte nombra un partido, tiene que ser el departamento oficial de
            esa localidad;
          - sin provincia en la cadena, solo la ULTIMA parte y solo si es unica
            en el pais (el catalogo del INDEC agrupa el GBA por partido:
            «NORDELTA, TIGRE» es la localidad canonica Tigre);
          - «CABA» pasa por `resolver_localidad` (y por el poligono si hace falta).
        El barrio es la parte inmediatamente anterior a la resuelta.
        """
        partes = [p.strip() for p in str(texto or "").split(",") if p.strip()]
        if len(partes) < 2:
            return None
        # «Belgrano, CABA»: la ciudad es CABA y lo anterior es barrio. No se
        # busca «Belgrano» como localidad de ninguna provincia.
        for i, parte in enumerate(partes):
            if normalizar(parte) in self.alias:
                r = self.resolver_localidad(parte, provincia=provincia, lat=lat, lon=lon)
                return (r, partes[i - 1] if i > 0 else None) if r.resuelta else None
        contexto, resto = None, []
        for parte in partes:
            n = normalizar(parte)
            if re.fullmatch(r"(?:g ?b ?a|gran buenos aires)(?: zona (?:norte|sur|oeste))?"
                            r"|zona (?:norte|sur|oeste)", n):
                contexto = contexto or "Buenos Aires"
                continue
            prov, _zona = self.provincia_declarada(parte)
            if prov and normalizar(prov) != "ciudad autonoma de buenos aires":
                if contexto and normalizar(contexto) != normalizar(prov):
                    return None
                contexto = prov
                resto.append(parte)  # puede ser tambien la capital homonima
                continue
            resto.append(parte)
        declarada = provincia if provincia and normalizar(provincia) in self.provincia_entidad else None
        if contexto and declarada and normalizar(contexto) != normalizar(declarada) \
                and normalizar(declarada) != "ciudad autonoma de buenos aires":
            return None
        contexto = contexto or declarada
        nombrados = {normalizar(p) for p in resto
                     if contexto and self._es_departamento_de(normalizar(p), contexto)}
        for i, parte in enumerate(resto):
            n = normalizar(parte)
            if contexto and normalizar(contexto) == n and i < len(resto) - 1:
                continue  # la provincia como parte: solo si no queda otra
            if contexto:
                r = self.resolver_localidad(parte, provincia=contexto, lat=lat, lon=lon)
            elif i == len(resto) - 1:
                r = self.resolver_localidad(parte, lat=lat, lon=lon)
                if r.certeza != EXACTA:
                    return None
            else:
                continue
            if not r.resuelta:
                continue
            departamento = normalizar(r.entidad.departamento or "")
            if nombrados and departamento not in nombrados and n not in nombrados:
                return None
            barrio = resto[i - 1] if i > 0 else None
            if barrio and normalizar(barrio) in (n, normalizar(contexto or ""),
                                                 normalizar(r.entidad.official_name)):
                barrio = None  # «Córdoba, Córdoba»: no es un barrio
            # Una direccion o una frase no es un barrio: «Bolla al 1400»,
            # «calle Estrada e/ 143 y 145», «Vias a Libertador».
            if barrio and (re.search(r"\d", barrio) or len(barrio) > 40 or re.match(
                    r"(?:vias?|calle|av|avenida|ruta|entre|esquina)\b", normalizar(barrio))
                    or re.search(r"\s(?:al?|e/)\s", barrio, re.I)):
                barrio = None
            return r, barrio
        return None

    def _es_departamento_de(self, clave: str, provincia: str) -> bool:
        objetivo = normalizar(provincia)
        return any(normalizar(e.provincia) == objetivo
                   and normalizar(e.departamento or "") == clave
                   for e in self.entidades)

    @staticmethod
    def _caba_confirmada_por_poligono(entidad: Entidad, provincia: str,
                                      lat: Any, lon: Any) -> bool:
        """CABA nombrada + provincia «Buenos Aires»: solo la geometria desempata.

        «Buenos Aires» a secas es el nombre de la provincia Y el de la ciudad,
        y hay plantillas que lo ponen en el campo provincia de avisos portenos
        (`cantale`, `agostinelli`, `blanco`: 99 fichas medidas el 28-09). Pero
        tambien hay avisos del conurbano con «CABA» de plantilla, y el
        conurbano rodea a la Ciudad: ni un radio ni un centroide separan
        Avellaneda de Barracas.

        Por eso la unica evidencia aceptada es la CONTENCION de la coordenada
        en el poligono oficial de CABA (IGN), lejos del limite. Sin coordenada,
        afuera, o sobre la frontera, el conflicto se mantiene (fail-closed).
        Cualquier otra provincia declarada sigue contradiciendo.
        """
        if (normalizar(entidad.provincia) != "ciudad autonoma de buenos aires"
                or normalizar(provincia) != "buenos aires"):
            return False
        from connectors.poligono_caba import DENTRO, contencion
        return contencion(lat, lon) == DENTRO

    def resolver_localidad(self, texto: Any, *, provincia: str | None = None,
                           departamento: str | None = None,
                           lat: float | None = None,
                           lon: float | None = None,
                           provenance: str = DE_TEXTO_DE_LA_FUENTE
                           ) -> Resolucion:
        """Resuelve una cadena a una localidad canonica, o no la resuelve.

        Preferir no afirmar antes que afirmar mal: una ciudad equivocada no se
        distingue despues de una correcta, y una ausente si.
        """
        def controlar(resolucion: "Resolucion") -> "Resolucion":
            """Descarta la resolucion si la coordenada la contradice.

            La ciudad que publica una ficha puede ser la de la inmobiliaria y
            no la del inmueble. Cuando las dos evidencias se contradicen no se
            elige una: no afirmar es preferible a afirmar mal, porque una
            ciudad equivocada despues no se distingue de una correcta.
            """
            entidad = resolucion.entidad
            if (entidad is not None and provincia
                    and normalizar(entidad.provincia) != normalizar(provincia)):
                if self._caba_confirmada_por_poligono(entidad, provincia,
                                                      lat, lon):
                    return Resolucion(entidad, POR_COORDENADA,
                                      APOYADA_EN_COORDENADA,
                                      resolucion.candidatas,
                                      CABA_POR_POLIGONO_REASON)
                return Resolucion(None, CONTRADICHA, DESCONOCIDA,
                                  resolucion.candidatas,
                                  PROVINCE_CONFLICT_REASON)
            if entidad is None or entidad.lat is None:
                return resolucion
            if not _en_argentina(lat, lon):
                return resolucion
            km = _distancia(lat, lon, entidad.lat, entidad.lon)
            if km <= CONTRADICE_A_KM:
                return resolucion
            return Resolucion(
                None, CONTRADICHA, DESCONOCIDA, resolucion.candidatas,
                f"la coordenada esta a {km:.0f} km de "
                f"{entidad.official_name}")

        clave = normalizar(texto)
        if not clave:
            return Resolucion(None, NO_ENCONTRADA, DESCONOCIDA, 0,
                              "sin texto que resolver")

        # Una "provincia" que no nombra una provincia no puede contradecir a
        # una. En los datos reales ese campo trae zonas comerciales -"GBA Sur"-
        # y hasta rutas de API sin normalizar. Tratarlas como contradiccion
        # descartaba la candidata correcta: 1.498 avisos de La Plata quedaban
        # sin ciudad por decir "GBA Sur" en el campo provincia.
        if provincia and normalizar(provincia) not in self.provincia_entidad:
            provincia = None

        if clave in self.alias:
            candidatas = self.alias[clave]
            entidad = candidatas[0]
            return controlar(Resolucion(
                entidad, POR_ALIAS, NORMALIZADA_CANONICA, len(candidatas),
                f"alias de {entidad.provincia}"))

        capital = re.fullmatch(r"(?:(.+?) )?capital", clave)
        if capital:
            nombrada = capital.group(1)
            entidad = self._capital_de(nombrada or provincia)
            if entidad is not None:
                return controlar(Resolucion(
                    entidad, POR_ALIAS, NORMALIZADA_CANONICA, 1,
                    f"capital de {entidad.provincia}"))

        candidatas = list(self.por_nombre.get(clave, ()))
        aglomerado = self.alias_de_aglomerado.get(clave)
        if (not candidatas and aglomerado is not None
                and (not provincia
                     or normalizar(provincia) == normalizar(aglomerado.provincia))):
            return controlar(Resolucion(
                aglomerado, POR_ALIAS, NORMALIZADA_CANONICA, 1,
                f"parte del aglomerado {aglomerado.official_name}"))
        if not candidatas:
            # GeoRef no cataloga barrios: lo mas probable es que sea uno.
            return Resolucion(None, NO_ENCONTRADA, DESCONOCIDA, 0,
                              "no hay localidad canonica con ese nombre")

        total = len(candidatas)
        if total == 1 and not provincia:
            return controlar(Resolucion(
                candidatas[0], EXACTA, NORMALIZADA_CANONICA, 1,
                "unica localidad con ese nombre"))

        filtradas = self._filtrar_por_contexto(
            candidatas, provincia=provincia, departamento=departamento)
        if not filtradas:
            if provincia and self._es_departamento_de(clave, provincia):
                # «San Jeronimo, Santa Fe» (`metro`, lotes en Monje) o «Colon,
                # Cordoba» (`jm norte`, 38): nombran un DEPARTAMENTO de la
                # provincia declarada, y la unica localidad homonima esta en
                # otra provincia. No hay contradiccion: la provincia es cierta y
                # la localidad no se afirma. 51 de 288 conflictos medidos el 28-09.
                return Resolucion(None, AMBIGUA, DESCONOCIDA, total,
                                  DEPARTAMENTO_REASON)
            return Resolucion(None, AMBIGUA, DESCONOCIDA, total,
                              PROVINCE_CONFLICT_REASON)
        if len(filtradas) == 1:
            certeza = EXACTA if total == 1 else POR_CONTEXTO
            return controlar(Resolucion(
                filtradas[0], certeza, NORMALIZADA_CANONICA, total,
                "resuelta por contexto territorial"))

        if _en_argentina(lat, lon):
            elegida = self._desempatar_por_coordenada(filtradas, lat, lon)
            if elegida is not None:
                return Resolucion(elegida, POR_COORDENADA,
                                  APOYADA_EN_COORDENADA, total,
                                  "la coordenada separa a una sola candidata")

        return Resolucion(None, AMBIGUA, DESCONOCIDA, total,
                          f"{len(filtradas)} candidatas y nada que las separe")


@lru_cache(maxsize=4)
def geografia(directorio: str = str(DIRECTORIO_POR_DEFECTO)) -> Geografia:
    """Instancia compartida: el snapshot se lee una sola vez por proceso."""
    return Geografia(directorio)

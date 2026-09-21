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

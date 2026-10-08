#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Una base lista para servir la API, armada con datos locales reales.

Se deriva de los artefactos locales y del contrato de API vigente, con indices
para filtros, precio y area de busqueda. Su cantidad y alcance se miden en cada
construccion; no representa automaticamente el catalogo publicado en Supabase.

**Es derivada y desechable.** Se reconstruye entera desde los artefactos
locales, no se edita a mano y no es fuente de verdad de nada. Si el resultado
no gusta, se arregla el generador y se vuelve a correr.

No escribe en ninguna base productiva.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.api_contract import CONTRATO_API_VERSION, fila_de_api  # noqa: E402
from api.slugs import sin_acento  # noqa: E402
from scripts.prepare_api_v2_snapshot import _publish_no_clobber  # noqa: E402


def publish_snapshot(temporary: Path, output: Path, *, replace: bool = False) -> None:
    """Replacement must be explicit, including a destination created mid-build."""
    if replace:
        os.replace(temporary, output)
    else:
        _publish_no_clobber(temporary, output)


@contextmanager
def _snapshot_connections(source: Path, temporary: Path):
    """Close handles and clean only our exclusively created build."""
    owned = False
    origen = api = None
    try:
        with temporary.open('xb'):
            owned = True
        origen = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        api = sqlite3.connect(temporary)
        yield origen, api
    finally:
        try:
            if api is not None:
                api.close()
        finally:
            try:
                if origen is not None:
                    origen.close()
            finally:
                if owned:
                    temporary.unlink(missing_ok=True)
from scripts.property_contract import FILTRO_OPERACION, alcances  # noqa: E402
from scripts.image_quality import is_known_page_asset  # noqa: E402
from scripts.plan_de_escritura import agencias_con_web_ajena  # noqa: E402
from scripts.property_freshest import (CAMPOS_FUSIONABLES,  # noqa: E402
                                       fusionar, mas_frescas)
from scripts.run_rollout import (FRACCION_COMPARTIDA,  # noqa: E402
                                 MINIMO_PARA_JUZGAR)
from connectors.base import (RE_TIPO_ACCESORIO, detectar_operacion,  # noqa: E402
                             detectar_tipo, geografia)
from connectors.exterior import (POLITICA_PUBLICA, evidencia_de_exterior,  # noqa: E402
                                 publicable)
from connectors import poligono_caba  # noqa: E402
from connectors import poligono_provincia  # noqa: E402
from connectors.coherencia import _es_simbolico  # noqa: E402
from connectors.geografia import (PROVINCIA_POR_POLIGONO_REASON,  # noqa: E402
                                  CABA_POR_POLIGONO_REASON,  # noqa: E402
                                  PROVINCE_CONFLICT_REASON)
from scripts.geo_coverage_audit import (cargar_cache,  # noqa: E402
                                        catalogo_de_localidades,
                                        cobertura_de_fila)
from scripts.snapshot_certificadas import (conocidas_de, decidir,  # noqa: E402
                                           paquetes_vigentes)
from connectors.generico import es_url_de_categoria  # noqa: E402
import heapq  # noqa: E402
import re  # noqa: E402
import unicodedata  # noqa: E402


def _sin_tildes(texto: str) -> str:
    texto = re.sub(r"\s+", " ", (texto or "").lower())
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _texto_servible(valor: Any) -> Any:
    """El texto sin entidades HTML crudas, que el frontend mostraria tal cual.

    La v4 del 24-09 servia 1.524 titulos y descripciones de 102 agencias con
    «&amp;», «&#8211;» o «&lt;p&gt;». Se desescapa hasta dos veces (hay dobles:
    «&amp;nbsp;») y SOLO si hubo entidades se quitan las etiquetas que quedan
    a la vista. Los saltos de linea se conservan.
    """
    if not isinstance(valor, str):
        return valor
    texto = valor
    for _ in range(2):
        nuevo = html.unescape(texto)
        if nuevo == texto:
            break
        texto = nuevo
    if texto == valor:
        return valor
    texto = re.sub(r"</?[A-Za-z][^<>]{0,200}>", " ", texto).replace("\xa0", " ")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r" *\n *", "\n", texto).strip()
    return texto or None


# Una secuencia UTF-8 leida como latin-1: el byte inicial (C2-F4) seguido de
# sus bytes de continuacion (80-BF), que en latin-1 son «Ã³», «Â²», «ð\x9f…».
RE_MOJIBAKE = re.compile("[Â-ô][\u0080-¿]{1,3}")


def _sin_mojibake(valor: Any) -> Any:
    """Repara el mojibake por TRAMOS, cuando cada tramo se puede demostrar.

    La v4d servia 89 descripciones con «Ã³», muchas mezcladas con acentos
    buenos («realización … operaciÃ³n»): `connectors.texto.reparar` recodifica
    el texto ENTERO y ahi falla. Cada tramo se decodifica solo si es UTF-8
    valido; «Ã» suelta o «Ñandú» no se tocan.
    """
    if not isinstance(valor, str):
        return valor

    def tramo(m: "re.Match") -> str:
        try:
            return m.group(0).encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return m.group(0)
    return RE_MOJIBAKE.sub(tramo, valor)


# Las claves de `detectar_operacion` hasta el 04-10, que se buscaban como
# SUBCADENA: «rent» en «fRENTE», «sale» en «RoSALEs», «venta» en «VENTAnal».
# Solo sirven para reconocer una operacion que salio de ahi.
_OPERACION_POR_SUBCADENA = (("venta", "venta"), ("vender", "venta"), ("sale", "venta"),
                            ("alquiler", "alquiler"), ("alquilar", "alquiler"),
                            ("rent", "alquiler"))

# Tipos que un conector viejo guardo en ingles (`alta`: 16 filas servidas en
# la final_v6, de un cierre NEEDS_FIX que no se recertifica).
TIPOS_EN_INGLES = {"land": "terreno", "condo": "departamento",
                   "apartment": "departamento", "house": "casa"}


RE_MONOAMBIENTE = re.compile(r"\bmono\s?ambiente")
RE_DORM_EN_TITULO = re.compile(r"\d\s*dorm")


def _monoambiente_con_dormitorios(fila: dict[str, Any]) -> bool:
    """El titulo dice monoambiente y la fila dice 2 o mas dormitorios: es falso.

    P0 de final_v6 (04-10): `crestale` toma los dormitorios del menu del sitio (53 fichas)
    y `metro` servia un monoambiente con 15 dormitorios. En final_v7: 96 filas. Con 1
    dormitorio no se toca -'monoambiente dividido' es una convencion habitual-; si el
    titulo nombra sus propios dormitorios ('2 dorm + monoambiente') tampoco.
    """
    titulo = _sin_tildes(fila.get("titulo") or "")
    return ((fila.get("dormitorios") or 0) >= 2 and bool(RE_MONOAMBIENTE.search(titulo))
            and not RE_DORM_EN_TITULO.search(titulo))


TIPOS_NO_RESIDENCIALES = {"local", "oficina", "galpon"}
RE_MENCION_RESIDENCIAL = re.compile(
    r"\b(dorm|dormitorio|habitaci|vivienda|casa|departamento|depto|dpto|ph\b|monoambiente|suite|cuarto|"
    r"ambientes?\b|amb\b|recamara|caba[nn]a)")


def _no_residencial_con_dormitorios(fila: dict[str, Any]) -> bool:
    """Local, oficina o galpon con dormitorios que su propio texto no menciona: el conteo es ajeno.

    Mismo origen que el P0 de final_v6: el conteo sale del menu o de un widget de la pagina
    (`crestale` 108, `veiga` lo rotaba entre cargas, 06-10). En final_v7c: 420 filas sin ninguna
    mencion de vivienda, dormitorio o ambientes en titulo ni descripcion. Si la ficha menciona
    vivienda ('galpon con casa', 'oficina 3 ambientes') no se toca.
    """
    if fila.get("tipo_propiedad") not in TIPOS_NO_RESIDENCIALES or (fila.get("dormitorios") or 0) < 1:
        return False
    texto = _sin_tildes(f"{fila.get('titulo') or ''} {fila.get('descripcion') or ''}")
    return not RE_MENCION_RESIDENCIAL.search(texto)


def _operacion_por_subcadena(texto: str) -> str | None:
    t = (texto or "").lower()
    if "temporario" in t or "temporal" in t:
        return "alquiler_temporario"
    return next((val for clave, val in _OPERACION_POR_SUBCADENA if clave in t), None)


def _operacion_sin_evidencia(fila: dict[str, Any]) -> bool:
    """La operacion salio SOLO de una subcadena del titulo o la URL.

    Asi la tiene una fila heredada -servida o de la base- que nunca paso por el
    detector de palabra entera: 172 de las 516 filas falsas de la final_v6 (04-10)
    eran de agencias sin cierre vigente, que la recertificacion no alcanza
    (`pelay` «Dto 2 Amb Al Frente» USD 63.000 como ALQUILER, `ruiz` «Av Rosales»
    ARS 450.000 como VENTA). Si la descripcion la nombra como palabra, hay
    evidencia y se respeta.
    """
    op = fila.get("operacion")
    if op not in ("venta", "alquiler"):
        return False
    texto = f"{fila.get('titulo') or ''} {fila.get('source_url') or ''}"
    return (_operacion_por_subcadena(texto) == op and detectar_operacion(texto) != op
            and detectar_operacion(fila.get("descripcion") or "") != op)


def _corregir_heredada(fila: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Una fila sin paquete fresco, sin la operacion por subcadena ni el tipo en ingles.

    La operacion falsa queda vacia -nunca se deduce del precio: eso seria
    inventarla- y la fila sale del filtro venta/alquiler. En una fila servida
    tambien se corrigen el `documento` y los `alcances` que la API devuelve.
    """
    nueva, cambios = dict(fila), []
    if _operacion_sin_evidencia(fila):
        nueva["operacion"] = None
        cambios.append("operacion")
    if _monoambiente_con_dormitorios(fila) or _no_residencial_con_dormitorios(fila):
        nueva["dormitorios"] = None
        cambios.append("dormitorios")
    tipo = TIPOS_EN_INGLES.get(str(fila.get("tipo_propiedad") or "").strip().lower())
    if tipo:
        nueva["tipo_propiedad"] = tipo
        cambios.append("tipo")
    if cambios and isinstance(fila.get("documento"), str):
        documento = json.loads(fila["documento"])
        documento["operacion"] = nueva["operacion"]
        documento["tipo_propiedad"] = nueva["tipo_propiedad"]
        if "dormitorios" in cambios:
            documento["dormitorios"] = None
        if "operacion" in cambios:
            documento["alcances"] = [a for a in documento.get("alcances") or []
                                     if a != FILTRO_OPERACION]
            nueva["alcances"] = json.dumps(documento["alcances"], ensure_ascii=False)
        nueva["documento"] = json.dumps(documento, ensure_ascii=False)
    return nueva, cambios


from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)
try:  # raiz del estado operativo configurable (ERETZ_DATA_ROOT)
    from scripts.rutas_de_datos import dato  # noqa: E402
except ImportError:  # corrido como `python scripts/x.py`
    from rutas_de_datos import dato  # noqa: E402

SNAPSHOT_VERSION = "api_snapshot_v4"

# Review threshold only: shared building renders can occur in many listings.
# Exclusion requires an independent page-asset signal, never frequency alone.
FICHAS_PARA_SER_COMPARTIDA = 5

# «inmobiliaria-» es un patron de NOMBRE de archivo, no de recurso: `cip` y
# `next inmobiliaria` suben sus fotos como `inmobiliaria-cip-lotes-...-01.jpg`.
# Aplicado solo, dejaba 128 fichas sin ninguna foto (medido 02-10 sobre los
# paquetes: next 108, cip 20; 3.481 fotos). El runner ya exigia repeticion
# para descartar (`descartar_imagenes_compartidas`); aca se exige lo mismo
# cuando ese nombre es la UNICA senal. Un logo sigue cayendo por `logo`.
PATRON_SOLO_DE_NOMBRE = "inmobiliaria-"


def _es_recurso_de_pagina(url: Any, veces: int) -> bool:
    if not is_known_page_asset(url):
        return False
    texto = str(url).lower()
    if PATRON_SOLO_DE_NOMBRE in texto and not is_known_page_asset(
            texto.replace(PATRON_SOLO_DE_NOMBRE, "")):
        return veces >= FICHAS_PARA_SER_COMPARTIDA
    return True

ESQUEMA = """
create table if not exists propiedades (
    id text primary key,
    agency_id text not null,
    source_url text not null,
    titulo text,
    descripcion text,
    operacion text,
    tipo_propiedad text,
    precio real,
    moneda text,
    ambientes integer,
    dormitorios integer,
    banos integer,
    superficie_total real,
    superficie_cubierta real,
    imagenes_n integer not null default 0,
    latitud real,
    longitud real,
    localidad text,
    localidad_id text,
    municipio text,
    departamento text,
    provincia text,
    barrio text,
    area_nivel text not null,
    area_nombre text,
    -- Los mismos nombres sin acentos y en minuscula. Estan guardados en vez
    -- de calcularse al vuelo porque el autocompletado se dispara con cada
    -- tecla: resolverlo con una funcion de Python sobre las 57.665 filas
    -- medio 436 ms, y con estas columnas indexadas vuelve a ser una busqueda
    -- por prefijo. El dato original no se toca; esto es para comparar.
    area_nombre_plano text,
    barrio_plano text,
    geo_estado text,
    alcances text not null,
    documento text not null
);
-- Los indices salen de las consultas que el frontend hace, no de "por si
-- acaso": listado filtrado por operacion y tipo, rango de precio, y busqueda
-- por area. Cada uno se justifica con una consulta real o no va.
create index if not exists ix_operacion on propiedades(operacion);
create index if not exists ix_tipo on propiedades(tipo_propiedad);
-- Compuesto porque el filtro mas frecuente del listado son los dos juntos.
-- Medido: con `ix_operacion` solo, operacion+tipo tardaba 167 ms porque
-- filtraba 42.536 filas por el segundo campo.
create index if not exists ix_operacion_tipo
    on propiedades(operacion, tipo_propiedad);
create index if not exists ix_precio on propiedades(moneda, precio);
create index if not exists ix_area on propiedades(area_nivel, area_nombre);
-- Prefijo sin acentos: es exactamente lo que consulta el autocompletado.
-- Los indices llevan TAMBIEN las columnas que la consulta agrupa y devuelve,
-- porque si no el planificador prefiere `ix_area` -que cubre el `group by`- y
-- filtra escaneando. Medido sobre las 57.665 filas: con el indice de una sola
-- columna la consulta tardaba 469 ms; con estos, 2,8 ms. `ANALYZE` no
-- alcanzaba: el planificador seguia eligiendo mal con estadisticas.
create index if not exists ix_area_plano
    on propiedades(area_nombre_plano, area_nivel, area_nombre);
create index if not exists ix_barrio_plano
    on propiedades(barrio_plano, barrio);
create index if not exists ix_localidad on propiedades(localidad);
create index if not exists ix_agencia on propiedades(agency_id);
-- El conteo del mapa sin otros filtros: con `geo_estado` adentro es un
-- indice cubriente y cuenta la caja en 4 ms en vez de 549. La API lo usa
-- SOLO en ese caso; ver `mapa` en `api/v2.py`, donde esta lo medido.
create index if not exists ix_coord_geo on propiedades(latitud, longitud, geo_estado);

-- Busqueda por texto. Sin esto, `/buscar` hace un scan completo: 409 ms
-- medidos sobre las 58.427, que para una caja de busqueda es demasiado.
-- FTS5 viene con SQLite y no agrega dependencias.
create virtual table if not exists busqueda using fts5(
    id unindexed, titulo, descripcion, barrio, area_nombre,
    tokenize = "unicode61 remove_diacritics 2"
);

-- Lo que la snapshot declara de si misma y la API puede usar:
-- `orden_de_filas = id`: las filas se insertaron en orden de `id`, y por eso
--   el `rowid` de `busqueda` sigue ese orden.
-- `busqueda_rowid = propiedades`: cada fila de `busqueda` lleva el `rowid` de
--   su fila en `propiedades`, y las dos se pueden unir por `rowid`.
create table if not exists snapshot_meta (clave text primary key, valor text);
"""


def _leer_jsonl(ruta: Path, clave: str = "hash_dedup") -> dict[str, dict[str, Any]]:
    fuera: dict[str, dict[str, Any]] = {}
    if not ruta.exists():
        return fuera
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            fila = json.loads(linea)
            if fila.get(clave):
                fuera[fila[clave]] = fila
    return fuera


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(base_canonica()))
    ap.add_argument("--gate",
                    default=str(base_canonica().parent / "PROPERTY_QUALITY_GATE.jsonl"))
    ap.add_argument("--cobertura",
                    default=str(dato('ERETZ_GEO', 'GEO_COVERAGE_AUDIT.jsonl')))
    ap.add_argument("--directorio",
                    default=str(Path(str(dato('agency_platform_directory.jsonl')))))
    ap.add_argument('--paquetes', type=Path,
                    default=Path(str(dato('ERETZ_AGENCY_CERTIFICATION_20260827', 'agencies'))))
    ap.add_argument("--salida", default=str(dato('ERETZ_API_CONTRACT')))
    ap.add_argument('--replace-derived', action='store_true',
                    help='replace an existing derived snapshot atomically after successful construction')
    # Las dos decisiones de `snapshot_certificadas`, cada una explicita: sin
    # estas banderas la snapshot sale exactamente como antes.
    ap.add_argument('--sumar-certificadas', action='store_true',
                    help='sumar las propiedades de inventarios certificados vigentes que la '
                         'preingestion no tiene, y refrescar los avisos que cambiaron de URL')
    ap.add_argument('--retirar-ausentes', action='store_true',
                    help='no servir filas que ya no estan en el inventario COMPLETO vigente '
                         'de su agencia')
    # Politica P1 (29-09): se retira solo con muerte demostrada en la propia URL.
    # El archivo lo produce `scripts/verificar_retiros.py`; aca se retira lo que
    # dice REMOVED y ademas sigue ausente del inventario completo al construir.
    ap.add_argument('--retiros-verificados', type=Path, default=None,
                    help='JSONL de verificar_retiros.py: se retiran solo las REMOVED')
    ap.add_argument('--servida', type=Path, default=None,
                    help='snapshot SERVIDA: sus filas que la candidata perderia sin motivo de '
                         'politica se conservan tal cual (P1/P8; ver _servidas_a_conservar)')
    ap.add_argument('--ledger', type=Path, default=None,
                    help='ledger de certificacion (por defecto, junto a --paquetes)')
    ap.add_argument("--cache-geometrica",
                    default=str(dato('ERETZ_GEO', 'GEO_REVERSE_CACHE.jsonl')))
    args = ap.parse_args()
    salida = Path(args.salida)
    destino = salida / 'ERETZ_API_SNAPSHOT.sqlite3'
    if Path(args.db).resolve() == destino.resolve():
        ap.error('output must differ from source; the source is immutable')
    if destino.exists() and not args.replace_derived:
        ap.error('output already exists; choose a new path or explicitly --replace-derived')
    exigir_base_vigente(args.db)

    # Una propiedad leida en la web de OTRO no es de esta inmobiliaria, y el
    # buscador es donde se veria: `Barreira Bienes Raices` tiene cargada la
    # pagina de socios de una asociacion que comparten tres inmobiliarias, y
    # 729 propiedades leidas de ahi. La misma retencion que aplica el plan de
    # escritura tiene que aplicar el indice de lectura.
    ajenas = agencias_con_web_ajena(Path(args.directorio))
    geo = _leer_jsonl(Path(args.cobertura))
    # Tambien los NEEDS_FIX que solo fallan por campos, con sus campos
    # EXTRACTED y valores presentes: `blanco` servia 1.127 titulos «Blanco
    # Propiedades» del 03-09 teniendo los reales en su paquete del 25-09.
    frescas = mas_frescas(args.paquetes, parciales=True)
    gate = _leer_jsonl(Path(args.gate))

    salida.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f'{destino.name}.building.{os.getpid()}')
    with _snapshot_connections(Path(args.db), temporal) as (origen, api):
        resumen = _build_contents(origen, api, args, ajenas, geo, frescas, gate, destino)
        # Windows publication requires all SQLite file handles closed first.
        api.close()
        origen.close()
        publish_snapshot(temporal, destino, replace=args.replace_derived)
    (salida / "ERETZ_API_SNAPSHOT_SUMMARY.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


def _publicable_en_argentina(cruda: dict[str, Any], fresca: dict[str, Any] | None) -> bool:
    """False para lo publicado fuera de Argentina (marcado o con evidencia)."""
    if not publicable((fresca or {}).get("extra")) or not publicable(cruda.get("extra")):
        return False
    try:
        catalogo = geografia()
        es_argentina = lambda texto: catalogo.resolver_localidad(texto).resuelta  # noqa: E731
    except (OSError, ValueError):
        es_argentina = lambda texto: True  # noqa: E731  sin catalogo no se afirma nada
    extra = cruda.get("extra") if isinstance(cruda.get("extra"), dict) else {}
    return not evidencia_de_exterior(
        cruda.get("titulo"), cruda.get("ciudad"), cruda.get("barrio"),
        extra.get("pais_publicado") or extra.get("pais"), es_argentina,
        lat=cruda.get("latitud"), lon=cruda.get("longitud"))


CABA = "Ciudad Autónoma de Buenos Aires"

# Los campos de los que sale la cobertura geografica de una fila.
CAMPOS_GEO = ("ciudad", "barrio", "provincia", "latitud", "longitud")


def _cobertura_de_la_fila_servida(cobertura: dict[str, Any] | None, base: dict[str, Any],
                                  cruda: dict[str, Any], hash_dedup: str | None,
                                  localidades: dict[str, Any], geometria: dict[str, Any]
                                  ) -> tuple[dict[str, Any] | None, str | None]:
    """La cobertura de la fila que se SIRVE, no la de la preingestion del 03-09.

    `GEO_COVERAGE_AUDIT` se armo sobre la fila vieja. Cuando la lectura fresca
    trae otra ciudad, barrio, provincia o coordenada, esa cobertura describe
    una fila que ya no es la servida: medido el 29-09, 12.108 filas fusionadas
    cambiaban de geografia y 3.816 ganaban una localidad demostrada que la
    snapshot no mostraba nunca.

    Una localidad ya demostrada no se pierde por un vacio: `bottega` servia
    «Rosario» y su lectura fresca dejo solo el barrio («Parque Field»), 69
    filas. Sin evidencia contraria -otra localidad o un conflicto- se conserva
    la que habia.
    """
    if all(cruda.get(k) == base.get(k) for k in CAMPOS_GEO):
        return cobertura, None
    recalculada = cobertura_de_fila(cruda, cruda.get("connector"), hash_dedup,
                                    localidades, geometria)
    if ((cobertura or {}).get("localidad_canonica")
            and not recalculada.get("localidad_canonica")
            and recalculada.get("estado_geografico") != "GEO_CONFLICT"):
        return cobertura, "localidad_conservada"
    return recalculada, "recalculada"


def _resolucion_vigente(conflicto: dict[str, Any]):
    """Lo que da HOY el resolvedor para lo que la ficha publico, o None."""
    publicado = conflicto.get("publicado") or {}
    if not publicado.get("localidad"):
        return None
    try:
        return geografia().resolver_localidad(
            publicado.get("localidad"), provincia=publicado.get("provincia"),
            lat=publicado.get("latitud"), lon=publicado.get("longitud"))
    except (OSError, ValueError):
        return None


def _conflicto_vigente(conflicto: dict[str, Any]) -> str:
    """El motivo que da HOY el resolvedor para lo que la ficha publico.

    Sin catalogo se respeta el conflicto registrado (fail-closed).
    """
    resolucion = _resolucion_vigente(conflicto)
    return resolucion.motivo if resolucion is not None else PROVINCE_CONFLICT_REASON


def _geo_p10(g: dict[str, Any] | None, conflicto: dict[str, Any]) -> dict[str, Any] | None:
    """Las dimensiones de la localidad que P10 confirmo, con la evidencia a la vista.

    La localidad, el departamento y el municipio salen del catalogo de la
    localidad NOMBRADA por la fuente; la provincia, de la geometria (P10). La
    provincia publicada queda en `provincia_publicada_en_conflicto`.
    """
    resolucion = _resolucion_vigente(conflicto)
    if resolucion is None or resolucion.motivo != PROVINCIA_POR_POLIGONO_REASON:
        return None
    e = resolucion.entidad
    publicado = conflicto.get("publicado") or {}
    return dict(
        g or {}, localidad_canonica=e.official_name, localidad_id=e.official_id,
        departamento_canonico=e.departamento, municipio_canonico=e.municipio,
        provincia_canonica=e.provincia,
        procedencia_de_dimensiones={"provincia": "GEO_GEOMETRY",
                                    "departamento": "SOURCE_LOCALITY",
                                    "municipio": "SOURCE_LOCALITY"},
        area_busqueda={"nivel": "LOCALIDAD", "nombre": e.official_name,
                       "id": e.official_id, "origen": "localidad"},
        provincia_publicada_en_conflicto=publicado.get("provincia"),
        estado_geografico=None, conflicto=None)


def _provincia_declarada_por_poligono(g: dict[str, Any] | None, conflicto: dict[str, Any],
                                      fresca: dict[str, Any] | None) -> dict[str, Any] | None:
    """La provincia que la ficha PUBLICO, confirmada porque su coordenada cae adentro.

    El conflicto «la provincia declarada contradice al catalogo» es entre la
    provincia y el NOMBRE de la localidad («Merlo» de San Luis contra «Merlo»
    de Buenos Aires). Si la coordenada de la propia ficha esta DENTRO del
    poligono oficial de la provincia declarada, la provincia queda demostrada
    por dos evidencias independientes; lo dudoso es solo la localidad, que no
    se afirma. Ocultar tambien provincia y coordenada perdia 102 puntos de mapa
    validos (medido 03-10).
    """
    publicado = conflicto.get("publicado") or {}
    provincia = publicado.get("provincia")
    lat = publicado.get("latitud", (fresca or {}).get("latitud"))
    lon = publicado.get("longitud", (fresca or {}).get("longitud"))
    if not provincia or lat is None or lon is None:
        return None
    # «Buenos Aires» + localidad «CABA» con la coordenada en Quilmes: ahi el
    # «Buenos Aires» puede ser la ciudad y la contradiccion es real; se respeta.
    localidad = "".join(c for c in unicodedata.normalize("NFKD", str(publicado.get("localidad") or "").lower())
                        if not unicodedata.combining(c)).strip(" .")
    if localidad in {"caba", "c.a.b.a", "capital federal", "ciudad autonoma de buenos aires",
                     "ciudad de buenos aires", "buenos aires"}:
        return None
    if poligono_provincia.contencion(provincia, lat, lon) != poligono_provincia.DENTRO:
        return None
    try:
        por_codigo, por_nombre, _ = poligono_provincia._cargar(str(poligono_provincia.GEOMETRIA))
        codigo = poligono_provincia._codigo(provincia, por_nombre, por_codigo)
        nombre = (por_codigo.get(codigo) or {}).get("nombre")
    except (OSError, ValueError, KeyError):
        return None
    if not nombre:
        return None
    return dict(
        g or {}, localidad_canonica=None, localidad_id=None,
        departamento_canonico=None, municipio_canonico=None,
        provincia_canonica=nombre,
        procedencia_de_dimensiones={"provincia": "SOURCE_PROVINCE+GEO_GEOMETRY"},
        area_busqueda={"nivel": "PROVINCIA", "nombre": nombre, "id": None,
                       "origen": "provincia"},
        estado_geografico=None, conflicto=None)


def _geo_de_la_extraccion(g: dict[str, Any] | None, fresca: dict[str, Any] | None
                          ) -> tuple[dict[str, Any] | None, str | None]:
    """La cobertura geo (21-09) corregida por lo que decidio la extraccion fresca.

    - Un conflicto registrado por la extraccion mas nueva manda sobre la
      cobertura vieja TAMBIEN en cierres parciales, cuyo `extra` no se fusiona:
      `blanco` servia 53 fichas «CABA» + provincia «Buenos Aires», sin
      coordenadas, como provincia de Buenos Aires.
    - CABA confirmada por contencion en el poligono oficial del IGN
      (`extra.provincia_por_poligono`) levanta el conflicto de texto que la
      cobertura habia registrado. Solo la provincia: la comuna no se deduce.
    - Un conflicto registrado por un paquete VIEJO se re-evalua con el
      resolvedor vigente: si hoy ya no es contradiccion (un departamento de la
      provincia declarada, «San Jeronimo, Santa Fe»; o CABA dentro del
      poligono) no se impone. Devuelve `conflicto_obsoleto` o
      `caba_por_poligono`, y quien llama saca ese conflicto de la fila.
    """
    extra = (fresca or {}).get("extra") or {}
    conflicto = extra.get("geo_conflicto")
    poligono = extra.get("provincia_por_poligono")
    if isinstance(conflicto, dict) and conflicto:
        vigente = _conflicto_vigente(conflicto)
        if vigente == CABA_POR_POLIGONO_REASON:
            poligono = {"provincia": CABA, "geometria": poligono_caba.procedencia() or {}}
        elif vigente == PROVINCIA_POR_POLIGONO_REASON:
            confirmada = _geo_p10(g, conflicto)
            if confirmada is not None:
                return confirmada, "provincia_por_poligono"
            return dict(g or {}, estado_geografico="GEO_CONFLICT", conflicto=conflicto), "conflicto_fresco"
        elif vigente != PROVINCE_CONFLICT_REASON:
            return g, "conflicto_obsoleto"
        elif (declarada := _provincia_declarada_por_poligono(g, conflicto, fresca)) is not None:
            return declarada, "provincia_declarada_por_poligono"
        elif (g or {}).get("estado_geografico") == "GEO_CONFLICT":
            return g, None
        else:
            return dict(g or {}, estado_geografico="GEO_CONFLICT", conflicto=conflicto), "conflicto_fresco"
    # La provincia que la extraccion fresca SOLO INFIRIO del padron (no la
    # publico la ficha) no puede contradecir a la coordenada: `d amato`
    # publica Villa del Parque con la coordenada en CABA y el padron supone
    # «Buenos Aires». Al fusionar con la preingestion esa suposicion volvia
    # como si fuera publicada y la fila salia GEO_CONFLICT, sin provincia ni
    # coordenada (regresion medida 03-10). CABA por el poligono oficial.
    if (not isinstance(poligono, dict) and fresca
            and (extra.get("provincia_confianza") == "inferida"
                 or extra.get("provincia_supuesta_descartada"))
            and ((g or {}).get("estado_geografico") == "GEO_CONFLICT"
                 or not (g or {}).get("provincia_canonica"))
            and poligono_caba.contencion(fresca.get("latitud"), fresca.get("longitud")) == "DENTRO"):
        poligono = {"provincia": CABA, "geometria": poligono_caba.procedencia() or {}}
    if isinstance(poligono, dict) and poligono.get("provincia") == CABA:
        if ((g or {}).get("provincia_canonica") == CABA
                and (g or {}).get("estado_geografico") != "GEO_CONFLICT"):
            return g, ("conflicto_obsoleto" if conflicto else None)
        return dict(
            g or {}, localidad_canonica=None, localidad_id=None,
            departamento_canonico=None, municipio_canonico=None,
            provincia_canonica=CABA,
            procedencia_de_dimensiones={"provincia": "GEO_GEOMETRY"},
            area_busqueda={"nivel": "PROVINCIA", "nombre": CABA, "id": None,
                           "origen": "provincia"},
            geometria={"provincia": CABA, "fuente": (poligono.get("geometria") or {}).get("fuente")},
            estado_geografico=None, conflicto=None), "caba_por_poligono"
    return g, None


def _decision_certificadas(origen, args, ajenas):
    """Que sumar, que refrescar por alias y que retirar; None sin banderas."""
    if not (getattr(args, 'sumar_certificadas', False)
            or getattr(args, 'retirar_ausentes', False)
            or getattr(args, 'retiros_verificados', None)):
        return None
    ledger = args.ledger or Path(args.paquetes).parent / "AGENCY_CERTIFICATION_RESULTS.jsonl"
    return decidir(paquetes_vigentes(Path(args.paquetes), Path(ledger)),
                   conocidas_de(origen), ajenas)


def _listadas_en_paquetes(paquetes: Path) -> set[str]:
    """Los `hash_dedup` que algun paquete actual (de cualquier estado) sigue listando."""
    vistos: set[str] = set()
    for archivo in Path(paquetes).glob("*/properties_run2.jsonl"):
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                h = json.loads(linea).get("hash_dedup")
                if h:
                    vistos.add(h)
    return vistos


def _servidas_a_conservar(origen, ruta_servida, nuevas, retirar) -> list[dict]:
    """Filas SERVIDAS que la candidata perderia sin un motivo de politica.

    El constructor solo suma paquetes cuyo cierre VIGENTE es certificado. Una
    agencia que retrocede a NEEDS_FIX -`casamia` por un slug editado, `d amato`
    por tres fichas vacias, `pennacchio` por una ficha cambiada- dejaba caer
    filas que ya se servian, sin evidencia de muerte: 100 el 2026-10-01 (57
    seguian vivas en su paquete actual). P1 retira solo con muerte demostrada o
    tres ausencias, y P8 dice que la propiedad real sobrevive. La compuerta P2
    lo freno; esto lo evita: la fila se conserva TAL CUAL se servia. Lo que se
    retira por una politica (retiro verificado, web ajena, exterior...) sigue
    retirandose: eso pasa en el recorrido normal, que aca no se toca.
    """
    if not ruta_servida or not Path(ruta_servida).is_file():
        return []
    presentes = {h for (h,) in origen.execute(
        "select hash_dedup from rows where status = 'CANDIDATE'")} - set(retirar)
    presentes |= {f.get("hash_dedup") for f in nuevas}
    servida = sqlite3.connect(f"file:{Path(ruta_servida).as_posix()}?mode=ro", uri=True)
    try:
        cursor = servida.execute("select * from propiedades order by id")
        columnas = [c[0] for c in cursor.description]
        conservar = [dict(zip(columnas, fila)) for fila in cursor
                     if fila[0] not in presentes and fila[0] not in retirar]
    finally:
        servida.close()
    return conservar


def _ids_de_aviso(url) -> set[str]:
    """Los numeros de 5 cifras o mas de la ruta y la consulta: el id del aviso en casi
    todas las plataformas (`/p/10500121-...`). El mismo criterio que la compuerta P2 de
    duplicados probables; con 4 cifras entraria la altura de una calle."""
    p = urllib.parse.urlparse(str(url or ""))
    return set(re.findall(r"\d{5,}", p.path + "?" + p.query))


def _sin_avisos_ya_servidos(origen, ruta_servida, nuevas, retirar) -> tuple[list[dict], int]:
    """Las altas certificadas, sin los avisos que ya se sirven con otro slug.

    08-10, `sprint_rc3`: P2 freno por 14 duplicados probables con altas. Eran el mismo
    aviso dos veces: la fila servida con el slug viejo y la del paquete nuevo con el
    slug editado por la fuente (`/p/10500121-...-627` -> `-621`). La servida habia
    entrado por un paquete, no por la preingestion, asi que `decidir` no la conocia, y
    `_servidas_a_conservar` la conservaba porque su hash no volvia. Se aplica a lo
    servido HUERFANO (ni en la preingestion ni entre las altas, ni retirado por una
    politica) la regla `numero_de_url_ya_visto` de la preingestion: el alta no entra y
    la fila servida sigue tal cual. Lo servido que el paquete sigue listando con el
    mismo hash no es huerfano y se refresca como siempre.
    """
    if not nuevas or not ruta_servida or not Path(ruta_servida).is_file():
        return nuevas, 0
    presentes = {h for (h,) in origen.execute(
        "select hash_dedup from rows where status = 'CANDIDATE'")}
    presentes |= {f.get("hash_dedup") for f in nuevas}
    huerfanos: dict[str, set[str]] = defaultdict(set)
    servida = sqlite3.connect(f"file:{Path(ruta_servida).as_posix()}?mode=ro", uri=True)
    try:
        for i, agencia, url in servida.execute(
                "select id, agency_id, source_url from propiedades"):
            if i not in presentes and i not in retirar:
                huerfanos[agencia] |= _ids_de_aviso(url)
    finally:
        servida.close()
    quedan = [f for f in nuevas
              if not (_ids_de_aviso(f.get("source_url"))
                      & huerfanos.get((f.get("_snapshot_certificadas") or {}).get("agencia"),
                                      set()))]
    return quedan, len(nuevas) - len(quedan)


def _ids_servidos(ruta_servida) -> set[str] | None:
    """Los ids de la snapshot servida; None si no hay servida con la que comparar."""
    if not ruta_servida or not Path(ruta_servida).is_file():
        return None
    servida = sqlite3.connect(f"file:{Path(ruta_servida).as_posix()}?mode=ro", uri=True)
    try:
        return {i for (i,) in servida.execute("select id from propiedades")}
    finally:
        servida.close()


def _servidas_sin_frescura(origen, ruta_servida, frescas, retirar) -> dict[str, dict]:
    """Filas servidas de propiedades que HOY no tienen paquete fresco confiable.

    Sin paquete fresco, la fila se rearmaba desde la base de preingestion, que
    es MAS VIEJA que lo servido: `pennacchio` (ultimo cierre NEEDS_FIX por «second
    run is not idempotent») perdia superficie_total en 101 fichas y barrio en 34
    que la servida si tenia de su ultima certificacion (Regression Gate de
    snapshots, 2026-10-02). Lo servido salio de un paquete certificado o de esa
    misma base, asi que nunca es mas viejo: se sirve tal cual, como
    `_servidas_a_conservar`. Lo que una politica retira se sigue retirando.
    """
    if not ruta_servida or not Path(ruta_servida).is_file():
        return {}
    faltan = [h for (h,) in origen.execute(
        "select hash_dedup from rows where status = 'CANDIDATE'")
        if h and h not in frescas and h not in retirar]
    salida: dict[str, dict] = {}
    servida = sqlite3.connect(f"file:{Path(ruta_servida).as_posix()}?mode=ro", uri=True)
    try:
        for i in range(0, len(faltan), 500):
            tramo = faltan[i:i + 500]
            cursor = servida.execute(
                f"select * from propiedades where id in ({','.join('?' * len(tramo))})", tramo)
            columnas = [c[0] for c in cursor.description]
            for fila in cursor:
                salida[fila[0]] = dict(zip(columnas, fila))
    finally:
        servida.close()
    return salida


def _filas_en_orden(origen, frescas, nuevas, retirar, servidas=()):
    """(fila base, fresca, es_nueva) en orden de `hash_dedup`, sin las retiradas.

    Las filas nuevas no tienen version vieja: son su propia lectura fresca, y
    asi `_geo_de_la_extraccion` ve el conflicto o el poligono que registro su
    extraccion.
    """
    def de_la_preingestion():
        for (crudo,) in origen.execute(
                "select row_json from rows where status = 'CANDIDATE' "
                "order by hash_dedup"):
            fila = json.loads(crudo)
            if fila.get("hash_dedup") in retirar:
                continue
            yield fila.get("hash_dedup") or "", fila, frescas.get(fila.get("hash_dedup")), False

    def de_los_paquetes():
        for fila in sorted(nuevas, key=lambda f: f["hash_dedup"]):
            yield fila["hash_dedup"], fila, fila, True

    def de_la_servida():
        for fila in servidas:
            yield fila["id"], {"__servida__": fila}, None, False

    for _clave, fila, fresca, es_nueva in heapq.merge(
            de_la_preingestion(), de_los_paquetes(), de_la_servida(), key=lambda x: x[0]):
        yield fila, fresca, es_nueva


def _build_contents(origen, api, args, ajenas, geo, frescas, gate, destino):
    decision = _decision_certificadas(origen, args, ajenas)
    sumar = decision is not None and getattr(args, 'sumar_certificadas', False)
    nuevas = decision.nuevas if sumar else []
    retirar = (decision.retirables
               if decision is not None and getattr(args, 'retirar_ausentes', False) else set())
    retiros_evidencia: dict[str, dict] = {}
    if decision is not None and getattr(args, 'retiros_verificados', None):
        listadas_hoy = _listadas_en_paquetes(Path(args.paquetes))
        for linea in Path(args.retiros_verificados).read_text(encoding='utf-8').splitlines():
            if not linea.strip():
                continue
            fila = json.loads(linea)
            # Muerte verificada (P1). Antes solo se aplicaba si la agencia
            # tenia cierre COMPLETO vigente: cuando `pennacchio` retrocedio a
            # NEEDS_FIX, 6 fichas con soft-404 verificado el 29-09 (redirigen a
            # la portada) volvian a servirse. Ahora tambien se retira si la
            # ficha NO figura en el paquete actual de nadie: si volvio a
            # listarse, la evidencia vieja no alcanza.
            if fila.get('veredicto') == 'REMOVED' and (
                    fila.get('hash_dedup') in decision.retirables
                    or fila.get('hash_dedup') not in listadas_hoy):
                retiros_evidencia[fila['hash_dedup']] = fila
        retirar = set(retirar) | set(retiros_evidencia)
    alias_refrescados = 0
    if sumar:
        # El aviso con URL nueva refresca a la fila que ya se sirve, si esa
        # fila no tiene ya su propia lectura fresca.
        frescas = dict(frescas)
        for hash_viejo, fila in decision.alias.items():
            if hash_viejo not in frescas:
                frescas[hash_viejo] = fila
                alias_refrescados += 1
    localidades = catalogo_de_localidades(geografia())
    geometria = cargar_cache(Path(getattr(args, 'cache_geometrica', None)
                                  or str(dato('ERETZ_GEO', 'GEO_REVERSE_CACHE.jsonl'))))

    # Frecuencia por agencia para revisión; repetir no demuestra ser un logo.
    apariciones: dict[str, Counter] = defaultdict(Counter)
    # El texto del sitio, con la MISMA regla del runner
    # (`descartar_descripciones_compartidas`): la v4 del 2026-09-24 traia
    # 4.813 filas en 61 agencias con la descripcion institucional, de agencias
    # todavia no recertificadas con el codigo que la descarta.
    descripciones: dict[str, Counter] = defaultdict(Counter)
    titulos: dict[str, Counter] = defaultdict(Counter)
    fichas_de: Counter = Counter()
    for fila, fresca, es_nueva in _filas_en_orden(origen, frescas, nuevas, retirar):
        canonical = fila.get("canonical_agency_id")
        if canonical in ajenas:
            continue
        for url in set(fila.get("imagenes") or []):
            apariciones[canonical][url] += 1
        fusionada = fila if es_nueva else fusionar(fila, fresca, CAMPOS_FUSIONABLES)
        texto = fusionada.get("descripcion")
        fichas_de[canonical] += 1
        # Sin el minimo de 40 caracteres del runner: la preingestion trae
        # esloganes cortos en TODAS las fichas de 9 agencias (898 filas,
        # «Encontrá tu propiedad» en 201 de 201 de `fdc`). Repetido en la
        # mitad del catalogo, corto o largo, no describe a ninguna ficha.
        if texto:
            descripciones[canonical][texto] += 1
        if fusionada.get("titulo"):
            titulos[canonical][fusionada["titulo"]] += 1

    def es_del_sitio(canonical: str, texto: Any) -> bool:
        if not texto:
            return False
        inicio = str(texto).lstrip()
        if inicio[:1] == "©" or inicio[:9].lower() == "copyright":
            return True
        n = fichas_de[canonical]
        return (n >= MINIMO_PARA_JUZGAR
                and descripciones[canonical][texto]
                >= max(MINIMO_PARA_JUZGAR // 2, n * FRACCION_COMPARTIDA))

    # El nombre de la agencia como titulo, repetido como el texto del sitio:
    # la v4 del 25-09 servia 1.980 («Patagonica Propiedades» en 320 fichas,
    # «Meta Inmobiliaria | Propiedades en Tucuman»). Las dos condiciones: un
    # titulo repetido que no es la agencia («Casa» en `pozzobon`) es pobre pero
    # propio, y «Blanco Propiedades - Casa en Pilar» nombra a la agencia y
    # tambien a la casa.
    def es_titulo_del_sitio(canonical: str, titulo: Any) -> bool:
        if not titulo:
            return False
        nombre = _sin_tildes(str(canonical).split(":", 1)[-1]).strip()
        partes = [_sin_tildes(parte).strip()
                  for parte in re.split(r"\s*[|–—-]\s*", str(titulo))
                  if parte.strip()]
        if not nombre or not partes or nombre not in (partes[0], partes[-1]):
            return False
        # Solo el nombre, sin nada mas, no dice nada de la ficha: no hace
        # falta que se repita (`blanco`, tras la frescura parcial, quedo con
        # 88 de 1.215, lejos de la mitad).
        if partes == [nombre]:
            return True
        n = fichas_de[canonical]
        return (n >= MINIMO_PARA_JUZGAR
                and titulos[canonical][titulo]
                >= max(MINIMO_PARA_JUZGAR // 2, n * FRACCION_COMPARTIDA))

    api.executescript(ESQUEMA)

    filas = 0
    descripciones_del_sitio = 0
    titulos_del_sitio = 0
    tipos_cochera_corregidos = 0
    heredadas_corregidas: Counter = Counter()
    cocheras_incoherentes = 0
    monoambientes_corregidos = 0
    no_residenciales_corregidos = 0
    textos_limpiados = 0
    ajenas_omitidas = 0
    exterior_no_publicadas = 0
    precios_simbolicos = 0
    correcciones_geo: Counter = Counter()
    imagenes_compartidas = 0
    imagenes_repetidas_sin_evidencia = 0
    fichas_sin_foto_propia = 0
    filas_con_frescura_parcial = 0
    sumadas = 0
    no_son_fichas = 0
    geo_de_la_fila_fresca: Counter = Counter()
    # Por que cada id entra o no (politica P2: altas y bajas explicadas por id).
    cambios: dict[str, str] = {h: ("RETIRO_MUERTE_VERIFICADA" if h in retiros_evidencia
                                   else "RETIRO_AUSENTE_DE_INVENTARIO_COMPLETO")
                               for h in retirar}
    anterior: tuple[str | None, int | None] = (None, None)
    # En orden de `hash_dedup`, que es el `id` de la API. La busqueda rankeada
    # elige su ventana de candidatos «por id» -una muestra estable y diversa:
    # 207 inmobiliarias distintas en los 400 candidatos de «casa», contra 9 en
    # orden de insercion- y ordenar 16.965 coincidencias por id costaba 243 ms
    # de los 330 de la consulta. Insertando en orden de id, el `rowid` del
    # indice de texto YA es ese orden y la API lo usa gratis: 9 ms, la misma
    # muestra. Ver `orden_de_filas` en `snapshot_meta`.
    nuevas, avisos_ya_servidos = _sin_avisos_ya_servidos(
        origen, getattr(args, 'servida', None), nuevas, retirar)
    servidas = (_servidas_a_conservar(origen, getattr(args, 'servida', None), nuevas, retirar)
                if decision is not None else [])
    conservadas = 0
    sin_frescura = (_servidas_sin_frescura(origen, getattr(args, 'servida', None), frescas, retirar)
                    if decision is not None else {})
    servidas_sin_paquete_fresco = 0
    # Una fila que NO se servia y no llega con un paquete certificado no es un alta:
    # P2 solo aprueba altas SUMADA_CERTIFICADA. Sin esto, una fila excluida antes por un
    # motivo que dependia del paquete reaparecia sin verificar: `o feely` (06-10) volvia
    # a publicar dos emprendimientos de URUGUAY (Colonia, Punta del Este) con provincia
    # 'Santa Fe' inferida del padron, porque su ultima corrida no llego a esas fichas y
    # se perdio la marca de exterior del paquete anterior.
    ids_servidos = (_ids_servidos(getattr(args, 'servida', None))
                    if decision is not None else None)
    altas_sin_certificar = 0
    for base, fresca, es_nueva in _filas_en_orden(origen, frescas, nuevas, retirar, servidas):
        if (fresca is None and not es_nueva and "__servida__" not in base
                and base.get("hash_dedup") in sin_frescura):
            base = {"__servida__": sin_frescura[base["hash_dedup"]]}
            servidas_sin_paquete_fresco += 1
        if "__servida__" in base:
            # La fila servida, tal cual: sin recalcular nada (ver
            # `_servidas_a_conservar`). Solo la web ajena se sigue aplicando.
            servida_fila = base["__servida__"]
            if servida_fila["agency_id"] in ajenas:
                ajenas_omitidas += 1
                cambios[servida_fila["id"]] = "WEB_AJENA"
                continue
            if servida_fila["id"] == anterior[0] and anterior[1] is not None:
                continue
            servida_fila, corregidas = _corregir_heredada(servida_fila)
            heredadas_corregidas.update(corregidas)
            propiedad = api.execute(
                f"insert or replace into propiedades values ({','.join('?' * len(servida_fila))})",
                tuple(servida_fila.values()))
            api.execute(
                "insert into busqueda (rowid, id, titulo, descripcion, barrio, area_nombre) "
                "values (?,?,?,?,?,?)",
                (propiedad.lastrowid, servida_fila["id"], servida_fila.get("titulo") or "",
                 servida_fila.get("descripcion") or "", servida_fila.get("barrio") or "",
                 servida_fila.get("area_nombre") or ""))
            anterior = (servida_fila["id"], propiedad.lastrowid)
            filas += 1
            conservadas += 1
            continue
        if fresca is not None and "_campos_confiables" in fresca:
            filas_con_frescura_parcial += 1
        cruda = base if es_nueva else fusionar(base, fresca, CAMPOS_FUSIONABLES)
        hash_dedup = cruda.get("hash_dedup")
        if (ids_servidos is not None and fresca is None and not es_nueva
                and hash_dedup not in ids_servidos):
            altas_sin_certificar += 1
            cambios[hash_dedup] = "ALTA_SIN_CERTIFICAR"
            continue
        # Una fila de la preingestion que NO se servia y llega con el paquete CERTIFICADO
        # entero es un alta certificada: `gonzalez e hijos`, `gualtieri`, `oyharzabal`,
        # `morero` (CANDIDATE en la preingestion, ficha en las dos corridas COMPLETE). Sin
        # marca, P2 la frenaba como 'alta sin motivo' (sprint_rc1, 07-10). Con frescura
        # PARCIAL (`_campos_confiables`, de un NEEDS_FIX) no esta certificada: no se suma.
        alta_certificada = False
        if ids_servidos is not None and not es_nueva and hash_dedup not in ids_servidos:
            if "_campos_confiables" in fresca:
                altas_sin_certificar += 1
                cambios[hash_dedup] = "ALTA_SIN_CERTIFICAR"
                continue
            alta_certificada = True
        canonical = cruda.get("canonical_agency_id")
        if canonical in ajenas:
            ajenas_omitidas += 1
            cambios[hash_dedup] = "WEB_AJENA"
            continue
        # Una pagina de categoria o un archivo de WordPress no es una propiedad:
        # 46 servidas en la v4j («Candel Raul Propiedades» en
        # /propiedades/locales_venta_lomas-de-zamora). Mismo criterio que el
        # extractor (`es_url_de_categoria`), para filas todavia no recertificadas.
        if es_url_de_categoria(cruda.get("source_url") or ""):
            no_son_fichas += 1
            cambios[hash_dedup] = "NO_ES_FICHA_CATEGORIA"
            continue
        # Politica publica ARGENTINA_ONLY (decidida el 28-09): lo del exterior
        # se conserva en paquetes y canonico, y no se sirve. Decide la marca de
        # la extraccion y, para filas que todavia no se recertificaron con
        # ella, la misma evidencia conservadora de `connectors.exterior`.
        if not _publicable_en_argentina(cruda, fresca):
            exterior_no_publicadas += 1
            cambios[hash_dedup] = "EXTERIOR_ARGENTINA_ONLY"
            continue
        # Sin titulo, la descripcion se conserva: el contrato promete que
        # nunca faltan las dos, y una fila sin ningun texto no se entiende.
        if cruda.get("titulo") and es_del_sitio(canonical, cruda.get("descripcion")):
            cruda = dict(cruda, descripcion=None)
            descripciones_del_sitio += 1
        elif (cruda.get("descripcion")
              and es_titulo_del_sitio(canonical, cruda.get("titulo"))):
            cruda = dict(cruda, titulo=None)
            titulos_del_sitio += 1
        # Sin paquete fresco, la fila viene de la base: ver `_corregir_heredada`.
        if fresca is None:
            cruda, corregidas = _corregir_heredada(cruda)
            heredadas_corregidas.update(corregidas)
        # «Dúplex … con cochera» no es una cochera: 272 filas de la v4 venian
        # de la regla vieja. Solo si el titulo tiene la forma accesoria, el
        # tipo se vuelve a derivar del titulo con la regla de hoy; sin otro
        # tipo, queda vacio antes que falso.
        if (cruda.get("tipo_propiedad") == "cochera" and cruda.get("titulo")
                and RE_TIPO_ACCESORIO.search(_sin_tildes(cruda["titulo"]))):
            nuevo_tipo = detectar_tipo(cruda["titulo"])
            if nuevo_tipo != "cochera":
                cruda = dict(cruda, tipo_propiedad=nuevo_tipo)
                tipos_cochera_corregidos += 1
        # Una cochera no tiene dormitorios ni varios ambientes: 169 de 957 en
        # la v4e. Decide el titulo: si dice cochera y no describe ambientes,
        # sobran los conteos (`farina` «Newbery 9192 – Cochera», 1 dormitorio);
        # si describe ambientes o no nombra tipo, sobra el tipo (`berrueta`
        # «3 AMBIENTES AL FRENTE»). El tipo que falta nunca se inventa.
        if (cruda.get("tipo_propiedad") == "cochera"
                and ((cruda.get("dormitorios") or 0) >= 1
                     or (cruda.get("ambientes") or 0) >= 2)):
            titulo_plano = _sin_tildes(cruda.get("titulo") or "")
            describe_ambientes = re.search(
                r"\b\d+\s*(?:amb|dorm)|\b(?:semipiso|piso|departamento|depto|casa|duplex|triplex|ph)\b",
                titulo_plano)
            if detectar_tipo(cruda.get("titulo")) == "cochera" and not describe_ambientes:
                cruda = dict(cruda, dormitorios=None, ambientes=None)
            else:
                cruda = dict(cruda, tipo_propiedad=None)
            cocheras_incoherentes += 1
        if _monoambiente_con_dormitorios(cruda):
            cruda = dict(cruda, dormitorios=None)
            monoambientes_corregidos += 1
        elif _no_residencial_con_dormitorios(cruda):
            cruda = dict(cruda, dormitorios=None)
            no_residenciales_corregidos += 1
        # La misma regla de `coherencia.revisar` para las filas que la cola
        # todavia no recertifico: 42 en la v4i servian «US$1» o ventas por USD
        # 460 (`next`, `oyharzabal`, `domus`, `must`...).
        precio_actual = cruda.get("precio")
        try:
            precio_actual = float(precio_actual) if precio_actual is not None else None
        except (TypeError, ValueError):
            precio_actual = None
        if (precio_actual is not None and precio_actual > 0
                and _es_simbolico(precio_actual, cruda.get("moneda"), cruda.get("operacion"))):
            cruda = dict(cruda, precio=None, moneda=None)
            precios_simbolicos += 1
        for campo in ("titulo", "descripcion"):
            limpio = _sin_mojibake(_texto_servible(cruda.get(campo)))
            if limpio != cruda.get(campo):
                cruda = dict(cruda, **{campo: limpio})
                textos_limpiados += 1
        propias = [u for u in (cruda.get("imagenes") or [])
                   if not _es_recurso_de_pagina(u, apariciones[canonical][u])]
        imagenes_repetidas_sin_evidencia += sum(
            apariciones[canonical][u] >= FICHAS_PARA_SER_COMPARTIDA for u in propias)
        imagenes_compartidas += len(cruda.get("imagenes") or []) - len(propias)
        if cruda.get("imagenes") and not propias:
            # Se queda sin fotos, no sin propiedad: lo que tenia no era suyo.
            fichas_sin_foto_propia += 1
        cruda = dict(cruda, imagenes=propias)
        cobertura = geo.get(hash_dedup)
        if es_nueva:
            # La misma regla de `geo_coverage_audit`, para la fila que su
            # artefacto (armado sobre la preingestion) no podia tener.
            cobertura = cobertura_de_fila(cruda, cruda.get("connector"), hash_dedup,
                                          localidades, geometria)
            sumadas += 1
            cambios[hash_dedup] = "SUMADA_CERTIFICADA"
        elif fresca is not None:
            cobertura, recalculo = _cobertura_de_la_fila_servida(
                cobertura, base, cruda, hash_dedup, localidades, geometria)
            if recalculo:
                geo_de_la_fila_fresca[recalculo] += 1
        if alta_certificada:
            cambios[hash_dedup] = "SUMADA_CERTIFICADA"
        g, correccion_geo = _geo_de_la_extraccion(cobertura, fresca)
        if correccion_geo:
            correcciones_geo[correccion_geo] += 1
        if (correccion_geo in ("conflicto_obsoleto", "caba_por_poligono",
                               "provincia_por_poligono", "provincia_declarada_por_poligono")
                and isinstance(cruda.get("extra"), dict)
                and "geo_conflicto" in cruda["extra"]):
            # `fila_de_api` vuelve a imponer el conflicto que lleve la fila.
            cruda = dict(cruda, extra={k: v for k, v in cruda["extra"].items()
                                       if k != "geo_conflicto"})
        # The stored gate may predate this merge. It cannot promise a price or
        # operation scope that the actual row no longer supports.
        actual_scopes, _ = alcances(cruda, g)
        previous_scopes = (gate.get(hash_dedup) or {}).get('alcances')
        scopes = sorted(actual_scopes & set(previous_scopes)) if previous_scopes is not None else sorted(actual_scopes)
        documento = fila_de_api(cruda, g, scopes)
        area = documento["geo"]["area_busqueda"] or {}
        propiedad = api.execute(
            "insert or replace into propiedades values "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (documento["id"], documento["agency_id"], documento["source_url"],
             documento["titulo"], documento["descripcion"], documento["operacion"],
             documento["tipo_propiedad"], documento["precio"], documento["moneda"],
             documento["ambientes"], documento["dormitorios"], documento["banos"],
             documento["superficie_total"], documento["superficie_cubierta"],
             len(documento["imagenes"]), documento["latitud"], documento["longitud"],
             documento["geo"]["localidad"]["nombre"],
             documento["geo"]["localidad"].get("id"),
             documento["geo"]["municipio"]["nombre"],
             documento["geo"]["departamento"]["nombre"],
             documento["geo"]["provincia"]["nombre"],
             documento["geo"]["barrio"]["nombre"],
             area.get("nivel") or "SIN_AREA",
             area.get("nombre"),
             sin_acento(area.get("nombre")),
             sin_acento(documento["geo"]["barrio"]["nombre"]),
             documento["geo"].get("estado"),
             json.dumps(documento["alcances"], ensure_ascii=False),
             json.dumps(documento, ensure_ascii=False)))
        # `insert or replace` de arriba deja UNA fila por id en `propiedades`;
        # el indice de texto tiene que quedar igual, o un id repetido en el
        # origen apareceria dos veces en la busqueda. Como las filas llegan en
        # orden de id, un repetido es siempre el anterior: se borra por
        # `rowid`, que en FTS5 es directo (`id` no esta indexado y borrar por
        # el recorreria el indice entero en cada fila).
        #
        # Y la fila de texto lleva el MISMO `rowid` que la de `propiedades`:
        # asi la API une las dos por `rowid` (207 ms el conteo de una busqueda
        # combinada) en vez de por `id` (351 ms). Ver `busqueda_rowid`.
        if documento["id"] == anterior[0] and anterior[1] is not None:
            api.execute("delete from busqueda where rowid = ?", (anterior[1],))
        api.execute(
            "insert into busqueda (rowid, id, titulo, descripcion, barrio, area_nombre) "
            "values (?,?,?,?,?,?)",
            (propiedad.lastrowid, documento["id"], documento["titulo"] or "",
             documento["descripcion"] or "",
             documento["geo"]["barrio"]["nombre"] or "",
             area.get("nombre") or ""))
        anterior = (documento["id"], propiedad.lastrowid)
        filas += 1
    api.executemany("insert or replace into snapshot_meta values (?, ?)",
                    [("orden_de_filas", "id"), ("busqueda_rowid", "propiedades")])
    with (destino.parent / "CAMBIOS_DE_INVENTARIO.jsonl").open("w", encoding="utf-8") as fh:
        for h in sorted(cambios):
            fh.write(json.dumps({"id": h, "motivo": cambios[h]}, ensure_ascii=False) + "\n")
    if retiros_evidencia:
        # Procedencia de cada retiro (P1): que, cuando y con que evidencia.
        with (destino.parent / "RETIROS_APLICADOS.jsonl").open("w", encoding="utf-8") as fh:
            for h in sorted(retiros_evidencia):
                fh.write(json.dumps(retiros_evidencia[h], ensure_ascii=False) + "\n")
    api.commit()

    resumen = {
        "snapshot_version": SNAPSHOT_VERSION,
        "contrato_api_version": CONTRATO_API_VERSION,
        "propiedades": filas,
        "omitidas_por_web_ajena": ajenas_omitidas,
        "exterior_conservadas_no_publicadas": exterior_no_publicadas,
        "paginas_de_categoria_omitidas": no_son_fichas,
        "politica_publica": POLITICA_PUBLICA,
        "geo_conflictos_de_la_extraccion_fresca": correcciones_geo["conflicto_fresco"],
        "caba_confirmada_por_poligono": correcciones_geo["caba_por_poligono"],
        "provincia_normalizada_por_poligono_p10": correcciones_geo["provincia_por_poligono"],
        "servidas_conservadas_sin_muerte_verificada": conservadas,
        "servidas_sin_paquete_fresco": servidas_sin_paquete_fresco,
        "altas_sin_certificar_omitidas": altas_sin_certificar,
        "geo_conflictos_viejos_que_ya_no_lo_son": correcciones_geo["conflicto_obsoleto"],
        "imagenes_compartidas_descartadas": imagenes_compartidas,
        "descripciones_del_sitio_descartadas": descripciones_del_sitio,
        "titulos_del_sitio_descartados": titulos_del_sitio,
        "tipos_cochera_por_accesorio_corregidos": tipos_cochera_corregidos,
        "heredadas_operacion_por_subcadena_anulada": heredadas_corregidas["operacion"],
        "heredadas_tipo_en_ingles_traducido": heredadas_corregidas["tipo"],
        "cocheras_incoherentes_resueltas": cocheras_incoherentes,
        "monoambientes_con_dormitorios_anulados": monoambientes_corregidos,
        "no_residenciales_con_dormitorios_anulados": no_residenciales_corregidos,
        "heredadas_dormitorios_anulados": heredadas_corregidas["dormitorios"],
        "precios_simbolicos_descartados": precios_simbolicos,
        "textos_con_entidades_limpiados": textos_limpiados,
        "filas_con_frescura_parcial": filas_con_frescura_parcial,
        "geo_recalculada_sobre_la_fila_fresca": geo_de_la_fila_fresca["recalculada"],
        "geo_localidad_conservada_ante_un_vacio": geo_de_la_fila_fresca["localidad_conservada"],
        "imagenes_repetidas_sin_evidencia_de_descarte": imagenes_repetidas_sin_evidencia,
        "fichas_que_quedaron_sin_foto_propia": fichas_sin_foto_propia,
        "fichas_para_ser_compartida": FICHAS_PARA_SER_COMPARTIDA,
        "certificadas": None if decision is None else {
            "sumadas_servidas": sumadas,
            "nuevas_elegibles": len(decision.nuevas) if sumar else 0,
            "avisos_con_url_nueva_refrescados": alias_refrescados,
            "altas_omitidas_por_aviso_ya_servido": avisos_ya_servidos,
            "retiradas_ausentes_de_inventario_completo": len(retirar),
            "retiradas_con_muerte_verificada": len(retiros_evidencia),
            "retirables_detectadas": len(decision.retirables),
            "motivos": dict(decision.motivos.most_common()),
        },
        "generada_en": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origen": str(Path(args.db)),
        "artefacto": destino.name,
        "database_writes": 0,
    }
    return resumen


if __name__ == "__main__":
    raise SystemExit(main())

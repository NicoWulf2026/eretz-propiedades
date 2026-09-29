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
from scripts.property_contract import alcances  # noqa: E402
from scripts.image_quality import is_known_page_asset  # noqa: E402
from scripts.plan_de_escritura import agencias_con_web_ajena  # noqa: E402
from scripts.property_freshest import (CAMPOS_FUSIONABLES,  # noqa: E402
                                       fusionar, mas_frescas)
from scripts.run_rollout import (FRACCION_COMPARTIDA,  # noqa: E402
                                 MINIMO_PARA_JUZGAR)
from connectors.base import RE_TIPO_ACCESORIO, detectar_tipo, geografia  # noqa: E402
from connectors.exterior import (POLITICA_PUBLICA, evidencia_de_exterior,  # noqa: E402
                                 publicable)
from connectors import poligono_caba  # noqa: E402
from connectors.coherencia import _es_simbolico  # noqa: E402
from connectors.geografia import (CABA_POR_POLIGONO_REASON,  # noqa: E402
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


from scripts.preingestion_manifest import (base_canonica,  # noqa: E402
                                           exigir_base_vigente)

SNAPSHOT_VERSION = "api_snapshot_v4"

# Review threshold only: shared building renders can occur in many listings.
# Exclusion requires an independent page-asset signal, never frequency alone.
FICHAS_PARA_SER_COMPARTIDA = 5

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
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_COVERAGE_AUDIT.jsonl")
    ap.add_argument("--directorio",
                    default=str(Path("D:/INMO CAPITAL/agency_platform_directory.jsonl")))
    ap.add_argument('--paquetes', type=Path,
                    default=Path(r'D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\agencies'))
    ap.add_argument("--salida", default=r"D:\INMO CAPITAL\ERETZ_API_CONTRACT")
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
    ap.add_argument('--ledger', type=Path, default=None,
                    help='ledger de certificacion (por defecto, junto a --paquetes)')
    ap.add_argument("--cache-geometrica",
                    default=r"D:\INMO CAPITAL\ERETZ_GEO\GEO_REVERSE_CACHE.jsonl")
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


def _conflicto_vigente(conflicto: dict[str, Any]) -> str:
    """El motivo que da HOY el resolvedor para lo que la ficha publico.

    Sin catalogo se respeta el conflicto registrado (fail-closed).
    """
    publicado = conflicto.get("publicado") or {}
    try:
        resolucion = geografia().resolver_localidad(
            publicado.get("localidad"), provincia=publicado.get("provincia"),
            lat=publicado.get("latitud"), lon=publicado.get("longitud"))
    except (OSError, ValueError):
        return PROVINCE_CONFLICT_REASON
    if not publicado.get("localidad"):
        return PROVINCE_CONFLICT_REASON
    return resolucion.motivo


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
        elif vigente != PROVINCE_CONFLICT_REASON:
            return g, "conflicto_obsoleto"
        elif (g or {}).get("estado_geografico") == "GEO_CONFLICT":
            return g, None
        else:
            return dict(g or {}, estado_geografico="GEO_CONFLICT", conflicto=conflicto), "conflicto_fresco"
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


def _filas_en_orden(origen, frescas, nuevas, retirar):
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

    for _clave, fila, fresca, es_nueva in heapq.merge(
            de_la_preingestion(), de_los_paquetes(), key=lambda x: x[0]):
        yield fila, fresca, es_nueva


def _build_contents(origen, api, args, ajenas, geo, frescas, gate, destino):
    decision = _decision_certificadas(origen, args, ajenas)
    sumar = decision is not None and getattr(args, 'sumar_certificadas', False)
    nuevas = decision.nuevas if sumar else []
    retirar = (decision.retirables
               if decision is not None and getattr(args, 'retirar_ausentes', False) else set())
    retiros_evidencia: dict[str, dict] = {}
    if decision is not None and getattr(args, 'retiros_verificados', None):
        for linea in Path(args.retiros_verificados).read_text(encoding='utf-8').splitlines():
            if not linea.strip():
                continue
            fila = json.loads(linea)
            if fila.get('veredicto') == 'REMOVED' and fila.get('hash_dedup') in decision.retirables:
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
                                  or r"D:\INMO CAPITAL\ERETZ_GEO\GEO_REVERSE_CACHE.jsonl"))

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
    cocheras_incoherentes = 0
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
    for base, fresca, es_nueva in _filas_en_orden(origen, frescas, nuevas, retirar):
        if fresca is not None and "_campos_confiables" in fresca:
            filas_con_frescura_parcial += 1
        cruda = base if es_nueva else fusionar(base, fresca, CAMPOS_FUSIONABLES)
        hash_dedup = cruda.get("hash_dedup")
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
                   if not is_known_page_asset(u)]
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
        g, correccion_geo = _geo_de_la_extraccion(cobertura, fresca)
        if correccion_geo:
            correcciones_geo[correccion_geo] += 1
        if (correccion_geo in ("conflicto_obsoleto", "caba_por_poligono")
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
        "geo_conflictos_viejos_que_ya_no_lo_son": correcciones_geo["conflicto_obsoleto"],
        "imagenes_compartidas_descartadas": imagenes_compartidas,
        "descripciones_del_sitio_descartadas": descripciones_del_sitio,
        "titulos_del_sitio_descartados": titulos_del_sitio,
        "tipos_cochera_por_accesorio_corregidos": tipos_cochera_corregidos,
        "cocheras_incoherentes_resueltas": cocheras_incoherentes,
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

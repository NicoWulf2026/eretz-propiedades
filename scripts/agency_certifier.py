#!/usr/bin/env python
"""Certificacion individual, read-only y fail-closed de una inmobiliaria ERETZ.

Reutiliza los connectors productivos, ejecuta dos corridas secuenciales sobre
la web oficial y deja evidencia durable fuera de Git. Nunca abre Supabase ni
escribe, desactiva o elimina propiedades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.base import (ESQUEMA_CHECKPOINT, HUELLA_VERSION, Checkpoint,
                             Descargador, Fuente, LimitadorDeRitmo,
                             detectar_operacion, detectar_tipo)
from connectors.century21 import Century21Connector
from connectors.generico import (ETIQUETAS_DE_CONTEO, GenericoConnector,
                                 _texto, cuerpo_principal,
                                 normalizar_texto_campos,
                                 sin_filtros_catalogo)
from connectors.tokko import (RE_COORD as TOKKO_RE_COORD, TokkoConnector,
                              _campo as tokko_campo,
                              _cantidad as tokko_cantidad,
                              _cantidad_descriptiva as tokko_cantidad_descriptiva,
                              _descripcion as tokko_descripcion,
                              _texto_plano as tokko_texto)
from connectors.wasi import (WasiConnector, _campos_descriptivos,
                             _campos_wasi, _descripcion_wasi)
from connectors.wordpress import WordPressConnector
from scripts.agency_fingerprints import (
    FINGERPRINT_SCHEMA_VERSION,
    strategy_fingerprint,
    strategy_for,
)
from scripts.run_rollout import (PRESUPUESTO_POR_FUENTE, _procesar_con,
                                 version_del_codigo)
from scripts.agency_web_discovery import es_portal, franquicia_de_dominio

CERTIFIER_VERSION = "agency_certifier_v1"
IDENTITY_STRATEGY_VERSION = "canonical_main_exact_live_v2"
LOW_INVENTORY_MAX = 11
COLLAPSE_THRESHOLD = 0.80
EXTERNAL_PORTAL_HOSTS = {
    "argenprop.com", "datoinmobiliario.com.ar", "inmoclick.com.ar",
    "mercadolibre.com.ar", "mercadolibre.com.uy", "todoprops.com.ar",
    "zonaprop.com.ar",
}
CONNECTORS = {
    "century21": Century21Connector,
    "generico": GenericoConnector,
    "tokko": TokkoConnector,
    "wasi": WasiConnector,
    "wordpress": WordPressConnector,
}
PLATFORM_CONNECTOR = {
    "CENTURY21": "century21", "TOKKO": "tokko", "WASI": "wasi",
    "WORDPRESS": "wordpress",
}

FIELDS = (
    "titulo", "descripcion", "precio", "moneda", "operacion",
    "tipo_propiedad", "direccion", "barrio", "ciudad", "provincia",
    "ambientes", "dormitorios", "banos", "superficie_total",
    "superficie_cubierta", "latitud", "longitud", "imagenes",
)
# Son senales conservadoras de que la ficha FUENTE declara un campo. Los
# numeros sueltos no cuentan: asi no confundimos una fecha con ambientes.
SOURCE_SIGNALS = {
    "titulo": re.compile(r"<(?:h1|title)\b", re.I),
    "descripcion": re.compile(r"(?:descripci[oó]n|property-description|prop-desc)", re.I),
    "precio": re.compile(r"(?:USD|U\$S|US\$|ARS|\$)\s*[\d.,]{3,}", re.I),
    # Una moneda aislada en metadata, menues o copy institucional no prueba
    # que la publicacion informe un precio. Exigimos monto adyacente.
    "moneda": re.compile(r"(?:USD|U\$S|US\$|ARS)\s*[\d.,]{3,}", re.I),
    "operacion": re.compile(
        r"(?:<title[^>]*>\s*(?:venta|alquiler)\b|"
        r"\b(?:en venta|en alquiler|se vende|se alquila|alquiler inicial)\b)", re.I),
    "tipo_propiedad": re.compile(
        r"<(?:li|span)[^>]*>\s*(?:casas?|departamentos?|terrenos?|lotes?|"
        r"locales?|oficinas?|cocheras?|galp[oó]nes?|campos?|ph)\s*</", re.I),
    "direccion": re.compile(r"class=[\"'][^\"']*direccion[^\"']*[\"']", re.I),
    "barrio": re.compile(
        r"(?:class=[\"'][^\"']*(?:barrio|neighborhood)[^\"']*[\"']|"
        r"[\"'](?:barrio|neighborhood)[\"']\s*:)", re.I),
    "ciudad": re.compile(
        r"(?:class=[\"'][^\"']*(?:ciudad|localidad)[^\"']*[\"']|"
        r"[\"'](?:ciudad|localidad|addressLocality)[\"']\s*:)", re.I),
    "provincia": re.compile(r"\bprovincia\s*:?", re.I),
    "ambientes": re.compile(r"(?:\b[1-9]\d?\s*\b(?:ambientes?\b|amb\.)|\b(?:ambientes?\b|amb\.)\s*:?\s*[1-9]\d?\b)", re.I),
    "dormitorios": re.compile(r"(?:\b[1-9]\d?\s*(?:dormitorios?|habitaciones?)|(?:dormitorios?|habitaciones?)\s*:?\s*[1-9]\d?)", re.I),
    "banos": re.compile(r"(?:\b[1-9]\d?\s*(?:ba[nñ]os?|toilettes?)|(?:ba[nñ]os?|toilettes?)\s*:?\s*[1-9]\d?)", re.I),
    "superficie_total": re.compile(r"(?:superficie\s+total|sup\.?\s*total)[^\d]{0,18}[\d.,]+\s*m", re.I),
    "superficie_cubierta": re.compile(r"(?:superficie\s+cubierta|sup\.?\s*cubierta)[^\d]{0,18}[\d.,]+\s*m", re.I),
    # Con un NUMERO al lado. `inmobiliariacip.com.ar` publica el contenedor
    # del mapa sin coordenada -`data-lat="" data-lng=""`- en 49 de sus 192
    # fichas: la senal se conformaba con el nombre del atributo, decia que
    # la fuente provee la coordenada, el extractor -con razon- no sacaba
    # nada, y el triage leyo esas 49 como extraccion fallida de radio
    # FAMILIA y paro las dos colas.
    #
    # Es el mismo modo de falla que `arbinipropiedades.com.ar`: una senal
    # mas laxa que su extractor no reporta defectos, los fabrica.
    "latitud": re.compile(
        r"(?:\blat(?:itude|itud)?\b|data-lat)[\"'\s:=]{1,6}-?\d{1,3}\.\d{3,}", re.I),
    "longitud": re.compile(
        r"(?:\bl(?:ng|on|ongitude|ongitud)\b|data-lng)[\"'\s:=]{1,6}-?\d{1,3}\.\d{3,}",
        re.I),
    "imagenes": re.compile(r"(?:og:image[^>]+prop_new|prop_new[^\"']+\.(?:jpe?g|png|webp))", re.I),
}


def source_signals(body: str, url: str = "") -> dict[str, bool]:
    # Lo que viene despues de relacionadas, footer o scripts de filtros no
    # describe la ficha principal y no puede probar que un campo fue provisto.
    main = cuerpo_principal(body)
    is_development = (
        "/emprendimiento/" in urllib.parse.urlparse(url).path.lower())
    if is_development:
        main = re.split(r">\s*UNIDADES\s*<", main, maxsplit=1, flags=re.I)[0]
    # Portales legacy insertan el formulario de busqueda dentro del mismo
    # documento que la ficha. Sus opciones ("1 dormitorio", "10 dormitorios")
    # no son atributos de la propiedad y se eliminan por su contrato HTML
    # explicito, sin recortar el detalle ni la galeria.
    main = sin_filtros_catalogo(main)
    signals = {field: bool(pattern.search(main))
               for field, pattern in SOURCE_SIGNALS.items()}
    # Un icono con alt="direccion" no es una direccion. Debe haber texto real
    # dentro del bloque de la ficha.
    address_blocks = re.findall(
        r"<p[^>]+class=[\"'][^\"']*direccion[^\"']*[\"'][^>]*>(.*?)</p>",
        main, re.I | re.S)
    address_text = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).strip()
                    for block in address_blocks]
    signals["direccion"] = any(len(text) >= 4 for text in address_text)
    text = normalizar_texto_campos(_texto(main))
    # Las entidades HTML se vuelven texto visible recien aqui. Portales
    # legacy publican "Descripci&oacute;n" y no deben figurar como si la fuente
    # no hubiese provisto el campo.
    signals["descripcion"] = bool(re.search(r"\bdescripci[oó]n\b", text, re.I))
    title_match = re.search(
        r"<title[^>]*>(.{1,200}?)</title>", main, re.S | re.I)
    title = _texto(title_match.group(1)) if title_match else ""
    signals["operacion"] = bool(
        detectar_operacion(f"{title} {url}")
        or GenericoConnector._operacion_en_la_ficha(text))
    # Para cantidades y moneda auditamos texto visible, no atributos meta ni
    # bloques estructurales invisibles. Un cero explicito (p. ej. dormitorios
    # de un terreno) no constituye un valor extraible del campo.
    for field in ("moneda", "ambientes", "dormitorios", "banos"):
        signals[field] = bool(SOURCE_SIGNALS[field].search(text))
    # Cuando la ficha publica sus atributos como pares rotulo/valor, el
    # extractor lee la estructura y descarta la prosa a proposito. La senal de
    # fuente tiene que leer donde lee el extractor: si no, el auditor exige un
    # dato que el parser fue disenado para no tomar, y la agencia queda en
    # NEEDS_FIX por hacer lo correcto.
    #
    # Las dos fichas que lo probaron: la descripcion de un monoambiente habla
    # de "departamentos monoambientes, 1 y 2 dormitorios" -la mezcla de
    # unidades del EDIFICIO- y la de un terreno describe la casa a demoler que
    # tiene encima. Ninguna de las dos publica dormitorios propios.
    if GenericoConnector._es_tabla_estructurada(main):
        for campo, etiqueta in ETIQUETAS_DE_CONTEO.items():
            signals[campo] = GenericoConnector._cuenta_de_ficha(
                main, "", etiqueta, None) is not None
    if is_development:
        # Un desarrollo ofrece unidades heterogeneas; sus cantidades no son
        # un escalar propio del registro padre aunque la descripcion enumere
        # tipologias disponibles.
        for field in ("ambientes", "dormitorios", "banos"):
            signals[field] = False
    # Un valor como 1 m2 es provisto pero inválido para una propiedad. No es
    # un fallo del extractor que la normalización conservadora lo descarte.
    signals["superficie_total"] = bool(
        GenericoConnector._sup(text, r"total|terreno"))
    signals["superficie_cubierta"] = bool(
        GenericoConnector._sup(text, r"cubiert|construid"))
    return signals


def tokko_source_signals(body: str, url: str = "") -> dict[str, bool]:
    """Señales conservadoras del contrato Tokko TFW, sin relacionadas."""
    text = tokko_texto(body)
    description = tokko_descripcion(text)
    title_match = (re.search(
        r'<meta[^>]+property="og:title"[^>]+content="([^"]{1,200})"', body, re.I)
        or re.search(r"<title[^>]*>(.{1,200}?)</title>", body, re.S | re.I))
    title = title_match.group(1) if title_match else ""
    source_id_match = re.search(r"/p/(\d+)", url)
    source_id = source_id_match.group(1) if source_id_match else ""
    money = re.search(
        r"(?:VENTA|ALQUILER[A-ZÁ ]*|TEMPORARIO)\s*"
        r"(?:USD|U\$S|US\$|\$)\s*[\d.,]{3,15}", text, re.I)
    # La senal pregunta EXACTAMENTE lo que pregunta el extractor, incluida la
    # guarda de unidad. Sin ella, `arbinipropiedades.com.ar` -que en la prosa
    # dice "Terreno 127 mx 50 m 6.350 m2"- daba superficie_total como provista
    # leyendo el ANCHO del lote como si fuera el area, el extractor se negaba
    # -correctamente- y el triage lo leyo como un defecto de radio FAMILIA y
    # paro las dos colas. Una senal mas laxa que su extractor fabrica defectos.
    total = re.search(
        r"(?:Superficie total|Total terreno|Terreno)\s*:?\s*[\d.,]+\s*"
        r"(?:ha|m)(?![a-z])", text, re.I)
    covered = re.search(
        r"(?:Total construido|Superficie cubierta|Cubierta|Total Built)"
        r"\s*:?\s*[\d.,]+\s*m(?![a-z])", text, re.I)
    return {
        "titulo": bool(title),
        "descripcion": bool(description),
        "precio": bool(money),
        "moneda": bool(money),
        "operacion": bool(re.search(r"\b(?:Venta|Alquiler|Temporario)\b", title, re.I)),
        "tipo_propiedad": bool(re.search(
            r"\b(?:Casa|PH|Departamento|Terreno|Lote|Local|Oficina|Cochera|Galp[oó]n)\b",
            title, re.I)),
        "direccion": bool(tokko_campo(text, "Dirección")
                           or tokko_campo(text, "Direccion")),
        "barrio": bool(tokko_campo(text, "Ubicación")
                        or tokko_campo(text, "Ubicacion")),
        "ciudad": False,
        "provincia": False,
        "ambientes": bool(tokko_cantidad(text, "Ambientes")),
        "dormitorios": bool(tokko_cantidad(text, "Dormitorios")
                             or tokko_cantidad_descriptiva(
                                 description, r"dormitorios?|habitaciones?")),
        "banos": bool(tokko_cantidad(text, "Baños", "Banos")
                       or tokko_cantidad_descriptiva(description, r"ba[nñ]os?")),
        "superficie_total": bool(total),
        "superficie_cubierta": bool(covered),
        "latitud": bool(TOKKO_RE_COORD.search(body)),
        "longitud": bool(TOKKO_RE_COORD.search(body)),
        "imagenes": bool(source_id and re.search(
            rf"static\.tokkobroker\.com/(?:pictures|thumbs)/{re.escape(source_id)}_",
            body, re.I)),
    }


def wasi_source_signals(body: str) -> dict[str, bool]:
    """Señales escalares alineadas con la tabla y descripción Wasi."""
    signals = source_signals(body)
    campos = _campos_wasi(body)
    tipo = detectar_tipo(campos.get("tipo_propiedad"))
    descriptivos, ambiguos = _campos_descriptivos(_descripcion_wasi(body), tipo)
    for campo in ("ambientes", "dormitorios", "banos",
                  "superficie_total", "superficie_cubierta"):
        signals[campo] = bool(campos.get(campo) is not None
                              or campo in descriptivos or campo in ambiguos)
    return signals


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                if line.strip():
                    rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    """Agrega una linea, con una sola llamada al sistema.

    Con dos workers, dos procesos agregan al mismo artefacto. Un `write`
    de Python puede partirse en varias llamadas y dejar media linea de un
    proceso adentro de la linea del otro: un JSONL corrupto justo en el
    archivo que es la fuente de verdad de las certificaciones.

    Abriendo con `O_APPEND` y escribiendo el renglon entero de una vez, el
    sistema operativo serializa la escritura y cada linea llega completa.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    renglon = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        os.write(descriptor, renglon)
    finally:
        os.close(descriptor)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def host(url: str | None) -> str:
    return (urllib.parse.urlparse(url or "").hostname or "").lower().removeprefix("www.")


def external_portal(url: str | None) -> bool:
    current = host(url)
    return es_portal(url or '') or any(
        current == blocked or current.endswith("." + blocked)
        for blocked in EXTERNAL_PORTAL_HOSTS)


def content_present(value: Any) -> bool:
    return not isinstance(value, bool) and value not in (None, "", [], {})


def collapse_ratio(current: int, baseline: int | None) -> float | None:
    if not baseline or baseline <= 0:
        return None
    return max(0.0, 1.0 - current / baseline)


def needs_exhaustive_review(current: int, baseline: int | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if current <= LOW_INVENTORY_MAX:
        reasons.append("LOW_INVENTORY_0_11")
    collapse = collapse_ratio(current, baseline)
    if collapse is not None and collapse > COLLAPSE_THRESHOLD:
        reasons.append("COLLAPSE_GT_80_PERCENT")
    return bool(reasons), reasons


def classify_field(source_has: bool | None, normalized_has: bool) -> str:
    if normalized_has:
        return "EXTRACTED"
    if source_has:
        return "EXTRACTION_FAILED"
    if source_has is None:
        return "SOURCE_UNKNOWN"
    return "SOURCE_NOT_PROVIDED"


def stable_signature(properties: Iterable[dict[str, Any]]) -> str:
    payload = sorted((str(p.get("hash_dedup")), str(p.get("fingerprint")))
                     for p in properties)
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


# Lo que el pipeline promete: las columnas del contrato. `extra` lleva los
# atributos que cada plataforma publica de mas y se pasan tal cual.
COLUMNAS_DEL_CONTRATO = (
    "titulo", "descripcion", "precio", "moneda", "operacion", "tipo_propiedad",
    "direccion", "barrio", "ciudad", "provincia", "latitud", "longitud",
    "dormitorios", "banos", "ambientes", "superficie_total",
    "superficie_cubierta", "imagenes", "source_status")


def firma_de_columnas(properties: Iterable[dict[str, Any]]) -> str:
    """Huella de lo que promete el contrato, sin los atributos de plataforma.

    Sirve para separar dos cosas que se veian iguales: que nuestra extraccion
    sea inestable, que es un defecto, y que la fuente parpadee en un atributo
    opcional, que no lo es y no lo podemos arreglar.

    La distincion no es de conveniencia: los cinco defectos reales encontrados
    -prosa como barrio, tipo adivinado, ficha vacia, atributos corridos, fotos
    ajenas- se manifestaron TODOS en columnas del contrato. Ninguno en `extra`.
    """
    payload = sorted(
        (str(p.get("hash_dedup")),
         json.dumps([p.get(c) for c in COLUMNAS_DEL_CONTRATO],
                    ensure_ascii=False, sort_keys=True))
        for p in properties)
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def compare_runs(run1: dict[str, Any], run2: dict[str, Any]) -> dict[str, Any]:
    props1, props2 = run1.get("_props", []), run2.get("_props", [])
    urls1 = {p.get("source_url") for p in props1 if p.get("source_url")}
    urls2 = {p.get("source_url") for p in props2 if p.get("source_url")}
    changes = Counter(p.get("_cambio") for p in props2)
    # Contar URLs distintas no dice cuantas propiedades quedan guardadas.
    # `hash_dedup` normaliza la URL —descarta el fragmento, los parametros de
    # tracking, la barra final— asi que dos avisos que se ven distintos pueden
    # colapsar en una sola fila. Una landing de Bitrix enumeraba tres tarjetas
    # que compartian una unica identidad: la certificacion informaba tres
    # propiedades donde el pipeline habria guardado una, y nada lo decia.
    ids2 = {p.get("hash_dedup") for p in props2 if p.get("hash_dedup")}
    return {
        "run2_identities": len(ids2),
        "identity_collisions": max(len(urls2) - len(ids2), 0),
        "run1_urls": len(urls1), "run2_urls": len(urls2),
        "same_url_set": urls1 == urls2,
        "missing_in_run2": len(urls1 - urls2),
        "new_in_run2": len(urls2 - urls1),
        "same_content_signature": stable_signature(props1) == stable_signature(props2),
        "same_contract_signature": (firma_de_columnas(props1)
                                    == firma_de_columnas(props2)),
        "run2_changes": dict(changes),
        "idempotent": (urls1 == urls2 and not changes.get("NUEVA", 0)
                       and not changes.get("MODIFICADA", 0)),
    }


def load_catalog(v2: Path, data_dir: Path, platform_directory: Path) -> dict[str, dict[str, Any]]:
    resolution = {r["canonical_agency_id"]: r
                  for r in read_jsonl(v2 / "AGENCY_ID_RESOLUTION_FINAL.jsonl")}
    live = {r["canonical_agency_id"]: r
            for r in read_jsonl(v2 / "LIVE_AGENCY_IDENTITY_VALIDATION.jsonl")}
    sources = {r["canonical_agency_id"]: r
               for r in read_jsonl(data_dir / "scrape_source_technology_map.jsonl")}
    platforms = {r["canonical_agency_id"]: r
                 for r in read_jsonl(platform_directory)}
    directory = {r["canonical_agency_id"]: r
                 for r in read_jsonl(data_dir / "agency_web_directory.jsonl")}
    # La web que alguien ABRIO y comprobo. `agency_web_directory.jsonl` viene de
    # `free_web_audit_v1`, que puntuo urls sin abrirlas: 597 de 598 dominios
    # descubiertos traen `OFFICIAL_WEB_HIGH_CONFIDENCE`, o sea que ese estado no
    # distingue el sitio propio del de un cuartel de bomberos. Esta salida si
    # abrio la pagina.
    verificada = {r["canonical_agency_id"]: r
                  for r in read_jsonl(data_dir / "AGENCY_OFFICIAL_WEB_VERIFIED.jsonl")
                  if r.get("verificacion") == "VERIFICADA_ARGENTINA"
                  and r.get("official_url")}
    keys = (set(resolution) | set(sources) | set(platforms) | set(directory)
            | set(verificada))
    return {key: {"resolution": resolution.get(key, {}),
                  "live": live.get(key, {}), "source": sources.get(key, {}),
                  "platform": platforms.get(key, {}),
                  "directory": directory.get(key, {}),
                  "verificada": verificada.get(key, {})}
            for key in keys}


def choose_connector(record: dict[str, dict[str, Any]]) -> str:
    if selected_source(record)[1] == "verified_recovery":
        # Technology/pattern evidence from a rejected portal does not describe
        # the recovered official website. Discover it with the generic family.
        return "generico"
    platform = record["platform"]
    named = str(platform.get("connector") or "").lower()
    if named in CONNECTORS:
        return named
    detected = str(record["source"].get("detected_platform") or "").upper()
    return PLATFORM_CONNECTOR.get(detected, "generico")


def baseline_inventory(record: dict[str, dict[str, Any]], pre_db: Path,
                       canonical_id: str) -> tuple[int | None, dict[str, Any]]:
    platform = record["platform"]
    candidates = [platform.get("declared_inventory"),
                  platform.get("enumerated_inventory"),
                  platform.get("properties_normalized")]
    prior = 0
    if pre_db.exists():
        connection = sqlite3.connect(f"file:{pre_db.as_posix()}?mode=ro", uri=True)
        try:
            prior = int(connection.execute(
                "SELECT count(*) FROM rows WHERE canonical_id = ?", (canonical_id,)
            ).fetchone()[0])
        finally:
            connection.close()
    numeric = [int(x) for x in candidates if isinstance(x, (int, float)) and x >= 0]
    if prior:
        numeric.append(prior)
    return (max(numeric) if numeric else None,
            {"declared": platform.get("declared_inventory"),
             "enumerated": platform.get("enumerated_inventory"),
             "normalized": platform.get("properties_normalized"),
             "preingestion_rows": prior})


def selected_source(record: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
    """Single effective selection used by identity and connector choice.

    Keep explicit operational overrides. Recover a rejected portal only from
    an existing, agency-keyed, actually verified Argentine official website.
    No name/URL heuristic or discovery candidate can authorize this recovery.
    """
    candidates = (
        (record.get("platform", {}).get("domain"), "platform"),
        (record.get("source", {}).get("official_url"), "source"),
        (record.get("resolution", {}).get("official_domain"), "resolution"),
        (record.get("verificada", {}).get("official_url"), "verified"),
        (record.get("directory", {}).get("official_url"), "directory"),
    )
    url, origin = next(((url, origin) for url, origin in candidates if url), (None, "none"))
    verified = record.get("verificada") or {}
    recovered = verified.get("official_url")
    if (url and external_portal(url) and recovered
            and verified.get("verificacion") == "VERIFICADA_ARGENTINA"
            and not external_portal(recovered)
            and not franquicia_de_dominio(recovered)):
        parsed = urllib.parse.urlparse(recovered)
        if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
            return recovered, "verified_recovery"
    return url, origin


def resolve_identity(record: dict[str, dict[str, Any]], canonical_id: str) -> dict[str, Any]:
    resolution, live = record["resolution"], record["live"]
    source, platform, directory = record["source"], record["platform"], record["directory"]
    eretz_id = resolution.get("eretz_id") or live.get("eretz_id") or platform.get("eretz_id")
    # La web leida va ANTES del directorio: evidencia que alguien abrio le gana
    # a un puntaje calculado sobre la cadena de la url sin visitarla.
    official, source_origin = selected_source(record)
    name = (resolution.get("agency_name") or source.get("agency_name")
            or platform.get("agency_name") or directory.get("agency_name") or canonical_id)
    status = "READY"
    reasons: list[str] = []
    if resolution.get("resolution_status") != "RESOLVED" or not eretz_id:
        status = "IDENTITY_PENDING"
        reasons.append("canonical agency lacks a resolved ERETZ foreign key")
    if live.get("validation_status") != "VALIDATED":
        status = "IDENTITY_PENDING"
        reasons.append("live identity was not validated")
    if not official:
        status = "IDENTITY_PENDING"
        reasons.append("official website unavailable")
    if official and external_portal(official):
        status = "BLOCKED_EXTERNAL"
        reasons.append("source points to an external property portal")
    if (source_origin != "verified_recovery"
            and platform.get("web_kind") not in (None, "OFFICIAL_WEB")):
        status = "BLOCKED_EXTERNAL"
        reasons.append(f"web_kind={platform.get('web_kind')}")
    return {"canonical_agency_id": canonical_id, "eretz_id": eretz_id,
            "agency_name": name, "official_url": official,
            "identity_status": status, "identity_reasons": reasons,
            "identity_evidence": {"resolution_status": resolution.get("resolution_status"),
                                  "live_validation": live.get("validation_status"),
                                  "web_kind": ("OFFICIAL_WEB" if source_origin == "verified_recovery"
                                               else platform.get("web_kind")),
                                  "source_origin": source_origin,
                                  "selection_version": "effective_source_v2"}}


class AuditDownloader(Descargador):
    """Downloader de produccion mas evidencia no sensible en memoria."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.pages: dict[str, dict[str, Any]] = {}

    def bajar(self, url: str) -> str:
        body = super().bajar(url)
        external_hosts = sorted({
            host(urllib.parse.urljoin(url, match.group(1)))
            for match in re.finditer(r'href=["\']([^"\']{4,600})', body, re.I)
            if external_portal(urllib.parse.urljoin(url, match.group(1)))
        })
        self.pages[url] = {
            "bytes": len(body.encode("utf-8", "ignore")),
            "sha256": hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
            "source_signals": source_signals(body, url),
            "source_signals_tokko": tokko_source_signals(body, url),
            "source_signals_wasi": wasi_source_signals(body),
            "requires_javascript_signal": bool(re.search(
                r"(?:__NEXT_DATA__|<div\s+id=[\"']root[\"']|enable javascript)", body, re.I)),
            "external_catalog_hosts": external_hosts,
        }
        return body


def field_audit(properties: list[dict[str, Any]], pages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_by_url = {
        urllib.parse.unquote(url).rstrip("/"): evidence for url, evidence in pages.items()
    }
    rows: dict[str, Any] = {}
    for field in FIELDS:
        present = sum(content_present(prop.get(field)) for prop in properties)
        source_present = 0
        extraction_failed = 0
        validation_rejected = 0
        failure_examples: list[str] = []
        for prop in properties:
            url = urllib.parse.unquote(str(prop.get("source_url") or "")).rstrip("/")
            evidence = evidence_by_url.get(url, {})
            # En WordPress REST la pagina fuente real es el objeto JSON, no la
            # ficha HTML. La API puede exponer taxonomias/meta que la ficha no
            # rotula, y el HTML puede variar por widgets o cache. El connector
            # deja la evidencia estructurada junto a la propiedad para auditar
            # exactamente el mismo contrato que normalizo.
            structured_via = (prop.get("extra") or {}).get("via")
            if ((prop.get("connector") == "wordpress" and structured_via == "rest")
                    or structured_via in {
                        "xintel_api", "wordpress_category_catalog",
                        "mapaprop_html", "php_ajax_search"}):
                signal = bool((prop.get("extra") or {}).get(
                    "source_fields_provided", {}).get(field))
                # Candidatos previos al filtro no prueban fotos propias.
                # Una galería normalizada vacía tampoco prueba que la fuente
                # no ofreciera ninguna; sin evidencia adicional es UNKNOWN.
                if field == "imagenes" and not content_present(prop.get(field)):
                    signal = False
            else:
                signal_key = ({"tokko": "source_signals_tokko",
                               "wasi": "source_signals_wasi"}
                              .get(prop.get("connector"), "source_signals"))
                signal = bool(evidence.get(signal_key, {}).get(field))
            source_present += signal
            if content_present(prop.get(field)):
                continue
            discarded = str((prop.get("extra") or {}).get("atributos_descartados") or "")
            rejected = (field in discarded or
                        (field in {"ambientes", "dormitorios"}
                         and "dormitorios>ambientes" in discarded) or
                        (field in {"superficie_total", "superficie_cubierta"}
                         and "cubierta>total" in discarded) or
                        (field in {"latitud", "longitud"}
                         and "coordenada_fuera_de_argentina" in discarded))
            if rejected:
                validation_rejected += 1
            elif signal:
                extraction_failed += 1
                if len(failure_examples) < 20:
                    failure_examples.append(str(prop.get("source_url")))
        state = ("EXTRACTION_FAILED" if extraction_failed else
                 "REJECTED_BY_VALIDATION" if validation_rejected else
                 classify_field(True if source_present else None, present > 0))
        rows[field] = {"state": state, "normalized_present": present,
                       "normalized_total": len(properties),
                       "coverage": round(present / len(properties), 4) if properties else 0.0,
                       "source_provided": source_present,
                       # Detectors provide positive signals, not exhaustive
                       # proof that every unobserved field is absent in source.
                       "source_not_provided": 0,
                       "source_unknown": len(properties) - source_present,
                       "source_signals_absent": len(properties) - source_present,
                       "extraction_failed": extraction_failed,
                       "validation_rejected": validation_rejected,
                       "failure_examples": failure_examples}
    return rows


def diagnose_enumeration(run: dict[str, Any], baseline: int | None,
                          pages: dict[str, dict[str, Any]]) -> dict[str, Any]:
    current = int(run.get("urls_unicas") or 0)
    review, reasons = needs_exhaustive_review(current, baseline)
    digests = [p["sha256"] for p in pages.values()]
    repeated_responses = len(digests) - len(set(digests))
    independent = [x for x in (baseline, run.get("total_declarado"))
                   if isinstance(x, (int, float))]
    independent_max = max(independent) if independent else None
    independent_gap = (int(independent_max) - current
                       if independent_max is not None else None)
    external_hosts = sorted({host_name for page in pages.values()
                             for host_name in page.get("external_catalog_hosts", [])})
    return {
        "baseline": baseline, "enumerated": current,
        "collapse_ratio": collapse_ratio(current, baseline),
        "exhaustive_review_required": review,
        "review_reasons": reasons,
        "pages_observed": len(pages), "repeated_response_digests": repeated_responses,
        "javascript_signals": sum(bool(p["requires_javascript_signal"])
                                  for p in pages.values()),
        "declared_total": run.get("total_declarado"),
        "enumeration_complete_by_connector": run.get("enumeracion_completa"),
        "coverage_by_connector": run.get("cobertura"),
        "independent_max_inventory_signal": independent_max,
        "independent_gap": independent_gap,
        "independent_source_exceeds_scraper": bool(independent_gap and independent_gap > 0),
        "external_catalog_hosts": external_hosts,
    }


def debe_reintentar_con_generico(connector_name: str,
                                 result: dict[str, Any]) -> bool:
    """Si conviene reintentar con el connector generico.

    Una plataforma declarada puede haber cambiado, y el fallback solo reemplaza
    al especifico si obtiene algo: nunca para mezclar ambos.

    Alcanza con que el especifico no haya obtenido NADA, sin exigirle ademas
    que se declare no soportado. Un connector que termina en OK con cero no
    distingue "esta inmobiliaria no publica" de "elegimos el connector
    equivocado": requenapropiedades.com.ar es una app Laravel y se le asigno el
    de WordPress porque el HTML menciona `wp-content`, la corrida cerro en OK
    con cero, se reporto sin inventario, y el sitio publica trece paginas de
    fichas. Un cero se demuestra, no se hereda del connector que elegimos.

    La excepcion es `BLOQUEADA`: ahi la fuente rechazo el acceso automatico y
    volver a pedirle lo mismo con otro connector la golpea sin aprender nada.
    """
    return (connector_name != "generico"
            and not result.get("_props")
            and result.get("estado") != "BLOQUEADA")


def run_once(connector_name: str, source: Fuente, checkpoint: Checkpoint,
             interval: float, max_listings: int, budget: float) -> tuple[dict[str, Any], AuditDownloader]:
    downloader = AuditDownloader(LimitadorDeRitmo(interval), timeout=25,
                                 reintentos=3, limite_bytes=800_000)
    connector = CONNECTORS[connector_name](downloader, checkpoint)
    result = _procesar_con(connector, source, max_listings, True, budget)
    if debe_reintentar_con_generico(connector_name, result):
        fallback = GenericoConnector(downloader, checkpoint)
        alternate = _procesar_con(fallback, source, max_listings, True, budget)
        if alternate.get("detalles_obtenidos") or alternate.get("estado") == "OK":
            alternate["fallback_from"] = connector_name
            result = alternate
    checkpoint.guardar()
    return result, downloader


def public_run(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if not key.startswith("_")}


def operational_metrics(canonical_id: str, connector: str, strategy: str,
                        run1: dict[str, Any], run2: dict[str, Any],
                        download1: "AuditDownloader",
                        download2: "AuditDownloader",
                        terminal_status: str) -> dict[str, Any]:
    properties = int(run2.get("detalles_obtenidos") or 0)
    requests = int(download1.pedidos + download2.pedidos)
    return {
        "canonical_agency_id": canonical_id,
        "connector": connector,
        "strategy": strategy,
        "properties": properties,
        "requests": requests,
        "duration_seconds": round(float(run1.get("segundos") or 0)
                                  + float(run2.get("segundos") or 0), 1),
        "requests_per_property": (
            round(requests / properties, 4) if properties else None),
        "retries": int(run1.get("reintentos_diferidos") or 0)
        + int(run2.get("reintentos_diferidos") or 0),
        "network_errors": int(run1.get("detalles_fallidos") or 0)
        + int(run2.get("detalles_fallidos") or 0),
        "result": terminal_status,
        "run1_duration_seconds": float(run1.get("segundos") or 0),
        "run2_duration_seconds": float(run2.get("segundos") or 0),
    }


def certification_status(run1: dict[str, Any], run2: dict[str, Any],
                         comparison: dict[str, Any], enumeration: dict[str, Any],
                         fields: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    states = {run1.get("estado"), run2.get("estado")}
    # El rechazo se decide PRIMERO: es una respuesta del sitio, no una
    # ausencia, y confundirlo con una baja daria por muerta a una fuente que
    # esta viva y solo no nos quiere.
    if states & {"BLOQUEADA"}:
        return "BLOCKED_EXTERNAL", ["official source rejected automated access"]
    # Un dominio suspendido o vencido no es una inmobiliaria sin propiedades ni
    # un defecto nuestro: es una fuente que dejo de publicar. Dejarlo en
    # NEEDS_FIX lo condena a esperar para siempre un arreglo que no existe.
    #
    # Se exige que las DOS corridas lo vean: una pagina de baja puede ser un
    # error momentaneo del hosting, y dar de baja una inmobiliaria viva por una
    # lectura es peor que revisarla de nuevo manana.
    bajas = [c.get("fuera_de_servicio") for c in (run1, run2)]
    if all(bajas):
        return "INACTIVE", [
            f"the domain is not serving a website: {bajas[0]}"]
    if (states == {"VARIANTE_NO_SOPORTADA"}
            and enumeration.get("external_catalog_hosts")):
        return "BLOCKED_EXTERNAL", [
            "official site delegates inventory to an external property portal"]
    # Una corrida que se quedo sin presupuesto esta truncada: comparar media
    # inventario contra el inventario entero no dice nada sobre la fuente, dice
    # que se acabo el reloj. Informarlo como "no es idempotente" manda a buscar
    # un defecto de extraccion que no existe.
    truncadas = [run for run in (run1, run2) if run.get("presupuesto_agotado")]
    if truncadas:
        return "NEEDS_FIX", [
            "one or both runs ran out of time budget before finishing; "
            "the comparison between them is not conclusive"]

    estados_no_ok = states - {"OK"}
    agotadas = all(bool(run.get("enumeracion_agotada"))
                   for run in (run1, run2))
    if estados_no_ok == {"ENUMERACION_INCOMPLETA"} and agotadas:
        # La paginacion llego hasta el final y aun asi quedo por debajo del
        # total que el sitio declara de si mismo. No es lo mismo que haber
        # cortado antes de tiempo, y el contador del sitio puede estar mal:
        # berruetainmob.com.ar declara 197, sirve 193, y la ficha 194 que
        # aparecia era /propiedad/0, que devuelve el catalogo entero.
        #
        # Se registra como limitacion documentada y no como defecto. La perdida
        # grave de inventario la sigue atajando `collapse_ratio`, que compara
        # contra lo que esta inmobiliaria tenia, no contra un numero que
        # publica su propia pagina y que nadie verifico.
        enumeration.setdefault("review_reasons", []).append(
            "DECLARED_TOTAL_ABOVE_ENUMERATION")
        enumeration["exhaustive_review_required"] = True
    elif estados_no_ok:
        reasons.append("one or both runs did not finish with connector state OK")
    # Un 404 sobre una ficha que la fuente sigue enlazando no es una lectura
    # fallida: es una inconsistencia de la fuente. `almadimatteo.com.ar`
    # publica 28 enlaces y 3 estan muertos; con la regla anterior ese sitio no
    # podia certificar nunca, aunque sus 25 propiedades vivas se leyeran
    # enteras y de forma idempotente.
    #
    # Solo se descuentan las que desaparecieron en LAS DOS corridas: una baja
    # que aparece en una sola no es una baja, es un sitio inestable.
    fallidos_de_lectura = max(
        0, int(run1.get("detalles_fallidos") or 0)
        - min(int(run1.get("detalles_desaparecidos") or 0),
              int(run2.get("detalles_desaparecidos") or 0)))
    fallidos_de_lectura += max(
        0, int(run2.get("detalles_fallidos") or 0)
        - min(int(run1.get("detalles_desaparecidos") or 0),
              int(run2.get("detalles_desaparecidos") or 0)))
    if fallidos_de_lectura:
        reasons.append("one or more listing details failed")
    if not comparison["same_url_set"]:
        reasons.append("run inventories differ")
    if not comparison["idempotent"]:
        if (comparison.get("same_url_set")
                and comparison.get("same_contract_signature")):
            # Lo que cambio entre corridas esta en `extra`, no en el contrato:
            # la fuente parpadea en un atributo opcional que publica de mas. No
            # es inestabilidad nuestra y no se puede arreglar del lado de aca.
            enumeration.setdefault("review_reasons", []).append(
                "UNSTABLE_SOURCE_ATTRIBUTES")
            enumeration["exhaustive_review_required"] = True
        else:
            reasons.append("second run is not idempotent")
    colisiones = comparison.get("identity_collisions") or 0
    if colisiones:
        reasons.append(
            f"{colisiones} listings collapse into another identity after url "
            "normalization")
    failures = [field for field, audit in fields.items()
                if audit["state"] == "EXTRACTION_FAILED"]
    if failures:
        reasons.append("source fields not extracted: " + ", ".join(failures))
    collapse = enumeration.get("collapse_ratio")
    if collapse is not None and collapse > COLLAPSE_THRESHOLD:
        reasons.append("inventory collapsed by more than 80% against baseline")
    current = int(enumeration.get("enumerated") or 0)
    if current == 0:
        if not reasons and enumeration.get("pages_observed", 0) >= 2:
            return "NO_INVENTORY_CONFIRMED", ["two stable runs found no listing"]
        reasons.append("zero inventory was not exhaustively proven")
    if reasons:
        return "NEEDS_FIX", reasons
    if enumeration.get("exhaustive_review_required"):
        return "CERTIFIED_BEST_AVAILABLE", enumeration["review_reasons"]
    return "CERTIFIED_COMPLETE", ["two complete idempotent runs passed"]


def certify(canonical_id: str, catalog: dict[str, dict[str, Any]], output: Path,
            pre_db: Path, interval: float = 1.5, max_listings: int = 0,
            budget: float = 1800.0) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    packet_dir = output / "agencies" / hashlib.sha256(canonical_id.encode()).hexdigest()[:16]
    packet_dir.mkdir(parents=True, exist_ok=True)
    record = catalog.get(canonical_id)
    if record is None:
        result = {"canonical_agency_id": canonical_id, "status": "IDENTITY_PENDING",
                  "reasons": ["canonical agency is absent from all identity artifacts"],
                  "certifier_version": CERTIFIER_VERSION, "checked_at": started}
        write_json(packet_dir / "certification.json", result)
        return result

    identity = resolve_identity(record, canonical_id)
    base_result = {**identity, "certifier_version": CERTIFIER_VERSION,
                   "checked_at": started}
    if identity["identity_status"] != "READY":
        result = {**base_result, "status": identity["identity_status"],
                  "reasons": identity["identity_reasons"]}
        write_json(packet_dir / "certification.json", result)
        return result

    connector_name = choose_connector(record)
    recovered_source = selected_source(record)[1] == "verified_recovery"
    baseline, baseline_evidence = baseline_inventory(record, pre_db, canonical_id)
    source = Fuente(canonical_agency_id=canonical_id,
                    agency_name=str(identity["agency_name"]),
                    official_url=str(identity["official_url"]),
                    inmobiliaria_id=int(identity["eretz_id"]),
                    detected_platform=(None if recovered_source else record["source"].get("detected_platform")),
                    extra={"city": record["directory"].get("city"),
                           "province": record["directory"].get("province"),
                           "patron_ficha": (None if recovered_source
                                            else record["platform"].get("pattern_ficha"))})
    checkpoint = Checkpoint(packet_dir / "checkpoint.json")
    try:
        run1, download1 = run_once(connector_name, source, checkpoint, interval,
                                   max_listings, budget)
        run2, download2 = run_once(connector_name, source, checkpoint, interval,
                                   max_listings, budget)
    except Exception as error:
        result = {**base_result, "status": "NEEDS_FIX", "connector": connector_name,
                  "reasons": [f"unhandled {type(error).__name__}: {str(error)[:160]}"]}
        write_json(packet_dir / "certification.json", result)
        return result

    pages = {**download1.pages, **download2.pages}
    comparison = compare_runs(run1, run2)
    enumeration = diagnose_enumeration(run2, baseline, pages)
    fields = field_audit(run2.get("_props", []), pages)
    status, reasons = certification_status(run1, run2, comparison, enumeration, fields)
    site_hashes = sorted(page["sha256"] for page in pages.values())
    site_fingerprint = hashlib.sha256("".join(site_hashes).encode()).hexdigest()[:16]
    effective_connector = run2.get("connector") or connector_name
    connector_strategy = strategy_for(
        effective_connector, run2.get("variante"))
    result = {
        **base_result, "status": status, "reasons": reasons,
        "platform": (None if recovered_source else record["source"].get("detected_platform")),
        "publication_mechanism": run2.get("variante"),
        "connector": effective_connector,
        "connector_version": version_del_codigo(effective_connector),
        "connector_strategy": connector_strategy,
        "strategy_fingerprint": strategy_fingerprint(
            effective_connector, connector_strategy),
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
        "normalizer_version": HUELLA_VERSION,
        "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
        "checkpoint_schema_version": ESQUEMA_CHECKPOINT,
        "code_fingerprint": version_del_codigo(effective_connector),
        "site_fingerprint": site_fingerprint,
        "baseline_inventory": baseline_evidence,
        "run1": public_run(run1), "run2": public_run(run2),
        "comparison": comparison, "enumeration_audit": enumeration,
        "field_coverage": fields,
        "network": {"requests_run1": download1.pedidos,
                    "requests_run2": download2.pedidos,
                    "bytes_run1": download1.bytes_bajados,
                    "bytes_run2": download2.bytes_bajados,
                    "minimum_interval_per_host_seconds": interval},
    }
    result["operational_metrics"] = operational_metrics(
        canonical_id, effective_connector, connector_strategy,
        run1, run2, download1, download2, status)
    write_json(packet_dir / "run1.json", public_run(run1))
    write_json(packet_dir / "run2.json", public_run(run2))
    write_jsonl(packet_dir / "properties_run1.jsonl", run1.get("_props", []))
    write_jsonl(packet_dir / "properties_run2.jsonl", run2.get("_props", []))
    write_jsonl(packet_dir / "shape_rejects_run1.jsonl", run1.get("_descartes", []))
    write_jsonl(packet_dir / "shape_rejects_run2.jsonl", run2.get("_descartes", []))
    write_json(packet_dir / "field_coverage.json", fields)
    write_json(packet_dir / "metrics.json", result["operational_metrics"])
    write_json(packet_dir / "certification.json", result)
    return result


def find_canonical(catalog: dict[str, dict[str, Any]], canonical_id: str | None,
                   eretz_id: int | None) -> str:
    if canonical_id:
        return canonical_id
    matches = [key for key, record in catalog.items()
               if int(record["resolution"].get("eretz_id") or 0) == eretz_id]
    if len(matches) != 1:
        raise SystemExit(f"expected one canonical agency for ERETZ id {eretz_id}; found {len(matches)}")
    return matches[0]


def update_rollups(output: Path, result: dict[str, Any]) -> None:
    append_jsonl(output / "AGENCY_CERTIFICATION_RESULTS.jsonl", result)
    append_jsonl(output / "FIELD_COVERAGE_AUDIT.jsonl", {
        "canonical_agency_id": result["canonical_agency_id"],
        "status": result["status"], "fields": result.get("field_coverage", {})})
    if result.get("operational_metrics"):
        append_jsonl(output / "AGENCY_CERTIFICATION_METRICS.jsonl",
                     result["operational_metrics"])
    enumeration = result.get("enumeration_audit", {})
    if "LOW_INVENTORY_0_11" in enumeration.get("review_reasons", []):
        append_jsonl(output / "LOW_INVENTORY_AUDIT.jsonl", result)
    if "COLLAPSE_GT_80_PERCENT" in enumeration.get("review_reasons", []):
        append_jsonl(output / "INVENTORY_COLLAPSE_AUDIT.jsonl", result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-id")
    parser.add_argument("--eretz-id", type=int)
    parser.add_argument("--v2-dir", default=r"D:\INMO CAPITAL\ERETZ_SUPABASE_RECONCILIATION_V2_20260827")
    parser.add_argument("--data-dir", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
    parser.add_argument("--platform-directory", default=r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
    # Import local a proposito: `main` esta fuera de la huella, asi que
    # corregir a que base se apunta no invalida ninguna certificacion. Un
    # import de nivel superior si la cambiaria.
    from scripts.preingestion_manifest import base_canonica
    parser.add_argument("--preingestion-db", default=str(base_canonica()))
    parser.add_argument("--output", default=r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--max-listings", type=int, default=0,
                        help="0 certifies the full live inventory")
    # El default sale del modulo, no de un numero repetido aca: tenerlo en dos
    # lugares hizo que subir el presupuesto no tuviera ningun efecto, porque el
    # CLI seguia pasando el viejo.
    parser.add_argument("--budget", type=float,
                        default=PRESUPUESTO_POR_FUENTE)
    args = parser.parse_args()
    if bool(args.canonical_id) == bool(args.eretz_id):
        parser.error("provide exactly one of --canonical-id or --eretz-id")
    v2, data = Path(args.v2_dir), Path(args.data_dir)
    catalog = load_catalog(v2, data, Path(args.platform_directory))
    canonical_id = find_canonical(catalog, args.canonical_id, args.eretz_id)
    output = Path(args.output)
    result = certify(canonical_id, catalog, output, Path(args.preingestion_db),
                     args.interval, args.max_listings, args.budget)
    update_rollups(output, result)
    print(json.dumps({"canonical_agency_id": canonical_id,
                      "status": result["status"],
                      "enumerated": result.get("run2", {}).get("urls_unicas"),
                      "idempotent": result.get("comparison", {}).get("idempotent")},
                     ensure_ascii=False))
    return 0 if result["status"] in {
        "CERTIFIED_COMPLETE", "CERTIFIED_BEST_AVAILABLE",
        "NO_INVENTORY_CONFIRMED", "IDENTITY_PENDING", "BLOCKED_EXTERNAL"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())

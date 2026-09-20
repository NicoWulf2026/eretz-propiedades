#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""El dry-run definitivo, con la politica de merge aprobada. No escribe nada.

Una linea por candidata, y en cada una la decision explicita campo por campo:
que se completa, que se sobrescribe, que se conserva y por que. Nada queda
implicito, porque lo que no esta escrito aca es lo que despues se escribe por
descuido.

**La regla que manda sobre todas.** Un nulo nuestro NUNCA pisa un valor
productivo. Eso no es una preferencia: son 62.283 valores -sobre todo ciudad,
barrio y direccion- que un UPDATE ingenuo borraria en el 99,3 % de las filas
que ya existen.

**Las tres politicas, por familia de campo.**

  ESTRUCTURALES  precio, moneda, operacion, tipo_propiedad, ambientes,
                 dormitorios, banos, superficies, provincia, direccion.
                 Pueden sobrescribir: son numeros y etiquetas que nuestras
                 reglas de coherencia validan y el legacy no -el legacy llego a
                 guardar un timestamp en `ambientes`-.

  TEXTO Y FOTOS  titulo, descripcion, imagenes.
                 Solo completan. Que el nuestro sea distinto no lo hace mejor:
                 si produccion tiene una descripcion de 800 caracteres y
                 nosotros una de 200, "actualizar" empeora.

  GEOGRAFIA      ciudad, barrio, latitud, longitud.
                 Solo completan, y solo si la coordenada de la fila paso la
                 validacion. Nunca sobrescriben.

**La excepcion que descubrio la validacion de coordenadas.** `provincia` es
estructural, pero hay filas donde la provincia que declara la ficha contradice
su propia coordenada: `enz propiedades` publica 266 fichas de Rosario con
provincia `Catamarca` -que es una CALLE de Rosario- y `fogliese` 88 de la costa
con provincia `Ciudad Autonoma de Buenos Aires`. En esas filas no se puede
saber cual de los dos datos esta mal, asi que no se toca ninguno: ni la
provincia ni el par de coordenadas. Es GEO_CONFLICT.

Es un defecto de extraccion en componente fingerprintado. Queda anotado; no se
arregla aca.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from hashlib import md5
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

# --- lo que bajo de produccion, en el orden en que lo bajo -------------------

PRESENCIA = ("precio", "moneda", "ambientes", "dormitorios", "banos",
             "superficie_total", "superficie_cubierta", "latitud", "ciudad",
             "barrio", "provincia", "direccion", "titulo", "descripcion",
             "imagenes")
VALORES = PRESENCIA
EXTRA = ("operacion", "tipo_propiedad", "longitud")

# --- la politica ------------------------------------------------------------

ESTRUCTURALES = {"precio", "moneda", "operacion", "tipo_propiedad", "ambientes",
                 "dormitorios", "banos", "superficie_total",
                 "superficie_cubierta", "provincia", "direccion"}
SOLO_COMPLETAN = {"titulo", "descripcion", "imagenes", "ciudad", "barrio",
                  "latitud", "longitud"}
# Campos que la contradiccion geografica inhabilita en esa fila.
INHABILITA_GEO_CONFLICT = {"provincia", "latitud", "longitud", "ciudad", "barrio"}

# Urls que NO son una ficha aunque hayan entrado como candidatas.
#
# Un WordPress inmobiliario publica un sitemap INDICE, y si se consume entero
# entran las paginas de archivo -/property-city/barrio-vicente-lopez/, que
# dice "1 a 3 fuera de 3 propiedades"-, las de agente y las de amenities.
# Certificar eso da campos vacios, que es molesto; ESCRIBIRLO mete en el
# catalogo una "propiedad" que en realidad es una categoria, que es peor.
#
# Se descubrio el 2026-09-10 diagnosticando la parada de `carlos castano`.
# Son 22 candidatas en 4 agencias. La causa esta en codigo fingerprintado y
# espera la ventana semantica; el filtro de aca es para que mientras tanto no
# se escriban.
NO_SON_FICHA = ("/property-city/", "/property-type/", "/property-feature/",
                "/property-status/", "/property-label/", "/property-country/",
                "/property-state/", "/agente/", "/agent/", "/agencia/",
                "/agency/", "/socios/", "/partners/", "/author/",
                "/category/", "/tag/")

CANDIDATAS = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
                  r"\DB_WRITE_ELIGIBLE.jsonl")
DQ = Path(r"D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY")
GATE = Path(r"D:\INMO CAPITAL\ERETZ_PREINGESTION_REBUILD_20260903"
            r"\PROPERTY_QUALITY_GATE.jsonl")
DIRECTORIO = Path(r"D:\INMO CAPITAL\agency_platform_directory.jsonl")
NO_SON_WEB_PROPIA = {"EXTERNAL_PORTAL_PROFILE", "AMBIGUOUS_WEB_ATTRIBUTION",
                     "NOT_A_REAL_ESTATE_WEB"}

DECIMALES = {"precio": 2, "superficie_total": 2, "superficie_cubierta": 2,
             "latitud": 5, "longitud": 5}
ENTEROS = {"ambientes", "dormitorios", "banos"}
ESPACIOS = re.compile(r"\s+")


def firma(campo: str, valor) -> str | None:
    """La misma normalizacion que aplico Postgres del otro lado."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if campo == "imagenes":
        # Una galeria vacia NO es una galeria. Postgres da `cardinality('{}')
        # = 0` y eso hashea a algo distinto de nulo, asi que sin esta guarda
        # una ficha sin una sola foto se contaba como "trae fotos" y entraba a
        # completar la galeria de produccion con nada.
        if not isinstance(valor, (list, tuple)) or not valor:
            return None
        s = str(len(valor))
    elif campo in DECIMALES:
        try:
            s = f"{round(float(valor), DECIMALES[campo]):.{DECIMALES[campo]}f}"
            s = s.rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return None
    elif campo in ENTEROS:
        try:
            s = str(int(valor))
        except (TypeError, ValueError):
            return None
    else:
        s = ESPACIOS.sub(" ", str(valor)).strip().lower()
    return md5(s.encode()).hexdigest()[:2]


def tiene(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple, dict)):
        return len(v) > 0
    if isinstance(v, float):
        return math.isfinite(v)
    return True


def normalizar_url(u: str | None) -> str:
    p = urlsplit(u or "")
    return p.netloc.lower().removeprefix("www.") + unquote(p.path).lower().rstrip("/")


def tira(ruta: Path, largo: int) -> dict[str, str]:
    crudo = ruta.read_text(encoding="utf-8", errors="replace")
    t = max(re.findall("[0-9a-f]+", crudo), key=len, default="")
    if len(t) % largo:
        raise SystemExit(f"{ruta.name}: {len(t)} no es multiplo de {largo}")
    return {t[i:i + 8]: t[i + 8:i + largo] for i in range(0, len(t), largo)}


def agencias_ajenas() -> set[str]:
    fuera = set()
    for linea in DIRECTORIO.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        f = json.loads(linea)
        if f.get("web_kind") in NO_SON_WEB_PROPIA and f.get("canonical_agency_id"):
            fuera.add(f["canonical_agency_id"])
    return fuera


def alcances() -> dict[str, list[str]]:
    """El alcance de calidad de cada ficha, por hash."""
    fuera = {}
    if not GATE.exists():
        return fuera
    for linea in GATE.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        f = json.loads(linea)
        h = f.get("hash_dedup")
        if h:
            fuera[h] = f.get("alcances") or f.get("alcance") or []
    return fuera


def main() -> int:
    pres = tira(Path(sys.argv[1]), 8 + len(PRESENCIA))
    vals = tira(Path(sys.argv[2]), 8 + 2 * len(VALORES))
    extra = tira(Path(sys.argv[3]), 8 + 2 * len(EXTRA))
    # Segunda llave, para las que cambiaron de url. Una ficha que se renombro
    # -otro slug, mismo aviso- no resuelve por url y parece nueva. Si su
    # `id_externo` ya esta en produccion, no es nueva: insertarla duplica.
    #
    # El par (inmobiliaria_id, id_externo) NO es unico en produccion -60 pares
    # de estas agencias tienen mas de una fila-, asi que sirve para DESCARTAR
    # un alta, nunca para decidir sola cual fila actualizar.
    externos = tira(Path(sys.argv[4]), 9) if len(sys.argv) > 4 else {}
    print(f"produccion: {len(pres)} claves | {len(externos)} id_externo")

    ajenas = agencias_ajenas()
    alcance_de = alcances()

    geo = {}
    for linea in (DQ / "coordenadas_validadas.jsonl").read_text(
            encoding="utf-8").splitlines():
        if linea.strip():
            f = json.loads(linea)
            geo[f["hash_dedup"]] = f["clase"]

    clases = Counter()
    completa = Counter()
    sobrescribe = Counter()
    conserva = Counter()
    no_tocar_t = Counter()
    coord_hab = coord_bloq = 0
    omitidos_insert = Counter()
    nuevas_con_geo_recortada = 0
    salida = DQ / "dry_run_politica.jsonl"
    resumen_geo = Counter()

    with open(CANDIDATAS, encoding="utf-8") as f, \
            open(salida, "w", encoding="utf-8") as g:
        for linea in f:
            if not linea.strip():
                continue
            r: dict[str, Any] = json.loads(linea)
            h = r.get("hash_dedup")
            aid = str(r.get("inmobiliaria_id") or "")
            un = normalizar_url(r.get("source_url"))
            clase_geo = geo.get(h, "SIN_COORDENADA")
            conflicto_geo = clase_geo in ("CONTRADICE_LA_PROVINCIA",
                                          "PROVINCIA_DESCONOCIDA",
                                          "FUERA_DE_ARGENTINA", "INVERTIDA",
                                          "RANGO_IMPOSIBLE", "ORIGEN_NULO")
            resumen_geo[clase_geo] += 1

            fila = {"hash_dedup": h, "canonical_agency_id": r.get("canonical_agency_id"),
                    "inmobiliaria_id": aid, "url_normalizada": un,
                    "alcance": alcance_de.get(h, []),
                    "geo": clase_geo, "writes": False}

            if any(seg in ("/" + un) for seg in NO_SON_FICHA):
                fila.update(clase="NOT_PUBLISHABLE",
                            motivo="la url no es una ficha: es una pagina de "
                                   "archivo, de agente o de amenity")
                clases["NOT_PUBLISHABLE"] += 1
                g.write(json.dumps(fila, ensure_ascii=False) + "\n")
                continue

            if r.get("canonical_agency_id") in ajenas:
                fila.update(clase="RETENIDA_WEB_AJENA",
                            motivo="la web cargada de la inmobiliaria no es suya")
                clases["RETENIDA_WEB_AJENA"] += 1
                g.write(json.dumps(fila, ensure_ascii=False) + "\n")
                continue

            k = md5(f"{aid}|{un}".encode()).hexdigest()[:8]
            m = pres.get(k)
            if m is None and externos and r.get("source_listing_id"):
                ke = md5(f"{aid}|{r['source_listing_id']}".encode()).hexdigest()[:8]
                marca = externos.get(ke)
                if marca:
                    # Existe, pero la resolucion campo por campo se calculo
                    # contra "no hay fila", asi que no sabemos que escribirle.
                    # No se inserta y no se adivina: se lista.
                    fila.update(
                        clase="REVIEW_URL_CAMBIO",
                        fila_productiva=ke,
                        motivo=("el id_externo ya esta en produccion con otra "
                                "url: es la misma ficha renombrada, no un alta"
                                + ("" if marca == "1" else
                                   "; y ese id_externo se repite dentro de la "
                                   "agencia, asi que ni siquiera esta claro "
                                   "cual fila es")))
                    clases["REVIEW_URL_CAMBIO"] += 1
                    g.write(json.dumps(fila, ensure_ascii=False) + "\n")
                    continue
            if m is None:
                # En un INSERT no hay nada que pisar, pero eso no autoriza a
                # escribir un dato que sabemos malo. Si la geografia de la
                # ficha se contradice a si misma, los campos geograficos entran
                # en NULL: mejor sin provincia que con la provincia de otro
                # lado. Es la misma regla de siempre -no inventar geografia-
                # aplicada al alta.
                omitir = sorted(INHABILITA_GEO_CONFLICT) if conflicto_geo else []
                if clase_geo != "VALIDA":
                    omitir = sorted(set(omitir) | {"latitud", "longitud"})
                omitir = [c for c in omitir if tiene(r.get(c))]
                fila.update(clase="NEW", fila_productiva=None,
                            omitir_en_insert=omitir,
                            motivo="ninguna clave resuelve a una fila productiva")
                for c in omitir:
                    omitidos_insert[c] += 1
                if omitir:
                    nuevas_con_geo_recortada += 1
                clases["NEW"] += 1
                if clase_geo == "VALIDA":
                    coord_hab += 1
                elif clase_geo != "SIN_COORDENADA":
                    coord_bloq += 1
                g.write(json.dumps(fila, ensure_ascii=False) + "\n")
                continue

            v = vals.get(k, "")
            e = extra.get(k, "")
            iguales, distintos = [], []
            a_completar, a_sobrescribir, a_conservar, no_tocar = [], [], [], []

            def decidir(campo: str, presente_prod: bool, firma_prod: str | None):
                mio = firma(campo, r.get(campo))
                if mio is None:
                    if presente_prod:
                        no_tocar.append(campo)
                        no_tocar_t[campo] += 1
                    return
                # El par de coordenadas se escribe solo si esta DEMOSTRADO
                # valido. "No pude contrastarlo contra ninguna provincia" no es
                # lo mismo que "esta bien": tambien queda afuera.
                if campo in ("latitud", "longitud") and clase_geo != "VALIDA":
                    if presente_prod:
                        no_tocar.append(campo)
                        no_tocar_t[campo] += 1
                    else:
                        a_conservar.append(campo)
                        conserva[campo] += 1
                    return
                if not presente_prod:
                    if campo in INHABILITA_GEO_CONFLICT and conflicto_geo:
                        a_conservar.append(campo)
                        conserva[campo] += 1
                        return
                    a_completar.append(campo)
                    completa[campo] += 1
                    return
                if firma_prod is not None and mio == firma_prod:
                    iguales.append(campo)
                    return
                distintos.append(campo)
                if campo in INHABILITA_GEO_CONFLICT and conflicto_geo:
                    a_conservar.append(campo)
                    conserva[campo] += 1
                elif campo in ESTRUCTURALES:
                    a_sobrescribir.append(campo)
                    sobrescribe[campo] += 1
                else:
                    a_conservar.append(campo)
                    conserva[campo] += 1

            for pos, campo in enumerate(PRESENCIA):
                fp = v[2 * pos:2 * pos + 2] if len(v) >= 2 * pos + 2 else None
                decidir(campo, m[pos] == "1", fp if fp not in (None, "00") else None)

            # `operacion` y `tipo_propiedad` estan al 100 % en produccion;
            # `longitud` acompana a `latitud`.
            for pos, campo in enumerate(EXTRA):
                fp = e[2 * pos:2 * pos + 2] if len(e) >= 2 * pos + 2 else None
                presente = fp not in (None, "00")
                decidir(campo, presente, fp if presente else None)

            if clase_geo == "VALIDA":
                coord_hab += 1
            elif clase_geo != "SIN_COORDENADA":
                coord_bloq += 1

            clase = ("UPDATE" if (a_completar or a_sobrescribir) else "UNCHANGED")
            # De donde sale cada valor de la fila que quedaria. Sin esto el
            # artefacto dice QUE se escribe pero no POR QUE, y despues de
            # escribir ya no hay forma de reconstruirlo.
            #
            # `PRODUCTION_PRESERVED` es el caso que hay que poder auditar: son
            # los campos donde produccion tiene algo, nosotros tenemos otra
            # cosa, y la politica decidio no pisar. Si alguna vez hay que
            # revisar una decision, es esa.
            origen = {}
            for campo in a_completar:
                origen[campo] = "FRESH_COMPLETA_VACIO"
            for campo in a_sobrescribir:
                origen[campo] = "FRESH_SOBRESCRIBE"
            for campo in a_conservar:
                origen[campo] = "PRODUCTION_PRESERVED"
            for campo in no_tocar:
                origen[campo] = "PRODUCTION_PRESERVED_FRESH_VACIO"
            for campo in iguales:
                origen[campo] = "COINCIDEN"
            fila.update(clase=clase, fila_productiva=k,
                        campos_iguales=iguales, campos_distintos=distintos,
                        a_completar=a_completar,
                        a_sobrescribir=a_sobrescribir,
                        conservar_produccion=a_conservar,
                        no_tocar=no_tocar,
                        provenance=origen,
                        motivo=("la fila existe; se completa lo que falta y se "
                                "sobrescribe solo lo estructural validado"))
            clases[clase] += 1
            g.write(json.dumps(fila, ensure_ascii=False) + "\n")

    esc = sum(n for c, n in clases.items() if c != "RETENIDA_WEB_AJENA")
    print(f"\n{'clase':24} filas")
    for c, n in clases.most_common():
        print(f"  {c:22} {n:7}")
    print(f"\nescribibles: {esc}")

    print(f"\n{'campo':22} {'completa':>9} {'sobrescribe':>12} {'conserva':>9} {'no_tocar':>9}")
    for campo in list(PRESENCIA) + list(EXTRA):
        print(f"{campo:22} {completa[campo]:9} {sobrescribe[campo]:12} "
              f"{conserva[campo]:9} {no_tocar_t[campo]:9}")
    print(f"{'TOTAL':22} {sum(completa.values()):9} {sum(sobrescribe.values()):12} "
          f"{sum(conserva.values()):9} {sum(no_tocar_t.values()):9}")

    print(f"\naltas con geografia recortada: {nuevas_con_geo_recortada}")
    if omitidos_insert:
        print("   campos omitidos en el INSERT:",
              ", ".join(f"{c}:{n}" for c, n in omitidos_insert.most_common()))
    print(f"\ncoordenadas habilitadas: {coord_hab}  |  bloqueadas: {coord_bloq}")
    print("clases geograficas:",
          ", ".join(f"{c}:{n}" for c, n in resumen_geo.most_common()))
    print(f"\nartefacto: {salida}")
    print("database_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

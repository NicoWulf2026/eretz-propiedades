# -*- coding: utf-8 -*-
"""De quien es una url compartida, decidido por el dominio y no por el texto.

El intento anterior contaba menciones de cada nombre en la pagina y fallaba de
una forma sistematica: **contar menciones no distingue al dueno del
mencionado**. En `remax-net.com.ar` eligio `remax star`, y en
`rodriguezjurado.com.ar` eligio al azar porque las dos agencias aparecian doce
veces cada una.

La evidencia que si distingue es el dominio. Un dominio lo registra su dueno;
el cuerpo de la pagina solo nombra. `rodriguezjurado` contiene `jurado`, y de
las dos candidatas una sola se llama asi. Eso no es un empate: es una
respuesta.

La regla, en tres pasos:

1. Se sacan del nombre las palabras que no distinguen a nadie -`inmobiliaria`,
   `propiedades`, `remax`-. Lo que queda son sus tokens propios.
2. Una candidata **explica** el dominio si TODOS sus tokens propios estan
   adentro. Explica *mejor* que otra si sus tokens cubren mas caracteres del
   dominio.
3. Una sola explicandolo -o una cubriendo estrictamente mas- es duena. Varias
   empatadas es `IDENTITY_REVIEW`. Ninguna tocandolo siquiera es de nadie: un
   directorio o una tercera marca.

El paso 3 es el que importa y es el que hace que esto sea usable sin
preguntar. **Devolver `IDENTITY_REVIEW` es un resultado, no una falla.**

Dos detalles que salieron de los casos reales y no de la teoria:

  - El sufijo ordinal cuenta como token propio. `remax urbana iii` y
    `re max urbana` se diferencian **solo** en el `iii`, y el dominio
    `remax-urbana.com.ar` no lo tiene. Sin esto las dos empatan siempre.
  - La ruta se mira **solo** cuando el host es de una plataforma.
    `century21.com.ar/v/oficina/133-franchi-la-plata` identifica a la oficina
    por la ruta porque el host es de la franquicia. `urbanorosario.com.ar/
    servicios` NO: ahi el host ya es de alguien, y dejar que `/servicios` se
    lo lleve le daria el sitio a la agencia equivocada.

`database_writes: 0`. No aplica nada: escribe un dictamen para revisar.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlsplit

CATALOGO_GEO = Path(r"D:\INMO CAPITAL\ERETZ_GEO")

DUENA = "DUENA"
DE_NADIE = "DE_NADIE"
PARA_REVISAR = "IDENTITY_REVIEW"

# Palabras que aparecen en cientos de nombres y no distinguen a nadie. Sacarlas
# es lo que deja `jurado` a la vista en `rodriguez jurado propiedades`.
PALABRAS_QUE_NO_DISTINGUEN = frozenset({
    "inmobiliaria", "inmobiliarias", "inmobiliario", "inmobiliarios",
    "propiedades", "propiedad", "negocios", "negocio", "bienes", "raices",
    "inmuebles", "inmueble", "real", "estate", "grupo", "group", "sa", "srl",
    "s", "a", "de", "del", "la", "el", "los", "las", "y", "e", "servicios",
    "servicio", "gestion", "desarrollos", "arquitectura", "contacto",
    "consultora", "broker", "brokers", "inversiones", "compania",
    # Las redes: todas sus oficinas las llevan, asi que no separan una de otra.
    "remax", "re", "max", "century", "c21", "century21", "21",
})

# Hosts de plataforma: el sitio es de la red y la oficina se identifica por la
# ruta. Fuera de esta lista, la ruta NO decide.
HOSTS_DE_PLATAFORMA = frozenset({
    "century21.com.ar", "remax.com.ar", "tokkobroker.com", "licuo.com.ar",
    "proppies.app", "wasi.co",
})

# Sufijos de segundo nivel que no son parte del nombre de nadie.
SUFIJOS = ("com.ar", "org.ar", "net.ar", "gob.ar", "tur.ar", "com.uy",
           "com.br", "com", "net", "org", "ar", "app", "io", "co")


def aplanar(texto: Any) -> str:
    """Sin acentos, sin mayusculas. `Piñeyro` y `pineyro` son lo mismo."""
    crudo = unicodedata.normalize("NFKD", str(texto or ""))
    return crudo.encode("ascii", "ignore").decode().lower()


def etiqueta_del_dominio(url: str) -> str:
    """El nombre registrable, sin `www` ni sufijo, sin puntuacion.

    `https://www.remax-net.com.ar/x` -> `remaxnet`. Se junta todo porque los
    duenos escriben `remax-net`, `remaxnet` y `remax_net` para la misma cosa.
    """
    host = aplanar(urlsplit(url if "//" in url else f"//{url}").netloc)
    host = host.split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for sufijo in SUFIJOS:
        if host.endswith("." + sufijo):
            host = host[: -(len(sufijo) + 1)]
            break
    return re.sub(r"[^a-z0-9]", "", host)


def host_completo(url: str) -> str:
    host = aplanar(urlsplit(url if "//" in url else f"//{url}").netloc)
    return host[4:] if host.startswith("www.") else host


def pajar(url: str) -> str:
    """Donde se buscan los tokens: el dominio, y la ruta solo si es plataforma."""
    etiqueta = etiqueta_del_dominio(url)
    if host_completo(url) in HOSTS_DE_PLATAFORMA:
        ruta = re.sub(r"[^a-z0-9]", "", aplanar(urlsplit(
            url if "//" in url else f"//{url}").path))
        return etiqueta + ruta
    return etiqueta


def palabras_de_lugar(*lugares: Any) -> frozenset[str]:
    """Las palabras del lugar donde esta registrada ESTA agencia.

    Primero probe con el catalogo entero de GeoRef y fue un error del mismo
    tipo que el `\b` mal puesto: en Argentina los pueblos se llaman como la
    gente. `Zarate`, `Rodriguez`, `Martinez` y `Alberdi` son ciudades **y**
    apellidos, asi que descartar todo nombre de lugar borraba justo los
    tokens que distinguen a una inmobiliaria de otra -`rodriguezjurado` se
    quedaba sin `rodriguez`-.

    Lo que si vale es la geografia **de la candidata**: si una agencia esta
    registrada en Rosario, que `rosario` aparezca en el dominio no dice nada
    sobre ella, porque lo comparte con las otras doscientas de Rosario. La
    misma palabra es marca para una agencia y ruido para otra, y lo que lo
    decide es donde esta cada una.
    """
    palabras: set[str] = set()
    for lugar in lugares:
        for palabra in re.split(r"[^a-z0-9]+", aplanar(lugar)):
            if len(palabra) > 3:
                palabras.add(palabra)
    return frozenset(palabras)


def tokens_propios(nombre: str, su_lugar: Iterable[str] = ()) -> list[str]:
    """Lo que la distingue: su marca, sin las genericas ni su propia geografia.

    Si no queda nada -una agencia llamada `Rosario Propiedades` registrada en
    Rosario- se devuelve la lista vacia y esa agencia no puede explicar
    ningun dominio. Es la respuesta correcta: su nombre no la distingue.
    """
    suyo = palabras_de_lugar(*su_lugar)
    palabras = [p for p in re.split(r"[^a-z0-9]+", aplanar(nombre)) if p]
    return [p for p in palabras
            if p not in PALABRAS_QUE_NO_DISTINGUEN and p not in suyo]


def tokens_debiles(nombre: str, su_lugar: Iterable[str] = ()) -> list[str]:
    """Lo que la nombra sin distinguirla: su propia geografia.

    Sirve para una sola cosa y es importante: que a una agencia cuyo lugar
    figura en el dominio NO se le retire la fuente por ajena. Alcanza para
    dudar, no para decidir.
    """
    suyo = palabras_de_lugar(*su_lugar)
    palabras = [p for p in re.split(r"[^a-z0-9]+", aplanar(nombre)) if p]
    return [p for p in palabras if p in suyo]


def cobertura(tokens: Iterable[str], donde: str) -> int:
    """Cuantos caracteres del pajar explican estos tokens, sin contar dos veces."""
    ocupado = [False] * len(donde)
    for token in sorted(set(tokens), key=len, reverse=True):
        desde = donde.find(token)
        if desde >= 0:
            for posicion in range(desde, desde + len(token)):
                ocupado[posicion] = True
    return sum(ocupado)


def dictaminar(url: str, candidatas: dict[str, str],
               lugar_de: dict[str, Iterable[str]] | None = None) -> dict[str, Any]:
    """Quien es duena de esta url, entre estos nombres.

    `candidatas` va de id de agencia a su nombre. Devuelve el veredicto y, por
    agencia, si explica el dominio, si lo toca apenas o si no lo toca: lo
    ultimo alcanza para retirarle la fuente aunque el grupo quede sin duena.
    """
    donde = pajar(url)
    detalle: dict[str, dict[str, Any]] = {}
    # La geografia se junta POR GRUPO, no por agencia. El padron guarda en
    # `city` la zona observada y no la ciudad -`distrito centro` en vez de
    # `Rosario`-, asi que preguntarle a cada candidata por su propio lugar
    # deja pasar el de la vecina. Y el criterio correcto es el del grupo: un
    # lugar donde esta parada CUALQUIERA de las candidatas no distingue a
    # ninguna de las otras, porque lo comparten.
    lugares = lugar_de or {}
    del_grupo = [pedazo for agencia in candidatas
                 for pedazo in lugares.get(agencia, ()) if pedazo]
    for agencia, nombre in candidatas.items():
        suyo = del_grupo
        tokens = tokens_propios(nombre, suyo)
        presentes = [t for t in tokens if t and t in donde]
        # La geografia no decide, pero impide retirarle la fuente a alguien
        # cuyo lugar figura en el dominio.
        debiles = [t for t in tokens_debiles(nombre, suyo) if t in donde]
        detalle[agencia] = {
            "tokens": tokens, "presentes": presentes,
            "lugares_en_el_dominio": debiles,
            "explica": bool(tokens) and len(presentes) == len(tokens),
            "toca": bool(presentes) or bool(debiles),
            "cobertura": cobertura(presentes, donde)}

    explican = [a for a, d in detalle.items() if d["explica"]]
    if len(explican) == 1:
        ganadora, motivo = explican[0], "unica que explica el dominio"
    elif len(explican) > 1:
        mejor = max(explican, key=lambda a: detalle[a]["cobertura"])
        techo = detalle[mejor]["cobertura"]
        empatadas = [a for a in explican if detalle[a]["cobertura"] == techo]
        ganadora = mejor if len(empatadas) == 1 else None
        motivo = ("cubre estrictamente mas del dominio que las otras"
                  if ganadora else "varias explican el dominio por igual")
    else:
        ganadora = None
        motivo = ("ninguna candidata aparece en el dominio"
                  if not any(d["toca"] for d in detalle.values())
                  else "ninguna explica el dominio entera")

    if ganadora:
        veredicto = DUENA
    elif any(d["toca"] for d in detalle.values()):
        veredicto = PARA_REVISAR
    else:
        veredicto = DE_NADIE

    # A quien se le retira la url compartida:
    #   - si hay duena, a TODAS las demas. Dejarsela a la que perdio manteniendo
    #     armada la mina: dos oficinas enumerando el mismo catalogo y las
    #     propiedades atribuidas dos veces, que es lo que esto vino a evitar.
    #   - si no hay duena, solo a las que no tocan el dominio. De las que lo
    #     tocan no se puede afirmar nada todavia.
    if ganadora:
        retirar = [a for a in detalle if a != ganadora]
    else:
        retirar = [a for a, d in detalle.items() if not d["toca"]]
    return {"url": url, "dominio": donde, "veredicto": veredicto,
            "duena": ganadora, "motivo": motivo,
            "retirar_de": sorted(retirar),
            "detalle": detalle}


def leer_jsonl(ruta: Path) -> Iterator[dict[str, Any]]:
    if not ruta.exists():
        return
    with ruta.open(encoding="utf-8") as fichero:
        for linea in fichero:
            linea = linea.strip()
            if linea:
                try:
                    yield json.loads(linea)
                except json.JSONDecodeError:
                    continue


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument(
        "--grupos", type=Path,
        default=Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827"
                     r"\ERETZ_FUENTES_COMPARTIDAS.json"))
    analizador.add_argument(
        "--directorio", type=Path,
        default=Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA"
                     r"\agency_web_directory.jsonl"))
    analizador.add_argument("--json", type=Path, default=None)
    opciones = analizador.parse_args(argv)

    registro = {fila["canonical_agency_id"]: fila
                for fila in leer_jsonl(opciones.directorio)
                if fila.get("canonical_agency_id")}
    nombres = {a: (f.get("canonical_name") or a) for a, f in registro.items()}
    crudo = json.loads(opciones.grupos.read_text(encoding="utf-8"))
    grupos = crudo if isinstance(crudo, list) else (
        crudo.get("grupos") or crudo.get("compartidas") or [])

    dictamenes = []
    for grupo in grupos:
        agencias = [a if isinstance(a, str) else a.get("canonical_agency_id")
                    for a in grupo.get("agencias", [])]
        candidatas = {a: nombres.get(a, a.split(":", 1)[-1]) for a in agencias if a}
        lugar_de = {a: [registro.get(a, {}).get("city"),
                        registro.get(a, {}).get("province")]
                    for a in candidatas}
        dictamenes.append(dictaminar(grupo["url"], candidatas, lugar_de))

    cuenta = {DUENA: 0, PARA_REVISAR: 0, DE_NADIE: 0}
    for d in dictamenes:
        cuenta[d["veredicto"]] += 1
        print(f"\n{d['veredicto']:16s} {d['url']}")
        print(f"                 dominio={d['dominio']!r} — {d['motivo']}")
        if d["duena"]:
            print(f"                 DUENA: {d['duena']}")
        for agencia, info in sorted(d["detalle"].items()):
            marca = "*" if agencia == d["duena"] else (
                " " if info["toca"] else "-")
            print(f"   {marca} {agencia:50s} tokens={info['tokens']} "
                  f"presentes={info['presentes']}")
        if d["retirar_de"]:
            print(f"                 retirar la fuente de: "
                  f"{', '.join(d['retirar_de'])}")

    print(f"\n{'-'*70}\nduenas resueltas: {cuenta[DUENA]}   "
          f"para revisar: {cuenta[PARA_REVISAR]}   "
          f"de nadie: {cuenta[DE_NADIE]}")
    retiros = sum(len(d["retirar_de"]) for d in dictamenes)
    print(f"agencias a las que se les puede retirar la fuente ya: {retiros}")
    if opciones.json:
        opciones.json.write_text(
            json.dumps({"dictamenes": dictamenes, "database_writes": 0},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Que hacer ante un `NEEDS_FIX`: parar la cola o anotarlo y seguir.

Parar en cada defecto da maxima correccion y cuesta semanas de cola detenida.
Seguir siempre es rapido y certifica agencias con un defecto conocido encima.
Ninguna de las dos es la respuesta: **lo que decide es el RADIO del defecto**.

Un parser que no lee `superficie` en una estrategia que comparten 343
inmobiliarias no puede seguir corriendo: cada agencia que certifique despues
hereda el mismo error. Un sitio que anduvo lento media hora afecta a una sola
inmobiliaria y no justifica detener 758.

**La asimetria es deliberada: para clasificar algo como local hace falta
evidencia POSITIVA de que su causa es externa o acotada. Sin esa evidencia se
para.** No alcanza con que el defecto "parezca" local; no encontrar razones
para parar no es lo mismo que tener razones para seguir. Un defecto compartido
que se toma por local certifica mal a cientos de agencias, y un defecto local
que se toma por compartido cuesta una parada.

El paquete NUNCA queda como certificado. Con `CONTINUE` sigue siendo
`NEEDS_FIX` y entra a `AGENCY_DEFECT_QUEUE.jsonl` con su clasificacion y su
evidencia, pendiente de resolucion y recertificacion.

No escribe en ninguna base.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

TRIAGE_VERSION = "defect_triage_v1"

STOP = "STOP"
CONTINUE = "CONTINUE"

# Radios, de mayor a menor. El nombre dice a cuantas agencias puede alcanzar.
RADIO_COMPARTIDO = "COMPARTIDO"      # base, runner, certifier, geografia
RADIO_FAMILIA = "FAMILIA"            # un connector entero o generic/common
RADIO_ESTRATEGIA = "ESTRATEGIA"      # una estrategia de generico
RADIO_AGENCIA = "AGENCIA"            # esta inmobiliaria y ninguna otra

# El piso de fotos con el que el guardian de forma acepta una ficha. Se
# declara aca, y no se importa de `generico`, para que el triaje no dependa
# de un connector: si el piso cambiara alla, este numero queda como lo que el
# triaje afirma, y la diferencia se ve en los tests en vez de propagarse sola.
FOTOS_MINIMAS_PARA_SOSPECHAR = 3

# Clases de error del descargador que hablan del SITIO, no de nosotros.
CLASES_EXTERNAS = ("ErrorTransitorio", "Bloqueado", "TimeoutError",
                   "URLError", "HTTPError", "ConnectionResetError",
                   "IncompleteRead", "socket.timeout")


# Senales de que un sitio SI publica catalogo, aunque no lo hayamos podido
# enumerar. Se miran ENLACES y rutas, no vocabulario: una inmobiliaria sin
# catalogo igual dice "venta" y "propiedad" en su texto institucional, y
# contarlo como inventario seria el falso positivo simetrico.
#
# Los patrones salen de los dos casos reales, no de suponer:
#
#   alta.com.ar          Next.js con ruta /buscador; las fichas viven en
#                        /propiedad/<id> y el catalogo detras de
#                        /api/tokko/properties. 16 propiedades.
#   almadimatteo.com.ar  HTML estatico; el menu enlaza casasychalets/,
#                        deptosyph/, duplex/, lotes/, locales/ y alquileres/,
#                        y cada ficha es un .html en su carpeta. 28 fichas.
#
# Entre las dos, 44 propiedades que el sistema dio por inexistentes.

# Rutas de ficha individual.
RE_URL_DE_FICHA = re.compile(
    r"""href=["'][^"']*/(?:propiedad|propiedades|inmueble|inmuebles|ficha|"""
    r"""listing|emprendimiento)/[^"']{2,90}["']""", re.I)

# Un endpoint de catalogo referenciado desde el cliente.
RE_API_DE_CATALOGO = re.compile(
    r"""["'][^"']*/api/[^"']*(?:propert|propiedad|inmueble|listing|tokko|"""
    r"""wasi|search)[^"']*["']""", re.I)

# Un contador publicado: "16 propiedades encontradas".
#
# El `(?<![%\w])` no es cosmético: sin él, esta expresión inventa un contador
# donde no hay ninguno, y eso detuvo la cola. El 2026-09-16 `gabriela aloise
# propiedades` paró con la evidencia "contador publicado: 20propiedades". No
# había 20 propiedades: el sitio tiene un enlace de WhatsApp,
#
#     wa.me/54...?text=Hola!%20Quisiera%20mas%20informacion%20sobre%20las%20propiedades
#
# y `%20` es un espacio codificado. Con `\s*` —cero o más espacios— el patrón
# leyó "20propiedades" adentro de una url y lo reportó como total declarado. El
# sitio, en su propia página de listado, dice "0 propiedades".
#
# Es la misma clase de error que ya costó caro antes: tomar por dato de la
# fuente algo que es un artefacto del marcado. Un contador falso no sólo miente,
# detiene a los dos workers hasta que alguien lo mira.
#
# El `%` cubre la url y el `\w` el caso simétrico, "casa20propiedades".
RE_CONTADOR = re.compile(
    r"(?<![%\w.,])([1-9]\d{0,2}(?:[.,]\d{3})+|\d{1,6})\s+"
    r"(?:propiedades|inmuebles|resultados|avisos)\b", re.I)

# Enlaces a una pagina de busqueda o listado.
RE_RUTA_DE_BUSQUEDA = re.compile(
    r"""href=["'][^"']*/(?:buscador|busqueda|buscar|listado|catalogo|"""
    r"""propiedades|inmuebles)(?:[/?."']|["'])""", re.I)

# Enlaces a categorias del rubro. Es la forma que toma un catalogo estatico:
# el menu lleva a una pagina por tipo y ahi cuelgan las fichas.
RE_CATEGORIA = re.compile(
    r"""href=["'][^"']*(?:casas?ychalets?|casas|departamentos?|deptos?|"""
    r"""duplex|lotes|terrenos|locales|galpones|cocheras|campos|"""
    r"""alquileres?|ventas?)[^"']*\.(?:html?|php|aspx)["']""", re.I)


def senales_de_catalogo(html: str) -> list[str]:
    """Evidencia estructural de que hay inventario publicado."""
    if not html:
        return []
    senales = []
    fichas = set(RE_URL_DE_FICHA.findall(html))
    if fichas:
        senales.append(f"{len(fichas)} enlaces con forma de ficha")
    categorias = set(RE_CATEGORIA.findall(html))
    if len(categorias) >= 2:
        senales.append(f"{len(categorias)} paginas de categoria del rubro")
    if RE_API_DE_CATALOGO.search(html):
        senales.append("endpoint de catalogo referenciado en el cliente")
    if RE_RUTA_DE_BUSQUEDA.search(html):
        senales.append("enlace a una pagina de busqueda o listado")
    contador = RE_CONTADOR.search(html)
    if contador and int(re.sub(r"[.,]", "", contador.group(1))) > 0:
        senales.append(f"contador publicado: {contador.group(0).strip()}")
    return senales


def _corridas(resultado: dict[str, Any]) -> list[dict[str, Any]]:
    return [resultado.get(nombre) or {} for nombre in ("run1", "run2")]


def _campos_con_extraccion_fallida(resultado: dict[str, Any]) -> list[str]:
    cobertura = resultado.get("field_coverage") or {}
    return sorted(campo for campo, dato in cobertura.items()
                  if isinstance(dato, dict)
                  and dato.get("state") == "EXTRACTION_FAILED")


def _errores_externos(resultado: dict[str, Any]) -> dict[str, int]:
    """Errores del descargador, agrupados, que apuntan al sitio y no al parser."""
    fuera: dict[str, int] = {}
    for corrida in _corridas(resultado):
        for clave, cuantos in (corrida.get("errores_por_etapa") or {}).items():
            if any(clase in clave for clase in CLASES_EXTERNAS):
                fuera[clave] = fuera.get(clave, 0) + int(cuantos)
    return fuera


def firma(resultado: dict[str, Any], componente: str) -> str:
    """Identifica el PATRON del defecto, no la inmobiliaria.

    Dos defectos con la misma firma son el mismo problema apareciendo dos
    veces, y eso es motivo de corte por lote aunque cada uno se haya
    clasificado como local.
    """
    partes = [
        resultado.get("connector") or "",
        resultado.get("connector_strategy") or "",
        componente,
        "|".join(sorted(resultado.get("reasons") or [])),
        "|".join(_campos_con_extraccion_fallida(resultado)),
    ]
    return hashlib.sha256("::".join(partes).encode("utf-8")).hexdigest()[:12]


# Hasta cuanto un defecto de campo se considera "una ficha rara" y no un
# problema del parser compartido.
#
# Son DOS condiciones y hay que cumplir las dos, porque cada una sola miente:
# el porcentaje solo deja pasar 40 fichas de 2.000, y el tope solo deja pasar
# 4 de 4 -o sea el 100 %-.
#
# Los numeros salen del historial, no de la intuicion. En esta pasada pararon
# las dos colas: `conti` 1 de 275, `civeira` 1 de 163, `cocucci` 1 de 152.
# Tres ciclos completos de diagnostico y relanzamiento por tres fichas. Del
# otro lado, lo que hay que seguir atajando empieza mucho mas arriba: `blanco`
# pierde 1.207 precios de 1.211 y `bardi` 48 ambientes de 59.
#
# Entre 1 ficha y 48 hay lugar de sobra para un umbral, y este se pone cerca
# del piso a proposito: ante la duda, parar.
#
# Los dos topes son INCLUSIVOS. En el borde exacto -4 fichas de 200, que es
# justo el 2 %- el que manda es el tope absoluto: cuatro propiedades son
# cuatro propiedades, y discutir si el 2,0 % entra o no entra por un decimal
# no cambia nada del mundo real. El quinto caso ya no pasa ni por el tope de
# fichas ni por el porcentual.
# El tope absoluto estuvo en 4 y, junto al porcentual, dejaba una franja
# imposible: las agencias chicas no pasaban el porcentual y las grandes no
# pasaban el absoluto. Medido sobre los 778 casos de EXTRACTION_FAILED del
# historial, 287 tienen ratio <= 0,10 y se reparten asi por cantidad de fallas:
#
#     1 falla   206 casos        6 fallas    2
#     2          14              7           3
#     3          10              8           4
#     4          15              9           1
#     5          30             20+          2
#
# Entre 9 y 20 hay un hueco. El tope en 10 admite todo lo que esta debajo del
# hueco y deja afuera los dos casos grandes -27 de 395 y 20 de 254-.
#
# Eran 42 casos en 9 agencias los que caian por el absoluto teniendo un ratio
# chico: `agostinelli` con 8 coordenadas de 154 -5,2 %- paro las dos colas
# teniendo las 388 propiedades enumeradas y completas.
#
# El riesgo de subirlo -perder la senal de un fallo sistematico- no se
# materializa: la regla de "dos defectos con la misma firma" SI cuenta los
# menores, asi que un campo que falla igual en dos agencias sigue cortando.
#
# 2026-09-21: subido de 10 a 15, y la razon NO es que molestara.
#
# El 10 se eligio esa misma manana por un hueco entre 9 y 20 en los datos de
# entonces. Ese hueco se lleno: la cola siguio corriendo y aparecieron casos
# en 11, 12, 13, 16 y 18. El valor estaba ajustado a una forma de los datos
# que ya no esta.
#
# El caso que lo destapo:
#
#     13 de 428 (3,04 %)  brunetti propiedades  tipo_propiedad
#
# Es el porcentaje MAS BAJO de toda su banda. Los demas casos entre 10 y 30
# fallos son 45 %, 75 %, 96 % y 100 %, y a esos los frena el tope porcentual
# sin ayuda del absoluto.
#
# Se elige 15 y no mas: en los datos de hoy hay un hueco entre 13 y 16, y
# sobre todo porque la decision de la manana fue deliberada en dejar `27 de
# 395` y `20 de 254` del lado de STOP. Un tope de 50 los habria dado por
# menores y habria pisado esa decision sin evidencia nueva sobre ELLOS. Lo
# probaron cuatro tests que ya existian.
#
# Medido sobre los 67 casos de `EXTRACTION_FAILED` del corpus, con 15 cambia
# exactamente un caso -brunetti- y sigue siendo mayor todo lo que debe:
# 1.206 de 1.213, 724 de 724, 179 de 502, 80 de 159, 27 de 395, 20 de 254.
TOPE_DE_FICHAS_MENORES = 15
# El porcentual estuvo en 0,02 y frenaba de mas. Medido sobre los 382 casos
# historicos con 4 fallas o menos:
#
#     ratio <= 0,02   142 casos   37 %     <- el tope viejo
#     ratio <= 0,05   182 casos   48 %
#     ratio <= 0,10   245 casos   64 %     <- el tope nuevo
#     ratio <= 0,25   247 casos   65 %
#     ratio <= 0,50   264 casos   69 %
#
# Entre 0,10 y 0,30 hay un HUECO: pasar de 0,10 a 0,25 suma dos casos. El corte
# esta puesto donde los datos tienen el salto, no donde me parecia razonable.
#
# Lo que quedaba afuera con 0,02 era `3 de 103` -2,9 %-, `4 de 129` -3,1 %- y
# `2 de 54` -3,7 %, el paro de `abril negocios inmobiliarios` que destapo
# esto-: defectos de dos o tres fichas que paraban LAS DOS COLAS. Eran 240
# casos en 29 agencias, el 63 % de todas las fallas chicas del historial.
#
# Y lo que sigue quedando afuera es lo que tiene que quedar afuera: `cavacini`
# con `ambientes` 3 de 3 y `alder` con 4 de 4 son el 100 %, o sea que el campo
# falla en todo lo que hay. Un tope absoluto solo los habria dado por menores.
TOPE_PORCENTUAL_MENOR = 0.10

COMPONENTE_MENOR = "extraccion_de_baja_magnitud"
# Debajo de esta cantidad de fichas vistas, la proporcion sobre
# `source_provided` deja de ser informativa y se mide contra el inventario.
MUESTRA_MINIMA = 10

# Cuanto hueco entre lo declarado y lo enumerado deja de ser ruido. Las dos
# condiciones se exigen juntas: diez propiedades invisibles sobre tres mil no
# son un defecto, y el 20 % de un catalogo de diez tampoco.
INVISIBLES_MINIMAS = 10
TOPE_DE_HUECO = 0.10


# Con cuanta cobertura de imagenes se acepta que la regla acerto. No es 1,0
# porque una ficha sin fotos publicadas es normal; si es alta, lo descartado
# era ajeno.
COBERTURA_DE_IMAGENES_SANA = 0.95


def _cobertura_de_imagenes(resultado: dict[str, Any]) -> float | None:
    dato = (resultado.get("field_coverage") or {}).get("imagenes")
    if not isinstance(dato, dict):
        return None
    cobertura = dato.get("coverage")
    return float(cobertura) if isinstance(cobertura, (int, float)) else None


def _galeria_intacta(resultado: dict[str, Any]) -> bool:
    """¿Descartar imagenes compartidas dejo a las fichas con sus fotos?

    Separar "descarto" de "perdio" es toda la diferencia. Medido el 2026-09-14
    sobre las 33 agencias donde la regla descarto algo:

        fdc             1.616 descartadas, cobertura 1,0     sana
        vera cruz         516 descartadas, cobertura 0,0     destruida
        belvedere         252 descartadas, cobertura 0,0     destruida
        blangiforti       249 descartadas, cobertura 0,29    destruida

    El numero de descartadas no ordena nada: la que mas descarta es la unica
    que no pierde. La cobertura si, y ya venia en el resultado.

    Sin el dato se devuelve False y el corte se mantiene: no poder mirar no es
    haber mirado y no haber encontrado nada.
    """
    cobertura = _cobertura_de_imagenes(resultado)
    return cobertura is not None and cobertura >= COBERTURA_DE_IMAGENES_SANA


def _es_de_baja_magnitud(resultado: dict[str, Any],
                         fallidos: list[str]) -> bool:
    """¿Los campos que fallaron fallaron en poquisimas fichas?

    Se exige campo por campo: alcanza con que UNO exceda para que el conjunto
    deje de ser menor. Si `christian arce` pierde una ficha de ambientes pero
    nueve de operacion, lo que manda son las nueve.

    Sin `source_provided` no se puede calcular proporcion, y sin proporcion no
    se difiere: la respuesta es que no es menor.
    """
    if not fallidos:
        return False
    if os.environ.get("ERETZ_TRIAGE_SIN_BAJA_MAGNITUD"):
        return False
    cobertura = resultado.get("field_coverage") or {}
    for campo in fallidos:
        dato = cobertura.get(campo)
        if not isinstance(dato, dict):
            return False
        fallas = int(dato.get("extraction_failed") or 0)
        provistos = int(dato.get("source_provided") or 0)
        if fallas > TOPE_DE_FICHAS_MENORES or not provistos:
            return False
        # Con una muestra chiquita la proporcion no mide lo que se quiere
        # medir. `baron` fallo `banos` 1 de 1 -100 %- sobre 182 propiedades
        # enumeradas, y esa unica pagina era /emprendimientos/imperio-baron,
        # un proyecto de 24 pisos que no tiene un valor unico de banos.
        #
        # La proporcion existe para atrapar "3 de 5", donde el campo falla en
        # casi todo lo que hay. Cuando la senyal vio el campo en menos de
        # `MUESTRA_MINIMA` paginas, lo que hay que preguntarse es otra cosa:
        # cuanto pesa la falla sobre el inventario real.
        denominador = provistos
        if provistos < MUESTRA_MINIMA:
            enumeradas = int((resultado.get("enumeration_audit") or {}).get(
                "enumerated") or 0)
            if enumeradas > provistos:
                denominador = enumeradas
        if fallas / denominador > TOPE_PORCENTUAL_MENOR:
            return False
    return True


def descarte_parecia_una_propiedad(descarte: dict[str, Any]) -> bool:
    """Un rechazo del guardian que SI tenia pinta de ficha.

    Se miran dos senales y no mas: que la pagina publicara un **precio** o un
    **schema**. Son las unicas dos que no las tiene una pagina institucional.

    `operacion_en_texto` queda afuera a proposito, y no por prolijidad: de los
    100 rechazos registrados en el corpus, 88 lo traian en `True`, y entre
    ellos estan `historia.php`, `ubicacion.php`, `como_llegar.php` y
    `galerias.html` del portal de `gama`. Se dispara porque la palabra
    «venta» aparece en el menu del sitio, no porque la pagina venda algo.

    Es el tercer caso del mismo vicio en este proyecto: la senal de `ciudad`
    disparando con la direccion de la oficina en el nodo `RealEstateAgent`, y
    el patron de `ambientes` encontrando «ambiente 1» dentro de
    «Monoambiente». Las tres veces la senal se conformo con que la palabra
    apareciera.
    """
    fuerte = descarte.get("precio") is not None or bool(descarte.get("tipo_ld"))
    if not fuerte:
        return False
    # Y ademas tiene que haber tenido fotos suficientes.
    #
    # `arquitectura inmobiliaria` paro las dos colas por esto: sus 9 rechazos
    # son paginas de CATEGORIA -`ventas-locales`, `alquileres-monoambientes`,
    # tituladas «3 dormitorios»- y una de ellas muestra un precio en el
    # listado. Con el precio solo, eso alcanzaba para llamarla sospechosa.
    #
    # Las nueve tienen exactamente UNA foto. Y una pagina que no llega al piso
    # de fotos no es publicable como propiedad por ningun camino: el guardian
    # la rechaza por ahi, no por el precio, asi que su rechazo no puede ser
    # una perdida. La unica excepcion del guardian -un catalogo ya verificado
    # en runtime- ni siquiera mira las fotos, con lo cual nunca llega aca.
    #
    # No afloja el caso que importa: las fichas de `alma di matteo` que
    # destaparon el defecto real traian 8 fotos y precio, y seguirian
    # disparando. Medido sobre los 59 rechazos distintos del corpus, con este
    # agregado ninguno queda sospechoso.
    return (descarte.get("fotos") or 0) >= FOTOS_MINIMAS_PARA_SOSPECHAR


def paro_por_el_guardian_de_forma(corrida: dict[str, Any]) -> str | None:
    """Por que parar -o no- cuando el guardian descarto fichas.

    La regla anterior paraba las dos colas con **cualquier** descarte. El
    problema es que descartar es lo que el guardian hace: mezclaba «el
    guardian se equivoco», que es grave y compartido, con «el guardian
    funciono», que es su operacion normal.

    Medido sobre los 100 rechazos que hay registrados en el corpus: **los 100
    son correctos**, ninguno traia precio ni schema, y son cosas como
    `area_cliente.php?sec=sol` y `quienes-somos.php`. Con eso, la regla vieja
    paro las dos colas dos veces -`gama` y `bottai`- por trabajo bien hecho.
    `bottai` descarto 1 sobre 234.

    Se para en tres casos, y el primero es el que importa:

    1. **Un rechazo con precio o schema.** Ahi el guardian pudo equivocarse y
       el guardian es compartido. No paso nunca todavia, que es justamente por
       que hay que dejarlo armado.
    2. **No sobrevivio ninguna ficha.** Aunque cada rechazo sea correcto, una
       agencia que termina en cero necesita que alguien mire por que. Es el
       caso `gama`, y mirarlo encontro que su fuente era un perfil de portal.
    3. **No hay evidencia de los rechazos.** Sin el detalle no se puede
       afirmar que estuvieran bien, y el silencio no es una respuesta
       tranquilizadora: se para igual que antes.
    """
    descartadas = corrida.get("descartadas_por_forma") or 0
    if not descartadas:
        return None

    # Dos formas de la misma evidencia. El rollout guarda el detalle completo
    # en `_descartes`; el paquete del certificador no lo serializa -las claves
    # con guion bajo se caen- y por eso el conteo viaja aparte. Se prefiere el
    # conteo porque esta en los dos caminos.
    cuantos = corrida.get("descartes_con_senal")
    ejemplos = corrida.get("descartes_con_senal_ejemplos") or []
    detalle = corrida.get("_descartes")
    if cuantos is None:
        if detalle is None:
            return (f"{descartadas} fichas descartadas por el guardian de "
                    f"forma, que es compartido, y sin evidencia de por que")
        sospechosos = [d for d in detalle if descarte_parecia_una_propiedad(d)]
        cuantos = len(sospechosos)
        ejemplos = [str(d.get("source_url"))[:200] for d in sospechosos[:3]]

    if cuantos:
        urls = ", ".join(str(u)[:70] for u in ejemplos)
        return (f"{cuantos} de {descartadas} fichas descartadas por el "
                f"guardian de forma TENIAN precio o schema: pudo no ser "
                f"institucional, y el guardian es compartido. {urls}")

    if not corrida.get("detalles_obtenidos"):
        return (f"{descartadas} fichas descartadas y ninguna sobrevivio: cada "
                f"rechazo se ve correcto -ninguna traia precio ni schema- "
                f"pero la agencia termino en cero y eso necesita explicacion")

    return None


def _detalle_menor(resultado: dict[str, Any], fallidos: list[str]) -> str:
    cobertura = resultado.get("field_coverage") or {}
    partes = []
    for campo in fallidos:
        dato = cobertura.get(campo) or {}
        partes.append(f"{campo} {dato.get('extraction_failed')} de "
                      f"{dato.get('source_provided')}")
    return "; ".join(partes)


def clasificar(resultado: dict[str, Any]) -> dict[str, Any]:
    """STOP o CONTINUE, con la evidencia que lo justifica."""
    razones = list(resultado.get("reasons") or [])
    comparacion = resultado.get("comparison") or {}
    corridas = _corridas(resultado)
    auditoria = resultado.get("enumeration_audit") or {}
    revision = list(auditoria.get("review_reasons") or [])

    fallidos = _campos_con_extraccion_fallida(resultado)
    externos = _errores_externos(resultado)

    # ------- STOP: una corrida vio inventario que la otra no --------------
    #
    # Va PRIMERO, antes que cualquier CONTINUE, porque es la unica familia de
    # falla que puede terminar en un COMPLETE falso.
    #
    # `carames` lo mostro el 2026-09-13: run1 enumero 207 urls y run2 177, con
    # 30 faltantes, y el triage lo dejo pasar como `sitio_externo` afirmando
    # "el catalogo enumero igual en las dos corridas". No enumero igual.
    #
    # El error era leer el RELATO en vez del DATO: la diferencia de inventario
    # se deducia buscando las frases "inventories differ" o "not idempotent"
    # entre las razones, y ese resultado traia otra razon -se quedo sin
    # presupuesto de tiempo-, asi que la deduccion dijo que no habia
    # diferencia mientras `comparison.missing_in_run2` decia 30.
    #
    # Ahora se mira el numero. Que a una corrida le falte tiempo explica POR
    # QUE faltan; no vuelve seguro publicar lo que quedo.
    # Lo que la fuente DICE que tiene contra lo que pudimos ver. Va antes que
    # cualquier defecto de campo porque es de otro orden: un campo que falla
    # ensucia una ficha, un catalogo corto declara completo lo que no lo esta.
    #
    # El triage no miraba esto. Medido el 2026-09-14 sobre la pasada, 59
    # agencias declaran mas de lo que enumeramos y tres ya habian cerrado
    # CERTIFIED_COMPLETE asi: `alberti` 102 de 168, `eckert` 29 de 39, `calma`
    # 90 de 108.
    #
    # El umbral tiene dos mitades a proposito. Un techo declarado suele incluir
    # unidades despublicadas o contadas distinto, asi que una diferencia de
    # tres sobre doscientas no dice nada; una de sesenta sobre ciento sesenta y
    # ocho si.
    auditoria = resultado.get("enumeration_audit") or {}
    enumeradas = int(auditoria.get("enumerated") or 0)
    techo = max(int(auditoria.get("declared_total") or 0),
                int(auditoria.get("independent_max_inventory_signal") or 0))
    if enumeradas and techo > enumeradas:
        invisibles = techo - enumeradas
        proporcion = invisibles / techo
        if invisibles >= INVISIBLES_MINIMAS and proporcion >= TOPE_DE_HUECO:
            # El techo sale del MAXIMO entre lo que la fuente declara hoy y la
            # senal historica, y el mensaje decia "la fuente declara {techo}"
            # aunque el techo viniera del historico. Eso hacia falsa la
            # evidencia del paro en mas de la mitad de los casos.
            #
            # Medido sobre las 81 agencias con hueco: en 46 -el 57 %- la
            # fuente declara HOY exactamente lo que enumeramos, y el hueco es
            # contra un baseline anterior. `carina gonzalez` declara 337,
            # enumeramos 337, y el baseline decia 407: el catalogo se achico,
            # no se nos escapo nada.
            #
            # La DECISION no cambia -seguir parando es correcto hasta que el
            # ciclo de vida pueda distinguir una baja de una perdida, y hoy no
            # puede porque no registra QUE propiedades faltan-. Lo que cambia
            # es que la evidencia diga de donde sale cada numero.
            hoy = int(auditoria.get("declared_total") or 0)
            historico = int(auditoria.get("independent_max_inventory_signal") or 0)
            if hoy and enumeradas >= hoy and historico > hoy:
                origen = (f"la fuente declara {hoy} HOY y enumeramos "
                          f"{enumeradas}: el techo de {techo} viene de una "
                          f"corrida anterior, asi que el catalogo se achico "
                          f"en {invisibles} ({proporcion:.1%}) o los perdimos, "
                          f"y todavia no sabemos cual de las dos")
            else:
                origen = (f"la fuente declara {techo} y enumeramos "
                          f"{enumeradas}: {invisibles} propiedades "
                          f"({proporcion:.1%}) que existen y no vimos")
            return _veredicto(
                STOP, resultado, "catalogo_declarado_mayor_que_el_enumerado",
                RADIO_FAMILIA,
                f"{origen}. Certificar esto como completo seria afirmar que el "
                f"catalogo termina donde termino nuestra enumeracion")

    faltantes = int(comparacion.get("missing_in_run2") or 0)
    if faltantes:
        return _veredicto(
            STOP, resultado, "inventario_inestable_entre_corridas",
            RADIO_FAMILIA,
            f"{faltantes} propiedades que la primera corrida vio no "
            f"aparecieron en la segunda ({comparacion.get('run1_urls')} "
            f"contra {comparacion.get('run2_urls')} urls); mientras no se "
            f"sepa por que, publicar la corrida corta seria declarar completo "
            f"un inventario que no lo esta")

    # ---------------- STOP: evidencia de radio transversal ----------------
    #
    # Un defecto de campo minusculo no puede parar las dos colas, pero tampoco
    # puede taparle el paso a un diagnostico mas grave: este chequeo era el
    # PRIMERO de la funcion, asi que una ficha con un campo ilegible devolvia
    # antes de mirar colisiones de identidad, enumeracion o inventario.
    #
    # Por eso lo menor NO devuelve CONTINUE aca: cae al resto de los chequeos,
    # y solo si ninguno encuentra nada termina en CONTINUE, al final.
    menor = _es_de_baja_magnitud(resultado, fallidos)
    if fallidos and not menor:
        # La fuente publica el campo y no lo leimos. El que lee es el parser, y
        # el parser lo comparten todas las agencias de la familia.
        return _veredicto(
            STOP, resultado, "extraccion_transversal_de_atributos",
            RADIO_FAMILIA,
            f"la fuente publica {', '.join(fallidos)} y la extraccion fallo; "
            f"quien lee esos campos es codigo compartido")

    if comparacion.get("identity_collisions"):
        # `hash_dedup` se calcula en `connectors/base.py`.
        return _veredicto(
            STOP, resultado, "shared/base", RADIO_COMPARTIDO,
            f"{comparacion['identity_collisions']} colisiones de identidad; "
            f"el hash se calcula en codigo compartido")

    for corrida in corridas:
        if corrida.get("descartadas_por_forma"):
            motivo = paro_por_el_guardian_de_forma(corrida)
            if motivo:
                return _veredicto(
                    STOP, resultado, "guardian_de_forma_compartido",
                    RADIO_FAMILIA, motivo)
        if corrida.get("fichas_sin_contenido"):
            return _veredicto(
                STOP, resultado, "lectura_de_ficha_compartida", RADIO_FAMILIA,
                f"{corrida['fichas_sin_contenido']} fichas sin contenido: la "
                f"pagina respondio y no se pudo leer")
        if corrida.get("paginacion_interrumpida"):
            return _veredicto(
                STOP, resultado, "enumeracion_compartida", RADIO_FAMILIA,
                "la paginacion se interrumpio: la enumeracion es compartida")
        if (corrida.get("imagenes_compartidas_descartadas")
                and not _galeria_intacta(resultado)):
            return _veredicto(
                STOP, resultado, "imagenes_compartidas", RADIO_FAMILIA,
                f"{corrida['imagenes_compartidas_descartadas']} imagenes "
                f"compartidas descartadas y la cobertura de imagenes quedo en "
                f"{_cobertura_de_imagenes(resultado)}; la regla es compartida")

    # Antes de leer un colapso como perdida sistematica hay que haber podido
    # LEER el sitio. `varelanegociosinmobiliarios.com` no respondio en 102 s en
    # ninguna de las dos corridas: su inventario "colapso" al 0 % porque nunca
    # se llego a la portada, y eso no es un defecto transversal nuestro sino un
    # sitio caido. Sin esta puerta, cualquier caida ajena para la cola entera
    # con un veredicto de radio FAMILIA que no se sostiene.
    inaccesibles = [c for c in corridas
                    if c.get("estado") in ("ERROR_DISCOVERY", "ERROR_LISTADO")]
    if len(inaccesibles) == len(corridas) and corridas:
        return _veredicto(
            CONTINUE, resultado, "fuente_inaccesible", RADIO_AGENCIA,
            "no se pudo llegar al sitio en ninguna de las dos corridas: "
            f"{'; '.join(sorted({str(c.get('detalle') or 'sin detalle')[:60] for c in inaccesibles}))}")

    if "COLLAPSE_GT_80_PERCENT" in revision:
        return _veredicto(
            STOP, resultado, "perdida_sistematica_de_inventario",
            RADIO_FAMILIA,
            "el inventario colapso mas del 80 %: perdida sistematica")

    if resultado.get("status") == "RUNNER_ERROR":
        return _veredicto(
            STOP, resultado, "shared/runner", RADIO_COMPARTIDO,
            "el runner se cayo; hasta saber por que no se puede acotar")

    # ---------------- CONTINUE: evidencia positiva de radio acotado -------
    inventarios_distintos = any(
        "inventories differ" in r or "not idempotent" in r for r in razones)
    detalles_fallidos = sum(int(c.get("detalles_fallidos") or 0)
                            for c in corridas)

    # Fichas que fallaron por la red o por el servidor del sitio. NO se exige
    # que los inventarios difieran: la rama pedia eso y su propia evidencia
    # decia "el catalogo enumero igual en las dos corridas", o sea que el
    # codigo y el texto se contradecian.
    #
    # Que coincidan es MAS evidencia de salud, no menos. `andrea gianfelice`
    # enumero 153 las dos veces, obtuvo 152 las dos veces, y fallo siempre la
    # misma ficha con un error de red: el triage no supo clasificarlo y paro
    # las dos colas por un radio COMPARTIDO que no existia.
    if detalles_fallidos and externos:
        coinciden = not inventarios_distintos
        return _veredicto(
            CONTINUE, resultado, "sitio_externo", RADIO_AGENCIA,
            f"{detalles_fallidos} detalles fallaron con errores de red o del "
            f"servidor ({', '.join(sorted(externos))}); "
            + ("el catalogo enumero igual en las dos corridas"
               if coinciden else
               "y eso explica que los inventarios difieran"))

    estados = [c.get("estado") for c in corridas if c.get("estado")]
    if "ENUMERACION_INCOMPLETA" in estados:
        # La enumeracion es codigo compartido. No se puede distinguir "el sitio
        # nos corto" de "nuestra paginacion no llego", asi que se para.
        return _veredicto(
            STOP, resultado, "enumeracion_compartida", RADIO_FAMILIA,
            "la enumeracion quedo incompleta y el enumerador es compartido; "
            "no se puede separar el sitio de nuestra paginacion")
    if "VARIANTE_NO_SOPORTADA" in estados:
        # "No reconoci la forma" NO es "no hay inventario". Si el sitio muestra
        # estructura de catalogo, lo que esta en juego son propiedades reales
        # que no estamos publicando, y eso pesa mas que ahorrarse una parada.
        senales = resultado.get("senales_de_catalogo") or []
        if senales:
            return _veredicto(
                STOP, resultado, "posible_perdida_de_inventario", RADIO_FAMILIA,
                f"el sitio publica catalogo y no lo pudimos enumerar: "
                f"{'; '.join(senales)}")
        return _veredicto(
            CONTINUE, resultado, COMPONENTE_VARIANTE, RADIO_ESTRATEGIA,
            "el connector no reconoce la forma de este sitio y no se hallaron "
            "senales de catalogo publicado")
    if "BLOQUEADA" in estados:
        return _veredicto(
            CONTINUE, resultado, "sitio_nos_bloquea", RADIO_AGENCIA,
            "el sitio nos bloqueo (403/429); es su decision, no nuestro parser")
    if {"ERROR_DISCOVERY", "ERROR_LISTADO"} & set(estados):
        return _veredicto(
            CONTINUE, resultado, "fuente_inaccesible", RADIO_AGENCIA,
            "una de las corridas no pudo llegar al sitio; es la red o el "
            "servidor, no nuestro parser")
    if "PRESUPUESTO_AGOTADO" in estados:
        return _veredicto(
            CONTINUE, resultado, "sitio_lento", RADIO_AGENCIA,
            "se agoto el presupuesto de tiempo: el sitio esta degradado")

    if any(c.get("presupuesto_agotado") for c in corridas):
        return _veredicto(
            CONTINUE, resultado, "sitio_lento", RADIO_AGENCIA,
            "se agoto el presupuesto de tiempo: el sitio esta degradado")

    if "LOW_INVENTORY_0_11" in revision and not fallidos:
        return _veredicto(
            CONTINUE, resultado, "inventario_chico", RADIO_AGENCIA,
            "inventario muy chico y ningun campo con extraccion fallida")

    # ------- CONTINUE: el defecto menor, ya que ningun otro aparecio -------
    #
    # Se llega aca solo despues de haber pasado por TODOS los chequeos de
    # arriba sin que ninguno encontrara nada. O sea: lo unico que hay es un
    # campo ilegible en una o dos fichas.
    #
    # Sigue anotandose entero en la cola de defectos y la agencia sigue
    # cerrando NEEDS_FIX. Lo unico que cambia es que no detiene a los dos
    # workers.
    if menor:
        return _veredicto(
            CONTINUE, resultado, COMPONENTE_MENOR, RADIO_AGENCIA,
            f"la extraccion fallo en poquisimas fichas y ningun otro chequeo "
            f"encontro nada: {_detalle_menor(resultado, fallidos)}")

    # ---------------- Sin evidencia para acotar: se para ------------------
    return _veredicto(
        STOP, resultado, "sin_determinar", RADIO_COMPARTIDO,
        "no hay evidencia positiva de que la causa sea externa o acotada; "
        "no encontrar razones para parar no es tener razones para seguir")


def _veredicto(decision: str, resultado: dict[str, Any], componente: str,
               radio: str, evidencia: str) -> dict[str, Any]:
    return {
        "triage_version": TRIAGE_VERSION,
        "canonical_agency_id": resultado.get("canonical_agency_id"),
        "status": resultado.get("status"),
        "causa_observable": "; ".join(resultado.get("reasons") or []) or "(sin razones)",
        "decision": decision,
        "componente_sospechoso": componente,
        "radio_estimado": radio,
        "evidencia": evidencia,
        "connector": resultado.get("connector"),
        "connector_strategy": resultado.get("connector_strategy"),
        "strategy_fingerprint": resultado.get("strategy_fingerprint"),
        "firma_del_patron": firma(resultado, componente),
        "pendiente_de_resolucion": True,
        "certificado": False,
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# --------------------------------------------------------------------------
# Corte por lote
# --------------------------------------------------------------------------
# El componente que se anota cuando no reconocimos la forma del sitio. Es
# un sintoma con tantas causas como formas de sitio hay, no un patron.
COMPONENTE_VARIANTE = "variante_no_soportada"

DEFECTOS_PARA_CORTAR = 5
HORAS_PARA_CORTAR = 12


def identidad_de_defecto(defecto: dict[str, Any]) -> str:
    """Lo que hace a un defecto EL MISMO defecto entre dos pasadas.

    Agencia, componente y huella de estrategia. Nada mas: ni la fecha ni la
    evidencia, que traen la hora y el conteo del momento y harian que cada
    pasada produjera una identidad nueva -y entonces la memoria no recordaria
    nada-.

    La huella SI entra, y es deliberado. Si cambiamos el codigo, el defecto de
    antes puede no ser el de ahora y merece volver a contar. Sin ese campo, un
    arreglo que no funciono quedaria silenciado para siempre, que es el modo de
    falla peligroso de cualquier memoria.
    """
    return "|".join((str(defecto.get("canonical_agency_id") or ""),
                     str(defecto.get("componente_sospechoso") or ""),
                     str(defecto.get("strategy_fingerprint") or "")))


def defectos_ya_cortados(ruta) -> frozenset[str]:
    """Las identidades que ya provocaron un corte alguna vez.

    Si el archivo no se puede leer se devuelve vacio, y eso hace **cortar de
    mas**, no de menos: un corte sobrante cuesta un relanzamiento y uno
    faltante deja corriendo codigo sospechado.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return frozenset()
    vistos: set[str] = set()
    try:
        for linea in ruta.open(encoding="utf-8", errors="replace"):
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except ValueError:
                continue
            for identidad in (fila.get("defectos") or []):
                if isinstance(identidad, str):
                    vistos.add(identidad)
    except OSError:
        return frozenset()
    return frozenset(vistos)


def anotar_corte(ruta, pendientes: list[dict[str, Any]], motivo: str) -> None:
    """Deja escrito que este lote ya pidio atencion, y cual era."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "motivo": motivo,
            "defectos": [identidad_de_defecto(d) for d in pendientes],
            "agencias": [d.get("canonical_agency_id") for d in pendientes],
        }, ensure_ascii=False) + "\n")


def debe_cortar_por_lote(pendientes: list[dict[str, Any]],
                         ahora: float | None = None,
                         ya_cortados: frozenset[str] = frozenset(),
                         ) -> tuple[bool, str]:
    """Si conviene detenerse aunque cada defecto fuera continuable.

    Cinco defectos sueltos ya justifican una tanda de diagnostico, y dos con la
    misma firma dejaron de ser casualidad: es el mismo problema apareciendo dos
    veces, y eso es exactamente lo que un radio mal estimado produce.

    Un corte que ya se dio no se vuelve a dar
    -----------------------------------------
    Medido sobre el log real: los tres ultimos cortes del worker 1 pararon en
    la MISMA agencia -`gomez servicios inmobiliarios`- con EXACTAMENTE los
    mismos cinco defectos, y ninguna de las cinco tenia diferida escrita. La
    cola se relanzaba, recorria el mismo tramo, reacumulaba los mismos cinco y
    volvia a cortar. Tres cortes por la misma informacion.

    Un corte por lote es un pedido de atencion sobre un conjunto concreto de
    defectos. Una vez hecho, repetirlo no informa nada nuevo -la informacion ya
    esta en la cola de defectos y en los reportes- y si cuesta un paro completo
    mas un relanzamiento a mano.

    Lo que cambia es **que cuenta**, no que se registra: el registro completo
    se conserva, y el radio, el ranking y los reportes lo siguen usando entero.
    """
    if not pendientes:
        return False, ""

    if ya_cortados:
        pendientes = [d for d in pendientes
                      if identidad_de_defecto(d) not in ya_cortados]
        if not pendientes:
            return False, ""

    # Los de baja magnitud no cuentan para el umbral. El corte junta defectos
    # para diagnosticarlos de a tanda, y un defecto clasificado por magnitud es
    # justamente uno que decidimos no diagnosticar: una ficha de 163, o cuatro
    # de 300. Sumarlos hacia que cinco defectos de UNA ficha pararan las dos
    # colas, que es lo que la politica de magnitud vino a evitar.
    #
    # Siguen contando para el radio y para la regla de firma repetida: si cinco
    # agencias fallan el mismo campo por poco, eso ya no es magnitud, es un
    # patron, y esas dos reglas lo ven.
    computables = [d for d in pendientes
                   if d.get("componente_sospechoso") != COMPONENTE_MENOR]

    if len(computables) >= DEFECTOS_PARA_CORTAR:
        return True, (f"{len(computables)} defectos pendientes sin resolver "
                      f"(umbral {DEFECTOS_PARA_CORTAR})")

    firmas: dict[str, int] = {}
    for defecto in pendientes:
        # `variante_no_soportada` no es un patron: es un sintoma. La firma se
        # arma con conector, estrategia, componente y razones, y para "no
        # reconoci la forma del sitio" esas cuatro cosas son identicas siempre,
        # asi que agrupa causas que no tienen nada que ver. Medido sobre las
        # que compartian la firma ef05c0690dea:
        #
        #   armanino   una SPA de React
        #   amud       jQuery contra la API de la plataforma SOM
        #   bergo      HTTP 200 con el cuerpo VACIO
        #   bottai     un catalogo real con una forma de url que no conocemos
        #   alta       16 propiedades detras de un /buscador (ya arreglada)
        #
        # Cinco causas, una firma. La regla -"dos con la misma firma dejo de
        # ser casualidad"- es buena justamente porque la firma identifica un
        # patron; donde no lo identifica, para la cola por nada. Estas siguen
        # contando para el umbral de cinco y para el radio, que no dependen de
        # que la firma signifique algo.
        if defecto.get("componente_sospechoso") == COMPONENTE_VARIANTE:
            continue
        clave = defecto.get("firma_del_patron")
        if clave:
            firmas[clave] = firmas.get(clave, 0) + 1
    repetida = [f for f, n in firmas.items() if n >= 2]
    if repetida:
        return True, (f"dos defectos con la misma firma ({repetida[0]}): dejo "
                      f"de ser casualidad y el radio quedo mal estimado")

    if any(d.get("radio_estimado") in (RADIO_COMPARTIDO, RADIO_FAMILIA)
           for d in pendientes):
        return True, ("un defecto pendiente tiene radio compartido o de "
                      "familia: el radio crecio respecto de lo estimado")

    ahora = ahora if ahora is not None else time.time()
    marcas = [d.get("epoch") for d in pendientes if d.get("epoch")]
    if marcas and (ahora - min(marcas)) >= HORAS_PARA_CORTAR * 3600:
        horas = (ahora - min(marcas)) / 3600
        return True, (f"pasaron {horas:.1f} h desde el primer defecto "
                      f"pendiente (umbral {HORAS_PARA_CORTAR} h)")
    return False, ""

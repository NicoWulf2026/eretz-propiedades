#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Nada relanzaba la cola, y eso costaba mas que todos los defectos juntos.

No escribe en produccion, no cambia extractores, no cambia huellas.
`database_writes: 0`. Lo unico que hace es lanzar procesos de la cola, y solo
cuando es seguro.

La medicion que lo justifica
----------------------------
Sobre las 2.501 corridas del historial completo, uniendo intervalos y contando
como parada cualquier hueco de mas de 20 minutos:

    span del historial      487,6 h
    tiempo ACTIVO           121,6 h
    tiempo PARADA           366,0 h   (75 %)
    episodios de parada     167

Y el reparto importa mas que el total: **117 de los 167 huecos no coinciden con
ningun paro registrado**, y suman **190,6 h -el 52 % de las horas paradas-**.
No son defectos: es la cola simplemente no corriendo. Proceso muerto, nadie
relanzo, maquina apagada.

Eliminar esa clase de hueco lleva el duty cycle del 25 % al **64 %** medido.
Ningun arreglo semantico del tablero se acerca a ese factor.

Y la infraestructura ya existia, apagada: `ERETZ_cola_w0` y `ERETZ_cola_w1`
estan en estado Ready con `NextRunTime` **vacio** y su ultima corrida es del
2026-09-09; `ERETZ_cola_certificacion` esta agendada para **2027-09-04**. Los
workers que corrieron el 17 los lanzo alguien a mano.

Que NO hace, y por que
----------------------
**No relanza sobre un paro sin diagnosticar.** Esa es la regla que no se
relaja: un paro transversal significa que sospechamos del codigo, y volver a
correrlo produce certificaciones que habria que rehacer. Relanzar tras un
**corte por lote** -salida limpia y planificada- o tras una **muerte del
proceso** si es legitimo, y son justamente los 117 huecos que cuestan las
190,6 h.

Un paro se considera atendido cuando hay una diferida firmada para esa agencia
escrita DESPUES del paro. No alcanza con que exista una diferida vieja: si el
paro es posterior, es informacion nueva.

**Pero detiene la familia, no la cola.** El 2026-09-21 un paro FAMILIA sin
firmar dejo los dos workers parados 34 horas. La regla estaba bien; el alcance
no: de 613 paros STOP del historial, **596 son FAMILIA y 17 COMPARTIDO**, y
sobre la cola `ready` de verdad -791 agencias- detener `generico` deja
corriendo el 53,7 %, `tokko` el 62,2 %, `wordpress` el 85,6 % y `wasi` el
98,5 %.

Asi que un paro FAMILIA con conector conocido relanza con
`--excluir-conector`: esa familia no se toca hasta que su paro este firmado -y
queda anotada en `ERETZ_FAMILIAS_DETENIDAS` para que siga sin tocarse despues,
porque el runner borra la bandera al arrancar-, y las demas avanzan. Un paro
COMPARTIDO, uno sin conector anotado o una bandera ilegible siguen deteniendo
todo.

**Nunca mas de 2 workers.** Se comprueba tres veces, y ninguna sobra: aca antes
de lanzar, el `MultipleInstancesPolicy: IgnoreNew` de la tarea, y el cerrojo
por worker del propio runner, que verifica PID vivo y latido.

Uso:
    python scripts/relanzar_la_cola.py            # dice que haria
    python scripts/relanzar_la_cola.py --lanzar
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

SALIDA = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827")
BITACORA = SALIDA / "ERETZ_RELANZAMIENTOS.jsonl"
WORKERS = 2


def _fecha(texto: str | None) -> float | None:
    if not texto:
        return None
    try:
        import datetime
        return datetime.datetime.fromisoformat(str(texto)[:19]).timestamp()
    except ValueError:
        return None


def paro_vigente(salida: Path) -> dict[str, Any] | None:
    """El paro escrito por un worker para el otro, si sigue en pie."""
    ruta = salida / "AGENCY_CERTIFICATION_STOP.json"
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Ilegible es peor que ausente: no se relanza a ciegas.
        return {"canonical_agency_id": "ilegible", "cuando": None}


def paro_atendido(salida: Path, paro: dict[str, Any]) -> bool:
    """Hay una diferida firmada para esa agencia, escrita DESPUES del paro.

    Una diferida vieja no alcanza. Si el paro es posterior, trae informacion
    que esa diferida no pudo haber tenido en cuenta.
    """
    agencia = paro.get("canonical_agency_id")
    cuando = _fecha(paro.get("cuando"))
    if not agencia or cuando is None:
        return False
    ruta = salida / "AGENCY_DEFECTS_DIFERIDOS.jsonl"
    if not ruta.exists():
        return False
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("canonical_agency_id") != agencia:
            continue
        firmada = _fecha(fila.get("cuando"))
        if firmada is not None and firmada >= cuando:
            return True
    return False


# El runner da por ocupado un cerrojo si el latido es reciente **o** el pid
# existe, y su umbral es de una hora. Ese umbral esta bien calibrado: una sola
# inmobiliaria puede tardar tres horas y bajarlo haria que un segundo worker
# diera por muerto a uno vivo.
LATIDO_VENCIDO = 3600.0


def cerrojo_de(salida: Path, worker: int) -> Path:
    return salida / f"AGENCY_CERTIFICATION_RUNNER.w{worker}.lock"


def limpiar_cerrojos_huerfanos(salida: Path, aplicar: bool) -> list[int]:
    """Borra los cerrojos cuyo PID ya no existe. Devuelve cuales.

    Sin esto el relanzador no sirve para el caso que vino a resolver. Se vio
    en vivo: despues de matar los workers a la fuerza quedaron sus cerrojos
    con latido reciente, `tomar_cerrojo` los dio por activos -su regla es
    latido fresco **o** pid vivo- y cada relanzamiento levantaba un proceso
    que moria en el acto con "Ya hay un runner activo (pid 13976...)". Iba a
    seguir asi **una hora entera**, hasta que el latido venciera.

    Borrar un cerrojo a ciegas es peligroso y por eso el runner no lo hace: dos
    procesos sobre el mismo checkpoint se pisan el cursor y le piden a los
    mismos sitios al doble del ritmo acordado. Pero aca no es a ciegas. El
    propio mensaje del runner dice "si comprobaste que murio, borra...", y
    `psutil.pid_exists` ES esa comprobacion. Automatizar una comprobacion
    verificable no es lo mismo que saltearla.

    Si el pid existe no se toca nada, ni siquiera cuando el latido esta
    vencido: la reutilizacion de pid por el sistema operativo empuja hacia el
    lado conservador, que es el correcto.
    """
    import psutil
    limpiados: list[int] = []
    for worker in range(WORKERS):
        ruta = cerrojo_de(salida, worker)
        if not ruta.exists():
            continue
        try:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
            pid = int(previo["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue  # ilegible: no se toca
        if pid > 0 and not psutil.pid_exists(pid):
            limpiados.append(worker)
            if aplicar:
                ruta.unlink(missing_ok=True)
    return limpiados


def workers_vivos(salida: Path) -> dict[int, int]:
    """Los workers cuyo cerrojo el RUNNER daria por activo.

    Se usa la misma regla que `tomar_cerrojo` -latido fresco **o** pid vivo- y
    no solo el pid. Con la regla de antes el relanzador creia libre un puesto
    que el runner iba a rechazar, y levantaba un proceso condenado a morir en
    el arranque. Preguntar distinto que el que decide es no preguntar.
    """
    import psutil
    vivos: dict[int, int] = {}
    for worker in range(WORKERS):
        ruta = cerrojo_de(salida, worker)
        if not ruta.exists():
            continue
        try:
            previo = json.loads(ruta.read_text(encoding="utf-8"))
            pid = int(previo["pid"])
            latido = float(previo["heartbeat_epoch"])
        except (OSError, ValueError, KeyError, TypeError):
            # Cerrojo ilegible: se trata como ocupado. El runner tiene la
            # misma politica y por una razon buena: borrarlo a ciegas es como
            # se terminan pisando dos procesos el mismo checkpoint.
            vivos[worker] = -1
            continue
        if pid > 0 and psutil.pid_exists(pid):
            vivos[worker] = pid
        elif (time.time() - latido) < LATIDO_VENCIDO:
            vivos[worker] = pid
    return vivos


def intentar_precedente(salida: Path) -> int:
    """Antes de rendirse ante un paro, ver si su firma ya se diagnostico.

    Es lo que hace que el relanzador sirva sin nadie mirando. Un paro
    transversal detiene la cola hasta que alguien escribe una diferida, y
    medido sobre las 93 agencias en `NEEDS_FIX`, **tres de cada cuatro** de
    las que no la tienen comparten firma con una que si.

    No relaja ninguna regla: `diferir_por_precedente` solo escribe cuando la
    firma es IDENTICA a una diagnosticada por una persona, del mismo radio,
    con el defecto todavia abierto, y nunca sobre `variante_no_soportada`. Si
    no hay precedente, no escribe nada y el paro sigue en pie.
    """
    try:
        from diferir_por_precedente import candidatas, texto, DIFERIDAS
        from diferir_por_precedente import MARCA_AUTOMATICA
    except Exception:  # noqa: BLE001 - sin la herramienta, se sigue como antes
        return 0
    try:
        lista = candidatas()
    except Exception:  # noqa: BLE001 - un artefacto ilegible no relanza nada
        return 0
    if not lista:
        return 0
    marca = time.strftime("%Y-%m-%dT%H:%M:%S")
    with DIFERIDAS.open("a", encoding="utf-8") as fh:
        for c in lista:
            fh.write(json.dumps({
                "canonical_agency_id": c["agencia"],
                "componente": c["componente"], "radio": c["radio"],
                "diagnostico": texto(c), "cuando": marca,
                MARCA_AUTOMATICA: True,
                "precedente_agencia": c["precedente"]["agencia"],
                "precedente_cuando": c["precedente"]["cuando"],
                "firma_del_patron": c["firma"],
                "database_writes": 0}, ensure_ascii=False) + "\n")
    return len(lista)


# Que familias quedaron detenidas y todavia no tienen diferida firmada.
#
# Hace falta un libro propio porque la bandera de paro es EFIMERA: el runner
# la borra al arrancar (`run_agency_certification_queue.py`, "una bandera de
# una corrida anterior no puede frenar la siguiente"). Sin este archivo, el
# primer relanzamiento consumiria el paro y el siguiente volveria a correr la
# familia sospechada como si nada hubiera pasado. Eso no seria acotar el
# fail-closed: seria perderlo.
LIBRO_DE_FAMILIAS = "ERETZ_FAMILIAS_DETENIDAS.jsonl"


def conector_del_triaje(salida: Path, paro: dict[str, Any]) -> str | None:
    """El conector que el TRIAJE anoto para este mismo paro.

    Hace falta porque la bandera no siempre lo trae: un worker que arranco
    antes del cambio escribe la bandera vieja, y el 2026-09-23 a las 12:29
    `alagna propiedades` paro asi -sin `conector`- con los dos workers en
    memoria del codigo anterior.

    No es adivinar. Se busca la entrada STOP de `AGENCY_DEFECT_QUEUE.jsonl`
    que coincida en las TRES cosas -agencia, componente y hora exacta- y se
    toma el conector que el triaje ya habia anotado ahi. Si no hay una que
    coincida entera, devuelve None y se detiene todo, como antes.
    """
    fila = fila_del_triaje(salida, paro)
    if not fila or str(fila.get("radio_estimado") or "").upper() != "FAMILIA":
        return None
    return str(fila.get("connector") or "").strip().lower() or None


def familia_de(paro: dict[str, Any] | None,
               salida: Path | None = None) -> str | None:
    """El conector del que sospecha un paro, si se puede acotar a uno.

    Un paro de radio FAMILIA sospecha de UN conector; uno COMPARTIDO sospecha
    del codigo que todos comparten. Confundirlos cuesta caro en una direccion
    y es peligroso en la otra, asi que esto acota solo el primero y devuelve
    `None` -o sea, detener todo- ante cualquier duda: otro radio, un paro sin
    conector anotado, o un archivo ilegible.
    """
    if not isinstance(paro, dict):
        return None
    if str(paro.get("radio") or "").upper() != "FAMILIA":
        return None
    conector = str(paro.get("conector") or "").strip().lower()
    if not conector and salida is not None:
        conector = conector_del_triaje(salida, paro) or ""
    return conector or None


def fila_del_triaje(salida: Path, paro: dict[str, Any]) -> dict[str, Any] | None:
    """La entrada STOP del triaje que es ESTE paro: agencia, componente y hora.

    Las tres, o ninguna. Heredar datos de otro paro de la misma agencia
    -otra hora, otro componente- seria atribuirle a este una evidencia que no
    es suya.
    """
    ruta = salida / "AGENCY_DEFECT_QUEUE.jsonl"
    if not ruta.exists():
        return None
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if fila.get("decision") != "STOP":
            continue
        if fila.get("canonical_agency_id") != paro.get("canonical_agency_id"):
            continue
        if fila.get("componente_sospechoso") != paro.get("componente"):
            continue
        if str(fila.get("cuando") or "")[:19] != str(paro.get("cuando") or "")[:19]:
            continue
        return fila
    return None


# Cuanto cuesta recalcular una huella: parsear el AST de quince archivos. El
# relanzador corre cada diez minutos y puede tener varias familias anotadas,
# asi que se calcula una vez por conector y estrategia en cada corrida.
_HUELLAS: dict[tuple[str, str], str | None] = {}


def huella_actual(conector: str, estrategia: str) -> str | None:
    clave = (conector, estrategia)
    if clave not in _HUELLAS:
        try:
            from agency_fingerprints import strategy_fingerprint
            _HUELLAS[clave] = strategy_fingerprint(conector, estrategia)
        except Exception:  # noqa: BLE001 - sin huella no se libera nada
            _HUELLAS[clave] = None
    return _HUELLAS[clave]


def la_huella_ya_cambio(salida: Path, paro: dict[str, Any]) -> bool:
    """¿El paro hablaba de un codigo que ya no existe?

    Es la mitad que faltaba para que un paro no vuelva a costar 34 horas.

    Un paro FAMILIA dice «este codigo, en esta familia, hace algo mal». La
    diferida firmada es una forma de levantarlo: alguien miro y decidio. La
    otra forma, que no existia, es que el codigo CAMBIE. El 2026-09-23
    `alagna` paro por «la fuente publica ciudad y la extraccion fallo»; se
    encontro la causa -el JSON-LD se descartaba entero por una url con el id
    al final- y se arreglo. El paro seguia en pie esperando una firma sobre
    un defecto que ya no estaba, con 366 agencias detenidas detras.

    Esto NO certifica nada. Libera la familia para que la cola la vuelva a
    PROBAR con el codigo nuevo, y el triaje decide de cero: si el defecto
    sigue, para otra vez, ahora con la huella nueva, y ese paro si espera. Lo
    que se acorta es la espera sobre evidencia vieja, no la exigencia sobre
    la evidencia nueva.

    Solo aplica a FAMILIA. Un paro COMPARTIDO sospecha del codigo comun, y la
    huella de una estrategia cambia tambien cuando cambia solo su archivo
    propio; liberarlo por eso seria confundir cualquier cambio con el cambio
    que hacia falta.
    """
    if str(paro.get("radio") or "").upper() != "FAMILIA":
        return False
    huella = str(paro.get("strategy_fingerprint") or "")
    estrategia = str(paro.get("connector_strategy") or "")
    conector = str(paro.get("conector") or "").strip().lower()
    if not (huella and estrategia and conector):
        triaje = fila_del_triaje(salida, paro) or {}
        huella = huella or str(triaje.get("strategy_fingerprint") or "")
        estrategia = estrategia or str(triaje.get("connector_strategy") or "")
        conector = conector or str(triaje.get("connector") or "").strip().lower()
    if not (huella and estrategia and conector):
        return False  # sin saber que codigo sospechaba, no se libera
    actual = huella_actual(conector, estrategia)
    if not actual:
        return False
    return actual[:len(huella)] != huella[:len(actual)]


def familias_pendientes(salida: Path) -> list[dict[str, Any]]:
    """Las anotaciones del libro que siguen detenidas.

    Deja de estarlo una familia con diferida firmada despues del paro, o una
    cuyo codigo cambio desde entonces -ver `la_huella_ya_cambio`-.
    """
    ruta = salida / LIBRO_DE_FAMILIAS
    if not ruta.exists():
        return []
    pendientes: list[dict[str, Any]] = []
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        if not fila.get("conector"):
            continue
        if paro_atendido(salida, fila):
            continue
        if la_huella_ya_cambio(salida, fila):
            continue
        pendientes.append(fila)
    return pendientes


COMPONENTE_SIN_DETERMINAR = "sin_determinar"


def es_sin_determinar(paro: dict[str, Any]) -> bool:
    """Un paro COMPARTIDO porque el triaje no pudo atribuirlo, no porque sepa
    que el defecto esta en el codigo comun.

    Los COMPARTIDO con componente nombrado -`shared/runner`, un KeyError del
    runner- SI saben donde esta el defecto, y esos siguen deteniendo todo.
    """
    return (str(paro.get("radio") or "").upper() == "COMPARTIDO"
            and paro.get("componente") == COMPONENTE_SIN_DETERMINAR)


def degradar_sin_determinar(salida: Path,
                            paro: dict[str, Any]) -> tuple[str | None, str]:
    """El radio minimo DEMOSTRABLE de un defecto que nadie pudo atribuir.

    El triaje dice COMPARTIDO cuando no encuentra evidencia positiva de un
    radio acotado, y hace bien: «no encontrar razones para parar no es tener
    razones para seguir». Esa regla no se toca y el veredicto sigue diciendo
    lo que dice. Lo que se decide aca es como DEGRADAR.

    Medido sobre el historial: de 622 paros STOP, 19 son COMPARTIDO y los 19
    son `sin_determinar`, en 19 agencias distintas. 18 de ellos se cerraron
    solos -certificaron en el reintento o se diagnosticaron como externos-, la
    mayoria en dos a cinco minutos. El de `varesse` dejo las 791 agencias
    paradas 4 h 19 min por UN campo de UNA ficha.

    Lo que si se puede demostrar de un defecto desconocido es que corrio el
    codigo comun MAS el de su familia. Si estuviera en el comun, se va a ver
    tambien en otra familia; mientras aparezca en una sola, la sospecha
    minima demostrable es esa familia. Entonces:

    - el primer defecto sin atribuir detiene SU familia, no el universo. La
      familia no se toca hasta que haya firma o cambie su codigo; nada se
      certifica -la agencia sigue en NEEDS_FIX-;
    - si aparece otro sin atribuir en una familia DISTINTA mientras el
      primero sigue abierto, eso ya es evidencia de algo transversal y se
      detiene todo, como antes;
    - sin conector identificable no hay familia que acotar: se detiene todo.

    El riesgo aceptado es el que el triaje describe: un defecto del codigo
    comun que se toma por local. Queda acotado porque las otras familias se
    certifican con los mismos controles por agencia -un defecto que se
    manifiesta en ellas las deja en NEEDS_FIX y escala esto- y porque la cola
    corre primero los canarios de cada familia. Simulado sobre los 19
    historicos: 11 se acotan y 8 escalan; 7 de esos 8 por un unico paro de
    `arte propiedades` que quedo abierto trece dias sin que nadie lo cerrara,
    y que hoy se liberaria al primer cambio de codigo.
    """
    conector = str(paro.get("conector") or "").strip().lower()
    if not conector:
        conector = str((fila_del_triaje(salida, paro) or {}).get("connector")
                       or "").strip().lower()
    if not conector:
        return None, " (sin conector identificable: no se puede acotar)"
    otras = sorted({str(f["conector"]).strip().lower()
                    for f in familias_pendientes(salida)
                    if f.get("degradado_de")
                    and str(f["conector"]).strip().lower() != conector})
    if otras:
        return None, (f" (escala a todo: ya hay un defecto sin atribuir abierto "
                      f"en {', '.join(otras)}, y dos familias con defectos "
                      f"sin causa apuntan al codigo comun)")
    return conector, ""


def anotar_familia(salida: Path, paro: dict[str, Any], conector: str) -> bool:
    """Deja escrito que esta familia queda detenida. Idempotente por paro."""
    clave = (paro.get("canonical_agency_id"), paro.get("componente"),
             paro.get("cuando"))
    for fila in familias_pendientes(salida):
        if (fila.get("canonical_agency_id"), fila.get("componente"),
                fila.get("cuando")) == clave:
            return False
    triaje = fila_del_triaje(salida, paro) or {}
    with (salida / LIBRO_DE_FAMILIAS).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "canonical_agency_id": paro.get("canonical_agency_id"),
            "componente": paro.get("componente"),
            "radio": paro.get("radio"),
            "conector": conector,
            # Si el triaje no lo pudo atribuir y se acoto a la familia. Es lo
            # que despues decide si un segundo defecto sin causa escala.
            "degradado_de": paro.get("degradado_de"),
            # Que codigo se sospechaba. Sin esto no hay forma de saber
            # despues si el paro habla de algo que todavia existe.
            "connector_strategy": (paro.get("connector_strategy")
                                   or triaje.get("connector_strategy")),
            "strategy_fingerprint": (paro.get("strategy_fingerprint")
                                     or triaje.get("strategy_fingerprint")),
            "cuando": paro.get("cuando"),
            "anotado": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "database_writes": 0}, ensure_ascii=False) + "\n")
    return True


def plan(salida: Path, anotar: bool = False) -> tuple[list[int], str, list[str]]:
    """Que workers lanzar, por que no los otros, y que familias no tocar.

    Un paro de radio FAMILIA sospecha de UN conector, no de la cola entera.
    Medido sobre todo el historial: de 613 paros STOP, **596 son FAMILIA y 17
    COMPARTIDO**. Y una familia no es la cola: sobre las 791 agencias de la
    cola `ready`, detener `generico` deja corriendo el 53,7 %, `tokko` el
    62,2 %, `wordpress` el 85,6 % y `wasi` el 98,5 %.

    El 2026-09-21 un paro FAMILIA sin firmar dejo los dos workers detenidos
    **34 horas**. No relanzar sin diferida firmada estaba bien y sigue igual;
    lo desproporcionado era el alcance: detener el 100 % de la cola por
    sospechar de una familia, en el 97 % de los paros.

    El fail-closed se conserva donde importa. La familia sospechada NO se
    toca hasta que su paro este diagnosticado y firmado -y queda anotada en
    `LIBRO_DE_FAMILIAS` para que siga sin tocarse en los relanzamientos
    siguientes, cuando la bandera ya no exista-. Lo que cambia es que las
    demas avanzan. Un paro COMPARTIDO, uno sin conector o una bandera
    ilegible siguen deteniendo todo.
    """
    bloqueadas = {str(f["conector"]).strip().lower()
                  for f in familias_pendientes(salida)}
    paro = paro_vigente(salida)
    motivo_extra = ""
    if paro is not None and str(paro.get("radio") or "") == RADIO_OPERACION:
        # La pusimos nosotros para relanzar: no es un defecto que esperar. Los
        # workers paran ante ella y el que arranque la borra.
        motivo_extra = "; relanzamiento pedido por el propio relanzador"
        paro = None
    if paro is not None and not paro_atendido(salida, paro):
        escritas = intentar_precedente(salida)
        if escritas:
            paro = paro_vigente(salida)
        if paro is not None and not paro_atendido(salida, paro):
            familia = familia_de(paro, salida)
            escalado = ""
            if not familia and es_sin_determinar(paro):
                familia, escalado = degradar_sin_determinar(salida, paro)
                if familia:
                    paro = {**paro, "radio": "FAMILIA",
                            "degradado_de": "COMPARTIDO/sin_determinar"}
            if not familia:
                return [], (f"paro sin diagnosticar en "
                            f"{paro.get('canonical_agency_id')} "
                            f"({paro.get('componente')}, radio "
                            f"{paro.get('radio')}): no se relanza hasta que "
                            f"haya una diferida firmada"
                            + escalado
                            + (f" (se escribieron {escritas} por precedente, "
                               f"ninguna cubre este paro)"
                               if escritas else "")), []
            if la_huella_ya_cambio(salida, {**paro, "conector": familia}):
                # El codigo del que sospechaba ya no es el que va a correr:
                # la familia se vuelve a probar en vez de esperar una firma
                # sobre un defecto que quizas ya no esta.
                motivo_extra = (f"; paro FAMILIA en "
                                f"{paro.get('canonical_agency_id')} sobre un "
                                f"codigo que ya cambio: `{familia}` se vuelve "
                                f"a probar")
            else:
                if anotar:
                    anotar_familia(salida, paro, familia)
                bloqueadas.add(familia)
                motivo_extra = (f"; paro FAMILIA sin diagnosticar en "
                                f"{paro.get('canonical_agency_id')} "
                                f"({paro.get('componente')})")
    excluir = sorted(bloqueadas)
    if excluir:
        motivo_extra += f"; sin los conectores {', '.join(excluir)}"
    limpiar_cerrojos_huerfanos(salida, aplicar=True)
    vivos = workers_vivos(salida)
    faltan = [w for w in range(WORKERS) if w not in vivos]
    if not faltan:
        liberadas = familias_liberadas_en_curso(salida, vivos, set(excluir))
        if liberadas:
            if anotar:
                pedir_relanzamiento(salida, liberadas)
            motivo_extra += (f"; se liberaron {', '.join(sorted(liberadas))} y "
                             f"los workers corren sin ellas: paran en la "
                             f"proxima agencia para tomarlas")
        return [], f"los {WORKERS} workers ya estan vivos: {vivos}{motivo_extra}", excluir
    return faltan, (f"faltan {len(faltan)} de {WORKERS}"
                    + (f"; vivos: {vivos}" if vivos else "")
                    + motivo_extra), excluir


# Una bandera que ponemos NOSOTROS para relanzar, no un defecto. El runner para
# ante cualquier bandera al terminar la agencia en curso -sin cortar una
# corrida a medias- y la borra al arrancar; el vigilante la reconoce y no
# alerta. Lo unico que faltaba es que el relanzador tampoco la tomara por un
# paro sin diagnosticar.
RADIO_OPERACION = "OPERACION"


def familias_liberadas_en_curso(salida: Path, vivos: dict[int, int],
                                excluir: set[str]) -> set[str]:
    """Familias que los workers VIVOS excluyen y que ya no hace falta excluir.

    Liberar una familia no llega sola a los workers que ya estan corriendo: el
    2026-09-24 a las 10:29 se firmaron los dos paros de `tokko` y el codigo de
    `wordpress` cambio, pero los workers lanzados a las 10:04 tenian las dos
    familias excluidas y las iban a seguir excluyendo hasta terminar las otras
    378 agencias. Dias.

    Se reconstruye que excluye cada worker vivo desde la bitacora de
    lanzamientos, por su pid. Un worker que no figura -lanzado a mano- no se
    toca: sin saber con que exclusiones corre, no hay nada que comparar.
    """
    ruta = salida / "ERETZ_RELANZAMIENTOS.jsonl"
    if not ruta.exists() or not vivos:
        return set()
    por_pid: dict[int, set[str]] = {}
    for linea in ruta.open(encoding="utf-8", errors="replace"):
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except ValueError:
            continue
        excluidos = {str(c).strip().lower()
                     for c in (fila.get("conectores_excluidos") or [])}
        for pid in (fila.get("lanzados") or {}).values():
            try:
                por_pid[int(pid)] = excluidos
            except (TypeError, ValueError):
                continue
    en_curso: set[str] = set()
    for pid in vivos.values():
        if pid in por_pid:
            en_curso |= por_pid[pid]
    return en_curso - excluir


def pedir_relanzamiento(salida: Path, liberadas: set[str]) -> bool:
    """Pide a los workers que paren en la proxima agencia. Nunca pisa un paro.

    Si ya hay una bandera -un defecto de verdad, u otro pedido nuestro- no se
    escribe nada: la de un defecto tiene que seguir diciendo lo que dice.
    """
    ruta = salida / "AGENCY_CERTIFICATION_STOP.json"
    if ruta.exists():
        return False
    ruta.write_text(json.dumps({
        "canonical_agency_id": "(relanzamiento)",
        "componente": "familias_liberadas",
        "radio": RADIO_OPERACION,
        "liberadas": sorted(liberadas),
        "evidencia": (f"se liberaron {', '.join(sorted(liberadas))}: los "
                      f"workers en curso las excluyen y hay que relanzarlos"),
        "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "database_writes": 0}, ensure_ascii=False), encoding="utf-8")
    return True


def decidir(salida: Path) -> tuple[list[int], str]:
    """Que workers lanzar, y por que no los otros."""
    faltan, motivo, _ = plan(salida)
    return faltan, motivo


def lanzar(worker: int, salida: Path, excluir: list[str] | None = None) -> int:
    """Un worker desprendido, con su log propio."""
    log = salida / f"cola_w{worker}.log"
    comando = [sys.executable, "-u",
               str(RAIZ / "scripts" / "run_agency_certification_queue.py"),
               "--ready", "--workers", str(WORKERS), "--worker", str(worker),
               "--limit", "0"]
    for conector in (excluir or []):
        comando += ["--excluir-conector", conector]
    with log.open("a", encoding="utf-8", errors="replace") as fh:
        fh.write(f"\n=== relanzado por relanzar_la_cola.py "
                 f"{time.strftime('%Y-%m-%dT%H:%M:%S')} ===\n")
        fh.flush()
        proceso = subprocess.Popen(
            comando, cwd=str(RAIZ), stdout=fh, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return proceso.pid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanzar", action="store_true")
    ap.add_argument("--salida", default=str(SALIDA))
    args = ap.parse_args()
    salida = Path(args.salida)

    # Dos corridas programadas -09:54 y 10:44 del 2026-09-24- murieron por el
    # limite de cinco minutos de la tarea SIN escribir una linea, y a mano la
    # misma corrida tarda cinco segundos. Sin esta linea no se puede saber si
    # el proceso llego a arrancar o se colgo adentro de `plan()`.
    inicio = time.time()
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  arranca pid {os.getpid()}",
          flush=True)
    faltan, motivo, excluir = plan(salida, anotar=args.lanzar)
    print(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}  {motivo}  "
          f"[plan en {time.time() - inicio:.1f} s]")
    if not faltan:
        print("nada que lanzar")
        return 0
    print(f"a lanzar: workers {faltan}")
    if excluir:
        print(f"familias detenidas, no se tocan: {', '.join(excluir)}")
    if not args.lanzar:
        print("\n  DRY-RUN. Para lanzar de verdad: --lanzar")
        print("\ndatabase_writes: 0")
        return 0

    lanzados = {}
    for worker in faltan:
        try:
            lanzados[worker] = lanzar(worker, salida, excluir)
        except OSError as error:
            print(f"  worker {worker}: NO se pudo lanzar ({error})")
    with BITACORA.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "motivo": motivo, "lanzados": lanzados,
            "conectores_excluidos": excluir,
            "database_writes": 0}, ensure_ascii=False) + "\n")
    for worker, pid in lanzados.items():
        print(f"  worker {worker} -> pid {pid}")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

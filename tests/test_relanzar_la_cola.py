# -*- coding: utf-8 -*-
"""Relanzar la cola vale más que cualquier arreglo, y por eso hay que acotarlo.

El 75 % del tiempo la cola está parada: 366,0 h de 487,6 h, en 167 episodios.
Y **117 de esos 167 huecos no coinciden con ningún paro registrado** —suman
190,6 h, el 52 % de las horas paradas—. No son defectos: es la cola no
corriendo porque nadie la relanzó.

Pero un relanzador sin freno es peor que ninguno: relanzar sobre un paro
transversal sin diagnosticar produce certificaciones con código sospechado que
después hay que rehacer. Estos tests fijan las dos mitades.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from relanzar_la_cola import (decidir, paro_atendido,  # noqa: E402
                              paro_vigente, workers_vivos)


def ahora(desplazamiento: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S",
                         time.localtime(time.time() + desplazamiento))


def poner_paro(salida: Path, agencia="roomix:fios", cuando=None) -> None:
    (salida / "AGENCY_CERTIFICATION_STOP.json").write_text(json.dumps({
        "canonical_agency_id": agencia, "componente": "perdida_de_inventario",
        "radio": "FAMILIA", "cuando": cuando or ahora(-3600)}),
        encoding="utf-8")


def poner_diferida(salida: Path, agencia="roomix:fios", cuando=None) -> None:
    with (salida / "AGENCY_DEFECTS_DIFERIDOS.jsonl").open(
            "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"canonical_agency_id": agencia,
                             "componente": "perdida_de_inventario",
                             "radio": "FAMILIA",
                             "cuando": cuando or ahora()}) + "\n")


def test_sin_paro_y_sin_workers_se_lanzan_los_dos(tmp_path):
    faltan, motivo = decidir(tmp_path)
    assert faltan == [0, 1], motivo


def test_MUERDE_un_paro_sin_diagnosticar_NO_relanza(tmp_path):
    """La regla que no se relaja.

    Un paro transversal significa que sospechamos del código. Volver a correrlo
    produce certificaciones que habría que rehacer, y encima esconde el paro
    detrás de trabajo nuevo.
    """
    poner_paro(tmp_path)
    faltan, motivo = decidir(tmp_path)
    assert faltan == []
    assert "sin diagnosticar" in motivo


def test_un_paro_con_diferida_posterior_si_relanza(tmp_path):
    """La otra mitad: diagnosticado y firmado, la cola tiene que seguir.

    Sin esto el relanzador sería un freno permanente y volveríamos a las
    190,6 h de cola parada, que es el problema que vino a resolver.
    """
    poner_paro(tmp_path, cuando=ahora(-3600))
    poner_diferida(tmp_path, cuando=ahora(-60))
    faltan, _ = decidir(tmp_path)
    assert faltan == [0, 1]


def test_MUERDE_una_diferida_ANTERIOR_al_paro_no_alcanza(tmp_path):
    """El orden importa y es la parte fácil de equivocar.

    Si el paro es posterior a la diferida, trae información que esa diferida no
    pudo haber tenido en cuenta. Aceptarla convertiría «esta agencia ya se
    miró alguna vez» en «este paro está atendido», que no es lo mismo.
    """
    poner_diferida(tmp_path, cuando=ahora(-7200))
    poner_paro(tmp_path, cuando=ahora(-60))
    faltan, motivo = decidir(tmp_path)
    assert faltan == [], motivo


def test_una_diferida_de_OTRA_agencia_no_atiende_este_paro(tmp_path):
    poner_paro(tmp_path, agencia="roomix:fios", cuando=ahora(-3600))
    poner_diferida(tmp_path, agencia="roomix:otra", cuando=ahora())
    assert decidir(tmp_path)[0] == []


def test_un_paro_ilegible_no_relanza(tmp_path):
    """Ilegible es peor que ausente: no se relanza a ciegas."""
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").write_text(
        "{roto", encoding="utf-8")
    assert paro_vigente(tmp_path) is not None
    assert decidir(tmp_path)[0] == []


def test_MUERDE_nunca_mas_de_dos_workers(tmp_path, monkeypatch):
    """El límite duro del proyecto, comprobado acá además del cerrojo."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111})
    faltan, _ = modulo.decidir(tmp_path)
    assert faltan == [1]
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111, 1: 222})
    assert modulo.decidir(tmp_path)[0] == []


def test_un_cerrojo_ilegible_cuenta_como_ocupado(tmp_path):
    """Misma política que el runner, y por la misma razón.

    Borrar un cerrojo ilegible a ciegas es como se terminan pisando dos
    procesos el mismo checkpoint.
    """
    (tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock").write_text(
        "no es json", encoding="utf-8")
    assert 0 in workers_vivos(tmp_path)
    assert decidir(tmp_path)[0] == [1]


def test_MUERDE_un_cerrojo_de_un_pid_muerto_no_deja_la_cola_trabada(tmp_path):
    """El caso que se vio en vivo, y que el relanzador NO resolvia.

    Tras matar los workers a la fuerza quedaron sus cerrojos con latido
    reciente. `tomar_cerrojo` los dio por activos —su regla es latido fresco
    **o** pid vivo— y cada relanzamiento levantaba un proceso que moria en el
    acto con «Ya hay un runner activo (pid 13976...)». Iba a seguir asi **una
    hora entera**, que es `LATIDO_VENCIDO`.

    O sea: el relanzador no servia justamente para el caso que vino a
    resolver, que son los 117 huecos sin paro registrado.
    """
    import relanzar_la_cola as modulo
    ruta = tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock"
    ruta.write_text(json.dumps({"pid": 999999999,
                                "heartbeat_epoch": time.time()}),
                    encoding="utf-8")
    faltan, _ = modulo.decidir(tmp_path)
    assert faltan == [0, 1]
    assert not ruta.exists(), "el cerrojo huerfano tiene que quedar borrado"


def test_MUERDE_un_cerrojo_de_un_pid_VIVO_no_se_toca(tmp_path):
    """Borrar a ciegas es como se terminan pisando dos procesos.

    Ni siquiera con el latido vencido: la reutilizacion de pid por el sistema
    operativo empuja hacia el lado conservador, y ese es el correcto.
    """
    import os
    import relanzar_la_cola as modulo
    ruta = tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock"
    ruta.write_text(json.dumps({"pid": os.getpid(),
                                "heartbeat_epoch": time.time() - 99999}),
                    encoding="utf-8")
    faltan, _ = modulo.decidir(tmp_path)
    assert faltan == [1]
    assert ruta.exists()


def test_un_latido_fresco_cuenta_como_ocupado_aunque_el_pid_no_exista(tmp_path):
    """Se pregunta lo mismo que el runner va a responder.

    Con la regla vieja —solo el pid— el relanzador creia libre un puesto que
    el runner iba a rechazar, y levantaba un proceso condenado. Preguntar
    distinto que el que decide es no preguntar.

    Acá el cerrojo no se limpia porque se le pasa `aplicar=False`: se
    comprueba la clasificacion, no la limpieza.
    """
    import relanzar_la_cola as modulo
    ruta = tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock"
    ruta.write_text(json.dumps({"pid": 999999999,
                                "heartbeat_epoch": time.time()}),
                    encoding="utf-8")
    assert 0 in modulo.workers_vivos(tmp_path)


def test_un_cerrojo_ilegible_no_se_borra(tmp_path):
    """Ilegible no es lo mismo que huerfano: no se puede comprobar nada."""
    import relanzar_la_cola as modulo
    ruta = tmp_path / "AGENCY_CERTIFICATION_RUNNER.w0.lock"
    ruta.write_text("no es json", encoding="utf-8")
    assert modulo.limpiar_cerrojos_huerfanos(tmp_path, aplicar=True) == []
    assert ruta.exists()


def test_paro_atendido_no_se_confunde_con_fecha_invalida(tmp_path):
    poner_paro(tmp_path, cuando="no es una fecha")
    paro = paro_vigente(tmp_path)
    assert paro_atendido(tmp_path, paro) is False


def test_MUERDE_un_paro_con_precedente_se_difiere_solo_y_la_cola_sigue(tmp_path, monkeypatch):
    """Lo que hace que el relanzador sirva sin nadie mirando.

    Tres de cada cuatro paros pendientes comparten firma con uno ya
    diagnosticado. Sin esto, cada uno deja la cola detenida hasta que aparece
    una persona, y el relanzador queda de adorno.
    """
    import relanzar_la_cola as modulo
    poner_paro(tmp_path, agencia="roomix:b", cuando=ahora(-600))

    def falso_precedente(salida):
        poner_diferida(salida, agencia="roomix:b", cuando=ahora())
        return 1

    monkeypatch.setattr(modulo, "intentar_precedente", falso_precedente)
    faltan, _ = modulo.decidir(tmp_path)
    assert faltan == [0, 1]


def test_MUERDE_si_el_precedente_no_cubre_ESE_paro_no_se_relanza(tmp_path, monkeypatch):
    """Escribir diferidas de otras agencias no desbloquea este paro.

    Es el modo de falla peligroso de automatizar esto: que la sola existencia
    de trabajo automático se lea como que el paro está atendido.
    """
    import relanzar_la_cola as modulo
    poner_paro(tmp_path, agencia="roomix:b", cuando=ahora(-600))

    def falso_precedente(salida):
        poner_diferida(salida, agencia="roomix:otra", cuando=ahora())
        return 1

    monkeypatch.setattr(modulo, "intentar_precedente", falso_precedente)
    faltan, motivo = modulo.decidir(tmp_path)
    assert faltan == []
    assert "ninguna cubre este paro" in motivo


# ---------------------------------------------------------------------------
# Un paro FAMILIA detiene una familia, no la cola entera.
#
# El 2026-09-21 un paro FAMILIA sin firmar dejó los dos workers detenidos
# 34 horas. No relanzar sin diferida firmada estaba bien y sigue igual; lo
# desproporcionado era el alcance. Medido sobre todo el historial: de 613
# paros STOP, **596 son FAMILIA y 17 COMPARTIDO**, y sobre las 791 agencias de
# la cola `ready` detener `generico` deja corriendo el 53,7 %, `tokko` el
# 62,2 %, `wordpress` el 85,6 % y `wasi` el 98,5 %.
# ---------------------------------------------------------------------------

def poner_paro_de_familia(salida: Path, agencia="roomix:fios",
                          conector="tokko", radio="FAMILIA",
                          cuando=None) -> None:
    (salida / "AGENCY_CERTIFICATION_STOP.json").write_text(json.dumps({
        "canonical_agency_id": agencia, "componente": "perdida_de_inventario",
        "radio": radio, "conector": conector,
        "cuando": cuando or ahora(-3600)}), encoding="utf-8")


def test_MUERDE_un_paro_FAMILIA_deja_correr_a_las_demas_familias(tmp_path):
    """El caso de las 34 horas.

    La familia sospechada no se toca; las otras sí. Detener el 100 % de la
    cola por sospechar del 35 % del código es desproporcionado en el 97 % de
    los paros, que es la proporción medida de paros FAMILIA.
    """
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="tokko")
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == [0, 1], motivo
    assert excluir == ["tokko"]
    assert "tokko" in motivo


def test_MUERDE_un_paro_COMPARTIDO_sigue_deteniendo_todo(tmp_path):
    """La mitad que no se relaja.

    COMPARTIDO sospecha del código que todas las familias comparten: excluir
    una sola no acota nada y el resto correría con el código sospechado.
    """
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="tokko", radio="COMPARTIDO")
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == []
    assert excluir == []
    assert "sin diagnosticar" in motivo


def test_MUERDE_un_paro_FAMILIA_sin_conector_anotado_detiene_todo(tmp_path):
    """Sin saber QUÉ familia, «acotar» sería adivinar.

    Las banderas viejas no traen `conector`. Ante la duda, el comportamiento
    de antes: detener todo.
    """
    import relanzar_la_cola as modulo
    poner_paro(tmp_path)  # radio FAMILIA, sin conector
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == []
    assert excluir == []


def test_una_bandera_ilegible_no_se_acota_a_ninguna_familia(tmp_path):
    import relanzar_la_cola as modulo
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").write_text(
        "{roto", encoding="utf-8")
    assert modulo.plan(tmp_path)[0] == []


def test_MUERDE_la_familia_sigue_detenida_cuando_la_bandera_ya_no_esta(tmp_path):
    """El agujero que haría inútil todo esto.

    El runner BORRA la bandera al arrancar. Sin el libro, el primer
    relanzamiento consumiría el paro y el siguiente volvería a correr la
    familia sospechada como si nada: acotar el fail-closed se habría
    convertido en perderlo.
    """
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="wordpress")
    modulo.plan(tmp_path, anotar=True)
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").unlink()

    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == [0, 1]
    assert excluir == ["wordpress"], motivo


def test_la_familia_vuelve_a_correr_con_una_diferida_firmada_despues(tmp_path):
    """La otra mitad: firmado el diagnóstico, la familia se reincorpora."""
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, agencia="roomix:fios",
                          conector="wordpress", cuando=ahora(-3600))
    modulo.plan(tmp_path, anotar=True)
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").unlink()
    poner_diferida(tmp_path, agencia="roomix:fios", cuando=ahora(-60))

    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == [0, 1]
    assert excluir == [], motivo


def test_el_dry_run_no_anota_familias(tmp_path):
    """Decir qué haría no puede cambiar el estado."""
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="tokko")
    _, _, excluir = modulo.plan(tmp_path, anotar=False)
    assert excluir == ["tokko"]
    assert not (tmp_path / modulo.LIBRO_DE_FAMILIAS).exists()


def test_anotar_dos_veces_el_mismo_paro_no_duplica(tmp_path):
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="tokko")
    modulo.plan(tmp_path, anotar=True)
    modulo.plan(tmp_path, anotar=True)
    lineas = [l for l in (tmp_path / modulo.LIBRO_DE_FAMILIAS).read_text(
        encoding="utf-8").splitlines() if l.strip()]
    assert len(lineas) == 1


def test_MUERDE_la_exclusion_llega_al_comando_del_worker(tmp_path, monkeypatch):
    """Decidir excluir sin pasárselo al runner sería un arreglo de mentira."""
    import relanzar_la_cola as modulo
    capturado = {}

    class FalsoProceso:
        pid = 4242

    def falso_popen(comando, **kwargs):
        capturado["comando"] = comando
        return FalsoProceso()

    monkeypatch.setattr(modulo.subprocess, "Popen", falso_popen)
    modulo.lanzar(0, tmp_path, ["tokko", "wordpress"])
    comando = capturado["comando"]
    assert comando.count("--excluir-conector") == 2
    assert comando[comando.index("--excluir-conector") + 1] == "tokko"
    assert "wordpress" in comando


def test_sin_familias_detenidas_el_comando_queda_como_estaba(tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    capturado = {}

    class FalsoProceso:
        pid = 1

    monkeypatch.setattr(modulo.subprocess, "Popen",
                        lambda c, **k: (capturado.update(comando=c),
                                        FalsoProceso())[1])
    modulo.lanzar(1, tmp_path)
    assert "--excluir-conector" not in capturado["comando"]


def poner_triaje(salida: Path, agencia="roomix:fios",
                 componente="perdida_de_inventario", conector="generico",
                 cuando=None, radio="FAMILIA") -> None:
    with (salida / "AGENCY_DEFECT_QUEUE.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"canonical_agency_id": agencia,
                             "decision": "STOP",
                             "componente_sospechoso": componente,
                             "radio_estimado": radio,
                             "connector": conector,
                             "cuando": cuando}) + "\n")


def test_MUERDE_una_bandera_vieja_saca_el_conector_del_triaje(tmp_path):
    """El caso real del 2026-09-23 a las 12:29.

    Los dos workers estaban corriendo el código anterior, así que `alagna`
    paró con una bandera sin `conector`. El triaje SÍ lo había anotado —
    `generico`— en su propia entrada, con la misma hora exacta.
    """
    import relanzar_la_cola as modulo
    cuando_paro = ahora(-600)
    poner_paro(tmp_path, agencia="roomix:alagna", cuando=cuando_paro)
    poner_triaje(tmp_path, agencia="roomix:alagna", conector="generico",
                 cuando=cuando_paro)
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert excluir == ["generico"], motivo
    assert faltan == [0, 1]


def test_MUERDE_una_entrada_de_triaje_de_OTRO_paro_no_sirve(tmp_path):
    """Coincidir en agencia y componente no alcanza: la hora también.

    Si bastara con la agencia, un paro de hoy heredaría el conector de uno de
    hace dos semanas y se excluiría la familia equivocada —dejando correr la
    sospechada—, que es peor que no acotar nada.
    """
    import relanzar_la_cola as modulo
    poner_paro(tmp_path, agencia="roomix:alagna", cuando=ahora(-600))
    poner_triaje(tmp_path, agencia="roomix:alagna", conector="generico",
                 cuando=ahora(-99999))
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert excluir == []
    assert faltan == []


def test_sin_entrada_de_triaje_se_detiene_todo_como_antes(tmp_path):
    import relanzar_la_cola as modulo
    poner_paro(tmp_path, cuando=ahora(-600))
    assert modulo.plan(tmp_path)[0] == []


# ---------------------------------------------------------------------------
# Un paro sobre un código que ya cambió se vuelve a probar, no se espera.
#
# El 2026-09-23 `alagna` paró por «la fuente publica ciudad y la extracción
# falló». Se encontró la causa y se arregló, y el paro seguía esperando una
# firma sobre un defecto que ya no estaba, con 366 agencias detrás.
# ---------------------------------------------------------------------------

def poner_paro_con_huella(salida: Path, huella: str, radio="FAMILIA",
                          conector="generico", estrategia="generic/sitemap",
                          cuando=None) -> str:
    cuando = cuando or ahora(-3600)
    (salida / "AGENCY_CERTIFICATION_STOP.json").write_text(json.dumps({
        "canonical_agency_id": "roomix:alagna", "componente": "extraccion",
        "radio": radio, "conector": conector, "connector_strategy": estrategia,
        "strategy_fingerprint": huella, "cuando": cuando}), encoding="utf-8")
    return cuando


def test_MUERDE_un_paro_sobre_codigo_que_ya_cambio_libera_la_familia(
        tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-nueva")
    poner_paro_con_huella(tmp_path, "huella-vieja")
    faltan, motivo, excluir = modulo.plan(tmp_path, anotar=True)
    assert faltan == [0, 1]
    assert excluir == [], motivo
    assert "ya cambio" in motivo


def test_MUERDE_con_el_mismo_codigo_la_familia_sigue_detenida(tmp_path, monkeypatch):
    """La mitad que no se relaja: si el código es el mismo, el paro habla de
    algo que todavía existe y la familia espera su firma."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-igual")
    poner_paro_con_huella(tmp_path, "huella-igual")
    faltan, motivo, excluir = modulo.plan(tmp_path, anotar=True)
    assert excluir == ["generico"], motivo


def test_MUERDE_un_paro_COMPARTIDO_no_se_libera_porque_cambie_una_huella(
        tmp_path, monkeypatch):
    """COMPARTIDO sospecha del código común. La huella de una estrategia
    cambia también cuando cambia sólo su archivo propio: liberarlo por eso
    sería confundir cualquier cambio con el cambio que hacía falta."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-nueva")
    poner_paro_con_huella(tmp_path, "huella-vieja", radio="COMPARTIDO")
    faltan, motivo, _ = modulo.plan(tmp_path)
    assert faltan == []
    assert "sin diagnosticar" in motivo


def test_una_familia_anotada_se_libera_cuando_su_codigo_cambia(tmp_path, monkeypatch):
    """Lo mismo para el libro: la bandera ya no está, la anotación sí."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-igual")
    poner_paro_con_huella(tmp_path, "huella-igual")
    modulo.plan(tmp_path, anotar=True)
    (tmp_path / "AGENCY_CERTIFICATION_STOP.json").unlink()
    assert modulo.plan(tmp_path)[2] == ["generico"]

    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-nueva")
    assert modulo.plan(tmp_path)[2] == []


def test_sin_saber_que_codigo_se_sospechaba_no_se_libera_nada(tmp_path, monkeypatch):
    """Un paro viejo sin huella ni entrada de triaje: no hay con qué comparar,
    y ante la duda se queda detenido."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "cualquiera")
    poner_paro_de_familia(tmp_path, conector="tokko")
    assert modulo.plan(tmp_path)[2] == ["tokko"]


def test_la_huella_se_toma_del_triaje_cuando_la_bandera_no_la_trae(
        tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "huella-nueva")
    cuando = ahora(-600)
    poner_paro(tmp_path, agencia="roomix:alagna", cuando=cuando)
    with (tmp_path / "AGENCY_DEFECT_QUEUE.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"canonical_agency_id": "roomix:alagna",
                             "decision": "STOP",
                             "componente_sospechoso": "perdida_de_inventario",
                             "radio_estimado": "FAMILIA", "connector": "generico",
                             "connector_strategy": "generic/sitemap",
                             "strategy_fingerprint": "huella-vieja",
                             "cuando": cuando}) + "\n")
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert excluir == [] and faltan == [0, 1], motivo


# ---------------------------------------------------------------------------
# Liberar una familia tiene que llegar a los workers que ya están corriendo.
#
# El 2026-09-24 a las 10:29 se firmaron los paros de `tokko` y cambió el
# código de `wordpress`; los workers lanzados a las 10:04 las excluían y las
# iban a seguir excluyendo hasta terminar las otras 378 agencias. Días.
# ---------------------------------------------------------------------------

def bitacora_de_lanzamiento(salida: Path, pids: dict, excluidos: list) -> None:
    with (salida / "ERETZ_RELANZAMIENTOS.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"cuando": ahora(-1800), "lanzados": pids,
                             "conectores_excluidos": excluidos}) + "\n")


def test_MUERDE_una_familia_liberada_hace_parar_a_los_workers_que_la_excluyen(
        tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111, 1: 222})
    bitacora_de_lanzamiento(tmp_path, {"0": 111, "1": 222}, ["tokko", "wordpress"])
    faltan, motivo, excluir = modulo.plan(tmp_path, anotar=True)
    assert faltan == [] and excluir == []
    bandera = json.loads((tmp_path / "AGENCY_CERTIFICATION_STOP.json").read_text(
        encoding="utf-8"))
    assert bandera["radio"] == "OPERACION"
    assert bandera["liberadas"] == ["tokko", "wordpress"]
    assert "paran en la proxima agencia" in motivo


def test_MUERDE_el_pedido_de_relanzamiento_nunca_pisa_un_paro_de_verdad(
        tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    poner_paro_de_familia(tmp_path, conector="generico")
    antes = (tmp_path / "AGENCY_CERTIFICATION_STOP.json").read_text(encoding="utf-8")
    assert modulo.pedir_relanzamiento(tmp_path, {"tokko"}) is False
    assert (tmp_path / "AGENCY_CERTIFICATION_STOP.json").read_text(
        encoding="utf-8") == antes


def test_MUERDE_nuestra_propia_bandera_no_bloquea_el_relanzamiento(tmp_path):
    """Sin esto, el pedido de relanzar se leería como un paro sin firma y
    dejaría la cola parada: el arreglo produciría el problema que arregla."""
    import relanzar_la_cola as modulo
    modulo.pedir_relanzamiento(tmp_path, {"tokko"})
    faltan, motivo, excluir = modulo.plan(tmp_path)
    assert faltan == [0, 1], motivo
    assert excluir == []


def test_un_worker_lanzado_a_mano_no_se_toca(tmp_path, monkeypatch):
    """Sin saber con qué exclusiones corre, no hay nada que comparar."""
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 999, 1: 998})
    bitacora_de_lanzamiento(tmp_path, {"0": 111, "1": 222}, ["tokko"])
    modulo.plan(tmp_path, anotar=True)
    assert not (tmp_path / "AGENCY_CERTIFICATION_STOP.json").exists()


def test_si_la_familia_sigue_detenida_no_se_relanza_nada(tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111, 1: 222})
    monkeypatch.setattr(modulo, "huella_actual", lambda c, e: "igual")
    bitacora_de_lanzamiento(tmp_path, {"0": 111, "1": 222}, ["tokko"])
    poner_paro_con_huella(tmp_path, "igual", conector="tokko", estrategia="tokko")
    modulo.plan(tmp_path, anotar=True)
    bandera = json.loads((tmp_path / "AGENCY_CERTIFICATION_STOP.json").read_text(
        encoding="utf-8"))
    assert bandera["radio"] == "FAMILIA"  # la del paro, intacta


def test_el_dry_run_no_pide_relanzar(tmp_path, monkeypatch):
    import relanzar_la_cola as modulo
    monkeypatch.setattr(modulo, "workers_vivos", lambda s: {0: 111, 1: 222})
    bitacora_de_lanzamiento(tmp_path, {"0": 111, "1": 222}, ["tokko"])
    _, motivo, _ = modulo.plan(tmp_path, anotar=False)
    assert "tokko" in motivo
    assert not (tmp_path / "AGENCY_CERTIFICATION_STOP.json").exists()

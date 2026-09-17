"""Dos workers: reparto por host, cerrojo propio y un STOP que corta a los dos."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.run_agency_certification_queue import (BANDERA_DE_PARO,
                                                    WORKERS_MAXIMO,
                                                    hay_que_parar, host_de,
                                                    particion, pedir_paro,
                                                    sufijado, tomar_cerrojo)


def _catalogo(pares):
    """canonical_id -> official_url, con la forma completa que lee `resolve_identity`."""
    return {cid: {"resolution": {"official_domain": url,
                                 "resolution_status": "RESOLVED",
                                 "eretz_id": 1},
                  "live": {"validation_status": "VALIDATED"},
                  "source": {}, "platform": {}, "directory": {}}
            for cid, url in pares.items()}


def test_el_reparto_es_por_host_y_no_por_posicion():
    """La cortesía se le debe al sitio, y el limitador vive dentro de cada
    proceso. Si dos workers pudieran tocar el mismo host, le estaríamos
    pidiendo al doble del ritmo acordado sin que ninguno se entere."""
    catalogo = _catalogo({"a": "https://mismo.com.ar",
                          "b": "https://mismo.com.ar",
                          "c": "https://otro.com.ar"})
    cola = ["a", "b", "c"]
    w0 = particion(cola, catalogo, 0, 2)
    w1 = particion(cola, catalogo, 1, 2)

    # `a` y `b` comparten host: caen en el mismo worker, siempre.
    assert ("a" in w0) == ("b" in w0)
    assert set(w0) | set(w1) == set(cola)
    assert not set(w0) & set(w1)


def test_el_reparto_es_deterministico():
    """La misma cola y el mismo número de workers dan siempre el mismo
    reparto: reiniciar un worker no le cambia el trabajo."""
    catalogo = _catalogo({f"a{i}": f"https://sitio{i}.com.ar" for i in range(30)})
    cola = sorted(catalogo)
    assert particion(cola, catalogo, 0, 2) == particion(cola, catalogo, 0, 2)


def test_un_solo_worker_no_reparte_nada():
    catalogo = _catalogo({"a": "https://x.com.ar"})
    assert particion(["a"], catalogo, 0, 1) == ["a"]


def test_sin_url_legible_el_id_hace_de_host():
    """Repartir nunca puede tumbar la cola: sin url se usa el id, que al menos
    es estable."""
    # Un registro que no se puede leer reparte por id: sigue siendo
    # deterministico y sigue dejando cada fuente en un solo worker.
    assert host_de({}, "roomix:alfa") == "roomix:alfa"
    entrada = _catalogo({"roomix:alfa": "https://www.X.com/p"})["roomix:alfa"]
    assert host_de(entrada, "roomix:alfa") == "x.com"


def test_con_un_worker_los_archivos_son_los_de_siempre():
    """Las corridas viejas y sus artefactos siguen siendo los mismos archivos."""
    assert sufijado("A.lock", 0, 1) == "A.lock"
    assert sufijado("A.json", 1, 2) == "A.w1.json"


def test_cada_worker_toma_su_propio_cerrojo(tmp_path):
    """Dos procesos sobre el MISMO checkpoint se pisan; sobre checkpoints
    distintos, no."""
    uno = tomar_cerrojo(tmp_path, 0, 2)
    dos = tomar_cerrojo(tmp_path, 1, 2)
    assert uno != dos
    assert uno.exists() and dos.exists()

    # Pero el mismo worker dos veces sigue estando prohibido.
    with pytest.raises(SystemExit):
        tomar_cerrojo(tmp_path, 0, 2)


def test_un_stop_transversal_corta_a_los_dos(tmp_path):
    """Un defecto transversal lo es para los dos workers: si uno para y el otro
    sigue, el segundo certifica con el mismo código sospechado y hay que
    rehacer su trabajo igual."""
    assert hay_que_parar(tmp_path) is None

    pedir_paro(tmp_path, "roomix:ami propiedades", {
        "componente_sospechoso": "posible_perdida_de_inventario",
        "radio_estimado": "FAMILIA", "evidencia": "publica catalogo"})

    bandera = hay_que_parar(tmp_path)
    assert bandera["canonical_agency_id"] == "roomix:ami propiedades"
    assert bandera["radio"] == "FAMILIA"
    assert (tmp_path / BANDERA_DE_PARO).exists()


def test_expired_heartbeat_cannot_steal_a_live_process_checkpoint(tmp_path):
    from scripts.run_agency_certification_queue import LATIDO_VENCIDO
    lock = tomar_cerrojo(tmp_path)
    data = json.loads(lock.read_text(encoding='utf-8'))
    data['heartbeat_epoch'] = time.time() - LATIDO_VENCIDO - 1
    lock.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(SystemExit, match='runner activo'):
        tomar_cerrojo(tmp_path)
    assert json.loads(lock.read_text(encoding='utf-8'))['pid'] == os.getpid()


def test_actual_concurrent_processes_have_only_one_checkpoint_owner(tmp_path):
    code = '''
import sys,time
from pathlib import Path
from scripts.run_agency_certification_queue import tomar_cerrojo
try:
    tomar_cerrojo(Path(sys.argv[1]))
except SystemExit:
    raise SystemExit(23)
time.sleep(1)
'''
    env = dict(os.environ, PYTHON_DOTENV_DISABLED='1')
    processes = [subprocess.Popen([sys.executable, '-c', code, str(tmp_path)],
                                 cwd=Path(__file__).resolve().parents[1], env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                 for _ in range(2)]
    results = [p.communicate(timeout=30) for p in processes]
    assert sorted(p.returncode for p in processes) == [0, 23], results


def test_una_bandera_ilegible_igual_detiene(tmp_path):
    """Ante la duda, parar: seguir corriendo porque no se pudo leer el motivo
    es exactamente al revés de lo que hay que hacer."""
    (tmp_path / BANDERA_DE_PARO).write_text("{roto", encoding="utf-8")
    assert hay_que_parar(tmp_path) is not None


def test_no_se_permiten_mas_de_dos_workers():
    """Más de dos procesos contra sitios de inmobiliarias chicas deja de ser
    paralelismo y pasa a ser una molestia para ellas."""
    assert WORKERS_MAXIMO == 2


def test_el_latido_late_mientras_se_trabaja(tmp_path, monkeypatch):
    """Antes se refrescaba sólo al empezar cada inmobiliaria, y ese diseño se
    calibró cuando la corrida más larga de 74 medidas tardaba 927 s. Con
    presupuesto de 5.400 s por corrida y dos corridas por inmobiliaria, una
    sola puede tardar tres horas: `abriola propiedades` llevaba una hora y
    catorce minutos con el proceso VIVO y su cerrojo ya figuraba vencido.

    No es un problema de reporte: `tomar_cerrojo` usa el mismo umbral, así que
    un segundo runner habría dado por muerto a un worker vivo y tomado su
    partición.
    """
    import json
    import time as _t

    from scripts import run_agency_certification_queue as cola

    monkeypatch.setattr(cola, "INTERVALO_DE_LATIDO", 0.05)
    ruta = tmp_path / "x.lock"
    with cola.Latido(ruta, "roomix:alfa"):
        primero = json.loads(ruta.read_text(encoding="utf-8"))["heartbeat_epoch"]
        _t.sleep(0.2)
        segundo = json.loads(ruta.read_text(encoding="utf-8"))["heartbeat_epoch"]

    assert segundo > primero, "el latido no se refresco durante el trabajo"


def test_el_latido_se_detiene_al_terminar(tmp_path, monkeypatch):
    """Un hilo que sigue latiendo despues de terminar mantendría vivo el
    cerrojo de un trabajo que ya no existe."""
    import json
    import time as _t

    from scripts import run_agency_certification_queue as cola

    monkeypatch.setattr(cola, "INTERVALO_DE_LATIDO", 0.05)
    ruta = tmp_path / "x.lock"
    with cola.Latido(ruta, "roomix:alfa"):
        _t.sleep(0.1)
    ultimo = json.loads(ruta.read_text(encoding="utf-8"))["heartbeat_epoch"]
    _t.sleep(0.25)
    assert json.loads(ruta.read_text(encoding="utf-8"))["heartbeat_epoch"] == ultimo


def test_un_fallo_al_escribir_el_latido_no_tumba_la_corrida(tmp_path, monkeypatch):
    """El cerrojo vencido se detecta solo; perder un latido no puede costar la
    inmobiliaria que se estaba certificando."""
    from scripts import run_agency_certification_queue as cola

    monkeypatch.setattr(cola, "INTERVALO_DE_LATIDO", 0.05)
    llamadas = []

    def rompe(ruta, canonical_id):
        llamadas.append(1)
        if len(llamadas) > 1:
            raise OSError("disco lleno")

    monkeypatch.setattr(cola, "latir", rompe)
    import time as _t
    with cola.Latido(tmp_path / "x.lock", "roomix:alfa"):
        _t.sleep(0.2)
    assert len(llamadas) > 1

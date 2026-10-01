"""Activacion de la snapshot en el volumen de la API beta (P21): atomica y verificada."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.snapshot_sintetica import construir

RUTA = Path(__file__).resolve().parents[1] / "deploy" / "api-beta" / "activar_snapshot.py"
spec = importlib.util.spec_from_file_location("activar_snapshot", RUTA)
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def _sha(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _hay_enlaces_simbolicos() -> bool:
    """El volumen de la API beta es Linux (contenedor P21) y ahi el enlace existe.

    En Windows sin modo desarrollador `os.symlink` falla con WinError 1314: eso
    es el sistema de la PC de desarrollo, no un defecto de la activacion. Los
    tests que NO crean el enlace siguen corriendo en todos lados.
    """
    with tempfile.TemporaryDirectory() as carpeta:
        try:
            os.symlink("destino", os.path.join(carpeta, "enlace"))
        except (OSError, NotImplementedError):
            return False
    return True


requiere_enlaces = pytest.mark.skipif(
    not _hay_enlaces_simbolicos(),
    reason="sin permiso para crear enlaces simbolicos (Windows sin modo desarrollador); "
           "la activacion corre en el volumen Linux de la API beta")


@pytest.fixture()
def volumen(tmp_path):
    (tmp_path / "incoming").mkdir()
    return tmp_path


def _subir(volumen: Path, nombre: str, marca: str | None = None, sintetica: bool = False) -> tuple[Path, str]:
    ruta = volumen / "incoming" / f"{nombre}.sqlite3"
    construir(ruta)
    con = sqlite3.connect(ruta)
    if marca:
        con.execute("insert into snapshot_meta values ('ensayo', ?)", (marca,))
    if not sintetica:
        # Se ensaya como si fuera real: la marca sintetica se saca.
        con.execute("delete from snapshot_meta where clave = 'sintetica'")
    con.commit()
    con.close()
    return ruta, _sha(ruta)


def test_un_sha_distinto_no_toca_nada(volumen):
    ruta, _ = _subir(volumen, "a")
    with pytest.raises(A.Rechazada, match="sha256 distinto"):
        A.activar(volumen, ruta, "0" * 64)
    assert ruta.exists() and not (volumen / A.ENLACE).exists()


def test_la_sintetica_no_se_activa_sin_permiso(volumen):
    ruta, sha = _subir(volumen, "a", sintetica=True)
    with pytest.raises(A.Rechazada, match="SINTETICA"):
        A.activar(volumen, ruta, sha)
    assert not (volumen / A.ENLACE).exists()


def test_una_base_que_no_es_snapshot_se_rechaza(volumen):
    ruta = volumen / "incoming" / "otra.sqlite3"
    sqlite3.connect(ruta).execute("create table x (y)").connection.close()
    with pytest.raises(A.Rechazada, match="no es una snapshot"):
        A.activar(volumen, ruta, _sha(ruta))


@requiere_enlaces
def test_activar_apunta_el_enlace_y_registra(volumen):
    ruta, sha = _subir(volumen, "a")
    evento = A.activar(volumen, ruta, sha)
    enlace = volumen / A.ENLACE
    assert enlace.is_symlink() and enlace.resolve().name == f"{sha}.sqlite3"
    assert evento["accion"] == "ACTIVAR" and evento["anterior"] is None and evento["propiedades"] > 0
    assert not ruta.exists()
    historial = [json.loads(x) for x in (volumen / "HISTORIAL.jsonl").read_text().splitlines()]
    assert historial[-1]["sha256"] == sha


@requiere_enlaces
def test_rollback_vuelve_a_la_anterior_y_otro_rollback_a_la_previa(volumen):
    shas = []
    for nombre in ("a", "b", "c"):
        ruta, sha = _subir(volumen, nombre, marca=nombre)
        A.activar(volumen, ruta, sha)
        shas.append(sha)
    assert (volumen / A.ENLACE).resolve().name == f"{shas[2]}.sqlite3"
    assert A.rollback(volumen)["sha256"] == shas[1]
    assert A.rollback(volumen)["sha256"] == shas[0]
    with pytest.raises(A.Rechazada, match="primera"):
        A.rollback(volumen)


@requiere_enlaces
def test_la_misma_snapshot_dos_veces_se_rechaza(volumen):
    ruta, sha = _subir(volumen, "a")
    A.activar(volumen, ruta, sha)
    ruta2, sha2 = _subir(volumen, "a")
    assert sha2 == sha
    with pytest.raises(A.Rechazada, match="ya es la activa"):
        A.activar(volumen, ruta2, sha2)


@requiere_enlaces
def test_poda_conserva_la_activa_y_la_anterior(volumen):
    shas = []
    for nombre in ("a", "b", "c", "d", "e"):
        ruta, sha = _subir(volumen, nombre, marca=nombre)
        A.activar(volumen, ruta, sha)
        shas.append(sha)
    guardadas = {p.name for p in (volumen / "snapshots").glob("*.sqlite3")}
    assert len(guardadas) == A.CONSERVAR
    assert {f"{shas[-1]}.sqlite3", f"{shas[-2]}.sqlite3"} <= guardadas


def test_un_archivo_real_en_lugar_del_enlace_no_se_pisa(volumen):
    (volumen / A.ENLACE).write_bytes(b"no soy un enlace")
    ruta, sha = _subir(volumen, "a")
    with pytest.raises(A.Rechazada, match="no un enlace"):
        A.activar(volumen, ruta, sha)
    assert (volumen / A.ENLACE).read_bytes() == b"no soy un enlace"


def test_la_cli_informa_rechazo_con_codigo_1(volumen, capsys):
    assert A.main(["--volumen", str(volumen), "rollback"]) == 1
    assert json.loads(capsys.readouterr().out)["resultado"] == "RECHAZADA"
    assert A.main(["--volumen", str(volumen), "estado"]) == 0

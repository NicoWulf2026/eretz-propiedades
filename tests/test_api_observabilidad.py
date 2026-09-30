"""Observabilidad de la API beta: un evento por pedido, sin valores de busqueda."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from scripts.snapshot_sintetica import construir


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    from api import v2
    ruta = tmp_path / "snap.sqlite3"
    construir(ruta)
    monkeypatch.setattr(v2, "SNAPSHOT", ruta)
    from api.main import app
    return TestClient(app, raise_server_exceptions=False)


def _eventos(capsys):
    return [json.loads(x) for x in capsys.readouterr().out.splitlines()
            if x.startswith("{") and '"http_request"' in x]


def test_un_evento_por_pedido_con_la_ruta_y_sin_los_valores(cliente, capsys):
    r = cliente.get("/v2/buscar", params={"q": "casa con pileta en palermo", "limit": 3})
    assert r.status_code == 200
    (evento,) = _eventos(capsys)
    assert evento["route"] == "/v2/buscar" and evento["status"] == 200 and evento["outcome"] == "ok"
    assert evento["paramKeys"] == ["limit", "q"] and evento["paramCount"] == 2
    assert "pileta" not in json.dumps(evento)
    assert evento["requestId"] == r.headers["x-request-id"]


def test_la_ruta_es_la_plantilla_no_el_id(cliente, capsys):
    cliente.get("/v2/propiedades/no-existe")
    (evento,) = _eventos(capsys)
    assert evento["route"] == "/v2/propiedades/{propiedad_id}"
    assert evento["outcome"] == "client_error" and evento["level"] == "warn"


def test_respeta_un_request_id_razonable_y_descarta_uno_raro(cliente, capsys):
    assert cliente.get("/healthz", headers={"x-request-id": "abc12345-de"}).headers["x-request-id"] == "abc12345-de"
    raro = cliente.get("/healthz", headers={"x-request-id": "<script>"}).headers["x-request-id"]
    assert raro != "<script>" and len(raro) == 36


def test_encabezados_de_seguridad_y_noindex(cliente):
    h = cliente.get("/healthz").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-robots-tag"] == "noindex, nofollow"
    assert h["referrer-policy"] == "no-referrer"


def test_una_excepcion_responde_500_limpio_y_queda_en_el_log(cliente, capsys, monkeypatch):
    from api import v2

    def rota(*a, **k):
        raise RuntimeError("detalle interno con /ruta/secreta")

    monkeypatch.setattr(v2, "conexion", rota)
    r = cliente.get("/v2/stats")
    assert r.status_code == 500
    assert "secreta" not in r.text and r.json()["requestId"] == r.headers["x-request-id"]
    (evento,) = _eventos(capsys)
    assert evento["outcome"] == "server_error" and evento["errorName"] == "RuntimeError"
    assert "secreta" not in json.dumps(evento)

"""P7: busqueda paga con tope duro de USD 10 por mes, costo declarado y registro."""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from scripts import search_provider as sp


@pytest.fixture()
def libro(tmp_path, monkeypatch):
    ruta = tmp_path / "ERETZ_SEARCH_SPEND.jsonl"
    monkeypatch.setenv(sp.ENV_LIBRO, str(ruta))
    monkeypatch.delenv(sp.ENV_TOPE, raising=False)
    for nombre in ("BRAVE", "TAVILY", "SERPER", "FALSO"):
        monkeypatch.delenv(sp.PREFIJO_COSTO + nombre, raising=False)
    monkeypatch.setattr(sp, "_GASTO_DEL_PROCESO", {})
    monkeypatch.setattr(sp, "_CONSULTAS_DEL_PROCESO", {})
    return ruta


def _lineas(ruta):
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines()] if ruta.exists() else []


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _brave_que_responde(monkeypatch, *fallos):
    """urlopen falso: primero los HTTPError de `fallos`, despues una respuesta valida."""
    pendientes = list(fallos)
    llamadas = []

    def urlopen(req, timeout=0):
        llamadas.append(req.full_url)
        if pendientes:
            raise urllib.error.HTTPError(req.full_url, pendientes.pop(0), "x", {}, None)
        return _Respuesta(json.dumps({"web": {"results": [{"url": "https://a.com.ar"}]}}).encode())

    monkeypatch.setattr(sp.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(sp.time, "sleep", lambda s: None)
    monkeypatch.setenv(sp.Brave.ENV, "clave-de-prueba")
    return llamadas


def test_sin_costo_declarado_no_se_consulta(libro, monkeypatch):
    llamadas = _brave_que_responde(monkeypatch)
    with pytest.raises(sp.CostoNoDeclarado):
        sp.Brave(pausa=0).buscar("inmobiliaria alfa")
    assert llamadas == [] and _lineas(libro) == []


def test_cada_pedido_se_anota_antes_de_salir_y_sin_el_texto(libro, monkeypatch):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "0.005")
    llamadas = _brave_que_responde(monkeypatch, 503)   # un reintento
    res = sp.Brave(pausa=0).buscar("inmobiliaria alfa rosario")
    assert [r.url for r in res] == ["https://a.com.ar"]
    registros = _lineas(libro)
    assert len(llamadas) == 2 and len(registros) == 2   # el reintento tambien cuenta
    assert all(r["tipo"] == "consulta" and r["costo_usd"] == 0.005 for r in registros)
    assert "alfa" not in libro.read_text(encoding="utf-8")


def test_el_tope_corta_antes_del_pedido_que_lo_pasaria(libro, monkeypatch):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "4")
    llamadas = _brave_que_responde(monkeypatch)
    buscador = sp.Brave(pausa=0)
    buscador.buscar("uno")
    buscador.buscar("dos")                       # USD 8 gastados
    with pytest.raises(sp.PresupuestoAgotado, match="tope mensual de USD 10.00"):
        buscador.buscar("tres")                  # 8 + 4 > 10
    assert len(llamadas) == 2
    assert sp.gastado_en_el_mes() == 8


def test_el_presupuesto_agotado_corta_el_lote_como_un_proveedor_sin_creditos():
    assert issubclass(sp.PresupuestoAgotado, sp.ProveedorAgotado)
    assert issubclass(sp.CostoNoDeclarado, sp.ProveedorAgotado)


@pytest.mark.parametrize("pedido,efectivo", [("50", 10.0), ("1.5", 1.5), ("abc", 10.0), ("-3", 0.0)])
def test_la_variable_solo_puede_bajar_el_tope(libro, monkeypatch, pedido, efectivo):
    monkeypatch.setenv(sp.ENV_TOPE, pedido)
    assert sp.tope_mensual() == efectivo


def test_el_gasto_de_otro_mes_no_cuenta(libro, monkeypatch):
    libro.write_text(json.dumps({"tipo": "consulta", "mes": "2000-01", "costo_usd": 9.99}) + "\n",
                     encoding="utf-8")
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "5")
    _brave_que_responde(monkeypatch)
    sp.Brave(pausa=0).buscar("uno")
    assert sp.gastado_en_el_mes() == 5


def test_un_nivel_gratuito_declarado_en_cero_se_registra_igual(libro, monkeypatch):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "0")
    _brave_que_responde(monkeypatch)
    sp.Brave(pausa=0).buscar("uno")
    assert _lineas(libro)[-1]["costo_usd"] == 0


def test_la_cache_no_gasta(libro, monkeypatch, tmp_path):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "1")
    _brave_que_responde(monkeypatch)
    buscador = sp.ConCache(sp.Brave(pausa=0), tmp_path / "cache.jsonl")
    buscador.buscar("Inmobiliaria  Alfa")
    buscador.buscar("inmobiliaria alfa")
    assert buscador.hits == 1 and sp.gastado_en_el_mes() == 1


def test_la_corrida_registra_proveedor_costo_agencias_y_utiles(libro, monkeypatch):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "0.25")
    _brave_que_responde(monkeypatch)
    buscador = sp.Brave(pausa=0)
    buscador.buscar("uno")
    buscador.buscar("dos")
    corrida = sp.registrar_corrida("brave", agencias_buscadas=2, resultados_utiles=1)
    assert corrida == {**corrida, "tipo": "corrida", "proveedor": "brave", "consultas_pagadas": 2,
                       "costo_usd": 0.5, "agencias_buscadas": 2, "resultados_utiles": 1,
                       "tope_mensual_usd": 10.0, "gastado_en_el_mes_usd": 0.5}
    assert _lineas(libro)[-1]["tipo"] == "corrida"


def test_un_libro_bloqueado_no_deja_gastar(libro, monkeypatch):
    monkeypatch.setenv(sp.PREFIJO_COSTO + "BRAVE", "0.01")
    llamadas = _brave_que_responde(monkeypatch)
    libro.parent.mkdir(parents=True, exist_ok=True)
    (libro.parent / (libro.name + ".lock")).write_text("", encoding="utf-8")
    monkeypatch.setattr(sp._Cerrojo, "__init__",
                        lambda self, ruta, espera=0.1: setattr(self, "ruta", ruta.with_name(ruta.name + ".lock"))
                        or setattr(self, "espera", 0.1))
    with pytest.raises(sp.PresupuestoAgotado, match="bloqueado"):
        sp.Brave(pausa=0).buscar("uno")
    assert llamadas == []


def test_los_cinco_proveedores_pagos_cobran_antes_de_cada_pedido():
    """Ningun proveedor que hable HTTP puede saltear el cobro (fuente, no ejecucion)."""
    from pathlib import Path
    raiz = Path(sp.__file__).resolve().parent
    fuente = (raiz / "search_provider.py").read_text(encoding="utf-8")
    extra = (raiz / "providers_extra.py").read_text(encoding="utf-8")
    assert fuente.count("urllib.request.urlopen(req") == fuente.count("cobrar(self.nombre, consulta)") == 3
    assert extra.count("urllib.request.urlopen(req") == extra.count("sp.cobrar(self.nombre, consulta)") == 2

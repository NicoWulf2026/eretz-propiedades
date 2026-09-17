import json

from api import main as api


def test_public_api_uses_eretz_brand():
    """La marca, no el payload entero: congelar el diccionario completo hacia
    fallar el test por agregar un campo, que es lo contrario de lo que este
    test cuida."""
    assert api.app.title == "ERETZ Propiedades API"
    raiz = api.root()
    assert raiz["status"] == "ok"
    assert raiz["proyecto"] == "ERETZ Propiedades API"
    assert "InmoCapital" not in json.dumps(raiz)
    assert "Roomix" not in json.dumps(raiz)


def test_property_filters_only_reference_live_schema_columns(monkeypatch):
    captured = {}

    def fake_get(params):
        captured.update(params)
        return []

    monkeypatch.setattr(api, "supabase_get", fake_get)
    api.listar_propiedades(
        operacion=None,
        tipo=None,
        ciudad=None,
        barrio="Centro",
        precio_min=None,
        precio_max=None,
        moneda=None,
        ambientes=None,
        dormitorios=None,
        limit=20,
        offset=0,
    )

    assert captured["barrio"] == "ilike.*Centro*"
    assert "barrio_normalizado" not in captured
    assert captured["order"] == "updated_at.desc.nullslast,id.desc"
    assert "calidad_score" not in captured["order"]


def test_stats_use_exact_counts_instead_of_capped_row_downloads(monkeypatch):
    calls = []

    def fake_count(filters=None):
        calls.append(filters or {})
        return len(calls) * 10

    monkeypatch.setattr(api, "supabase_count", fake_count)

    assert api.estadisticas() == {
        "total_propiedades": 10,
        "alquileres": 20,
        "ventas": 30,
        "con_coordenadas": 40,
    }
    assert calls == [
        {},
        {"operacion": "eq.alquiler"},
        {"operacion": "eq.venta"},
        {"latitud": "not.is.null", "longitud": "not.is.null"},
    ]


def test_exact_count_parses_postgrest_content_range(monkeypatch):
    class Response:
        headers = {"Content-Range": "0-0/257475"}

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(api.requests, "get", lambda *args, **kwargs: Response())

    assert api.supabase_count({"operacion": "eq.venta"}) == 257475

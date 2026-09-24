"""API v2: la forma del contrato y las dos reglas que la API hace cumplir."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))


def _documento(**cambios):
    base = {
        "id": "h1",
        "source_url": "https://alfa.com.ar/p/1",
        "agency_id": "roomix:alfa",
        "titulo": "Casa en Venta",
        "descripcion": "Muy linda",
        "operacion": "venta",
        "tipo_propiedad": "casa",
        "precio": 100000.0,
        "moneda": "USD",
        "ambientes": 4,
        "dormitorios": 3,
        "banos": 2,
        "superficie_total": None,
        "superficie_cubierta": 120.0,
        "imagenes": [],
        "latitud": -31.4,
        "longitud": -64.2,
        "geo": {
            "localidad": {"nombre": None, "id": None, "procedencia": "UNKNOWN"},
            "municipio": {"nombre": "La Calera"},
            "departamento": {"nombre": "Colon"},
            "provincia": {"nombre": "Cordoba"},
            "barrio": {"nombre": "Chacra del Norte"},
            "area_busqueda": {
                "nivel": "MUNICIPIO",
                "nombre": "La Calera",
                "id": None,
                "origen": "municipio",
            },
            "estado": None,
        },
        "alcances": ["FICHA", "LISTADO", "AREA_BUSQUEDA", "FILTRO_PRECIO"],
    }
    base.update(cambios)
    return base


@pytest.fixture()
def v2(tmp_path, monkeypatch):
    ruta = tmp_path / "snap.sqlite3"
    con = sqlite3.connect(ruta)
    con.executescript("""
        create table propiedades (
            id text primary key, agency_id text not null, source_url text not null,
            titulo text, descripcion text, operacion text, tipo_propiedad text,
            precio real, moneda text, ambientes integer, dormitorios integer,
            banos integer, superficie_total real, superficie_cubierta real,
            imagenes_n integer not null default 0, latitud real, longitud real,
            localidad text, localidad_id text, municipio text, departamento text,
            provincia text, barrio text, area_nivel text not null,
            area_nombre text, geo_estado text, alcances text not null,
            documento text not null);
        create virtual table busqueda using fts5(
            id unindexed, titulo, descripcion, barrio, area_nombre,
            tokenize = "unicode61 remove_diacritics 2");
    """)
    filas = [
        (_documento(), "MUNICIPIO", "La Calera", None),
        (
            _documento(
                id="h2",
                titulo="Depto en Alquiler",
                operacion="alquiler",
                precio=None,
                moneda=None,
                geo=dict(
                    _documento()["geo"],
                    localidad={
                        "nombre": "Rosario",
                        "id": "82084010",
                        "procedencia": "CANONICAL_NORMALIZED",
                    },
                    area_busqueda={
                        "nivel": "LOCALIDAD",
                        "nombre": "Rosario",
                        "id": "82084010",
                        "origen": "localidad",
                    },
                ),
            ),
            "LOCALIDAD",
            "Rosario",
            None,
        ),
        (
            _documento(
                id="h3",
                titulo="Lote",
                operacion=None,
                precio=None,
                moneda=None,
                latitud=None,
                longitud=None,
                geo=dict(_documento()["geo"], estado="GEO_CONFLICT"),
            ),
            "MUNICIPIO",
            "La Calera",
            "GEO_CONFLICT",
        ),
    ]
    for doc, nivel, nombre, estado in filas:
        con.execute(
            "insert into propiedades values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "?,?,?,?,?,?,?,?,?,?,?)",
            (
                doc["id"],
                doc["agency_id"],
                doc["source_url"],
                doc["titulo"],
                doc["descripcion"],
                doc["operacion"],
                doc["tipo_propiedad"],
                doc["precio"],
                doc["moneda"],
                doc["ambientes"],
                doc["dormitorios"],
                doc["banos"],
                doc["superficie_total"],
                doc["superficie_cubierta"],
                len(doc["imagenes"]),
                doc["latitud"],
                doc["longitud"],
                doc["geo"]["localidad"]["nombre"],
                doc["geo"]["localidad"].get("id"),
                doc["geo"]["municipio"]["nombre"],
                doc["geo"]["departamento"]["nombre"],
                doc["geo"]["provincia"]["nombre"],
                doc["geo"]["barrio"]["nombre"],
                nivel,
                nombre,
                estado,
                json.dumps(doc["alcances"]),
                json.dumps(doc, ensure_ascii=False),
            ),
        )
        con.execute(
            "insert into busqueda values (?,?,?,?,?)",
            (
                doc["id"],
                doc["titulo"] or "",
                doc["descripcion"] or "",
                doc["geo"]["barrio"]["nombre"] or "",
                nombre or "",
            ),
        )
    con.commit()
    con.close()

    from api import v2 as modulo

    monkeypatch.setattr(modulo, "SNAPSHOT", ruta)
    return modulo


def test_una_propiedad_incompleta_se_devuelve_igual(v2):
    """Lo que falta le quita ALCANCE, no existencia. El frontend esconde el
    filtro, nunca la propiedad."""
    r = v2.listar(
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        barrio=None,
        agencia=None,
        ambientes=None,
        dormitorios=None,
        limit=24,
        offset=0,
    )
    assert r["total"] == 3
    sin_precio = [p for p in r["data"] if p["precio"] is None]
    assert sin_precio, "las propiedades sin precio tienen que seguir viniendo"


def test_mapa_combina_fts_viewport_y_filtros(v2):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(v2.router)
    response = TestClient(app).get('/v2/propiedades/mapa', params={
        'q': 'Casa', 'north': -30, 'south': -32, 'east': -63,
        'west': -65, 'operacion': 'venta', 'limit': 1,
    })
    assert response.status_code == 200
    result = response.json()
    assert result['total_matches'] == result['viewport_matches'] == 1
    assert result['returned_points'] == 1
    assert result['truncated'] is False
    assert result['data'][0]['id'] == 'h1'
    assert result['data'][0]['titulo'] == 'Casa en Venta'


def test_el_area_siempre_viaja_con_su_nivel(v2):
    """Un municipio devuelto sin decir que es un municipio se lee como una
    ciudad, y ahí es donde se inventa geografía."""
    r = v2.listar(
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        barrio=None,
        agencia=None,
        ambientes=None,
        dormitorios=None,
        limit=24,
        offset=0,
    )
    for propiedad in r["data"]:
        assert propiedad["geo"]["area_busqueda"]["nivel"]


def test_el_municipio_no_se_devuelve_como_localidad(v2):
    p = v2.detalle("h1")
    assert p["geo"]["localidad"]["nombre"] is None
    assert p["geo"]["localidad"]["procedencia"] == "UNKNOWN"
    assert p["geo"]["municipio"]["nombre"] == "La Calera"


def test_las_areas_se_ordenan_de_mas_precisa_a_menos(v2):
    """Si `PROVINCIA` compitiera de igual a igual con `LOCALIDAD`, la
    sugerencia más útil quedaría sepultada."""
    r = v2.areas(q=None, limit=10)
    niveles = [a["nivel"] for a in r["data"]]
    assert niveles.index("LOCALIDAD") < niveles.index("MUNICIPIO")


def test_el_filtro_por_precio_exige_moneda(v2):
    """Un precio sin moneda no es un precio: filtrar por rango sin exigirla
    mezclaría 90.000 dólares con 90.000 pesos."""
    r = v2.listar(
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=1,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        barrio=None,
        agencia=None,
        ambientes=None,
        dormitorios=None,
        limit=24,
        offset=0,
    )
    assert all(p["moneda"] for p in r["data"])


def test_la_busqueda_no_depende_de_la_localidad(v2):
    """Sólo el 16,5 % la tiene: exigirla dejaría la búsqueda vacía para cinco
    de cada seis propiedades."""
    r = v2.buscar(q="Chacra", operacion=None, tipo=None, limit=24, offset=0)
    assert r["total"] >= 1


def test_la_paginacion_no_repite_ni_saltea(v2):
    """Sin un desempate por id, dos páginas consecutivas pueden repetir o
    saltear una propiedad."""
    a = v2.listar(
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        barrio=None,
        agencia=None,
        ambientes=None,
        dormitorios=None,
        limit=2,
        offset=0,
    )
    b = v2.listar(
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        barrio=None,
        agencia=None,
        ambientes=None,
        dormitorios=None,
        limit=2,
        offset=2,
    )
    ids = [p["id"] for p in a["data"]] + [p["id"] for p in b["data"]]
    assert len(ids) == len(set(ids)) == 3


def test_el_conflicto_geografico_llega_al_frontend(v2):
    """Si el frontend no sabe que hay conflicto, lo muestra como un dato
    normal."""
    assert v2.detalle("h3")["geo"]["estado"] == "GEO_CONFLICT"
    assert v2.stats()["en_conflicto_geografico"] == 1


def test_los_barrios_se_declaran_no_canonizados(v2):
    """GeoRef no cataloga barrios, y decirlo es parte del contrato."""
    r = v2.barrios(q=None, limit=10)
    assert r["canonizado"] is False


def test_los_filtros_dicen_cuantas_faltan(v2):
    """Un filtro que no dice cuántas propiedades hay detrás invita a elegir una
    combinación vacía; y los que faltan importan tanto como los que están."""
    r = v2.filtros()
    assert r["sin_dato"]["operacion"] == 1
    assert r["sin_dato"]["localidad"] == 2


def test_una_propiedad_inexistente_es_404(v2):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        v2.detalle("no-existe")
    assert e.value.status_code == 404


def test_sin_snapshot_la_api_lo_dice(tmp_path, monkeypatch):
    """Un 503 explicando qué falta es mejor que un stacktrace."""
    from fastapi import HTTPException

    from api import v2 as modulo

    monkeypatch.setattr(modulo, "SNAPSHOT", tmp_path / "no-existe.sqlite3")
    with pytest.raises(HTTPException) as e:
        modulo.stats()
    assert e.value.status_code == 503


def test_la_busqueda_ignora_acentos_y_puntuacion(v2):
    """ "cordoba" y "Córdoba" son la misma búsqueda, y un guión en la caja no
    puede hacer fallar la consulta con un error de sintaxis de FTS."""
    from api.v2 import _termino

    assert _termino("San Martin - 450") == '"San" "Martin" "450"'
    assert _termino("") == '""'
    assert _termino("***") == '""'

    con_acento = v2.buscar(q="Cordoba", operacion=None, tipo=None, limit=5, offset=0)["total"]
    sin_acento = v2.buscar(q="córdoba", operacion=None, tipo=None, limit=5, offset=0)["total"]
    assert con_acento == sin_acento


def test_una_snapshot_vieja_lo_dice_en_vez_de_romperse(tmp_path, monkeypatch):
    """Sin el índice de texto la búsqueda fallaba con un `no such table` que no
    le dice a nadie qué hacer."""
    import sqlite3 as s

    from fastapi import HTTPException

    ruta = tmp_path / "vieja.sqlite3"
    con = s.connect(ruta)
    con.execute(
        "create table propiedades (id text primary key, "
        "operacion text, tipo_propiedad text, documento text)"
    )
    con.commit()
    con.close()

    from api import v2 as modulo

    monkeypatch.setattr(modulo, "SNAPSHOT", ruta)
    with pytest.raises(HTTPException) as e:
        modulo.buscar(q="algo", operacion=None, tipo=None, limit=5, offset=0)
    assert e.value.status_code == 503
    assert "api_snapshot" in e.value.detail


def _buscar_combinado(v2, **changes):
    args = dict(
        q=None,
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        municipio=None,
        departamento=None,
        provincia=None,
        barrio=None,
        ambientes=None,
        dormitorios=None,
        banos=None,
        superficie_min=None,
        sort="relevance",
        limit=24,
        offset=0,
    )
    args.update(changes)
    return v2.buscar(**args)


def test_explorer_combina_texto_filtros_geografia_y_total(v2):
    result = _buscar_combinado(
        v2,
        q="Casa",
        operacion="venta",
        tipo="casa",
        area="La Calera",
        nivel="MUNICIPIO",
        dormitorios=3,
        banos=2,
        superficie_min=100,
    )
    assert result["total"] == 1
    assert result["data"][0]["id"] == "h1"
    assert result["sort"] == "relevance"


def test_explorer_ordena_precio_sin_convertirlo_en_ranking(v2):
    asc = _buscar_combinado(v2, moneda="USD", sort="price_asc")
    desc = _buscar_combinado(v2, moneda="USD", sort="price_desc")
    assert [item["precio"] for item in asc["data"]] == [100000.0]
    assert [item["precio"] for item in desc["data"]] == [100000.0]
    assert asc["ranking"] is None and desc["ranking"] is None


def test_explorer_rechaza_sort_y_geografia_invalidos(v2):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        _buscar_combinado(v2, sort="inventado")
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        _buscar_combinado(v2, area="Rosario", nivel="CIUDAD")
    assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        _buscar_combinado(v2, sort="price_asc")
    assert error.value.status_code == 400


def test_mapa_aplica_viewport_filtros_y_declara_truncamiento(v2):
    args = dict(
        north=-30.0,
        south=-33.0,
        east=-63.0,
        west=-65.0,
        q=None,
        operacion=None,
        tipo=None,
        moneda=None,
        precio_min=None,
        precio_max=None,
        area=None,
        nivel=None,
        localidad=None,
        municipio=None,
        departamento=None,
        provincia=None,
        barrio=None,
        ambientes=None,
        dormitorios=None,
        banos=None,
        superficie_min=None,
    )
    result = v2.mapa(**args, limit=1)
    assert result["total_matches"] == 3
    assert result["viewport_matches"] == 2
    assert result["returned_points"] == 1
    assert result["truncated"] is True
    assert result["data"][0]["id"] == "h1"
    empty = v2.mapa(**dict(args, north=-40, south=-41), limit=1)
    assert empty["viewport_matches"] == 0 and empty["data"] == []


def test_mapa_recorta_la_caja_a_argentina_y_el_indice_no_cambia_la_respuesta(v2):
    """La caja se recorta en vez de sumar `latitud between -90 and -21`, y el
    indice por coordenadas es solo un camino mas rapido: misma respuesta."""
    base = dict(q=None, operacion=None, tipo=None, moneda=None, precio_min=None,
                precio_max=None, area=None, nivel=None, localidad=None,
                municipio=None, departamento=None, provincia=None, barrio=None,
                ambientes=None, dormitorios=None, banos=None, superficie_min=None,
                limit=10)
    argentina = dict(base, north=-21.0, south=-56.0, east=-53.0, west=-74.0)
    # Una caja que se sale de Argentina por los cuatro lados cuenta lo mismo.
    mundo = dict(base, north=80.0, south=-89.0, east=170.0, west=-170.0)
    # Y una que queda entera fuera no cuenta nada, aunque recortada se invierta.
    afuera = dict(base, north=10.0, south=0.0, east=-40.0, west=-50.0)
    sin_indice = [v2.mapa(**a) for a in (argentina, mundo, afuera)]
    assert sin_indice[0] == sin_indice[1]
    assert sin_indice[0]["viewport_matches"] == 2
    assert sin_indice[2]["viewport_matches"] == 0 and sin_indice[2]["data"] == []

    con = sqlite3.connect(v2.SNAPSHOT)
    con.execute("create index ix_coord_geo on propiedades(latitud, longitud, geo_estado)")
    con.commit()
    con.close()
    con_indice = [v2.mapa(**a) for a in (argentina, mundo, afuera)]
    assert con_indice == sin_indice
    filtrado = dict(argentina, operacion="venta")
    assert v2.mapa(**filtrado)["viewport_matches"] == 1


def test_detail_resuelve_alias_publico_sin_cambiar_id_canonico(v2):
    con = sqlite3.connect(v2.SNAPSHOT)
    con.execute("create table property_aliases(alias text primary key, property_id text not null)")
    con.execute("insert into property_aliases values ('123', 'h1')")
    con.commit()
    con.close()
    assert v2.detalle("123")["id"] == "h1"


def test_agencia_publica_no_inventa_contacto(v2):
    result = v2.agencia_detalle("roomix:alfa")["data"]
    assert result["name"] == "alfa"
    assert result["contact"] == {
        "status": "UNAVAILABLE",
        "phone": None,
        "whatsapp": None,
        "email": None,
    }


def test_batch_preserva_orden_deduplica_y_declara_faltantes(v2):
    result = v2.propiedades_batch(v2.BatchRequest(ids=["h2", "missing", "h1", "h2"]))
    assert [item["id"] for item in result["items"]] == ["h2", "h1"]
    assert result["requested_ids"] == ["h2", "missing", "h1"]
    assert result["missing_ids"] == ["missing"]


def test_openapi_formaliza_cutovers_y_valida_respuestas(v2):
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    search = client.get("/v2/buscar", params={"q": "Casa", "limit": 2})
    assert search.status_code == 200
    assert search.json()["sort"] == "relevance"
    map_response = client.get(
        "/v2/propiedades/mapa",
        params={"north": -30, "south": -33, "east": -63, "west": -65, "limit": 1},
    )
    assert map_response.status_code == 200
    batch = client.post("/v2/propiedades/batch", json={"ids": ["h2", "missing"]})
    assert batch.status_code == 200
    assert batch.json()["missing_ids"] == ["missing"]

    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/v2/buscar"]["get"]["responses"]["200"]["content"]
    assert schema["paths"]["/v2/propiedades/mapa"]["get"]["responses"]["200"]["content"]
    assert schema["paths"]["/v2/propiedades/batch"]["post"]["responses"]["200"]["content"]


def test_batch_rechaza_payload_sobredimensionado(v2):
    from fastapi.testclient import TestClient
    from api.main import app

    response = TestClient(app).post(
        "/v2/propiedades/batch", json={"ids": [f"id-{index}" for index in range(101)]}
    )
    assert response.status_code == 422


def test_http_rechaza_sort_bounds_y_combinaciones_abusivas(v2):
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    assert client.get("/v2/buscar", params={"sort": "random"}).status_code == 422
    assert client.get("/v2/buscar", params={"sort": "price_asc"}).status_code == 400
    assert client.get("/v2/buscar", params={"nivel": "CIUDAD"}).status_code == 400
    assert (
        client.get(
            "/v2/propiedades/mapa", params={"north": 91, "south": -35, "east": -58, "west": -59}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/v2/propiedades/mapa", params={"north": -35, "south": -34, "east": -58, "west": -59}
        ).status_code
        == 400
    )
def test_detected_conflict_is_withheld_even_from_an_old_snapshot(v2):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    con = sqlite3.connect(v2.SNAPSHOT)
    con.execute("update propiedades set latitud=-31.4, longitud=-64.2 where id='h3'")
    con.commit()
    con.close()
    app = FastAPI()
    app.include_router(v2.router)
    client = TestClient(app)
    for doc in (client.get('/v2/propiedades/h3').json(),
                client.post('/v2/propiedades/batch', json={'ids': ['h3']}).json()['items'][0]):
        assert doc['geo']['estado'] == 'GEO_CONFLICT'
        assert doc['geo']['municipio']['nombre'] is None
        assert doc['geo']['area_busqueda']['nivel'] == 'SIN_AREA'
        assert doc['geo']['area_busqueda']['id'] is None
        assert doc['geo']['area_busqueda']['origen'] == 'sin_area'
        assert doc['latitud'] is None
    result = client.get('/v2/propiedades/mapa', params={
        'north': -30, 'south': -33, 'east': -63, 'west': -65}).json()
    assert result['total_matches'] == 3  # property still exists in the list
    assert 'h3' not in [p['id'] for p in result['data']]
    assert 'h3' not in [p['id'] for p in _buscar_combinado(v2, municipio='La Calera')['data']]


def test_relevance_pages_are_slices_of_one_fixed_ranked_window(v2):
    # Low-quality early rows followed by higher-quality rows used to move
    # previously returned results when offset increased the candidate set.
    con = sqlite3.connect(v2.SNAPSHOT)
    for n in range(1, 31):
        doc = _documento(id=f'a{n:03}', descripcion='Casa' if n > 15 else None,
                         imagenes=['https://official.test/photo.jpg'] if n > 15 else [])
        con.execute("insert into propiedades select ?,agency_id,source_url,titulo,?,operacion,"
                    "tipo_propiedad,precio,moneda,ambientes,dormitorios,banos,superficie_total,"
                    "superficie_cubierta,?,latitud,longitud,localidad,localidad_id,municipio,"
                    "departamento,provincia,barrio,area_nivel,area_nombre,geo_estado,alcances,? "
                    "from propiedades where id='h1'", (doc['id'], doc['descripcion'],
                     len(doc['imagenes']), json.dumps(doc)))
    con.commit()
    con.close()
    combined = _buscar_combinado(v2, limit=10)['data']
    first = _buscar_combinado(v2, limit=5)['data']
    second = _buscar_combinado(v2, limit=5, offset=5)['data']
    assert [p['id'] for p in first + second] == [p['id'] for p in combined]

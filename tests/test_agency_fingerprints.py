"""Qué invalida una certificación y qué no.

Un cambio que no puede alterar la evidencia no debe invalidar una
certificación de propiedades. Antes sí lo hacía: `shared/runner` y
`shared/certifier` se hasheaban enteros, así que tocar `main()` —203 líneas de
CLI y logging— invalidaba las 44 certificaciones. Pasó tres veces.
"""
from __future__ import annotations

import ast
from pathlib import Path

from scripts.agency_fingerprints import (CERTIFIER_OPERACIONALES, RAIZ,
                                         RUNNER_OPERACIONALES,
                                         _archivo_sin_operativas,
                                         fingerprint_components,
                                         strategy_fingerprint)

RUNNER = RAIZ / "scripts" / "run_rollout.py"
CERTIFIER = RAIZ / "scripts" / "agency_certifier.py"


def _con_linea_en(ruta: Path, funcion: str, sentencia: str) -> str:
    """Devuelve el fuente con una sentencia extra dentro de `funcion`."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    encontrada = False
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == funcion:
            nodo.body.insert(0, ast.parse(sentencia).body[0])
            encontrada = True
            break
    assert encontrada, f"no existe {funcion} en {ruta.name}"
    return ast.unparse(arbol)


# ---------------------------------------------------------------- A
def test_tocar_el_cli_del_runner_no_invalida_ninguna_certificacion():
    """`main()` sólo orquesta: argparse, logging y escritura del resumen.

    Tres commits reales —3f2ebe015, 64b17caac y 4d49c8427— tocaron únicamente
    `main`, `universo` o `version_del_codigo` y provocaron un reset global de
    la cola sin poder cambiar el resultado de ninguna certificación.
    """
    original = RUNNER.read_text(encoding="utf-8")
    con_logging = _con_linea_en(RUNNER, "main", "print('traza nueva')")
    assert (_archivo_sin_operativas(original, RUNNER_OPERACIONALES)
            == _archivo_sin_operativas(con_logging, RUNNER_OPERACIONALES))


def test_tocar_el_cli_del_certificador_tampoco_invalida():
    original = CERTIFIER.read_text(encoding="utf-8")
    con_logging = _con_linea_en(CERTIFIER, "main", "print('traza nueva')")
    assert (_archivo_sin_operativas(original, CERTIFIER_OPERACIONALES)
            == _archivo_sin_operativas(con_logging, CERTIFIER_OPERACIONALES))


def test_escribir_reportes_y_rollups_es_presentacion():
    """`update_rollups` y `find_canonical` arman el resumen para leerlo; no
    participan de la decisión de certificar."""
    original = CERTIFIER.read_text(encoding="utf-8")
    for funcion in ("update_rollups", "find_canonical"):
        mutado = _con_linea_en(CERTIFIER, funcion, "_ = 1")
        assert (_archivo_sin_operativas(original, CERTIFIER_OPERACIONALES)
                == _archivo_sin_operativas(mutado, CERTIFIER_OPERACIONALES)), funcion


# ---------------------------------------------------------------- B
def test_tocar_el_bucle_de_detalles_si_invalida():
    """`_procesar_con` decide qué propiedades se obtienen y se guardan.

    El fix del reintento diferido cambió ahí: 209 detalles pasaron a 210. Eso
    cambia el inventario certificado y debe invalidar.
    """
    original = RUNNER.read_text(encoding="utf-8")
    mutado = _con_linea_en(RUNNER, "_procesar_con", "_ = 1")
    assert (_archivo_sin_operativas(original, RUNNER_OPERACIONALES)
            != _archivo_sin_operativas(mutado, RUNNER_OPERACIONALES))


def test_tocar_la_senal_de_fuente_o_la_comparacion_de_corridas_si_invalida():
    """`source_signals` decide si la fuente publica un campo y `compare_runs`
    decide la idempotencia entre RUN1 y RUN2."""
    original = CERTIFIER.read_text(encoding="utf-8")
    for funcion in ("source_signals", "compare_runs", "certification_status",
                    "field_audit", "classify_field"):
        mutado = _con_linea_en(CERTIFIER, funcion, "_ = 1")
        assert (_archivo_sin_operativas(original, CERTIFIER_OPERACIONALES)
                != _archivo_sin_operativas(mutado, CERTIFIER_OPERACIONALES)), funcion


def test_las_constantes_y_las_clases_siguen_dentro():
    """`PRESUPUESTO_POR_FUENTE`, `SOURCE_SIGNALS` y `AuditDownloader` deciden
    resultados. La exclusión es una lista corta de funciones, no un criterio
    automático: `source_signals` la usa la CLASE `AuditDownloader`, y un
    análisis de alcance ingenuo la habría dejado fuera de la huella."""
    runner = _archivo_sin_operativas(RUNNER.read_text(encoding="utf-8"),
                                     RUNNER_OPERACIONALES).decode()
    certifier = _archivo_sin_operativas(CERTIFIER.read_text(encoding="utf-8"),
                                        CERTIFIER_OPERACIONALES).decode()
    assert "PRESUPUESTO_POR_FUENTE" in runner
    assert "_procesar_con" in runner
    assert "AuditDownloader" in certifier
    assert "source_signals" in certifier
    assert "SOURCE_SIGNALS" in certifier


# ---------------------------------------------------------------- C
def test_una_estrategia_no_arrastra_a_las_demas():
    """Cambiar MAPAPROP no puede invalidar sitemap ni PHP legacy: sus métodos
    no se tocan y ninguna otra familia los ejecuta."""
    mapaprop = fingerprint_components("generico", "generic/mapaprop")
    sitemap = fingerprint_components("generico", "generic/sitemap")

    assert mapaprop["strategy/generic/mapaprop"] != sitemap["strategy/generic/sitemap"]
    # Lo compartido es idéntico: si cambiara algo compartido, cambian las dos.
    for comun in ("shared/base", "shared/runner", "shared/certifier",
                  "shared/geografia", "generic/common"):
        assert mapaprop[comun] == sitemap[comun]
    # Y el componente de una no contiene los métodos de la otra.
    assert "_catalogo_mapaprop" not in sitemap["strategy/generic/sitemap"].decode()
    assert "_catalogo_mapaprop" in mapaprop["strategy/generic/mapaprop"].decode()


def test_el_metodo_de_una_estrategia_solo_vive_en_su_componente():
    propios = {
        "generic/mapaprop": "_catalogo_mapaprop",
        "generic/xintel": "_normalizar_xintel",
        "generic/bitrix_landing": "_catalogo_bitrix_landing",
        "generic/wordpress_category": "_catalogo_wordpress_por_categoria",
    }
    for estrategia, metodo in propios.items():
        for otra in propios:
            componentes = fingerprint_components("generico", otra)
            dump = componentes[f"strategy/{otra}"].decode()
            assert (metodo in dump) == (otra == estrategia), (estrategia, otra, metodo)


# ---------------------------------------------------------------- D
def test_un_connector_propio_no_entra_en_la_huella_de_otro():
    """Tocar Tokko no puede invalidar Wasi, WordPress ni Century21."""
    familias = ("tokko", "wasi", "wordpress", "century21")
    for familia in familias:
        componentes = fingerprint_components(familia, familia)
        assert f"connector/{familia}" in componentes
        for otra in familias:
            if otra != familia:
                assert f"connector/{otra}" not in componentes
        # Un connector propio tampoco arrastra los componentes de generico.
        assert "generic/common" not in componentes


def test_las_familias_tienen_huellas_distintas_entre_si():
    familias = ["tokko", "wasi", "wordpress", "century21"]
    huellas = {f: strategy_fingerprint(f, f) for f in familias}
    assert len(set(huellas.values())) == len(familias), huellas


def test_la_huella_es_determinista():
    for connector, estrategia in (("generico", "generic/html_catalog"),
                                  ("tokko", "tokko")):
        assert (strategy_fingerprint(connector, estrategia)
                == strategy_fingerprint(connector, estrategia))


def test_el_esquema_de_huella_esta_versionado():
    """Cambiar QUE se hashea cambia todas las huellas. La version lo declara, y
    el preflight la usa para no dar amnistia a los defectos abiertos: redefinir
    la huella no corrige ninguno."""
    from scripts.agency_fingerprints import (FINGERPRINT_SCHEMA_VERSION,
                                             strategy_fingerprint_v1)
    assert FINGERPRINT_SCHEMA_VERSION == 5
    # El algoritmo viejo sigue disponible para juzgar paquetes del esquema 1.
    assert (strategy_fingerprint_v1("tokko", "tokko")
            != strategy_fingerprint("tokko", "tokko"))


def test_shared_geographic_integrity_is_in_every_connector_fingerprint():
    for connector in ('generico', 'tokko', 'wasi', 'wordpress', 'century21'):
        strategy = 'generic/html_catalog' if connector == 'generico' else connector
        component = fingerprint_components(connector, strategy)['shared/geo_reference']
        assert b'verified_rows' in component and b'entity_ids' in component


# ---- el modelo semantico por defecto (esquema 3) --------------------------

def test_discover_y_fetch_listing_estan_dentro_de_la_huella():
    """Son el corazón semántico del connector: `discover` elige la estrategia y
    `fetch_listing` decide qué se enumera. Estuvieron FUERA de toda huella, así
    que cambiar qué inventario se encuentra no invalidaba nada.
    """
    from scripts.agency_fingerprints import _comunes
    metodos, _ = _comunes()
    for critico in ("discover", "fetch_listing", "_es_tabla_estructurada",
                    "_catalogos_enlazados", "_total_declarado_en", "normalize"):
        assert critico in metodos, critico


def test_ningun_metodo_del_connector_queda_fuera_de_la_huella():
    """La regresión que impide que esto vuelva a pasar.

    El modelo viejo era una lista blanca y dejaba doce métodos afuera en
    silencio. Una lista blanca falla del lado peligroso: olvidarse de agregar
    uno deja certificaciones falsamente vigentes. Ahora es semántico por
    defecto, y olvidarse cuesta una recertificación de más.
    """
    import ast
    from scripts.agency_fingerprints import (GENERIC_STRATEGY_METHODS, ROOT,
                                             _comunes)
    arbol = ast.parse((ROOT / "connectors" / "generico.py").read_text(encoding="utf-8"))
    clase = next(n for n in arbol.body
                 if isinstance(n, ast.ClassDef) and n.name == "GenericoConnector")
    todos = {n.name for n in clase.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    comunes, _ = _comunes()
    de_estrategias = set().union(*GENERIC_STRATEGY_METHODS.values())
    huerfanos = todos - comunes - de_estrategias
    assert huerfanos == set(), f"metodos fuera de toda huella: {sorted(huerfanos)}"


def test_las_estrategias_nuevas_no_arrastran_a_las_viejas():
    """Un detector propio de una estrategia sólo invalida a la suya."""
    from scripts.agency_fingerprints import fingerprint_components
    tokko_proxy = fingerprint_components("generico", "generic/tokko_proxy")
    categoria = fingerprint_components("generico", "generic/category_html")
    assert tokko_proxy["strategy/generic/tokko_proxy"] != categoria["strategy/generic/category_html"]
    # y comparten el mismo tronco comun
    assert tokko_proxy["generic/common"] == categoria["generic/common"]


def test_las_familias_propias_no_se_invalidan_por_generico():
    """Tokko, Wasi, WordPress y Century21 tienen su propio archivo: el camino
    no-generico retorna antes de mirar `generico.py`."""
    from scripts.agency_fingerprints import fingerprint_components
    for connector in ("tokko", "wasi", "wordpress", "century21"):
        componentes = fingerprint_components(connector, connector)
        assert "generic/common" not in componentes
        assert f"connector/{connector}" in componentes


def test_shared_image_policy_is_fingerprinted_for_every_family():
    for connector, strategy in [('generico', 'generic/html_catalog'), ('tokko', 'tokko')]:
        components = fingerprint_components(connector, strategy)
        assert b'is_known_page_asset' in components['shared/image_quality']

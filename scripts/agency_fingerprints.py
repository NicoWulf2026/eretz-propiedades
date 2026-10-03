"""Fingerprints por mecanismo realmente usado por una certificacion.

La huella historica del connector generico cubria todo ``generico.py``. Un
cambio aislado en MAPAPROP invalidaba PHP legacy, sitemap y HTML aunque esas
fuentes no ejecutaran esa estrategia. Este modulo conserva las dependencias
transversales y separa solamente familias observadas y certificadas.
"""
from __future__ import annotations

import ast
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
RAIZ = ROOT  # alias en castellano para los tests
FINGERPRINT_SCHEMA_VERSION = 5

PUBLICATION_STRATEGIES = {
    "EMPTY_CATALOG_HTML": "generic/empty_catalog",
    "LISTADO_HTML": "generic/html_catalog",
    "MAPAPROP_HTML": "generic/mapaprop",
    "PHP_AJAX_SEARCH": "generic/php_ajax_search",
    "PORTAL_OFFSET_HTML": "generic/portal_offset",
    "QUERY_CATALOG_HTML": "generic/php_query_catalog",
    "SIN_INVENTARIO": "generic/no_inventory",
    "SITEMAP": "generic/sitemap",
    "WORDPRESS_CATEGORY_CATALOG": "generic/wordpress_category",
    "XINTEL_API": "generic/xintel",
    "BUSCADORPROP_JSON": "generic/buscadorprop_json",
    "BITRIX_LANDING_CARDS": "generic/bitrix_landing",
    "TOKKO_PROXY_JSON": "generic/tokko_proxy",
    "CATEGORY_HTML_CATALOG": "generic/category_html",
    # CRM TIV Tecnogestion: total declarado del buscador + POST de scroll infinito.
    "TIV_BUSQUEDA": "generic/tiv_busqueda",
}

# `generic/common` es SEMANTICO POR DEFECTO: todo metodo de la clase que no
# pertenezca a una estrategia concreta entra ahi, incluidos los que se agreguen
# despues.
#
# Antes era una lista blanca, y por eso dejaba afuera en silencio a doce
# metodos, entre ellos `discover` -que elige la estrategia-, `fetch_listing`
# -que decide que se enumera- y `_es_tabla_estructurada`, que decide que se
# extrae. Cambiar cualquiera de los tres cambia el inventario certificado y no
# invalidaba nada.
#
# La lista blanca falla del lado peligroso: olvidarse de agregar un metodo deja
# certificaciones falsamente vigentes. Al invertir el default, olvidarse cuesta
# una recertificacion de mas, que es el error barato.
METODOS_OPERATIVOS = frozenset()  # nada operativo en este connector, por ahora
GENERIC_STRATEGY_METHODS = {
    # `_fichas_en` NO es de ninguna estrategia: `normalize` la llama sin
    # condicion -la pagina titulada con el nombre del sitio que enlaza 8 o mas
    # fichas es un listado, `_es_pagina_contenedora`- para TODA ficha generica
    # y para las de WordPress que lee generico. Estaba repartida en seis
    # estrategias y faltaba en las demas: cambiarla dejaba vigentes TIV,
    # categoria, query, MAPAPROP y WordPress (ventana final, 03-10).
    "generic/empty_catalog": set(),
    "generic/html_catalog": {
        "_patron_de", "_patron_raiz_local", "_patron_catalogo_numerico",
    },
    "generic/mapaprop": {
        "_catalogo_mapaprop", "_fichas_mapaprop_en", "_detalle_mapaprop",
    },
    "generic/php_ajax_search": {
        "_catalogo_php_ajax", "_normalizar_php_ajax",
    },
    "generic/portal_offset": {
        "_patron_portal_offset_local", "_portal_catalogo",
    },
    "generic/php_query_catalog": {
        "_fichas_query_en", "_patron_catalogo_numerico",
    },
    "generic/no_inventory": set(),
    "generic/sitemap": {"_patron_de"},
    "generic/wordpress_category": {"_catalogo_wordpress_por_categoria"},
    # `_normalizar_xintel` tampoco: `normalize` la elige tambien por el
    # CONTENIDO de la ficha (`_es_ficha_xintel(html)`), no solo por la clave
    # del listado, asi que puede correr en cualquier agencia generica.
    "generic/xintel": set(),
    "generic/buscadorprop_json": {"_patron_de"},
    # Todo lo propio de la estrategia vive en estos tres metodos: cambiarlos
    # no invalida ninguna otra familia, y ninguna otra los usa.
    "generic/bitrix_landing": {
        "_catalogo_bitrix_landing", "_nodo_landing", "_clave_landing",
        "_normalizar_bitrix_landing",
    },
    # Un frontend propio que sirve el catalogo Tokko desde su mismo host.
    "generic/tokko_proxy": {
        "_catalogo_tokko_proxy", "_normalizar_tokko_proxy",
    },
    # Catalogo estatico repartido en paginas de categoria.
    "generic/category_html": {
        "_rutas_de_categoria", "_catalogo_por_categorias",
        "_catalogo_de_selector",
    },
    # `_ubicacion_tiv` solo corre en la ruta TIV (normalize lo condiciona a
    # `tiv_zonas`, que pone unicamente el fetch_listing de TIV): es propio de
    # esta estrategia y no invalida al resto de generico.
    "generic/tiv_busqueda": {"_catalogo_tiv", "_ubicacion_tiv"},
}

FUNCIONES_OPERATIVAS = frozenset()
GENERIC_STRATEGY_FUNCTIONS = {
    "generic/wordpress_category": {
        "_sin_variantes_wordpress", "_imagenes_galeria_wordpress"},
    # `_entero`, `_decimal` y `_coordenada` son comunes: tambien las usa
    # `_normalizar_strapi`, que no es de ninguna estrategia.
    # Solo las usa `_ubicacion_tiv`, que solo corre en la ruta TIV.
    "generic/tiv_busqueda": {"_calle_tiv", "_es_caba"},
}

# Lo que `normalize` -codigo comun- ejecuta de una estrategia, y la clave del
# crudo que lo condiciona. Esa clave la pone solo el listado de esa estrategia,
# asi que la llamada no corre en las demas ni en WordPress, que le pasa su
# crudo a `normalize`. `tests/test_huella_dependencias_cruzadas.py` exige que
# todo miembro de estrategia alcanzable desde `normalize` este aca y se llame
# dentro de un `if` con su clave: lo que corre sin condicion es comun.
LLAMADAS_CONDICIONADAS = {
    "_normalizar_php_ajax": "php_ajax",
    "_normalizar_bitrix_landing": "bitrix_card",
    "_normalizar_tokko_proxy": "tokko_objeto",
    "_detalle_mapaprop": "mapaprop_catalog",
    "_imagenes_galeria_wordpress": "wordpress_category_catalog",
    "_sin_variantes_wordpress": "wordpress_category_catalog",
    "_ubicacion_tiv": "tiv_zonas",
}

# Los conectores cuyas fichas el certificador audita con sus PROPIAS senales de
# fuente (`field_audit`). Los demas -WordPress, Century21- se auditan con
# `source_signals`, que lee la ficha con funciones de `generico.py`.
CONECTORES_CON_SENALES_PROPIAS = frozenset({"tokko", "wasi"})


# Lo unico que sale de la huella de certificacion. Son funciones que no pueden
# alterar la evidencia: CLI, orquestacion, lectura/escritura de reportes y
# metadatos. Todo lo demas del archivo -constantes, clases, imports y cualquier
# funcion nueva- se queda adentro por defecto.
#
# El default importa. Se probo derivar esta lista automaticamente por alcance
# desde `certify()` y el resultado marcaba `source_signals` como inalcanzable:
# la usa la CLASE `AuditDownloader`, no una llamada directa. Excluirla habria
# sacado de la huella la funcion que decide `source_provided`, y ese es el fallo
# grave -haria pasar por vigentes certificaciones que no lo son-. Por eso la
# regla es semantico por defecto y operativo solo con prueba explicita.
#
# Antes estos dos archivos se hasheaban ENTEROS. Tocar `main()` -203 lineas de
# argparse y logging en el runner- invalidaba las 44 certificaciones. Paso tres
# veces: 3f2ebe015, 64b17caac y 4d49c8427 no cambiaron nada que pudiera alterar
# un resultado y resetearon la cola entera.
RUNNER_OPERACIONALES = frozenset({
    "main",                 # CLI, orquestacion y escritura del resumen
    "universo",             # elige QUE fuentes correr, no que se extrae
    "procesar",             # envoltorio del modo standalone
    "leer_jsonl",           # lectura de artefactos
    "version_del_codigo",   # metadato: se escribe en el paquete, no decide nada
})
CERTIFIER_OPERACIONALES = frozenset({
    "main",                 # CLI y orquestacion
    "update_rollups",       # rollup de presentacion
    "find_canonical",       # busqueda para el reporte
    "read_jsonl",           # lectura de artefactos
    "append_jsonl",         # escritura de bitacora
})



@lru_cache(maxsize=1)
def _miembros_de_generico() -> tuple[frozenset[str], frozenset[str]]:
    """Que metodos y funciones existen hoy en `generico.py`.

    Se lee el archivo en vez de mantener una lista: una lista se desactualiza
    en silencio y el costo de ese olvido es una certificacion falsamente
    vigente.
    """
    arbol = ast.parse((ROOT / "connectors" / "generico.py").read_text(encoding="utf-8"))
    funciones = {n.name for n in arbol.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    metodos: set[str] = set()
    for nodo in arbol.body:
        if isinstance(nodo, ast.ClassDef) and nodo.name == "GenericoConnector":
            metodos = {n.name for n in nodo.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return frozenset(metodos), frozenset(funciones)


def _comunes() -> tuple[set[str], set[str]]:
    metodos, funciones = _miembros_de_generico()
    de_estrategias: set[str] = set()
    for grupo in GENERIC_STRATEGY_METHODS.values():
        de_estrategias |= grupo
    de_estrategias_f: set[str] = set()
    for grupo in GENERIC_STRATEGY_FUNCTIONS.values():
        de_estrategias_f |= grupo
    return (set(metodos) - de_estrategias - METODOS_OPERATIVOS,
            set(funciones) - de_estrategias_f - FUNCIONES_OPERATIVAS)


def strategy_for(connector: str, publication_mechanism: str | None) -> str:
    if connector != "generico":
        return connector
    return PUBLICATION_STRATEGIES.get(
        str(publication_mechanism or ""), "generic/unknown")


def _semantic_file(path: Path) -> bytes:
    # Cacheado por archivo y por su estado en disco. Cada huella de estrategia
    # recalculaba los mismos quince archivos compartidos: ~5 s por par
    # conector/estrategia, medido con cProfile el 2026-09-24. El relanzador
    # mira varias familias por pasada y con la maquina cargada eso lo acercaba
    # al limite de cinco minutos de su tarea; dos corridas murieron ahi sin
    # escribir una linea. `mtime_ns` y tamano cambian con cualquier edicion,
    # asi que el valor es el mismo que sin cache: solo se deja de recalcular.
    estado = path.stat()
    return _semantic_file_cacheado(str(path), estado.st_mtime_ns, estado.st_size)


@lru_cache(maxsize=64)
def _semantic_file_cacheado(ruta: str, _mtime_ns: int, _tamano: int) -> bytes:
    tree = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    return ast.dump(tree, include_attributes=False).encode()


@lru_cache(maxsize=16)
def _archivo_sin_operativas(fuente: str, excluidas: frozenset[str]) -> bytes:
    """El archivo entero menos las funciones operativas nombradas.

    Se excluye por lista corta y explicita, nunca por heuristica: lo que no
    esta en la lista pertenece a la huella, incluidas las clases, las
    constantes y cualquier funcion que se agregue despues.
    """
    arbol = ast.parse(fuente)
    arbol.body = [nodo for nodo in arbol.body
                  if not (isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and nodo.name in excluidas)]
    return ast.dump(arbol, include_attributes=False).encode()


def _selected_nodes(path: Path, class_name: str,
                    methods: Iterable[str], functions: Iterable[str],
                    module_assigns: bool = False,
                    constants: Iterable[str] = ()) -> bytes:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted_methods = set(methods)
    wanted_functions = set(functions)
    wanted_constants = set(constants)
    nodes: list[ast.AST] = []
    for node in tree.body:
        if (wanted_constants and isinstance(node, (ast.Assign, ast.AnnAssign))
                and _nombres_asignados(node) & wanted_constants):
            nodes.append(node)
            continue
        # Las constantes de MODULO (regex, mapas de rotulos, tablas) deciden lo
        # que se extrae igual que los metodos que las usan. No entraban en
        # ninguna huella: cambiar `RE_TIV_ZONA` o un mapa sin tocar un metodo
        # dejaba vigentes certificaciones que hoy no se reproducirian. Van en
        # el componente comun (ventana semantica final, 03-10).
        if module_assigns and isinstance(node, (ast.Assign, ast.AnnAssign)):
            nodes.append(node)
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in wanted_functions:
                nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == class_name:
            nodes.extend(child for child in node.body
                         if isinstance(child, (ast.FunctionDef,
                                               ast.AsyncFunctionDef))
                         and child.name in wanted_methods)
            nodes.extend(child for child in node.body
                         if isinstance(child, (ast.Assign, ast.AnnAssign)))
    return "\n".join(ast.dump(node, include_attributes=False)
                      for node in nodes).encode()


def _nombres_asignados(nodo: ast.AST) -> set[str]:
    destinos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
    return {x.id for t in destinos for x in ast.walk(t) if isinstance(x, ast.Name)}


def _alcance(path: Path, class_name: str, metodos: Iterable[str],
             funciones: Iterable[str]) -> tuple[frozenset, frozenset, frozenset]:
    """Metodos, funciones y constantes de modulo alcanzables desde las raices.

    Es la dependencia REAL de quien importa una funcion de otro modulo: la
    funcion, lo que ella llama y las tablas que lee. Meter el modulo entero en
    la huella invalidaria de mas; meter solo la funcion nombrada, de menos
    (cambiar una regex que ella usa no se veria).
    """
    estado = path.stat()
    return _alcance_cacheado(str(path), estado.st_mtime_ns, estado.st_size,
                             class_name, tuple(sorted(metodos)),
                             tuple(sorted(funciones)))


@lru_cache(maxsize=32)
def _alcance_cacheado(ruta: str, _mtime_ns: int, _tamano: int, class_name: str,
                      metodos: tuple, funciones: tuple):
    arbol = ast.parse(Path(ruta).read_text(encoding="utf-8"))
    funcs = {n.name: n for n in arbol.body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    consts: dict[str, ast.AST] = {}
    for n in arbol.body:
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            for nombre in _nombres_asignados(n):
                consts[nombre] = n
    de_la_clase: dict[str, ast.AST] = {}
    for n in arbol.body:
        if isinstance(n, ast.ClassDef) and n.name == class_name:
            de_la_clase = {m.name: m for m in n.body
                           if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
    vistos_m: set[str] = set()
    vistos_f: set[str] = set()
    vistos_c: set[str] = set()
    pila = [("m", m) for m in metodos] + [("f", f) for f in funciones]
    while pila:
        tipo, nombre = pila.pop()
        if tipo == "m":
            if nombre in vistos_m or nombre not in de_la_clase:
                continue
            vistos_m.add(nombre)
            nodo = de_la_clase[nombre]
        elif nombre in funcs:
            if nombre in vistos_f:
                continue
            vistos_f.add(nombre)
            nodo = funcs[nombre]
        elif nombre in consts:
            if nombre in vistos_c:
                continue
            vistos_c.add(nombre)
            nodo = consts[nombre]
        else:
            continue
        for x in ast.walk(nodo):
            if isinstance(x, ast.Name):
                pila.append(("f", x.id))
            elif (isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
                  and x.value.id in ("self", "cls", class_name)):
                pila.append(("m", x.attr))
    return frozenset(vistos_m), frozenset(vistos_f), frozenset(vistos_c)


GENERICO = ROOT / "connectors" / "generico.py"


def _componente_comun() -> bytes:
    comunes_m, comunes_f = _comunes()
    return _selected_nodes(GENERICO, "GenericoConnector",
                           comunes_m, comunes_f, module_assigns=True)


def _importado_de_generico(path: Path) -> set[str]:
    """Los nombres que un modulo importa de `generico.py`, tambien a mitad de
    funcion (`wordpress.py` lo hace asi, y por eso no se veia)."""
    nombres: set[str] = set()
    for nodo in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.ImportFrom) and (
                (nodo.level == 1 and nodo.module == "generico")
                or nodo.module == "connectors.generico"):
            nombres |= {a.name for a in nodo.names}
    return nombres


def _lo_que_usa_de_generico(connector: str) -> dict[str, bytes]:
    """La parte de `generico.py` que ejecuta un connector propio.

    WordPress le pasa a `GenericoConnector.normalize` toda ficha sin objeto REST
    o con REST sin meta (WORDPRESS_HTML, WORDPRESS_SITEMAP y parte de
    WORDPRESS_REST) y lee el precio con `cuerpo_principal`: depende del codigo
    comun de generico entero, y su huella no lo tenia. El P0 de KiteProp
    (d1f9fdf) cambio `cuerpo_principal` y dejo vigentes certificaciones de
    WordPress que ya no se reproducian. Wasi solo usa `fuera_de_servicio`: su
    huella lleva esa funcion con lo que ella lee, nada mas.
    """
    nombres = _importado_de_generico(ROOT / "connectors" / f"{connector}.py")
    salida: dict[str, bytes] = {}
    usa_la_clase = "GenericoConnector" in nombres
    if usa_la_clase:
        salida["generic/common"] = _componente_comun()
    sueltos = nombres - {"GenericoConnector"}
    if sueltos:
        m, f, c = _alcance(GENERICO, "GenericoConnector", (), sueltos)
        if usa_la_clase:
            comunes_m, comunes_f = _comunes()
            m, f, c = m - comunes_m, f - comunes_f, frozenset()
        if m or f or c:
            salida["generic/importado"] = _selected_nodes(
                GENERICO, "GenericoConnector" if m else "", m, f, constants=c)
    return salida


def _senales_genericas_del_certificador() -> bytes:
    """Lo de `generico.py` con que el certificador decide `source_provided`.

    `source_signals` lee cada pagina con `cuerpo_principal`,
    `_es_tabla_estructurada`, `_cuenta_de_ficha`... y es la senal con la que se
    auditan las fichas de WordPress y Century21. Esas funciones estaban en la
    huella de generico y en ninguna otra: cambiarlas cambiaba el veredicto de
    Century21 sin invalidarlo.
    """
    ruta = ROOT / "scripts" / "agency_certifier.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    funciones = _importado_de_generico(ruta) - {"GenericoConnector"}
    metodos = {x.attr for x in ast.walk(arbol)
               if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)
               and x.value.id == "GenericoConnector"}
    m, f, c = _alcance(GENERICO, "GenericoConnector", metodos, funciones)
    return _selected_nodes(GENERICO, "GenericoConnector", m, f, constants=c)


def _descarte_con_senal() -> bytes:
    """`run_rollout.descartes_sospechosos` decide con
    `defect_triage.descarte_parecia_una_propiedad` que rechazos del guardian
    tenian pinta de ficha, y eso entra en el veredicto (`descartes_sin_senal`).
    El triaje vive en ese archivo y no entraba en ninguna huella."""
    ruta = ROOT / "scripts" / "defect_triage.py"
    m, f, c = _alcance(ruta, "", (), {"descarte_parecia_una_propiedad"})
    return _selected_nodes(ruta, "", m, f, constants=c)


# Los dos unicos recursos que `Geografia._cargar` abre de verdad. Los otros
# cuatro del manifiesto -departamentos, municipios, localidades, asentamientos-
# no los lee nadie, y meterlos en la huella significaria recertificar 261
# agencias por un archivo que no cambio nada de lo extraido. Codex lo pidio
# asi: "capturar input realmente usado".
RECURSOS_GEO_USADOS = ("provincias", "localidades-censales")


def huella_del_input_geografico(directorio: "Path | None" = None) -> bytes:
    """La identidad del snapshot de GeoRef que la extraccion va a consultar.

    Sale de los `sha256` que el propio `MANIFEST.json` publica, que es la
    identidad que el descargador ya verifica al leer cada recurso.

    Si el manifiesto falta o no se puede leer, la huella lo DICE en vez de
    parecerse a la de un manifiesto presente. Dos maquinas, una con la
    referencia y otra sin ella, no producen el mismo resultado geografico:
    que produjeran la misma huella seria la falsedad exacta que esto cierra.
    """
    if directorio is None:
        from connectors.geografia import DIRECTORIO_POR_DEFECTO
        directorio = Path(DIRECTORIO_POR_DEFECTO)
    ruta = Path(directorio) / "MANIFEST.json"
    try:
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
        recursos = manifiesto["recursos"]
    except (OSError, ValueError, KeyError, TypeError):
        return b"georef:sin-manifiesto-legible"
    partes = []
    for nombre in RECURSOS_GEO_USADOS:
        entrada = recursos.get(nombre) or {}
        sha = entrada.get("sha256") if isinstance(entrada, dict) else None
        partes.append(f"{nombre}={sha or 'sin-sha'}")
    return ("georef:" + "|".join(partes)).encode()


def archivos_de_la_huella() -> list[Path]:
    """Todos los archivos que `fingerprint_components` lee, para cualquier
    conector y estrategia. `test_la_guarda_conoce_todos_los_archivos_de_la_huella`
    fija que no falte ninguno: un archivo que entra en la huella y no en esta
    lista es un cambio que la guarda de abajo no veria."""
    return [
        ROOT / "scripts" / "image_quality.py",
        ROOT / "scraper" / "network_security.py",
        ROOT / "scraper" / "models.py",
        ROOT / "scraper" / "detail_urls.py",
        ROOT / "scripts" / "agency_web_discovery.py",
        ROOT / "connectors" / "base.py",
        ROOT / "scripts" / "run_rollout.py",
        ROOT / "scripts" / "agency_certifier.py",
        ROOT / "scripts" / "defect_triage.py",
        ROOT / "connectors" / "geografia.py",
        ROOT / "scripts" / "geo_reference.py",
        ROOT / "connectors" / "texto.py",
        ROOT / "connectors" / "coherencia.py",
        ROOT / "connectors" / "exterior.py",
        ROOT / "connectors" / "poligono_caba.py",
        ROOT / "connectors" / "geometria" / "caba_ign.geojson",
        ROOT / "connectors" / "pais.py",
        ROOT / "connectors" / "geometria" / "argentina_ign.json",
        ROOT / "connectors" / "poligono_provincia.py",
        ROOT / "connectors" / "formularios.py",
        ROOT / "connectors" / "generico.py",
        ROOT / "connectors" / "tokko.py",
        ROOT / "connectors" / "wasi.py",
        ROOT / "scripts" / "wasi_fingerprint.py",
        ROOT / "connectors" / "wordpress.py",
        ROOT / "connectors" / "century21.py",
    ]


def _estado_de_la_huella() -> tuple:
    estados = []
    # Y este mismo archivo: no es componente de ninguna huella, pero DEFINE que
    # significa cada una. Un worker con la definicion vieja en memoria estampa
    # huellas que la nueva no reconoce, y como su guarda no lo veia, seguia
    # certificando de mas hasta reiniciarse (ventana final, 03-10).
    for ruta in [*archivos_de_la_huella(), Path(__file__).resolve()]:
        try:
            st = ruta.stat()
            estados.append((str(ruta), st.st_mtime_ns, st.st_size))
        except OSError:
            estados.append((str(ruta), None, None))
    return tuple(estados), huella_del_input_geografico()


# El estado de los archivos de la huella cuando este PROCESO los importo.
#
# `strategy_fingerprint` lee de disco en el momento en que se la pide. El
# certificador la estampa al TERMINAR la agencia, y un worker corre con el
# codigo que cargo al arrancar. Si alguien edita un conector con los workers
# en marcha, la siguiente certificacion sale con la huella del codigo NUEVO
# habiendo corrido el VIEJO: parece vigente y no lo es. Es la certificacion
# falsa mas silenciosa posible, porque la huella existe justamente para
# impedirla.
_ESTADO_AL_IMPORTAR = _estado_de_la_huella()


def codigo_cambiado_desde_el_arranque() -> list[str]:
    """Que archivos de la huella cambiaron desde que este proceso arranco.

    Vacio si ninguno. Si hay alguno, lo que este proceso tiene en memoria ya
    no es lo que `strategy_fingerprint` describe.
    """
    antes, geo_antes = _ESTADO_AL_IMPORTAR
    ahora, geo_ahora = _estado_de_la_huella()
    cambiados = [a[0] for a, b in zip(antes, ahora) if a != b]
    if geo_antes != geo_ahora:
        cambiados.append("georef:MANIFEST.json")
    return cambiados


def fingerprint_components(connector: str, strategy: str) -> dict[str, bytes]:
    components = {
        "shared/image_quality": _semantic_file(ROOT / "scripts" / "image_quality.py"),
        "shared/network_security": _semantic_file(ROOT / "scraper" / "network_security.py"),
        "shared/models": _semantic_file(ROOT / "scraper" / "models.py"),
        "shared/detail_urls": _semantic_file(ROOT / "scraper" / "detail_urls.py"),
        "shared/source_policy": _semantic_file(ROOT / "scripts" / "agency_web_discovery.py"),
        "shared/base": _semantic_file(ROOT / "connectors" / "base.py"),
        "shared/runner": _archivo_sin_operativas(
            (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8"),
            RUNNER_OPERACIONALES),
        "shared/certifier": _archivo_sin_operativas(
            (ROOT / "scripts" / "agency_certifier.py").read_text(encoding="utf-8"),
            CERTIFIER_OPERACIONALES),
        "shared/descarte_con_senal": _descarte_con_senal(),
        # La geografia canonica decide la ciudad y el barrio de cada
        # propiedad: cambiarla cambia lo que se extrae, asi que tiene que
        # invalidar la certificacion como cualquier otro cambio de extraccion.
        "shared/geografia": _semantic_file(
            ROOT / "connectors" / "geografia.py"),
        "shared/geo_reference": _semantic_file(
            ROOT / "scripts" / "geo_reference.py"),
        # Y el DATO, no solo el codigo que lo lee. `connectors/geografia.py`
        # ya esta en la huella porque decide la ciudad y la provincia de cada
        # propiedad; el snapshot de GeoRef que consulta decide lo mismo y no
        # estaba. Un snapshot nuevo cambia lo extraido y dejaba la huella
        # igual, o sea certificaciones vigentes describiendo un resultado que
        # hoy no se reproduciria.
        "shared/geo_input": huella_del_input_geografico(),
        # La normalizacion de texto decide que etiqueta se reconoce y que dos
        # valores son el mismo. Es codigo semantico y va en la huella desde el
        # primer dia: un modulo nuevo que nadie registra es exactamente el
        # agujero que tuvo `discover()` cuando era semantico y quedaba afuera.
        "shared/texto": _semantic_file(ROOT / "connectors" / "texto.py"),
        # El guardian de coherencia decide que atributos se descartan
        # -dormitorios>ambientes, cubierta>total, una foto que no es foto-.
        # `generico.py` lo importa y no era componente de ninguna huella:
        # cambiar esa regla habria cambiado lo que se extrae sin invalidar una
        # sola certificacion. Tercera vez que aparece codigo semantico afuera.
        "shared/coherencia": _semantic_file(
            ROOT / "connectors" / "coherencia.py"),
        # Decide que propiedades se marcan del exterior y quedan sin geografia
        # argentina (`base.completar_ubicacion`): cambia lo que se guarda.
        "shared/exterior": _semantic_file(
            ROOT / "connectors" / "exterior.py"),
        # CABA + provincia «Buenos Aires» se desempata por contencion en el
        # poligono oficial: el codigo y la GEOMETRIA deciden la provincia.
        "shared/poligono_caba": _semantic_file(
            ROOT / "connectors" / "poligono_caba.py"),
        "shared/geometria_caba": hashlib.sha256(
            (ROOT / "connectors" / "geometria" / "caba_ign.geojson").read_bytes()
        ).hexdigest().encode(),
        # El exterior tambien se decide por contencion en el poligono del pais.
        "shared/pais": _semantic_file(ROOT / "connectors" / "pais.py"),
        "shared/geometria_pais": hashlib.sha256(
            (ROOT / "connectors" / "geometria" / "argentina_ign.json").read_bytes()
        ).hexdigest().encode(),
        # P10: la provincia contradictoria se normaliza por contencion en el
        # poligono oficial de la provincia de la localidad.
        "shared/poligono_provincia": _semantic_file(
            ROOT / "connectors" / "poligono_provincia.py"),
        # Sin el archivo el modulo no afirma nada (P10 apagado): es un estado
        # propio de la huella, no un error.
        "shared/geometria_provincias": hashlib.sha256(
            (ROOT / "connectors" / "geometria" / "provincias_ign.json").read_bytes()
            if (ROOT / "connectors" / "geometria" / "provincias_ign.json").exists()
            else b"AUSENTE"
        ).hexdigest().encode(),
    }
    if connector != "generico":
        components[f"connector/{connector}"] = _semantic_file(
            ROOT / "connectors" / f"{connector}.py")
        if connector == "wasi":
            # `wasi.py` lee cada ficha con `scripts.wasi_fingerprint`: sin
            # esto, cambiar un rotulo cambiaba lo extraido sin invalidar nada.
            components["connector/wasi_parser"] = _semantic_file(
                ROOT / "scripts" / "wasi_fingerprint.py")
        components.update(_lo_que_usa_de_generico(connector))
        if connector not in CONECTORES_CON_SENALES_PROPIAS:
            components["certifier/generic_signals"] = (
                _senales_genericas_del_certificador())
        return components
    components["generic/common"] = _componente_comun()
    components[f"strategy/{strategy}"] = _selected_nodes(
        ROOT / "connectors" / "generico.py", "GenericoConnector",
        GENERIC_STRATEGY_METHODS.get(strategy, set()),
        GENERIC_STRATEGY_FUNCTIONS.get(strategy, set()))
    # El transporte de formularios POST no es solo de PHP AJAX: el listado
    # comun (`_fetch_listing`, `_catalogo_gvamax`, `_catalogo_por_tipo`) baja
    # con el las paginas de catalogo. Estaba solo en php_ajax_search, y
    # cambiarlo dejaba vigente el inventario de las demas (ventana, 03-10).
    components["generic/form_transport"] = _semantic_file(
        ROOT / "connectors" / "formularios.py")
    return components


def fingerprint_from_components(components: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, payload in sorted(components.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()[:12]


@lru_cache(maxsize=None)
def strategy_fingerprint_v1(connector: str, strategy: str) -> str:
    """La huella como se calculaba en el esquema 1: archivos enteros.

    Codigo de transicion. Sirve para una sola pregunta, que es la unica que
    importa ante un paquete viejo: cambio el COMPORTAMIENTO desde que se emitio
    ese veredicto, o solo cambio la definicion de la huella. Comparar un
    paquete del esquema 1 contra la huella del esquema 2 no puede responderla,
    porque todo difiere por construccion.

    Se puede borrar cuando no queden paquetes del esquema 1.
    """
    componentes = dict(fingerprint_components(connector, strategy))
    componentes["shared/runner"] = _semantic_file(
        ROOT / "scripts" / "run_rollout.py")
    componentes["shared/certifier"] = _semantic_file(
        ROOT / "scripts" / "agency_certifier.py")
    return fingerprint_from_components(componentes)


@lru_cache(maxsize=None)
def strategy_fingerprint(connector: str, strategy: str) -> str:
    return fingerprint_from_components(
        fingerprint_components(connector, strategy))


def current_code_evidence(result: dict[str, Any]) -> bool:
    """Positive code evidence, not proof of source identity/data correctness.

    Unknown old metadata keeps defects open elsewhere; it cannot establish
    success here. Never upgrade an old whole-file or retrospectively stamped
    fingerprint into a current strategy certificate.
    """
    if not isinstance(result, dict):
        return False
    if (type(result.get('fingerprint_schema_version')) is not int
            or result['fingerprint_schema_version'] != FINGERPRINT_SCHEMA_VERSION
            or result.get('fingerprint_backfilled_from_terminal_evidence', False) is not False):
        return False
    connector = result.get('connector')
    if not isinstance(connector, str) or connector not in {'generico', 'tokko', 'wasi', 'wordpress', 'century21'}:
        return False
    declared_strategy = result.get('connector_strategy')
    if declared_strategy is not None and not isinstance(declared_strategy, str):
        return False
    strategy = declared_strategy or strategy_for(
        connector, result.get('publication_mechanism'))
    if not isinstance(strategy, str):
        return False
    if connector == 'generico':
        if strategy not in GENERIC_STRATEGY_METHODS:
            return False
    elif strategy != connector:
        return False
    if result.get('publication_mechanism') is not None and strategy_for(connector, result['publication_mechanism']) != strategy:
        return False
    saved = result.get('strategy_fingerprint')
    return isinstance(saved, str) and saved == strategy_fingerprint(connector, strategy)

"""Fingerprints por mecanismo realmente usado por una certificacion.

La huella historica del connector generico cubria todo ``generico.py``. Un
cambio aislado en MAPAPROP invalidaba PHP legacy, sitemap y HTML aunque esas
fuentes no ejecutaran esa estrategia. Este modulo conserva las dependencias
transversales y separa solamente familias observadas y certificadas.
"""
from __future__ import annotations

import ast
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
RAIZ = ROOT  # alias en castellano para los tests
FINGERPRINT_SCHEMA_VERSION = 2

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
}

GENERIC_COMMON_METHODS = {
    "_es_ficha_url", "_solo_por_forma", "_id_de", "normalize",
    "_imagenes_de", "_direccion_de", "_titulo_de_la_ficha",
    "_operacion_en_la_ficha", "_confirma_ficha", "_estado_fuente",
    "_de_json_ld", "_cuenta", "_cuenta_de_ficha", "_sup",
    "_tipo_en_la_ficha", "_mismo_sitio",
}
GENERIC_STRATEGY_METHODS = {
    "generic/empty_catalog": {"_fichas_en"},
    "generic/html_catalog": {
        "_patron_de", "_patron_raiz_local", "_patron_catalogo_numerico",
        "_fichas_en",
    },
    "generic/mapaprop": {
        "_catalogo_mapaprop", "_fichas_mapaprop_en", "_detalle_mapaprop",
    },
    "generic/php_ajax_search": {
        "_catalogo_php_ajax", "_normalizar_php_ajax",
    },
    "generic/portal_offset": {
        "_patron_portal_offset_local", "_portal_catalogo", "_fichas_en",
    },
    "generic/php_query_catalog": {
        "_fichas_query_en", "_patron_catalogo_numerico",
    },
    "generic/no_inventory": {"_fichas_en"},
    "generic/sitemap": {"_patron_de", "_fichas_en"},
    "generic/wordpress_category": {"_catalogo_wordpress_por_categoria"},
    "generic/xintel": {"_normalizar_xintel"},
    "generic/buscadorprop_json": {"_patron_de", "_fichas_en"},
    # Todo lo propio de la estrategia vive en estos tres metodos: cambiarlos
    # no invalida ninguna otra familia, y ninguna otra los usa.
    "generic/bitrix_landing": {
        "_catalogo_bitrix_landing", "_nodo_landing", "_clave_landing",
        "_normalizar_bitrix_landing",
    },
}

GENERIC_COMMON_FUNCTIONS = {
    "patron_de_forma", "_texto", "cuerpo_principal",
    "sin_filtros_catalogo", "normalizar_texto_campos", "_aplanar_ld",
}
GENERIC_STRATEGY_FUNCTIONS = {
    "generic/wordpress_category": {
        "_sin_variantes_wordpress", "_imagenes_galeria_wordpress"},
}


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


def strategy_for(connector: str, publication_mechanism: str | None) -> str:
    if connector != "generico":
        return connector
    return PUBLICATION_STRATEGIES.get(
        str(publication_mechanism or ""), "generic/unknown")


def _semantic_file(path: Path) -> bytes:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return ast.dump(tree, include_attributes=False).encode()


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
                    methods: Iterable[str], functions: Iterable[str]) -> bytes:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wanted_methods = set(methods)
    wanted_functions = set(functions)
    nodes: list[ast.AST] = []
    for node in tree.body:
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


def fingerprint_components(connector: str, strategy: str) -> dict[str, bytes]:
    components = {
        "shared/base": _semantic_file(ROOT / "connectors" / "base.py"),
        "shared/runner": _archivo_sin_operativas(
            (ROOT / "scripts" / "run_rollout.py").read_text(encoding="utf-8"),
            RUNNER_OPERACIONALES),
        "shared/certifier": _archivo_sin_operativas(
            (ROOT / "scripts" / "agency_certifier.py").read_text(encoding="utf-8"),
            CERTIFIER_OPERACIONALES),
        # La geografia canonica decide la ciudad y el barrio de cada
        # propiedad: cambiarla cambia lo que se extrae, asi que tiene que
        # invalidar la certificacion como cualquier otro cambio de extraccion.
        "shared/geografia": _semantic_file(
            ROOT / "connectors" / "geografia.py"),
    }
    if connector != "generico":
        components[f"connector/{connector}"] = _semantic_file(
            ROOT / "connectors" / f"{connector}.py")
        return components
    methods = GENERIC_COMMON_METHODS | GENERIC_STRATEGY_METHODS.get(
        strategy, set())
    functions = GENERIC_COMMON_FUNCTIONS | GENERIC_STRATEGY_FUNCTIONS.get(
        strategy, set())
    components["generic/common"] = _selected_nodes(
        ROOT / "connectors" / "generico.py", "GenericoConnector",
        GENERIC_COMMON_METHODS, GENERIC_COMMON_FUNCTIONS)
    components[f"strategy/{strategy}"] = _selected_nodes(
        ROOT / "connectors" / "generico.py", "GenericoConnector",
        methods - GENERIC_COMMON_METHODS,
        functions - GENERIC_COMMON_FUNCTIONS)
    if strategy == "generic/php_ajax_search":
        components["strategy/php_form_transport"] = _semantic_file(
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

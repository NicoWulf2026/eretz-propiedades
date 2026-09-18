"""El contrato de propiedad: qué sobrevive y dónde puede aparecer."""
from __future__ import annotations

from scripts.property_contract import (AUSENTE_SIN_DIAGNOSTICO, EXTRACTED,
                                       EXTRACTION_FAILED,
                                       REJECTED_BY_VALIDATION,
                                       SOURCE_NOT_PROVIDED, alcances, evaluar,
                                       estado_de_campo)


def _propiedad(**cambios):
    base = {"source_url": "https://alfa.com.ar/p/1", "hash_dedup": "h1",
            "canonical_agency_id": "roomix:alfa", "titulo": "Casa en Venta",
            "descripcion": "Muy linda", "operacion": "venta",
            "tipo_propiedad": "casa", "precio": 100000.0, "moneda": "USD",
            "ciudad": "Rosario", "provincia": "Santa Fe",
            "latitud": -32.95, "longitud": -60.66}
    base.update(cambios)
    return base


def test_una_propiedad_real_incompleta_sobrevive():
    """La regla que ordena todo el contrato. Exigir `operacion` habría borrado
    del portal 10.916 propiedades que existen, con título, precio, fotos y
    dirección. Pierden el filtro venta/alquiler, no la existencia."""
    permitidos, razones = alcances(_propiedad(operacion=None, tipo_propiedad=None,
                                              precio=None, moneda=None,
                                              ciudad=None, latitud=None,
                                              longitud=None))
    assert "FICHA" in permitidos
    assert "LISTADO" in permitidos
    assert "FILTRO_OPERACION" not in permitidos
    assert razones  # dice por qué, en castellano


def test_sin_identidad_no_hay_propiedad():
    """Lo único que descarta de verdad: sin url no hay a qué volver, y sin
    `hash_dedup` no se la puede deduplicar ni actualizar."""
    for falta in ("source_url", "hash_dedup", "canonical_agency_id"):
        permitidos, razones = alcances(_propiedad(**{falta: None}))
        assert permitidos == set(), falta
        assert "sin identidad" in razones[0]


def test_sin_nada_que_mostrar_tampoco():
    permitidos, razones = alcances(_propiedad(titulo=None, descripcion=None))
    assert permitidos == set()
    assert "nada que mostrar" in razones[0]
    # Con uno de los dos alcanza.
    assert "FICHA" in alcances(_propiedad(titulo=None))[0]
    assert "FICHA" in alcances(_propiedad(descripcion=None))[0]


def test_un_precio_sin_moneda_no_es_un_precio():
    """90.000 puede ser dólares o pesos, y la diferencia es un orden de
    magnitud. La validación lo rechaza y el contrato lo registra como rechazo,
    no como ausencia."""
    fila = _propiedad(moneda=None, problemas={"precio sin moneda": True})
    assert estado_de_campo(fila, "moneda") == REJECTED_BY_VALIDATION
    assert "FILTRO_PRECIO" not in alcances(fila)[0]
    assert "FICHA" in alcances(fila)[0]


def test_un_par_imposible_marca_los_dos_campos():
    """`dormitorios>ambientes` es imposible: no se sabe cuál de los dos está
    mal, así que el guardián descarta los dos y el contrato lo dice de los
    dos."""
    fila = _propiedad(dormitorios=None, ambientes=None,
                      extra={"atributos_descartados": "dormitorios>ambientes"})
    assert estado_de_campo(fila, "dormitorios") == REJECTED_BY_VALIDATION
    assert estado_de_campo(fila, "ambientes") == REJECTED_BY_VALIDATION


def test_no_se_adivina_por_que_falta_un_campo():
    """`SOURCE_NOT_PROVIDED` y `EXTRACTION_FAILED` no son lo mismo: el primero
    no tiene arreglo y el segundo es un defecto nuestro. Sin la señal de la
    fuente no se puede separar, y marcar todo como "la fuente no lo publica"
    escondería justamente los defectos que hay que encontrar."""
    fila = _propiedad(banos=None)
    assert estado_de_campo(fila, "banos") == AUSENTE_SIN_DIAGNOSTICO
    assert estado_de_campo(fila, "banos", fuente_lo_publica=True) == EXTRACTION_FAILED
    assert estado_de_campo(fila, "banos", fuente_lo_publica=False) == SOURCE_NOT_PROVIDED


def test_un_campo_presente_esta_extraido():
    assert estado_de_campo(_propiedad(), "precio") == EXTRACTED
    # Un cero aceptado por normalizacion no equivale a un campo ausente.
    assert estado_de_campo(_propiedad(dormitorios=0), "dormitorios") == EXTRACTED


def test_el_veredicto_declara_su_version():
    """Cambiar el contrato tiene que verse en el artefacto; si no, no se puede
    auditar con qué reglas se decidió."""
    geo = {"localidad_canonica": "Rosario",
           "area_busqueda": {"nivel": "LOCALIDAD", "nombre": "Rosario"}}
    v = evaluar(_propiedad(), geo=geo)
    assert v["contrato_version"] == "property_contract_v5"
    assert v["publicable"] is True
    assert v["database_writes"] == 0
    assert set(v["alcances"]) == {"FICHA", "LISTADO", "FILTRO_OPERACION",
                                  "FILTRO_TIPO", "FILTRO_PRECIO",
                                  "FILTRO_LOCALIDAD", "AREA_BUSQUEDA", "MAPA"}


def test_la_localidad_no_se_afirma_sin_evidencia_canonica():
    """v2. Que la fuente escriba algo en el campo `ciudad` no la vuelve una
    localidad: `Villa del Parque` es un barrio de CABA y resolvía a una
    localidad de Río Negro."""
    v = evaluar(_propiedad(ciudad="Villa del Parque"))
    assert "FILTRO_LOCALIDAD" not in v["alcances"]
    assert any("localidad canonica" in r for r in v["razones_de_exclusion"])
    # Y sigue existiendo igual: la propiedad no se pierde por eso.
    assert v["publicable"] is True
    assert {"FICHA", "LISTADO"} <= set(v["alcances"])


def test_un_municipio_da_area_de_busqueda_pero_no_localidad():
    """La decisión: un municipio puede servir para descubrir una propiedad,
    pero no puede fingir ser una localidad."""
    v = evaluar(_propiedad(ciudad=None), geo={
        "localidad_canonica": None,
        "area_busqueda": {"nivel": "MUNICIPIO", "nombre": "La Calera"}})
    assert "AREA_BUSQUEDA" in v["alcances"]
    assert "FILTRO_LOCALIDAD" not in v["alcances"]


def test_sin_area_tampoco_se_pierde_la_propiedad():
    v = evaluar(_propiedad(ciudad=None), geo={
        "area_busqueda": {"nivel": "SIN_AREA", "nombre": None}})
    assert "AREA_BUSQUEDA" not in v["alcances"]
    assert v["publicable"] is True


def test_un_terreno_sin_dormitorios_no_es_un_defecto_nuestro():
    """La señal de "la fuente publica este campo" se agrega POR AGENCIA: si una
    inmobiliaria publica dormitorios en sus departamentos, la señal dice que
    los publica, y después cada terreno sin dormitorios se contaba como defecto
    nuestro.

    Eran 2.969 de 11.875 —uno de cada cuatro— y nos habrían mandado a buscar un
    bug de parser que no existe.
    """
    for campo in ("ambientes", "dormitorios", "banos", "superficie_cubierta"):
        assert estado_de_campo({"tipo_propiedad": "terreno"}, campo,
                               True) == SOURCE_NOT_PROVIDED
    assert estado_de_campo({"tipo_propiedad": "Terreno / Lote"}, "banos",
                           True) == SOURCE_NOT_PROVIDED


def test_una_vivienda_sin_dormitorios_si_lo_es():
    """La regla no puede tapar el defecto real: un departamento sin dormitorios
    en una agencia que los publica es algo que no leímos."""
    assert estado_de_campo({"tipo_propiedad": "departamento"}, "dormitorios",
                           True) == EXTRACTION_FAILED


def test_la_regla_es_conservadora():
    """Sólo lo imposible, no lo raro. Un local puede tener dos ambientes y un
    toilette; lo que no puede tener es dormitorios."""
    assert estado_de_campo({"tipo_propiedad": "local"}, "banos",
                           True) == EXTRACTION_FAILED
    assert estado_de_campo({"tipo_propiedad": "local"}, "ambientes",
                           True) == EXTRACTION_FAILED
    assert estado_de_campo({"tipo_propiedad": "local"}, "dormitorios",
                           True) == SOURCE_NOT_PROVIDED


def test_sin_tipo_no_se_supone_nada():
    """No saber de qué clase de propiedad se trata no autoriza a exonerar."""
    assert estado_de_campo({"tipo_propiedad": None}, "dormitorios",
                           True) == EXTRACTION_FAILED


def test_la_ciudad_la_decide_el_resolver_y_no_la_columna_cruda():
    """Tokko publica la ubicación en un solo campo, que cae en `barrio`:
    "Cordoba Capital" es una ciudad y está ahí. Mirando la columna `ciudad`
    vacía, el gate reportaba 1.092 propiedades como ciudad no extraída cuando
    no había nada que leer en ese campo —y al mismo tiempo la cobertura decía
    que la localidad estaba resuelta—."""
    resuelta = estado_de_campo({"ciudad": None}, "ciudad", True,
                               {"localidad_canonica": "Rosario"})
    assert resuelta == EXTRACTED


def test_un_barrio_publicado_no_es_una_ciudad_que_fallamos():
    """La fuente publicó un barrio. No fallamos en leer una ciudad: no había."""
    assert estado_de_campo({}, "ciudad", True,
                           {"match": "NOT_FOUND"}) == SOURCE_NOT_PROVIDED


def test_negarse_a_afirmar_una_ciudad_es_validacion_no_defecto():
    """La distinción que ordena todo el sistema: `azpropiedades` publica
    "Caseros" en el Gran Buenos Aires y la única Caseros del catálogo está en
    Entre Ríos, a 238 km."""
    for motivo in ("CONTRADICTED_BY_COORDINATES", "AMBIGUOUS"):
        assert estado_de_campo({}, "ciudad", True,
                               {"match": motivo}) == REJECTED_BY_VALIDATION


def test_el_contrato_lee_la_forma_que_la_cobertura_EMITE():
    """El contrato leía `valor` y la cobertura pasó a emitir `nombre` al
    unificar la forma. Los tests siguieron pasando porque la fixture también
    decía `valor`: se rompió el dato real y no el test.

    Este test construye la fila con el MISMO helper que usa la auditoría, así
    que la fixture no puede volver a divergir de lo que se emite.
    """
    from connectors.base import (AREA_MUNICIPIO, Connector, GEO_CANONICAL,
                                 dimension_geo)

    area = Connector._area_de_busqueda({
        "localidad": dimension_geo(None),
        "municipio": dimension_geo("La Calera", procedencia=GEO_CANONICAL),
        "departamento": dimension_geo(None),
        "provincia": dimension_geo(None)})
    assert area["nivel"] == AREA_MUNICIPIO

    permitidos, _ = alcances(_propiedad(), {"area_busqueda": area})
    assert "AREA_BUSQUEDA" in permitidos

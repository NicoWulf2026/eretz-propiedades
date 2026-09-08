

def test_el_nombre_entero_pegado_tambien_esta_en_el_dominio():
    """`ABP PROPIEDADES` vive en `abppropiedades.com.ar` y la compuerta lo daba
    por sin rastro: "abp" tiene tres letras y cae por el largo mínimo, y
    "propiedades" es genérica. Ninguna palabra sobrevivía, aunque el nombre
    completo sea EXACTAMENTE el dominio."""
    from scripts.agency_official_web_gate import nombre_en_el_dominio

    assert nombre_en_el_dominio("ABP PROPIEDADES",
                                "https://www.abppropiedades.com.ar/")
    assert nombre_en_el_dominio("CFG Negocios Inmobiliarios",
                                "https://cfgnegociosinmobiliarios.com/")
    # Y los acentos no lo rompen.
    assert nombre_en_el_dominio("J Braña Propiedades",
                                "https://jbranapropiedades.com.ar/")


def test_estar_contenido_no_alcanza():
    """`Buró 2` está contenido en `remax-buro2.com.ar`, que es el dominio de la
    franquicia y no el de la inmobiliaria. Se exige coincidencia exacta: no que
    el dominio contenga algo del nombre, sino que el dominio SEA el nombre."""
    from scripts.agency_official_web_gate import nombre_completo_en_el_dominio

    assert nombre_completo_en_el_dominio("Buró 2",
                                         "https://remax-buro2.com.ar/") is None
    assert nombre_completo_en_el_dominio("ABP Propiedades",
                                         "https://otracosa.com.ar/") is None


def test_el_dominio_propio_se_lee_entero_con_subdominios():
    """`MORESCO REAL ESTATE` publica en `propiedades.moresco.com.ar`. Leyendo
    solo la primera etiqueta, la marca era "propiedades" -genérica- y la
    inmobiliaria figuraba sin rastro de su nombre en su propio dominio."""
    from scripts.agency_official_web_gate import marca_de, nombre_en_el_dominio

    assert marca_de("https://www.propiedades.moresco.com.ar") == "propiedadesmoresco"
    assert nombre_en_el_dominio("MORESCO REAL ESTATE",
                                "https://www.propiedades.moresco.com.ar") == "moresco"


def test_los_acentos_no_parten_el_nombre_en_pedazos():
    """`Cuño Propiedades` vive en `cuno.com.ar`. Sin plegar los acentos, la
    expresión partía "cuño" en "cu" y "o" -las dos por debajo del largo
    mínimo- y el dominio que ES su nombre quedaba sin rastro."""
    from scripts.agency_official_web_gate import (nombre_en_el_dominio,
                                                  palabras_del_nombre)

    assert palabras_del_nombre("Cuño Propiedades") == ["cuno"]
    assert nombre_en_el_dominio("Cuño Propiedades", "https://www.cuno.com.ar") == "cuno"
    # Y no deja fragmentos que puedan coincidir con cualquier cosa.
    assert "berto" not in palabras_del_nombre("Bertoía Propiedades")


def test_el_sufijo_del_dominio_no_es_marca_de_nadie():
    """Sin sacar los sufijos, una inmobiliaria llamada `COMAR` coincidiría con
    cualquier dominio `.com.ar`."""
    from scripts.agency_official_web_gate import nombre_en_el_dominio

    assert nombre_en_el_dominio("COMAR Propiedades",
                                "https://otracosa.com.ar") is None


def test_un_dominio_del_estado_no_es_la_web_de_una_inmobiliaria():
    """`turismo.lacumbre.gob.ar` es la página de turismo de la municipalidad de
    La Cumbre. Coincide con el nombre de la inmobiliaria por la localidad, y sin
    esta regla quedaba afirmada como su sitio propio."""
    from scripts.agency_official_web_gate import dominio_institucional, evaluar

    assert dominio_institucional("https://turismo.lacumbre.gob.ar")
    assert dominio_institucional("https://boletinoficial.neuquen.gov.ar")
    assert not dominio_institucional("https://www.cuno.com.ar")

    fila = {"canonical_agency_id": "x", "nombre": "Estudio Inmobiliario Cumbre",
            "discovered_domain": "https://turismo.lacumbre.gob.ar/"}
    resultado = evaluar([fila])[0]
    assert resultado["estado"] == "DOMINIO_INSTITUCIONAL"
    assert resultado["official_url"] is None


def test_la_marca_de_iniciales_es_su_dominio():
    """`Vanesa Lorena Barros negocios inmobiliarios` publica en `vlbprop.com` y
    `Karina Enriquez Propiedades` en `kepropiedades.com.ar`. Ni una palabra del
    nombre ni el nombre entero aparecen: la marca son las iniciales."""
    from scripts.agency_official_web_gate import iniciales_en_el_dominio

    assert iniciales_en_el_dominio("Vanesa Lorena Barros negocios inmobiliarios",
                                   "https://vlbprop.com") == "vlb"
    assert iniciales_en_el_dominio("Karina Enriquez Propiedades",
                                   "https://www.kepropiedades.com.ar") == "ke"
    assert iniciales_en_el_dominio("ASG Propiedades SRL",
                                   "https://asgpropiedades.com.ar") == "asg"


def test_las_iniciales_tienen_que_estar_al_principio_y_solas():
    """`ARTE PROPIEDADES` figura en `lujanprop.com.ar`, que es el portal donde
    tiene su perfil. Si bastara con que las iniciales aparecieran en cualquier
    lado, o con cualquier resto detrás, el portal pasaría por sitio propio."""
    from scripts.agency_official_web_gate import iniciales_en_el_dominio

    assert iniciales_en_el_dominio("ARTE PROPIEDADES",
                                   "https://lujanprop.com.ar") is None
    # El resto tiene que ser una palabra genérica, no cualquier cosa.
    assert iniciales_en_el_dominio("Ana Beatriz Cordero",
                                   "https://abcinmobiliariaderosario.com") is None
    # Y una sola inicial no distingue a nadie.
    assert iniciales_en_el_dominio("Aguirre Inmobiliaria",
                                   "https://apropiedades.com.ar") is None



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

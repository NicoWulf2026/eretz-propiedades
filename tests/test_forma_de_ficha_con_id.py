# -*- coding: utf-8 -*-
"""Una forma de ficha con identificador, aprendida de la propia fuente.

El escaneo de las 50 agencias `NEEDS_FIX` con cero enumeradas encontró que
**14 de 49 publican fichas con una forma que ningún patrón nuestro ve**, en 10
formas distintas. Las que llevan un identificador numérico son:

    /<palabra>-<id>-<slug>          /propiedad-9871962-venta-casa-en-funes
    /<palabra-suelta>/<id>-<slug>   /p/7525662-Casa-en-Venta-en-Salvador-Maria
    /<palabra>-<id>                 /inmueble_6076

El proyecto ya tiene el mecanismo para esto y estaba atado a **una** forma:
`_patron_raiz_local` reconoce `/p-1749_departamento` y nada más. La idea era
buena —una forma verificada por fuente, sin aflojar el patrón global— y la
implementación estaba cableada a un solo caso.

Lo que hace seguro generalizarla es el guardián que ya existe:
`_confirma_ficha` valida **cada detalle** —precio o schema, operación o dos
atributos, y fotos— y sobre las 283 páginas con que se verificó acepta el
96,9 % de las formas confirmadas y sólo el 4,5 % de las descartadas.

Por eso se exige un identificador de tres dígitos o más: es la señal más
difícil de cumplir por accidente. `/quienes-somos` y `/servicios` no la tienen;
`/2024/09/nota` la tiene pero no sobrevive al guardián, y además se le pide
además una palabra o un tipo de inmueble.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from connectors.generico import GenericoConnector  # noqa: E402


def enlaces(*rutas: str) -> str:
    return "".join(f'<a href="{r}">x</a>' for r in rutas)


def test_MUERDE_la_forma_de_fios_se_aprende():
    """`/propiedad-<id>-<slug>`: la palabra pegada al id con un guion.

    Cuarta vez que este proyecto tropieza con la misma suposición —que la
    palabra abre un segmento—. `RE_FICHA` pide `/propiedad/algo` y
    `RE_FICHA_RAIZ` pide que el id vaya primero.
    """
    html = enlaces("/propiedad-9871962-venta-casa-en-funes",
                   "/propiedad-9478752-venta-departamento-en-funes",
                   "/propiedad-1234567-venta-ph-en-rosario")
    patron = GenericoConnector._patron_raiz_local(html)
    assert patron is not None
    assert patron.match("/propiedad-5555555-alquiler-local-en-rosario")


def test_la_forma_de_gianfelice_tambien():
    """`/p/<id>-<slug>`: sección corta y el id en el segundo segmento."""
    html = enlaces("/p/7525662-Casa-en-Venta-en-Salvador-Maria",
                   "/p/6731093-Haras-Santa-Cecilia-en-Lobos",
                   "/p/2494510-Lote-en-Canning")
    patron = GenericoConnector._patron_raiz_local(html)
    assert patron is not None and patron.match("/p/1111111-Depto-en-Lobos")


def test_la_forma_de_bottai_tambien():
    """`/inmueble_6076`: separador de guion bajo y sin slug."""
    html = enlaces("/inmueble_6076", "/inmueble_6067", "/inmueble_5912")
    patron = GenericoConnector._patron_raiz_local(html)
    assert patron is not None and patron.match("/inmueble_1234")


def test_la_forma_vieja_se_sigue_reconociendo():
    """`/p-1749_departamento` era el único caso que el método conocía.

    Generalizar no puede perder el caso por el que se escribió.
    """
    html = enlaces("/p-1749_departamento", "/p-1750_casa", "/p-1751_lote")
    patron = GenericoConnector._patron_raiz_local(html)
    assert patron is not None and patron.match("/p-1752_ph")


def test_MUERDE_dos_enlaces_no_alcanzan():
    """Tres es la evidencia mínima y no se relaja.

    Con dos, cualquier par de páginas numeradas —una paginación, dos notas—
    habilitaría una forma para toda la fuente.
    """
    html = enlaces("/propiedad-9871962-venta-casa", "/propiedad-9478752-venta-ph")
    assert GenericoConnector._patron_raiz_local(html) is None


def test_MUERDE_una_ruta_sin_identificador_no_habilita_forma():
    """`/quienes-somos`, `/servicios`, `/contacto`.

    Sin un id de tres dígitos no hay forma: una navegación institucional tiene
    exactamente la misma pinta que un slug de ficha.
    """
    html = enlaces("/quienes-somos", "/servicios-inmobiliarios", "/contactanos",
                   "/nuestra-empresa")
    assert GenericoConnector._patron_raiz_local(html) is None


def test_MUERDE_un_blog_con_fechas_no_habilita_forma():
    """`/2024/09/nota-del-blog` tiene números y no es una propiedad.

    Se pide id **y** una palabra que diga de qué se trata. El año no alcanza.
    """
    html = enlaces("/2024/09/mercado-inmobiliario-hoy",
                   "/2024/08/como-vender-tu-casa",
                   "/2023/12/balance-del-anio")
    assert GenericoConnector._patron_raiz_local(html) is None


def test_una_paginacion_no_habilita_forma():
    """`/propiedades?pagina=2` no es una ficha aunque tenga la palabra."""
    html = enlaces("/propiedades?pagina=1", "/propiedades?pagina=2",
                   "/propiedades?pagina=3")
    assert GenericoConnector._patron_raiz_local(html) is None


def test_la_forma_aprendida_no_matchea_otras_rutas_del_mismo_sitio():
    """El riesgo de una forma amplia: llevarse la navegación por delante.

    Si de `/propiedad-9871962-…` saliera un patrón como `/<algo>`, arrastraría
    `/quienes-somos` y una página institucional terminaría publicada como
    propiedad.
    """
    html = enlaces("/propiedad-9871962-venta-casa-en-funes",
                   "/propiedad-9478752-venta-departamento",
                   "/propiedad-1234567-venta-ph")
    patron = GenericoConnector._patron_raiz_local(html)
    for ajena in ("/quienes-somos", "/servicios", "/contacto",
                  "/propiedades", "/blog/nota-larga-con-guiones"):
        assert not patron.match(ajena), ajena

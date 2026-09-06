#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Normalizacion de texto: una etapa del pipeline, no una defensa por regla.

Cuatro veces una regla fallo porque comparo texto sin normalizar, y las cuatro
veces se arreglo dentro de la regla:

1. `_es_tabla_estructurada` no veia `Ba�os` con la enie rota y leia prosa
   donde habia tabla.
2. La senal de fuente y su extraccion usaban alfabetos distintos, y un campo
   publicado figuraba como no publicado.
3. `RE/MAX` no matcheaba `remax`, y `Remax Cuore` quedaba fuera de su propia
   verificacion de web.
4. `Tissera Esquina Los Cedros` y `Tissera esquina Los Cedros` contaban como
   direcciones distintas, y 72 grupos duplicados salieron clasificados como
   "pueden ser dos unidades" por una mayuscula.

Cada arreglo fue correcto y ninguno fue EL arreglo: mientras la defensa sea por
regla, la quinta regla nace rota igual que las cuatro anteriores.

**Tres formas del mismo texto, y ninguna reemplaza a la otra.**

  original   lo que publico la fuente. Se guarda intacto SIEMPRE: es la
             evidencia, y sin ella no se puede auditar que leimos ni discutir
             una lectura
  reparado   el original con el mojibake deshecho cuando se puede demostrar
             que lo es. Sigue siendo texto legible para una persona
  plegado    la forma de COMPARACION: sin acentos, sin mayusculas, sin
             puntuacion. No se muestra ni se guarda como dato

**Lo que no se toca.** Numeros, monedas, URLs e identificadores no pasan por
reparacion: un id no tiene ortografia, y "arreglarle" un caracter a una URL la
rompe. `reparar` los detecta y los devuelve tal cual.

**Determinismo.** La reparacion solo se aplica cuando el texto vuelve a
codificarse y decodificarse sin perdida Y el resultado tiene menos secuencias
sospechosas que el original. Si no se puede demostrar, no se toca: preferir el
texto raro al texto inventado.

**El caracter de reemplazo no se puede deshacer.** Cuando la fuente ya perdio
el byte -`Circunvalaci�n`- no hay reparacion posible, porque la
informacion no esta. Para esos casos esta `patron`, que construye una
expresion regular donde el caracter perdido matchea cualquier cosa. Es lo unico
honesto: no se adivina que letra era, se admite que puede ser cualquiera.
"""
from __future__ import annotations

import re
import unicodedata

# Secuencias que delatan UTF-8 leido como latin-1. No es una lista de
# reemplazos -eso seria la defensa por caso otra vez- sino la senal de que hay
# que intentar la reparacion completa.
SOSPECHOSAS = re.compile(r"[ÃÂ][-¿]|ï¿½")

REEMPLAZO = "�"

# Un texto que es una URL, un id o un numero no se repara.
URL = re.compile(r"^\s*(?:[a-z][a-z0-9+.-]*://|www\.)", re.I)
SOLO_TECNICO = re.compile(r"^[\w\-.:/@+]*$")


def _es_intocable(texto: str) -> bool:
    """URLs, ids y numeros no tienen ortografia que arreglar."""
    if URL.match(texto):
        return True
    if SOLO_TECNICO.match(texto) and not any(c.isspace() for c in texto):
        # Un token sin espacios ni puntuacion de prosa: id, slug o numero.
        return not any(unicodedata.category(c).startswith("L")
                       and ord(c) > 127 for c in texto)
    return False


def reparar(texto: str | None) -> str | None:
    """Deshace el mojibake cuando se puede DEMOSTRAR que lo es.

    `CircunvalaciÃ³n` es `Circunvalación` leido mal, y eso se
    prueba: al recodificar a latin-1 y decodificar como UTF-8 vuelve un texto
    con menos secuencias sospechosas. `Circunvalaci�n` no es reparable
    -el byte ya se perdio- y se devuelve igual.
    """
    if not texto or not isinstance(texto, str):
        return texto
    if _es_intocable(texto) or not SOSPECHOSAS.search(texto):
        return texto
    try:
        candidato = texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto
    # Solo si mejora. Un texto que ya estaba bien y "mejora" por casualidad
    # seria una reparacion inventada.
    if len(SOSPECHOSAS.findall(candidato)) < len(SOSPECHOSAS.findall(texto)):
        return candidato
    return texto


def sin_acentos(texto: str) -> str:
    """Descompone y descarta los diacriticos, sin tabla escrita a mano.

    Una tabla cubre los que alguien recordo. `unicodedata` cubre los que hay.
    """
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto
                   if unicodedata.category(c) != "Mn")


def plegar(texto: str | None, *, conservar_espacios: bool = True) -> str:
    """La forma de comparacion. NO se guarda ni se muestra.

    Repara, saca acentos, baja a minusculas y colapsa todo lo que no sea
    alfanumerico. `RE/MAX` y `remax` pliegan igual; `Tissera Esquina` y
    `tissera  esquina` tambien.

    `conservar_espacios=False` para comparar nombres donde la separacion no
    significa nada -marcas, identificadores de agencia-.
    """
    if not texto:
        return ""
    base = sin_acentos(reparar(texto) or "").casefold()
    if conservar_espacios:
        return re.sub(r"[^a-z0-9]+", " ", base).strip()
    return re.sub(r"[^a-z0-9]+", "", base)


def patron(texto: str) -> str:
    """Una regex donde cada caracter perdido matchea cualquier cosa.

    Para las reglas que TIENEN que leer texto ya danado en origen. No adivina
    que letra era: admite que puede ser cualquiera, que es lo unico que se
    puede afirmar.
    """
    partes = [("." if c == REEMPLAZO else re.escape(c))
              for c in sin_acentos(reparar(texto) or "")]
    return "".join(partes)


def equivalentes(a: str | None, b: str | None) -> bool:
    """Si dos textos son el mismo, tolerando un caracter perdido de cada lado.

    `Ba�os` y `Banos` son la misma palabra: la unica diferencia esta
    exactamente donde la fuente perdio un byte. Afirmarlo requiere que el
    resto coincida caracter por caracter, no que se parezcan.
    """
    pa, pb = plegar(a), plegar(b)
    if pa == pb:
        return True
    if REEMPLAZO not in (a or "") and REEMPLAZO not in (b or ""):
        return False
    # El plegado convierte el caracter perdido en separador, asi que se
    # compara contra el patron del original.
    for texto, otro in ((a, pb), (b, pa)):
        if REEMPLAZO in (texto or ""):
            regex = patron(texto or "")
            regex = re.sub(r"[^a-z0-9.]+", "[^a-z0-9]*", regex.casefold())
            if re.fullmatch(regex, otro):
                return True
    return False


# Las palabras que el pipeline lee de una ficha. Cuando la fuente perdio un
# byte -`Ba?os`- el caracter no se puede reconstruir en general, pero SI se
# puede reconocer contra un vocabulario declarado: si el token coincide con
# `banos` en todo salvo en la posicion perdida, es esa palabra.
#
# Esto reemplaza a la tabla de cuatro reemplazos escrita a mano que cubria
# `Banos`/`Bano` y nada mas. El vocabulario se declara una vez y vale para
# todas las reglas, que es la diferencia entre una etapa del pipeline y una
# defensa por regla.
VOCABULARIO_DE_CAMPOS = (
    "baño", "baños", "dormitorio", "dormitorios", "habitación", "habitaciones",
    "ambiente", "ambientes", "descripción", "ubicación", "superficie",
    "antigüedad", "cochera", "cocheras", "garage", "toilette", "toilettes",
    "balcón", "balcones", "año", "años", "construcción", "categoría",
    "orientación", "disposición", "expensas", "operación", "código",
)


def _canonico_de(token: str, vocabulario: tuple[str, ...]) -> str | None:
    """La palabra del vocabulario que este token roto puede ser, si es una sola.

    Si dos palabras distintas encajan, no se elige: quedarse con el token roto
    es preferible a inventar cual de las dos era.
    """
    if REEMPLAZO not in token:
        return None
    largo = len(token)
    candidatas = []
    for palabra in vocabulario:
        if len(palabra) != largo:
            continue
        if all(t == REEMPLAZO or t == p
               for t, p in zip(token.casefold(), palabra.casefold())):
            candidatas.append(palabra)
    if len(candidatas) != 1:
        return None
    return candidatas[0]


def _con_la_forma_de(original: str, canonico: str) -> str:
    """Devuelve el canonico respetando mayusculas del original."""
    if original.isupper():
        return canonico.upper()
    if original[:1].isupper():
        return canonico[:1].upper() + canonico[1:]
    return canonico


def normalizar_campos(texto: str | None,
                      vocabulario: tuple[str, ...] = VOCABULARIO_DE_CAMPOS
                      ) -> str:
    """Etiquetas visibles legibles otra vez, sin tabla escrita a mano.

    Primero repara el mojibake -que se puede demostrar-, y despues reconoce
    contra el vocabulario los tokens donde la fuente ya perdio el byte. Lo que
    no encaja con exactamente una palabra del vocabulario se deja como esta.
    """
    reparado = reparar(texto) or ""
    if REEMPLAZO not in reparado:
        return reparado

    def _pieza(m: re.Match) -> str:
        token = m.group(0)
        canonico = _canonico_de(token, vocabulario)
        return _con_la_forma_de(token, canonico) if canonico else token

    return re.sub(r"[^\s<>=\"'/]+", _pieza, reparado)

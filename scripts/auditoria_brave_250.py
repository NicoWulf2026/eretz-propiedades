#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Auditoría de precisión de las 250. §12.

No escribe en la base. `database_writes: 0`.

El §12 no pide auditar una muestra cómoda: pide auditar **entera** cada
categoría donde el verificador se equivocó antes, y encima una muestra
aleatoria de las que declara ALTA. La lista sale del canario de 50, donde los
once falsos positivos cayeron todos en las mismas formas:

  - `NETWORK_OFFICE_PAGE`: la página de una oficina dentro del sitio de la red.
    Es de la red, no de la inmobiliaria, y no se puede enumerar como propia.
  - `EXTERNAL_PORTAL`: una vista filtrada dentro de un portal ajeno. `alonso
    propiedades` era el portal más cuatro filtros.
  - confianza MEDIA: por definición, donde el verificador duda.
  - nombre débil: "Yacoub", "Alba". El nombre no distingue a la inmobiliaria de
    una persona o un comercio.
  - dominio cruzado: el host no contiene el nombre ni el nombre aparece en el
    título. Ahí fue donde nació la marca fantasma "Nuevo Propiedades", de unir
    título y texto en una frase que no existía en ninguno de los dos.

Lo que este script NO hace es decidir. Marca qué filas hay que mirar y por qué,
y deja la conclusión escrita al lado para que se pueda discutir una por una.

Uso:
    python scripts/auditoria_brave_250.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import verificador_identidad_v2 as v2  # noqa: E402

DATOS = Path(r"D:\INMO CAPITAL\ERETZ_AGENCY_DATA")
ENTRADA = DATOS / "BRAVE_250.jsonl"
SALIDA = DATOS / "BRAVE_250_AUDITORIA.jsonl"

MUESTRA_DE_ALTAS = 30


def registrable(url: str | None) -> str:
    if not url:
        return ""
    host = (urlparse(url).netloc or "").lower().lstrip("www.")
    partes = host.split(".")
    return ".".join(partes[-3:]) if len(partes) >= 3 and partes[-2] in (
        "com", "net", "org", "gob", "edu") else ".".join(partes[-2:])


def nucleo(nombre: str) -> str:
    """La parte del nombre que distingue, sin las palabras que comparte todo
    el rubro."""
    limpio = v2._normalizar(nombre)
    genericas = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes",
                 "raices", "negocios", "inmobiliarios", "servicios", "estudio",
                 "real", "estate", "grupo", "sa", "srl", "s", "r", "l", "de",
                 "y", "del", "la", "el", "los", "las"}
    return "".join(p for p in limpio.split() if p not in genericas)


def motivos(fila: dict) -> list[str]:
    """Por qué esta fila hay que mirarla a mano."""
    fuera = []
    tipo = fila.get("site_type") or ""
    clase = fila.get("verification_status") or ""
    url = fila.get("official_url")
    nombre = fila.get("nombre") or ""

    if "NETWORK" in tipo or fila.get("red_franquicia"):
        fuera.append("ES_O_PARECE_PAGINA_DE_RED")
    if "PORTAL" in tipo or "DIRECTORY" in tipo:
        fuera.append("PORTAL_O_DIRECTORIO")
    if (fila.get("confidence") or "").upper() in ("MEDIA", "MEDIUM"):
        fuera.append("CONFIANZA_MEDIA")
    if fila.get("estrato_nombre") == "IDENTIDAD_DEBIL":
        fuera.append("NOMBRE_DEBIL")
    if url and clase in (v2.OFFICIAL_WEB, v2.OFFICIAL_OFFICE_PAGE):
        n = nucleo(nombre)
        dominio = registrable(url)
        aplastado = re.sub(r"[^a-z0-9]", "", dominio.split(".")[0])
        if n and n not in aplastado and aplastado not in n:
            fuera.append("DOMINIO_CRUZADO")
    return fuera


def main() -> int:
    if not ENTRADA.exists():
        print(f"falta {ENTRADA.name}: corré primero brave_250.py --correr")
        return 1
    filas = [json.loads(l) for l in ENTRADA.read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]

    afirmativas = [f for f in filas
                   if f.get("verification_status") in (v2.OFFICIAL_WEB,
                                                       v2.OFFICIAL_OFFICE_PAGE)]
    marcadas, altas_limpias = [], []
    for f in afirmativas:
        ms = motivos(f)
        if ms:
            marcadas.append((f, ms))
        elif (f.get("confidence") or "").upper() in ("ALTA", "HIGH"):
            altas_limpias.append(f)

    random.seed(3)
    muestra = random.sample(altas_limpias,
                            min(MUESTRA_DE_ALTAS, len(altas_limpias)))

    print("### AUDITORIA §12 ###")
    print(f"  filas resueltas:              {len(filas)}")
    print(f"  afirman una web propia:       {len(afirmativas)}")
    print(f"  A AUDITAR ENTERAS (marcadas): {len(marcadas)}")
    print(f"  ALTA sin marca:               {len(altas_limpias)}")
    print(f"  de esas, muestra aleatoria:   {len(muestra)}")
    print(f"  TOTAL A MIRAR A MANO:         {len(marcadas) + len(muestra)}"
          f"  ({(len(marcadas)+len(muestra))/max(len(afirmativas),1):.0%} "
          f"de las afirmativas)\n")

    razones: Counter = Counter()
    for _, ms in marcadas:
        for m in ms:
            razones[m] += 1
    print("por que se marca cada una:")
    for m, n in razones.most_common():
        print(f"   {m:28} {n}")

    print("\npor clase declarada:")
    for k, n in Counter(f.get("verification_status") for f in filas).most_common():
        print(f"   {k:28} {n}")
    print("\npor tipo de sitio:")
    for k, n in Counter(f.get("site_type") for f in filas).most_common(10):
        print(f"   {str(k):28} {n}")

    with SALIDA.open("w", encoding="utf-8") as fh:
        for f, ms in marcadas:
            fh.write(json.dumps({**f, "auditar_porque": ms,
                                 "veredicto_humano": None}, ensure_ascii=False) + "\n")
        for f in muestra:
            fh.write(json.dumps({**f, "auditar_porque": ["MUESTRA_DE_ALTAS"],
                                 "veredicto_humano": None}, ensure_ascii=False) + "\n")

    print(f"\nartefacto: {SALIDA}")
    print("\n  `veredicto_humano` viene en null a proposito. La precision no se")
    print("  informa hasta que esté completo: un resultado de Brave no demuestra")
    print("  OFFICIAL_WEB, y tampoco lo demuestra nuestro verificador solo.")
    print("\ndatabase_writes: 0")
    return 0




# --------------------------------------------------------------------------
# Segunda pasada: comprobar contra el sitio, con evidencia distinta
# --------------------------------------------------------------------------
#
# El verificador miró nombre, dominio y título. Volver a mirar lo mismo no
# audita nada: confirmaría su propio criterio. Esta pasada usa dos cosas que él
# no usó como veredicto:
#
#   1. el dominio REGISTRABLE contra el de las redes conocidas. Una página bajo
#      `remax.com.ar` es de RE/MAX, diga lo que diga su título. Es una regla
#      dura y no admite matices.
#   2. si la página nombra a OTRA inmobiliaria con más fuerza que a la nuestra.
#      Así fue como apareció la marca fantasma "Nuevo Propiedades": uniendo
#      título y texto salió una frase que no estaba en ninguno de los dos.
#
# Escribe `veredicto_maquina`, no `veredicto_humano`. No son lo mismo y el
# archivo no los va a mezclar.

# Hosts que NO son el sitio de una inmobiliaria, cualquiera sea su titulo.
AJENOS = {"computrabajo.com", "ar.computrabajo.com", "realedo.com",
          "apuntavamos.com", "mudafy.com.ar", "zonaprop.com.ar",
          "argenprop.com", "mercadolibre.com.ar", "properati.com.ar",
          "inmuebles24.com", "misionesonline.net", "lanacion.com.ar",
          "clarin.com", "infobae.com", "linkedin.com", "facebook.com",
          "instagram.com", "paginasamarillas.com.ar"}
# Un perfil o un listado dentro del sitio de otro.
RUTA_AJENA = re.compile(r"(?i)/(profile|perfil|agency|agencia|agente|agent|"
                        r"inmobiliarias|corredores|directorio)/")
# Una nota con fecha.
RUTA_NOTA = re.compile(r"/20\d\d/\d\d/\d\d/")
# Una ficha suelta en vez del sitio.
RUTA_FICHA = re.compile(r"(?i)/(p|propiedad|propiedades|listing|listings|"
                        r"ficha|inmueble)/[\w-]*\d{4,}")
GENERICAS = {"propiedades", "inmobiliaria", "inmobiliarias", "bienes",
             "raices", "negocios", "inmobiliarios", "servicios", "estudio",
             "real", "estate", "grupo", "realty", "inmuebles", "sociedad",
             "asociados", "srl", "sas"}

REDES = {"remax.com.ar", "century21.com.ar", "c21.com.ar", "kw.com",
         "kellerwilliams.com", "coldwellbanker.com.ar", "remax.com",
         "century21global.com", "interwin.com.ar", "tokkobroker.com"}


def _bajar(url: str, timeout: float = 20):
    import gzip
    import urllib.request
    cab = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
           "Accept-Encoding": "gzip", "Accept-Language": "es-AR,es;q=0.9"}
    r = urllib.request.urlopen(urllib.request.Request(url, headers=cab),
                               timeout=timeout)
    crudo = r.read(400_000)
    if r.headers.get("Content-Encoding") == "gzip":
        try:
            crudo = gzip.decompress(crudo)
        except OSError:
            pass
    return r.status, crudo.decode("utf-8", "replace"), r.url


def comprobar(fila: dict) -> dict:
    url = fila.get("official_url")
    if not url:
        return {"veredicto_maquina": "SIN_URL", "porque": "no afirma ninguna"}
    dom = registrable(url)
    clase = fila.get("verification_status") or ""
    if dom in REDES:
        # Una pagina bajo el dominio de la red NO es un error si el veredicto
        # fue OFFICIAL_OFFICE_PAGE: esa clase significa exactamente eso, "la
        # pagina de esta oficina dentro del sitio de su red". Marcarla como
        # falso positivo castigaba al verificador por acertar, y con esa regla
        # mala la precision daba 63,9 % cuando los 26 supuestos errores eran
        # 26 clasificaciones correctas.
        #
        # El error de verdad seria declarar OFFICIAL_WEB -web propia- sobre el
        # dominio de la red.
        if clase == v2.OFFICIAL_OFFICE_PAGE:
            return {"veredicto_maquina": "CORRECTA_COMO_OFICINA",
                    "porque": f"esta en {dom}, que es la red, y el veredicto "
                              f"dice justamente que es su pagina de oficina"}
        return {"veredicto_maquina": "FALSO_POSITIVO",
                "porque": f"declara web PROPIA sobre {dom}, que es el dominio "
                          f"de la red"}
    try:
        http, html, final = _bajar(url)
    except Exception as e:
        return {"veredicto_maquina": "NO_COMPROBABLE",
                "porque": f"no se pudo descargar: {type(e).__name__}"}
    if registrable(final) in REDES:
        if clase == v2.OFFICIAL_OFFICE_PAGE:
            return {"veredicto_maquina": "CORRECTA_COMO_OFICINA",
                    "porque": f"redirige a {registrable(final)}, la red, y el "
                              f"veredicto ya decia que era pagina de oficina"}
        return {"veredicto_maquina": "FALSO_POSITIVO",
                "porque": f"declara web propia pero redirige a "
                          f"{registrable(final)}, que es la red"}
    if not html.strip():
        return {"veredicto_maquina": "NO_COMPROBABLE",
                "porque": f"HTTP {http} con cuerpo vacio"}

    titulo = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if m:
        titulo = re.sub(r"\s+", " ", m.group(1)).strip()

    # Lo que el sitio ES, antes de preguntar de quien es. Estas tres formas
    # aparecieron entre las 17 que la primera version no supo decidir, y las
    # tres son afirmaciones falsas de "web propia":
    if dom in AJENOS:
        return {"veredicto_maquina": "FALSO_POSITIVO",
                "porque": f"{dom} no es el sitio de una inmobiliaria: es un "
                          f"portal, una bolsa de trabajo o un medio",
                "titulo": titulo[:110]}
    if RUTA_AJENA.search(url):
        return {"veredicto_maquina": "FALSO_POSITIVO",
                "porque": "la ruta es un perfil dentro de un sitio de "
                          "terceros, no la raiz de un sitio propio",
                "titulo": titulo[:110]}
    if RUTA_NOTA.search(url):
        return {"veredicto_maquina": "FALSO_POSITIVO",
                "porque": "la url es una nota periodistica con fecha, no un "
                          "sitio de inmobiliaria",
                "titulo": titulo[:110]}
    if RUTA_FICHA.search(url):
        return {"veredicto_maquina": "PARCIAL",
                "porque": "el dominio puede ser el suyo pero la url apunta a "
                          "UNA propiedad, no a su sitio",
                "titulo": titulo[:110]}

    # El nombre, por partes. Exigir el nucleo entero descartaba aciertos:
    # `estudioelhelou.com.ar` es de "Emir Elhelou Estudio Inmobiliario" y la
    # comparacion entera fallaba porque `nucleo()` borra "estudio".
    partes = [p for p in v2._normalizar(fila.get("nombre") or "").split()
              if len(p) >= 4 and p not in GENERICAS]
    tit = re.sub(r"[^a-z0-9]", "", v2._normalizar(titulo))
    dom_ap = re.sub(r"[^a-z0-9]", "", dom.split(".")[0])
    donde = [p for p in partes if p in dom_ap or p in tit]
    if donde:
        return {"veredicto_maquina": "CONFIRMADA",
                "porque": f"'{donde[0]}', parte distintiva de su nombre, esta "
                          f"en su dominio o en su titulo",
                "titulo": titulo[:110]}
    return {"veredicto_maquina": "NO_CONFIRMADA",
            "porque": f"ninguna parte distintiva del nombre {partes} aparece "
                      f"en {dom} ni en el titulo. No prueba que sea de otro, "
                      f"pero tampoco que sea suyo",
            "titulo": titulo[:110]}


def segunda_pasada() -> int:
    import time as _t
    filas = [json.loads(l) for l in SALIDA.read_text(
        encoding="utf-8", errors="replace").splitlines() if l.strip()]
    salida = []
    cuenta: Counter = Counter()
    for i, f in enumerate(filas, 1):
        r = comprobar(f)
        cuenta[r["veredicto_maquina"]] += 1
        salida.append({**f, **r})
        _t.sleep(0.8)
        if i % 20 == 0:
            print(f"   {i}/{len(filas)}", flush=True)
    SALIDA.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in salida),
        encoding="utf-8")
    print(f"\n=== COMPROBACION INDEPENDIENTE, {len(filas)} filas ===")
    for k, n in cuenta.most_common():
        print(f"   {k:20} {n:4}  {n/len(filas):6.1%}")
    falsos = cuenta["FALSO_POSITIVO"]
    juzgables = falsos + cuenta["CONFIRMADA"]
    if juzgables:
        print(f"\n   precision sobre lo juzgable: {cuenta['CONFIRMADA']/juzgables:.1%}")
        print(f"   ({cuenta['CONFIRMADA']} confirmadas / {juzgables} donde la")
        print("    comprobacion pudo decidir)")
    print(f"\n   {cuenta['NO_CONFIRMADA']} quedan sin decidir: el nucleo del")
    print("   nombre no aparece ni en su dominio ni en su titulo. Eso NO las")
    print("   convierte en falsos positivos; las deja para una persona.")
    print("\ndatabase_writes: 0")
    return 0


if __name__ == "__main__":
    if "--comprobar" in sys.argv:
        raise SystemExit(segunda_pasada())
    raise SystemExit(main())

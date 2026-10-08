#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Caracteristicas de la propiedad que los extractores YA leen y que no llegaban a la API.

Mision 08-10 (`docs/agent/MISION_PADRON_COMPLETO.md`, punto 10). Medido sobre los 1.270 paquetes vigentes:
antiguedad 41k fichas, condicion 27k, orientacion 20k, situacion 20k, disposicion 16k, cocheras 16k,
plantas 14k, expensas 11,7k, apto credito 7k, codigo de origen 34k, fecha de modificacion 7,5k. Quedaban en
`extra` y la snapshot servia solo los 19 campos basicos.

Reglas (las mismas del resto del contrato):
- solo vocabulario limpio: "Frente Numero De Piso De ..." es un rotulo pegado al siguiente, no una
  disposicion; se descarta y se cuenta, no se adivina;
- rangos fisicos: fuera de rango -> None;
- no se infiere: "A estrenar" no es "0 anos"; expensas sin moneda publicada quedan sin moneda;
- nada de esto toca la huella: se calcula al construir la snapshot desde lo que el extractor dejo.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

VERSION = "caracteristicas_v1"


def _plano(texto: Any) -> str:
    s = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[_\s]+", " ", s).strip(" :.-")
    return s


def _vocabulario(texto: Any, vocab: dict[str, str]) -> str | None:
    """El valor solo si ES una palabra del vocabulario (despues de quitar ' :' finales)."""
    return vocab.get(_plano(texto))


ORIENTACION = {p: p.title() for p in ("norte", "sur", "este", "oeste", "noreste", "noroeste", "sudeste",
                                       "sudoeste")}
ORIENTACION.update({"suroeste": "Sudoeste", "sureste": "Sudeste", "n": None, "s": None})
DISPOSICION = {"frente": "Frente", "contrafrente": "Contrafrente", "interno": "Interno", "lateral": "Lateral",
               "esquina": "Esquina"}
CONDICION = {"excelente": "Excelente", "muy bueno": "Muy bueno", "bueno": "Bueno", "reciclado": "Reciclado",
             "a refaccionar": "A refaccionar", "regular": "Regular", "semi nuevo": "Semi nuevo",
             "usado": "Usado", "nuevo": "Nuevo", "a estrenar": "A estrenar", "reformado": "Reformado"}
SITUACION = {"vacia": "Vacia", "habitada": "Habitada", "constructora": "Constructora",
             "propietario": "Propietario", "inquilino": "Inquilino"}
ESTADO_FUENTE = {"disponible": "disponible", "vendido": "vendida", "vendida": "vendida",
                 "reservado": "reservada", "reservada": "reservada", "alquilado": "alquilada",
                 "alquilada": "alquilada"}


def _entero(valor: Any, minimo: int, maximo: int) -> int | None:
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    if f != int(f) or not minimo <= f <= maximo:
        return None
    return int(f)


def antiguedad(valor: Any) -> dict[str, Any] | None:
    s = _plano(valor)
    if not s:
        return None
    if s == "a estrenar":
        return {"a_estrenar": True}
    if s in ("en construccion", "en pozo"):
        return {"en_construccion": True}
    m = re.fullmatch(r"(\d{1,3})( anos?)?", s)
    if m:
        anios = _entero(m.group(1), 0, 200)
        return {"anios": anios} if anios is not None else None
    return None


def caracteristicas_de(extra: dict[str, Any] | None) -> dict[str, Any]:
    """Las caracteristicas publicables de una fila, con su procedencia. Vacio si no hay ninguna."""
    e = extra or {}
    out: dict[str, Any] = {}
    cocheras = _entero(e.get("cocheras"), 0, 50)
    if cocheras is not None:
        out["cocheras"] = cocheras
    plantas = _entero(e.get("plantas"), 1, 200)
    if plantas is not None:
        out["plantas"] = plantas
    suites = _entero(e.get("suites"), 0, 30)
    if suites is not None:
        out["suites"] = suites
    ant = antiguedad(e.get("antiguedad"))
    if ant:
        out["antiguedad"] = ant
    try:
        expensas = float(e.get("expensas")) if e.get("expensas") not in (None, "") else None
    except (TypeError, ValueError):
        expensas = None
    if expensas and 0 < expensas < 1e8:
        # La moneda solo si la fuente la publico junto al importe; si no, queda vacia.
        out["expensas"] = {"monto": expensas, "moneda": e.get("expensas_moneda") or None}
    for clave, vocab in (("orientacion", ORIENTACION), ("disposicion", DISPOSICION),
                         ("condicion", CONDICION), ("situacion", SITUACION)):
        valor = _vocabulario(e.get(clave), vocab)
        if valor:
            out[clave] = valor
    if "condicion" not in out:
        valor = _vocabulario(e.get("estado_inmueble"), CONDICION)
        if valor:
            out["condicion"] = valor
    estado = _vocabulario(e.get("estado_fuente"), ESTADO_FUENTE)
    if estado:
        out["estado_en_fuente"] = estado
    if e.get("apto_credito") is True:
        out["apto_credito"] = True
    codigo = e.get("codigo_fuente") or e.get("referencia")
    if isinstance(codigo, str) and 0 < len(codigo.strip()) <= 40:
        out["codigo_en_fuente"] = codigo.strip()
    modificado = e.get("modificado_en_fuente")
    if isinstance(modificado, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:]{8})?", modificado):
        out["modificado_en_fuente"] = modificado
    superficie_privada = e.get("superficie_privada")
    try:
        if superficie_privada is not None and 0 < float(superficie_privada) < 1e6:
            out["superficie_privada"] = float(superficie_privada)
    except (TypeError, ValueError):
        pass
    if out:
        out["procedencia"] = {"version": VERSION, "origen": "extraido_de_la_ficha"}
    return out

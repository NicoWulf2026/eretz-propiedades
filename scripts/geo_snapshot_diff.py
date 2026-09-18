#!/usr/bin/env python
"""Compara dos snapshots de GeoRef antes de reemplazar el catalogo.

Un catalogo externo no puede cambiar en silencio. Si GeoRef renombra una
localidad o le cambia el id, las propiedades que ya normalizamos quedan
apuntando a algo que ya no existe, y eso no se nota hasta que alguien busca por
ciudad y no encuentra nada.

Compara por `official_id`, que es lo unico estable, y separa lo que agrega de lo
que saca y de lo que cambia de nombre o de provincia. Cambiar de provincia es lo
mas grave: mueve propiedades de lugar sin que nadie las haya tocado.

No reemplaza nada. Produce el informe para decidir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.geo_reference import verified_rows  # noqa: E402

RECURSOS = ("provincias", "departamentos", "municipios",
            "localidades_censales", "localidades", "asentamientos")
JERARQUIAS = ('provincia', 'departamento', 'municipio', 'localidad_censal', 'localidad')


def _contexto(row: dict[str, Any], campo: str) -> dict[str, Any]:
    value = row.get(campo)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f'GeoRef {campo} context must be an object or null')
    return value


def indexar(directorio: Path, recurso: str) -> dict[str, dict[str, Any]]:
    return {row['id']: row for row in verified_rows(directorio, recurso)}


def comparar(viejo: dict[str, dict[str, Any]],
             nuevo: dict[str, dict[str, Any]]) -> dict[str, Any]:
    agregados = sorted(set(nuevo) - set(viejo))
    eliminados = sorted(set(viejo) - set(nuevo))
    renombrados = []
    mudados = []
    jerarquias = []
    otros = []
    for identificador in sorted(set(viejo) & set(nuevo)):
        antes, despues = viejo[identificador], nuevo[identificador]
        if antes.get("nombre") != despues.get("nombre"):
            renombrados.append({"id": identificador,
                                "antes": antes.get("nombre"),
                                "despues": despues.get("nombre")})
        provincia_antes = _contexto(antes, 'provincia')
        provincia_despues = _contexto(despues, 'provincia')
        if provincia_antes != provincia_despues:
            mudados.append({"id": identificador,
                            "nombre": despues.get("nombre"),
                            "antes": provincia_antes.get('nombre'),
                            "despues": provincia_despues.get('nombre'),
                            "contexto_antes": provincia_antes,
                            "contexto_despues": provincia_despues})
        for campo in JERARQUIAS:
            a, b = _contexto(antes, campo), _contexto(despues, campo)
            if a != b:
                jerarquias.append({'id': identificador, 'campo': campo,
                                  'antes': a, 'despues': b})
        # Do not assume that the API will always use the same geometry keys.
        # Report any other changed attribute, including centroid and geometry.
        campos = (set(antes) | set(despues)) - set(JERARQUIAS) - {'id', 'nombre'}
        for campo in sorted(campos):
            if (campo in antes) != (campo in despues) or antes.get(campo) != despues.get(campo):
                otros.append({'id': identificador, 'campo': campo,
                              'presente_antes': campo in antes, 'presente_despues': campo in despues,
                              'antes': antes.get(campo), 'despues': despues.get(campo)})
    return {
        "antes": len(viejo), "despues": len(nuevo),
        "agregados": len(agregados), "eliminados": len(eliminados),
        "renombrados": len(renombrados), "cambiaron_de_provincia": len(mudados),
        "ids_eliminados": eliminados[:50],
        "detalle_renombrados": renombrados[:50],
        "detalle_mudados": mudados[:50],
        "cambios_de_jerarquia": len(jerarquias),
        "detalle_jerarquias": jerarquias[:50],
        "otros_cambios": len(otros),
        "detalle_otros_cambios": otros[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("anterior")
    parser.add_argument("nuevo")
    parser.add_argument("--salida")
    args = parser.parse_args()

    anterior, nuevo = Path(args.anterior), Path(args.nuevo)
    informe: dict[str, Any] = {"anterior": str(anterior), "nuevo": str(nuevo),
                               'replacement_authorized': False,
                               "recursos": {}}
    for archivo in ("MANIFEST.json",):
        for etiqueta, base in (("manifiesto_anterior", anterior),
                               ("manifiesto_nuevo", nuevo)):
            ruta = base / archivo
            if ruta.exists():
                manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
                informe[etiqueta] = {
                    "descargado": manifiesto.get("descargado"),
                    "sha256": {k: v.get("sha256") for k, v
                               in (manifiesto.get("recursos") or {}).items()},
                }

    riesgo = 0
    for recurso in RECURSOS:
        resultado = comparar(indexar(anterior, recurso), indexar(nuevo, recurso))
        informe["recursos"][recurso] = resultado
        riesgo += (resultado["eliminados"] + resultado["renombrados"]
                   + resultado["cambios_de_jerarquia"] + resultado["otros_cambios"])
        print(f"  {recurso:22} {resultado['antes']:6} -> {resultado['despues']:6}"
              f" | +{resultado['agregados']:<5} -{resultado['eliminados']:<5}"
              f" renombrados {resultado['renombrados']:<4}"
              f" mudados {resultado['cambiaron_de_provincia']}")

    if args.salida:
        Path(args.salida).write_text(
            json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    if riesgo:
        print(f"REVISAR ANTES DE REEMPLAZAR: {riesgo} eliminaciones o cambios "
              f"de atributos detectados. Las propiedades que los referencian "
              f"quedarian apuntando a algo distinto.")
        return 1
    print("Sin eliminaciones ni cambios de atributos detectados. Este diagnóstico no autoriza el reemplazo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

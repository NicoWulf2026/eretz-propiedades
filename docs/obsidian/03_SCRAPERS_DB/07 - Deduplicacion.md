# Deduplicacion de propiedades

Ultima actualizacion: 2026-06-09

---

## Politica oficial

Si una misma propiedad aparece publicada en varias inmobiliarias, se conservan como publicaciones separadas.

No se fusionan automaticamente en una unica publicacion.

---

## Clasificacion de duplicados

| Tipo | Descripcion | Accion |
|------|-------------|--------|
| Duplicado exacto | Misma URL, mismo hash, misma publicacion repetida por el mismo origen | Bloquear import. No duplicar en raw ni staging. |
| Misma propiedad por varias inmobiliarias | La misma propiedad aparece publicada en 2 o mas inmobiliarias distintas | Conservar ambas publicaciones. No bloquear. Marcar como posible duplicado cross-agency. |
| Posible duplicado dudoso | Misma direccion aproximada, mismo precio, distinto origen | Conservar. Marcar para revision futura. |

---

## Comportamiento en el pipeline

- El import bloquea duplicados exactos (misma URL + misma inmobiliaria).
- No bloquea publicaciones de la misma propiedad por distintas inmobiliarias.
- Se registra el flag `possible_cross_agency_duplicate` como informacion, no como rechazo.

---

## Comportamiento futuro en frontend

A futuro puede mostrarse en el detalle de una propiedad:
"Tambien publicada por: [otras inmobiliarias]"

Esto requiere:
- Algoritmo de matching por coordenadas + tipo + operacion + superficie.
- Umbral de similitud configurable.
- No fusion automatica, solo indicacion.

Por ahora: no implementar. Conservar publicaciones separadas.

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[08 - Estados de propiedades]]

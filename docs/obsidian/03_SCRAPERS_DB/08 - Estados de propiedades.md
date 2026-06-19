# Estados de propiedades

Ultima actualizacion: 2026-06-09 (Sprint B cerrado)

---

## Estados posibles

| Estado | Descripcion |
|--------|-------------|
| `activa` | La propiedad esta publicada y disponible en la web original. |
| `reservada` | La propiedad fue reservada pero todavia no se concretó la operacion. |
| `vendida` | La propiedad fue vendida. |
| `alquilada` | La propiedad fue alquilada. |
| `no_detectada_en_ultimo_scraping` | La propiedad no aparecio en el ultimo scraping pero no hay confirmacion de que se haya vendido o alquilado. |
| `consultar` | Estado incierto. Se desconoce la disponibilidad actual. |
| `desconocida` | No hay informacion suficiente para asignar un estado. |

---

## Reglas de transicion

### Cuando la propiedad deja de aparecer en el sitio original

- No se borra de la base de datos.
- Se conserva como historico.
- Se marca como `no_detectada_en_ultimo_scraping`.
- No debe cambiarse automaticamente a `vendida` salvo que el sitio original lo confirme.

Motivo: una propiedad puede desaparecer del sitio por un error de scraping, por mantenimiento del sitio, por pausa temporal de la publicacion o por cambio de URL, no necesariamente por estar vendida o alquilada.

### Cuando el sitio original indica estado final

- Si dice "vendida": registrar `vendida`.
- Si dice "alquilada": registrar `alquilada`.
- Si dice "reservada": registrar `reservada`.

### Cuando no hay certeza

- Si no se puede determinar: `consultar` o `desconocida`.

---

## Visibilidad en el frontend

| Estado | Visible en listado | Visible en mapa | Cartel |
|--------|-------------------|-----------------|--------|
| `activa` | Si | Si (con coords) | — |
| `reservada` | Si | Si (con coords) | "Reservada" |
| `vendida` | Si | Si (con coords) | "Vendida" |
| `alquilada` | Si | Si (con coords) | "Alquilada" |
| `no_detectada_en_ultimo_scraping` | Si | Si (con coords) | "Sin datos recientes" |
| `consultar` | Si | Si (con coords) | "Consultar disponibilidad" |
| `desconocida` | Si | Si (con coords) | — |

Regla: ninguna propiedad se elimina del listado publico por su estado. Solo se agrega un cartel informativo cuando corresponde.

---

## Operaciones posibles

Una propiedad puede tener mas de una operacion a la vez:

- Venta.
- Alquiler.
- Venta y alquiler simultaneamente.

Si se desconoce la operacion: mostrar "Consultar".

---

## Datos obligatorios / opcionales

| Campo | Obligatorio | Sin dato: mostrar |
|-------|-------------|-------------------|
| Tipo de propiedad | No | Tipo desconocido |
| Operacion (venta/alquiler) | No | Consultar |
| Precio | No | Consultar precio |
| Moneda | No | Consultar |
| Superficie | No | — |
| Coordenadas | No | Sin mapa (aparece en listado) |
| Imagenes | No | Placeholder |
| Descripcion | No | — |
| Inmobiliaria | No | — |
| Link original | No | — |

Ningun campo faltante debe bloquear la publicacion de la propiedad.

---

---

## Estado de implementacion

| Item | Estado |
|------|--------|
| Schema Supabase con 7 estados | ✅ Ejecutado 2026-06-09 |
| Migracion activo → activa | ✅ 90.497 filas |
| Migracion inactivo → desconocida | ✅ 829 filas |
| Constraint SQL en Supabase | ✅ Activa |
| Frontend compatibilidad dual activo/activa | ✅ Sprint A |
| Scraper: genera `"activa"` (no `"activo"`) | ✅ Sprint B |
| `mark_inactivos()` busca activo/activa, marca `no_detectada_en_ultimo_scraping` | ✅ Sprint B |
| `publish_to_supabase.py`: estado default `"activa"` en nuevas publicaciones | ✅ Sprint B |
| Cartel de estado en frontend publico | ⏸ Sprint D |

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[07 - Deduplicacion]]
- [[03 - Modelo de datos propiedades]]
- [[2026-06-09 - Registro diario]]

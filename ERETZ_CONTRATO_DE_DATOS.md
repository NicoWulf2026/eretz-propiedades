# Contrato de datos de producción — para el frontend

**Medido el 2026-09-14 sobre las 257.073 filas reales de `public.propiedades`.**
No son estimaciones ni el esquema: son los datos que hay. `database_writes: 0`.

Esto es lo que el §25 asigna a Claude y Codex necesita para no construir sobre
supuestos: qué campos se pueden usar sin defensa, cuáles hay que defender, y
los tres casos donde renderizar el dato crudo produce un error visible.

---

## 1. Lo que hay, en porcentaje de filas

| campo | lleno | se puede usar sin defensa |
|---|---:|---|
| `url`, `operacion`, `tipo_propiedad` | **100 %** | sí |
| `descripcion` | 94,7 % | casi |
| `barrio` | 88,4 % | no |
| `direccion` | 80,2 % | no |
| `titulo` | **72,9 %** | **no** |
| `imagenes` (con al menos una) | **69,3 %** | **no** |
| `precio` | 65,5 % | **no** |
| `moneda` | 59,5 % | **no** |
| `ambientes` | 50,9 % | no |
| `banos` | 45,7 % | no |
| `superficie_total` | 46,0 % | no |
| `ciudad` / `provincia` | **43,2 %** | **no** |
| `dormitorios` | 41,5 % | no |
| `latitud` / `longitud` | 25,3 % | no |
| `superficie_cubierta` | **0,7 %** | tratarlo como inexistente |

Sólo tres campos están siempre: `url`, `operacion` y `tipo_propiedad`. Todo lo
demás necesita un camino para cuando falta.

---

## 2. Los tres que rompen el producto si se renderizan crudos

### 2.1 Precio sin moneda — 28.989 filas

**El más grave.** De las 168.385 filas con precio, **28.989 no tienen moneda**:
el 17 %.

Las monedas que existen son exactamente dos: `ARS` y `USD`. Entre una y otra
hay un factor de mil. Mostrar `450.000` sin saber cuál es no es un detalle
estético: es informar mal un precio.

**Regla:** `precio` no se muestra nunca sin `moneda`. Si falta la moneda, la
propiedad se muestra como *"Consultar precio"*, igual que si no tuviera precio.

(Al revés hay 13.685 filas con moneda y sin precio. Eso es ruido inofensivo:
sin precio no se muestra nada.)

### 2.2 Ciudad y provincia — 43,2 %

**Más de la mitad del catálogo no tiene ciudad ni provincia.** Es el filtro
principal de cualquier sitio inmobiliario, así que conviene decidirlo
explícitamente y no descubrirlo en producción.

Las dos se mueven juntas —sólo 274 filas tienen provincia sin ciudad y 468 al
revés—, así que no es una inconsistencia entre campos: es un hueco parejo.

`barrio` está mejor (88,4 %) pero no sustituye: un barrio sin ciudad no
ubica nada.

**Decisión pendiente, y es de producto:** un filtro por ubicación que excluya
al 57 % del catálogo, o una categoría *"sin ubicación"* visible. Lo que no
funciona es filtrar en silencio.

### 2.3 Título e imágenes — 27 % y 31 % faltantes

Una tarjeta de listado necesita las dos cosas. **72,9 %** tiene título y
**69,3 %** tiene al menos una imagen.

Para el título hay reemplazo derivable: `tipo_propiedad` + `barrio` o `ciudad`
+ `operacion` están en el 100 %, 88 % y 100 % respectivamente. Para la imagen
hay que decidir un placeholder.

---

## 3. Geografía

`latitud`/`longitud` están en el 25,3 %. Una vista de mapa cubre un cuarto del
catálogo.

962 filas tienen coordenadas **sin** ciudad o provincia. Ahí las coordenadas
son la única ubicación que hay, así que el texto de ubicación se puede derivar
de ellas por geocodificación inversa — pero eso es un dato *derivado* y hay que
marcarlo como tal, no mezclarlo con el que declara la fuente.

---

## 4. Identidad y duplicados

Las dos defensas existen y son `UNIQUE`:

```
propiedades_hash_dedup_key                          UNIQUE (hash_dedup)
idx_propiedades_unique_inmobiliaria_url_normalizada UNIQUE (inmobiliaria_id, url_normalizada)
                                                    WHERE url_normalizada IS NOT NULL AND <> ''
```

Con:

```
hash_dedup = left( sha256( inmobiliaria_id || '|url|' || url_normalizada ), 32 )
```

**Lo que el frontend tiene que saber:** `hash_dedup` **no es un id estable**.
Depende de `inmobiliaria_id`, así que si una inmobiliaria se fusiona con otra,
el hash de todas sus propiedades cambia. No sirve como clave de favoritos, de
comparación ni de URL compartible. Para eso está `propiedades.id`, que es la
PK y no se mueve.

---

## 5. Acceso

Hoy, sobre las cuatro tablas centrales:

| tabla | RLS | políticas | `anon` SELECT | `authenticated` SELECT |
|---|---|---:|---|---|
| `inmobiliarias_main` | sí | 5 | **no** | **no** |
| `inmobiliarias_staging` | sí | 4 | no | no |
| `propiedades` | sí | 3 | **no** | **no** |
| `inmobiliarias_scraping` | sí | 0 | no | no |

No es un problema de políticas: **falta el GRANT a nivel tabla**. Tiene dos
lecturas y hay que elegir una a propósito:

- si el frontend lee **a través de un backend** con service role, esto es
  correcto y es el diseño seguro;
- si el frontend consulta Supabase **directo con la anon key**, hoy recibe cero
  filas y es un bloqueante de lanzamiento.

---

## 6. Escala

```
propiedades                    257.073
inmobiliarias con propiedades    3.187
inmobiliarias en main            7.004
propiedades huérfanas                0
```

Cero huérfanas: toda propiedad tiene una inmobiliaria válida. El join es seguro
sin `LEFT`.

Las 3.187 con propiedades sobre 7.004 filas de `main` significan que **más de
la mitad de las inmobiliarias no tiene ninguna propiedad publicada**. Una
página de inmobiliaria tiene que contemplar el catálogo vacío como caso normal,
no como error.

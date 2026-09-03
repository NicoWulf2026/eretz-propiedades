# ERETZ — Contrato de propiedad

Qué promete ERETZ sobre cada propiedad que publica, y qué explícitamente no
promete.

Estado: **especificación V1.** Diseño y dry-run; sin escrituras productivas.

---

## 1. El principio que ordena todo

**Una propiedad real e incompleta se publica.**

Un campo que falta no convierte una propiedad real en inválida. Ya costó caro
haberlo hecho al revés: faltar operación o tipo marcaba la fila
`INVALID_OR_REJECTED` y **13.023 propiedades reales no llegaban a la base** —el
84 % con precio, el 90 % con descripción, el 61 % con coordenadas—. Se
descartaban por un atributo que el aviso no publicaba.

De ahí la regla: **la ausencia se anota, no descarta.**

Lo contrario también es regla: **no se inventa nada.** Si la fuente no lo dice y
no se puede derivar de forma demostrable, el campo queda ausente y dice por qué.

---

## 2. Los cuatro estados de un campo

Cada campo del contrato lleva uno de estos cuatro estados. La diferencia no es
cosmética: separa un defecto nuestro de un límite de la fuente, y sin ella no se
puede saber a quién reclamarle.

| Estado | Significa | ¿Es un defecto nuestro? |
|---|---|---|
| `EXTRACTED` | La fuente lo publica y lo leímos | — |
| `SOURCE_NOT_PROVIDED` | La fuente no lo publica | **No.** No hay nada que arreglar |
| `REJECTED_BY_VALIDATION` | Lo leímos y la validación lo rechazó | **No.** El guardián hizo su trabajo |
| `EXTRACTION_FAILED` | La fuente lo publica y no lo pudimos leer | **Sí.** Único que bloquea certificación |

Ejemplos reales de cada uno:

- `SOURCE_NOT_PROVIDED` — el bloque de ambientes de `alagnapropiedades.com.ar`
  vive dentro de un comentario HTML con la `X` de la plantilla. Ningún navegador
  lo muestra: la fuente no lo publica.
- `REJECTED_BY_VALIDATION` — `dormitorios > ambientes` en una misma ficha. Un
  par imposible; se descartan los dos valores y se registra el motivo.
- `EXTRACTION_FAILED` — la ficha rotula `Baños 2` en una tabla y no lo leímos.

**Hueco conocido:** hoy los cuatro estados se calculan **por inmobiliaria** en
`field_audit`, no por propiedad en la preingestión. Ahí sólo existe
`campos_pendientes`, que cubre operación y tipo. Llevar los cuatro estados al
registro de cada propiedad es el trabajo pendiente de este contrato.

---

## 3. Las columnas del contrato

Lo que el pipeline promete, ya definido en `COLUMNAS_DEL_CONTRATO`:

```
titulo  descripcion  precio  moneda  operacion  tipo_propiedad
direccion  barrio  ciudad  provincia  latitud  longitud
dormitorios  banos  ambientes  superficie_total  superficie_cubierta
imagenes  source_status
```

Todo lo que una plataforma publica de más viaja en `extra`, tal cual, sin
promesa.

**La distinción no es de conveniencia.** Los cinco defectos reales encontrados
—prosa como barrio, tipo adivinado, ficha vacía, atributos corridos, fotos
ajenas— se manifestaron **todos** en columnas del contrato. Ninguno en `extra`.
Por eso la idempotencia se juzga con `firma_de_columnas` y no con la firma
completa: que la fuente parpadee en un atributo opcional no es un defecto
nuestro y no lo podemos arreglar.

---

## 4. Cobertura medida — 58.427 candidatas

| Campo | Presente |
|---|---|
| título | 100,0 % |
| provincia | 98,2 % |
| moneda | 91,0 % |
| precio | 90,9 % |
| tipo | 90,2 % |
| descripción | 89,8 % |
| imágenes | 85,1 % |
| operación | 81,3 % |
| coordenadas | 72,7 % |
| baños | 66,2 % |
| dormitorios | 58,8 % |
| ambientes | 58,5 % |
| dirección | 51,1 % |
| sup. cubierta | 47,7 % |
| barrio | 38,6 % |
| sup. total | 26,5 % |
| **ciudad** | **10,2 %** |

Ninguno de esos huecos descarta una propiedad. `ciudad` en 10,2 % es el más
grave para la búsqueda y **ya tiene solución preparada**: 29.048 propuestas con
procedencia, esperando que vuelva la base.

---

## 5. Qué NO promete el contrato

- **No promete completitud.** Promete que lo que está, está bien, y que lo que
  falta dice por qué falta.
- **No promete que un campo ausente sea recuperable.** 40.635 propiedades tienen
  coordenada y no tienen ciudad, y hoy no se pueden resolver sin polígonos que
  GeoRef no publica.
- **No promete unicidad entre inmobiliarias.** La misma propiedad puede estar
  publicada por dos agencias; eso se agrupa, no se borra.
- **No promete que una propiedad ausente en un scrapeo esté dada de baja.** Ver
  el ciclo de vida.

---

## 6. Versionado y auditabilidad

Cada propiedad viaja con:

| Campo | Para qué |
|---|---|
| `fingerprint` + `fingerprint_version` | detectar cambios de contenido |
| `_preingestion.version` | qué reglas produjeron esta fila |
| `_preingestion.campos_pendientes` | qué le falta |
| `provenance` | de dónde salió cada campo derivado |
| `hash_dedup` | identidad estable, nunca inventada en el connector |
| `scraped_at` | cuándo |

**La procedencia es obligatoria en todo campo derivado.** Sin ella no se puede
auditar después, y la diferencia entre "la fuente lo publicó" y "nosotros lo
dedujimos" es justamente lo que evita que una inferencia se confunda con un
dato.

---

## 7. Qué falta para cerrar el contrato

1. Llevar los cuatro estados al registro de cada propiedad, no sólo al resumen
   por inmobiliaria.
2. Definir el mínimo publicable — ver `ERETZ_QUALITY_GATE.md`.
3. Conectar el ciclo de vida.

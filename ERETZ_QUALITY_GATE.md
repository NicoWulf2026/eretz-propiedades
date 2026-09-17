# ERETZ — Quality gate

Qué se publica, qué se publica con reserva y qué se retiene. Explicable,
versionado y auditable.

Estado: **especificación V1**, medida sobre las 58.427 candidatas del 3 de
septiembre. Sin escrituras productivas.

---

## 1. El gate no es un rechazador

Se midieron los criterios candidatos contra la población real antes de escribir
ninguna regla:

| Criterio | Cumplen | |
|---|---|---|
| Identificable (`source_url` + `hash_dedup`) | 58.427 | **100 %** |
| Algo que mostrar (título, descripción o imágenes) | 58.427 | **100 %** |
| Alguna señal de ubicación | 57.939 | 99,2 % |
| Precio y moneda | 53.088 | 90,9 % |
| Operación **y** tipo | 45.582 | 78,0 % |
| Todo lo anterior | 41.831 | 71,6 % |

**Ningún criterio estructural rechaza a nadie.** Cero propiedades sin identidad,
cero sin nada que mostrar. Sólo 488 (0,8 %) no tienen ninguna señal de dónde
están.

Eso decide la naturaleza del gate: **no filtra, clasifica.** Un gate que
rechazara por campos faltantes borraría el 28 % del inventario por ausencias que
la fuente nunca publicó, repitiendo el error de D-014 a mayor escala.

---

## 2. Niveles

| Nivel | Condición | Volumen estimado |
|---|---|---|
| `PUBLICABLE` | identificable + algo que mostrar + ubicable + operación + tipo | 41.831 (71,6 %) |
| `PUBLICABLE_CON_RESERVA` | identificable + algo que mostrar, con huecos anotados | 16.108 (27,6 %) |
| `RETENIDA` | no identificable, o nada que mostrar, o valor imposible que sobrevivió | 488 candidatas (0,8 %) a revisar |

**`PUBLICABLE_CON_RESERVA` se muestra.** La reserva no la esconde: la degrada en
el orden de resultados y la excluye de las facetas cuyo campo le falta. Una
propiedad sin operación no puede aparecer en el filtro "venta", pero sí en una
búsqueda por barrio o en el mapa.

Las 488 sin ninguna señal de ubicación **no se retienen automáticamente**: se
marcan para revisión. Una propiedad sin ubicación sigue siendo una propiedad; lo
que no puede es aparecer en una búsqueda geográfica.

---

## 3. Reglas, y por qué cada una

Cada regla tiene identificador estable, versión y motivo legible. Una propiedad
retenida **siempre** dice qué regla la retuvo y con qué valor.

| Regla | Qué exige | Por qué |
|---|---|---|
| `G01_IDENTIFICABLE` | `source_url` y `hash_dedup` | sin identidad no se puede deduplicar, actualizar ni dar de baja |
| `G02_ALGO_QUE_MOSTRAR` | título, descripción o imágenes | una ficha sin ninguno de los tres es un cascarón, no un aviso |
| `G03_SIN_VALOR_IMPOSIBLE` | ningún par contradictorio sobreviviente | `dormitorios > ambientes` o `cubierta > total` significan atributos corridos |
| `G04_UBICABLE` | ciudad, barrio, dirección, coordenada o provincia | sólo degrada; no retiene |
| `G05_BUSCABLE` | operación y tipo | sólo degrada; no retiene |
| `G06_CON_PRECIO` | precio y moneda | sólo degrada; no retiene |

`G01` a `G03` retienen. `G04` a `G06` **sólo degradan**. Esa separación es la
regla más importante del gate.

---

## 4. Lo que el gate no hace

- **No inventa.** No deduce operación del título ni tipo de la URL cuando la
  fuente no lo dice. Eso ya se intenta en extracción, con procedencia; si ahí no
  se pudo demostrar, el gate no lo va a arreglar adivinando.
- **No elige entre duplicados.** Los 514 grupos se agrupan; cuál se muestra es
  una decisión comercial.
- **No da de baja.** Ausencia no es baja; eso es el ciclo de vida.
- **No rechaza por campo faltante.** Nunca.

---

## 5. Versionado y auditoría

```
QUALITY_GATE_VERSION = "quality_gate_v1"
```

Cada evaluación emite, por propiedad: `hash_dedup`, nivel, reglas que fallaron
con su valor observado, campos degradados y la versión del gate. Cambiar una
regla cambia la versión, y las evaluaciones anteriores quedan identificadas por
la versión que las produjo.

**Un gate que no explica por qué retuvo algo es indistinguible de un bug.**

---

## 6. Qué falta

1. Implementar el dry-run sobre las 58.427 y publicar el desglose por regla.
2. Revisar las 488 sin ubicación: ver si es un defecto de extracción o fuentes
   que realmente no la publican.
3. Definir el peso de la degradación en el ranking, que es decisión de producto.

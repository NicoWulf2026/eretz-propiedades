# ERETZ Propiedades — Quality Gate: reglas actuales y camino a la base

Fecha: 2026-08-27

Este documento existe porque el bloque de performance empezó con una premisa
equivocada, y conviene que quede corregida antes de que alguien escriba SQL.

La premisa era: *"la elegibilidad se decide con reglas que hoy corren en Node;
hay que traducirlas a SQL"*. **No es así.** No hay reglas que traducir.

## Qué es realmente el gate

Es un **manifiesto precomputado**. Un CSV con tres columnas:

```
property_id,classification,preview_visible
```

Se produce fuera de este repositorio, se guarda comprimido en Vercel Blob
privado, y el frontend lo descarga entero, lo convierte en un `Map` en memoria y
filtra filas contra él.

No hay condición SQL que reproduzca la decisión. La decisión **ya está tomada**
cuando el manifiesto llega.

Eso cambia el trabajo: no es traducir lógica, es **mover una tabla de
asignaciones** a donde están los datos que filtra.

## Las reglas exactas, tal como están hoy

### Clasificaciones

Cinco valores, y sólo dos hacen visible una publicación:

| Clasificación | Visible |
| --- | --- |
| `PUBLICABLE_COMPLETE` | **sí** |
| `PUBLICABLE_INCOMPLETE` | **sí** |
| `REVIEW_REQUIRED` | no |
| `INVALID` | no |
| `SOURCE_UNAVAILABLE` | no |

`PUBLICABLE_INCOMPLETE` es visible a propósito: una publicación a la que le
faltan campos puede mostrarse, siempre que la ficha no invente lo que no tiene.
Eso ya está resuelto aguas arriba —nunca se presenta `null` como `false` o `0`—
y no es asunto del gate.

### Integridad del manifiesto

El parser rechaza el manifiesto entero, no la fila, ante:

- encabezado distinto de `property_id,classification,preview_visible`;
- id que no sea sólo dígitos;
- clasificación fuera de las cinco;
- columnas de más;
- id duplicado;
- **incoherencia entre `preview_visible` y la clasificación**.

Esa última es la que más protege: si alguien editara el CSV para marcar visible
algo que su clasificación excluye, no pasa. La columna no se cree; se verifica
contra la regla.

### Verificación de origen

Exactamente **una** fuente, nunca dos: archivo local o Blob privado. Si están
las dos configuradas, o ninguna, el gate falla.

Para el Blob se exige, además:

- extensión `.csv.gz`;
- `SHA256` esperado, comparado contra el contenido descargado;
- `fingerprint` esperado, comparado con `sha256(contenido)[:16]`;
- tope de tamaño comprimido y descomprimido, y `maxOutputLength` al
  descomprimir —una bomba de descompresión es una forma barata de tirar el
  proceso—;
- timeout de 10 s.

El archivo local, además, no puede vivir bajo `public/`: serviría el manifiesto
a cualquiera.

### Overrides

`applyPublicQualityGateOverrides` fuerza 40 ids concretos a `REVIEW_REQUIRED`.
Y **falla si alguno no está en el manifiesto**, en vez de ignorarlo: si esos ids
desaparecieran de la fuente, el override dejaría de aplicarse en silencio y esas
40 publicaciones volverían a ser visibles sin que nadie se enterara.

### Fail-closed

Con el gate apagado, `isVisible` devuelve **siempre false**. No hay camino en el
que un fallo de carga muestre de más: un manifiesto vacío, un checksum que no
coincide o un Blob caído dejan el catálogo en cero, no abierto.

Es la orientación correcta y hay que conservarla en cualquier rediseño.

### Dónde se aplica

Tres puntos, todos en `property-db-service.ts`:

| Punto | Qué hace |
| --- | --- |
| ~línea 293 | filtra el listado fila por fila |
| ~línea 404 | filtra los puntos del mapa |
| ~línea 456 | corta el acceso a la ficha individual |

La ficha es la más importante: sin ese corte, una publicación excluida seguiría
siendo accesible por URL directa aunque no apareciera en ninguna lista.

## Por qué es lento

El conteo no ejecuta `COUNT(*)`. Trae `id`, `latitud` y `longitud` de todas las
filas candidatas —257.073 sin filtros— las manda por la red y las filtra en
Node contra el `Map`.

El costo medido en la auditoría: 1.360 ms de base para el conteo sin filtros, y
hasta ~20 s de latencia fría sumando lectura, transferencia y filtrado JS.

El problema no es la consulta. Es que **la base no sabe qué es elegible**, así
que no puede contar sin entregar todo primero.

## El camino: llevar las asignaciones a la base

La forma correcta no es reescribir reglas: es materializar el manifiesto en una
relación privada y que la base filtre con un `JOIN`.

### Forma propuesta

```sql
-- Schema privado, nunca expuesto por Data API.
create table internal_scraping.gate_eligibility (
  gate_version  text    not null,
  property_id   bigint  not null,
  classification text   not null,
  visible       boolean not null,
  primary key (gate_version, property_id)
);
```

`gate_version` es el mismo `sha256(contenido)[:16]` que ya calcula el frontend.
Que sea parte de la clave permite cargar la versión nueva **al lado** de la
vigente y recién después cambiar cuál se usa: sin ventana en la que la base
quede a medio cargar.

### Fail-closed en SQL

La semántica tiene que ser `INNER JOIN` o `EXISTS`, nunca `LEFT JOIN` ni
`NOT IN`:

```sql
-- correcto: si la tabla está vacía, el resultado es vacío
select count(*)
from public.propiedades p
join internal_scraping.gate_eligibility g
  on g.property_id = p.id
 and g.gate_version = $1
 and g.visible
where <filtros>;
```

Con `LEFT JOIN` una tabla vacía mostraría **todo**. Es la diferencia entre un
fallo que cierra y uno que abre, y en este pipeline sólo la primera es
aceptable.

### Qué se gana

- `COUNT(*)` en la base, sin transferir 257.073 filas;
- facets con `count(*) filter (where ...)` en una sola pasada;
- el sitemap futuro puede preguntar qué es publicable sin traerse los ids;
- una sola fuente de verdad para listado, mapa, conteos, ficha y sitemap.

### Qué no se toca

- las clasificaciones y su significado;
- los overrides;
- la verificación de checksum y fingerprint del manifiesto;
- el corte de la ficha individual;
- la orientación fail-closed.

El objetivo es mover y acelerar, no redefinir qué se ve.

### Equivalencia, antes de retirar nada

La lógica de Node no se saca hasta comprobar, sobre el mismo `gate_version`, que
producen exactamente el mismo conjunto: mismos ids visibles, mismos conteos,
mismas propiedades con y sin mapa. Si hay diferencias, se clasifican; no se
asume que la versión nueva tiene razón.

## Estado

**No implementado.** Requiere ejecutar DDL contra la base, y hoy no existe
ninguna credencial que lo permita: ver la sección correspondiente en
`ERETZ_SECURITY_AND_DATA_AUDIT_2026-08-27.md`.

Lo que sí quedó hecho es el trabajo que no depende de la base: estas reglas
documentadas, que son el prerrequisito de cualquier migración, y la forma
propuesta con su semántica fail-closed explícita.

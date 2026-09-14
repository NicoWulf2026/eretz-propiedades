# Promoción `staging` → `main`: el cuello de botella real del 12/10

**Estado: PLAN. No ejecutado. `database_writes: 0`.**
Medido el 2026-09-14 contra el proyecto `inmolink`, sólo lectura.

---

## 1. Qué encontramos

La pregunta "¿vamos a llegar al 12 de octubre?" se venía respondiendo sobre
764 inmobiliarias. **764 es el 11,6 % del universo.** El universo canónico son
**6.597**, y el 75 % está detenido *antes* de llegar a la cola de
certificación.

No están detenidas por falta de web ni por defectos de extracción. Están
detenidas porque **existen sólo en `staging` y nunca se promovieron a `main`**.

Medido en la base:

| | filas |
|---|---:|
| `public.inmobiliarias_main` | 7.004 |
| `public.inmobiliarias_staging` | 12.263 |
| staging **sin equivalente por nombre** en main | **11.931** |
| main con `staging_id_origen` (o sea, promovidas alguna vez) | **138** |
| `public.propiedades` | 257.073 |
| propiedades huérfanas (sin FK válida a main) | **0** |

De nuestro universo canónico, **4.953** caen exactamente ahí: el resolver las
marca `STAGING_NAMESPACE_NOT_A_MAIN_FK` y su evidencia lo dice literal —
`"0/4920 candidates linked by main.staging_id_origen"`.

### No es un problema de matching

Era la hipótesis alternativa y hay que descartarla antes de proponer un write.
Sobre una muestra aleatoria de 14 agencias bloqueadas, comparando nombres sin
puntuación ni mayúsculas: **13 aparecen en `staging` y ninguna en `main`.**

No hace falta afinar el matcher. Las filas no están.

### Por qué bloquea la certificación

`eretz_id` tiene que ser FK de `main` porque se escribe como
`inmobiliaria_id` de cada propiedad. Sin promoción no hay FK, sin FK la
identidad no queda `READY`, y sin `READY` la cola no las toma.

**Encontrarles la web no las desbloquea**: 1.605 de esas 4.953 ya tienen
dominio conocido y siguen paradas igual.

---

## 2. Lo que esto implica para la fecha

```
ritmo real (agencias nuevas / 24 h):     48
ritmo requerido para el 12/10:          230
fecha proyectada al ritmo actual:  2027-01-26
DEADLINE_STATUS:                        RED
```

Ningún ajuste de throughput de certificación cierra una brecha de 5×, porque
el 75 % ni siquiera entra a esa cola. **La promoción es el camino crítico.**

Y como es un write productivo, las dos barreras que vengo reportando —*Exposed
schemas* y la credencial de Postgres— dejaron de ser preparación: están sobre
el camino crítico de 5.400 agencias.

---

## 3. La promoción es mecánicamente simple

Las dos tablas tienen **49 columnas cada una, 32 compartidas**. La única
columna obligatoria sin default en `main` es `nombre`, que staging siempre
trae.

O sea: el riesgo no está en la mecánica. Está en **a quién se promueve**.

### Tres alcances posibles, de menor a mayor riesgo

| alcance | filas | qué entra |
|---|---:|---|
| **A — sólo lo que la cola necesita** | **4.953** | las canónicas bloqueadas, con candidata de alta confianza ya verificada por el resolver |
| B — universo canónico completo | 5.428 | A + las 475 sin candidata, que son altas nuevas |
| C — todo staging | 11.931 | incluye 6.978 que nunca vimos en Roomix |

**Recomiendo A.** Es el mínimo que destraba la deadline, cada fila tiene
evidencia de identidad escrita, y deja fuera 7.000 filas sobre las que no
tenemos nada que decir todavía.

---

## 4. Controles previos, todos de lectura

Ninguno escribe. Hay que correrlos y adjuntar el resultado **antes** de pedir
autorización de escritura.

1. **Colisiones de nombre.** Ninguna de las 4.953 puede tener ya un equivalente
   en main: si lo tiene, es un duplicado y no una promoción.
2. **Colisiones internas.** Dos filas de staging con el mismo nombre
   normalizado entrarían como dos agencias distintas.
3. **Integridad de FK.** Hoy hay **0** propiedades huérfanas. Después de la
   promoción tiene que seguir habiendo 0.
4. **Conteo antes / después.** `main` pasa de 7.004 a 11.957 bajo el alcance A.
   Cualquier otro número es un error.
5. **Reversibilidad.** Cada fila insertada lleva su `staging_id_origen`, así
   que el rollback es exacto: borrar por ese campo. Sin él, no hay vuelta
   atrás distinguible.

---

## 4 bis. Resultado de los controles, y un defecto del plan

Los controles se corrieron el 2026-09-14. Encontraron algo que el plan de la
sección 5, tal como lo escribí primero, **no cubría**.

| control | resultado |
|---|---|
| staging sin nombre / sin id | **0** — nada que descartar |
| colisión por nombre con `main` | **332** — el `not exists` las frena |
| nombres repetidos **dentro** de staging | **152 nombres, 327 filas**, peor caso ×10 |
| propiedades huérfanas hoy | **0** |

**El defecto.** El `not exists` compara contra `main` *antes* del insert, así
que no ve los duplicados que vienen dentro del mismo lote. Con el plan
original, las 10 filas llamadas `Tizado` habrían entrado las 10, y las 5
llamadas **"Sucursal - Prueba Zonaprop"** —filas de prueba— también.

Hay que deduplicar por nombre normalizado dentro del lote, no sólo contra main.

### Lo que sí y lo que no cae en el alcance A

La basura peor **no está en el alcance A**: `Tizado` ×10, `Prueba Zonaprop` ×5
y las filas que son sólo un nombre de pila (`alberto`, `marcelo`) no tienen
inmobiliaria canónica que las reclame, así que el alcance las deja fuera solo.
Es una propiedad del alcance A que conviene tener escrita: **es más seguro que
el alcance C precisamente por esto.**

Dentro del alcance A quedan **20 nombres normalizados con más de una canónica,
40 filas en total**:

```
L.A PROPIEDADES            / L.A SERVICIOS INMOBILIARIOS
GUERRERO INMOBILIARIA      / Guerrero Propiedades
Alfa Propiedades           / ALFA Bienes Raíces
GD Brokers Inmobiliarios   / GD Negocios Inmobiliarios
Santos Propiedades         / Santos Inmobiliaria
Greco Propiedades          / Inmobiliaria Greco Propiedades
CAS.AS PROPIEDADES         / CasasPropiedades
MS PROPIEDADES             / M.S. PROPIEDADES
```

Algunas son la misma inmobiliaria cargada dos veces en Roomix —`MS` y `M.S.`,
`CAS.AS` y `CasasPropiedades`—. Otras podrían ser dos firmas distintas: `GD
Brokers` y `GD Negocios` no son obviamente la misma.

**No se resuelve automáticamente.** Promover las dos crea dos agencias y parte
sus propiedades entre dos `inmobiliaria_id`; fusionarlas a ciegas atribuye a una
inmobiliaria propiedades de otra, que es el error más caro de todos. Son 20
casos: se miran a mano en una sentada.

## 5. Forma de la escritura

```sql
-- NO EJECUTAR SIN AUTORIZACION EXPLICITA.
-- Alcance A. Idempotente: reejecutarla no duplica.
insert into public.inmobiliarias_main (nombre, /* ...32 columnas compartidas... */,
                                       staging_id_origen)
select s.nombre, /* ... */, s.id
from public.inmobiliarias_staging s
where s.id = any (:ids_del_alcance_A)
  -- Una sola fila por nombre normalizado DENTRO del lote. Sin esto entran las
  -- diez filas llamadas `Tizado`, porque el `not exists` de abajo solo mira
  -- main y no ve a sus propias companyeras de lote.
  and s.id = (select min(s2.id) from public.inmobiliarias_staging s2
               where s2.id = any (:ids_del_alcance_A)
                 and lower(regexp_replace(s2.nombre,'[^a-zA-Z0-9]','','g'))
                   = lower(regexp_replace(s.nombre,'[^a-zA-Z0-9]','','g')))
  and not exists (
      select 1 from public.inmobiliarias_main m
      where m.staging_id_origen = s.id
         or lower(regexp_replace(m.nombre,'[^a-zA-Z0-9]','','g'))
          = lower(regexp_replace(s.nombre,'[^a-zA-Z0-9]','','g')));
```

El `not exists` hace dos cosas a la vez: impide promover dos veces la misma
fila, e impide crear una agencia que ya existe con otro nombre de origen.

**Rollback:**

```sql
delete from public.inmobiliarias_main
where staging_id_origen = any (:ids_del_alcance_A);
```

Exacto y acotado, porque sólo toca filas que esta operación creó.

---

## 6. Lo que hace falta de vos

En orden:

1. **Supabase → Settings → API → Exposed schemas → agregar `public` → Guardar.**
   Sigue pendiente desde antes; ahora además bloquea esto.
2. **Credencial de Postgres válida** para el backup previo (`pg_dump`), que es
   requisito propio antes de cualquier escritura de este tamaño.
3. **Autorización explícita del alcance** — A, B o C.

Con las tres, la promoción se ejecuta en una ventana con backup, controles
antes y después, y rollback listo.

Sin ellas no se escribe nada, y el universo sigue topeado en 764.

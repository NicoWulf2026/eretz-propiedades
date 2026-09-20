# ERETZ Propiedades — Plan de rollback

Para cada fase de `ERETZ_SUPABASE_WRITE_PLAN.md`: cómo se vuelve atrás, cuánto
tarda, y qué **no** se recupera.

Regla de oro: **ninguna fase se ejecuta si su rollback no está escrito y
entendido antes.** Y una fase cuyo rollback sea "restaurar el dump" no se ejecuta
hasta que el dump exista y se haya restaurado al menos una vez (Fase 0).

---

## Qué hace que esto sea reversible

El plan está diseñado para que casi todo el rollback sea barato:

- **Nada se borra.** Ninguna fase ejecuta DELETE ni DROP.
- **Nada se desactiva.** La desactivación masiva está fuera del plan.
- **Nada cambia de dueño.** `inmobiliaria_id` no se toca.
- **Todo lote deja rastro.** Cada transacción anota los `id` que tocó y, en los
  UPDATE, el valor anterior de cada campo.

Ese último punto es lo que convierte el rollback de datos en un UPDATE inverso
en vez de una restauración completa.

---

## Fase 1 — Esquema expuesto

**Cómo se revierte.** Dashboard → Settings → API → Exposed schemas: vaciar el
campo. PostgREST vuelve a `pg_pgrst_no_exposed_schemas` en el siguiente reintento.

**Cuánto tarda.** Menos de un minuto; el efecto llega en ≤32 s.

**Qué se pierde.** Nada. No hay datos involucrados: se vuelve exactamente al
estado de hoy, que es la API caída.

**Riesgo real de la fase.** Bajísimo, y es la única fase que además **arregla**
algo por sí sola.

---

**Cuándo disparar el rollback, sin pensarlo dos veces.**
`scripts/verificar_fase1.py` corre siete controles. Si falla cualquiera de los
tres últimos —`anon` lee `propiedades`, `authenticated` lee `propiedades`, o
alguna tabla de producto devuelve filas— hay que **vaciar Exposed schemas
inmediatamente**, guardar la salida del verificador como evidencia y detener la
fase.

**Lo que no hay que hacer:** intentar arreglarlo con `REVOKE`, con RLS o con
policies. Eso sería cambiar el modelo de permisos sin autorización, para tapar
un síntoma cuyo origen no entendemos todavía. El rollback es un campo de texto.

---

## Credencial de Postgres — qué hacer y qué no

No hay rollback que preparar acá, porque **no se cambió nada**. Lo que hay es
una lista de lo que no hay que hacer para no empeorar el problema.

**Estado:** `CREDENTIAL_INVALID`. Diagnóstico completo en la auditoría §22: el
host, el puerto, el usuario, la forma de la URL y el escaping están todos bien,
y el servidor llega a evaluar la contraseña y la rechaza. La causa es una sola.

**Lo que NO hay que hacer:**

| tentación | por qué no |
|---|---|
| rotar la contraseña desde el dashboard | invalida todo lo que use esa clave hoy —incluido lo que escribe en `internal_scraping`— y el problema es que **nosotros** tenemos una vieja, no que la de producción esté mal |
| cambiar a `INTERNAL_DB_URL` | es la misma clave contra el mismo host: falla igual |
| pasar al pooler | con la contraseña correcta la directa alcanza; con la incorrecta ningún pooler ayuda |
| usar `NEON_DB_URL_BACKUP` | apunta a otra base, de otro proveedor. No es producción |

**Lo que sí:** copiar la contraseña vigente del proyecto a `.env`. Si esa
contraseña no existe en ningún lado —nadie la anotó— entonces sí hace falta
rotarla, y eso pasa a ser
`WAITING_USER_AUTHORIZATION_CREDENTIAL_ROTATION`: hay que hacerlo sabiendo qué
se rompe y teniendo con qué volver a configurarlo.

**Si se rota igual, el rollback es**: la contraseña anterior no se recupera. Se
vuelve rotando otra vez y actualizando todos los consumidores. Por eso conviene
inventariar quién usa esa clave *antes*, no después.

---

## Herramientas de restauración

**Estado:** `RESTORE_TEST_BLOCKED`. Ni `pg_dump`, ni `pg_restore`, ni `psql`, ni
Docker, ni permisos de administrador.

No hay nada que revertir —no se instaló nada—. La acción que lo desbloquea está
en `ERETZ_SUPABASE_WRITE_PLAN.md`, Fase 0, y necesita una terminal con
privilegios.

Y una advertencia sobre el orden: **instalar el cliente no sirve de nada sin la
credencial**, y la credencial sin el cliente permite el backup por `COPY`
—`scripts/backup_productivo.py`— pero no la prueba de restauración. Las dos
cosas hacen falta para cerrar la Fase 0 entera.

---

## Fase 4 — Upsert de propiedades

Dos mecanismos distintos, según qué haya fallado.

### 4a. Revertir un lote que salió mal

Cada lote corre en su transacción. Si falla dentro, Postgres revierte solo y no
hay nada que hacer.

Si un lote **terminó bien pero estaba mal calculado**, se revierte con lo que el
propio lote anotó:

- los `NEW` insertados: se identifican por su `id` en el registro del lote.
  Deshacerlos requiere DELETE, y **el esquema hace que ese DELETE sea mucho más
  caro de lo que parece** (auditoría §20): seis tablas cuelgan de `propiedades`
  con `ON DELETE CASCADE` —`geocoding_results`, `historial_precios`,
  `property_analysis`, `property_events`, `property_location_corrections`,
  `property_scores`— y `property_merge_audit` con `SET NULL`.

  Borrar una propiedad borra su historial de precios y sus eventos, que es
  justamente lo que no se puede reconstruir. **Alternativa preferible y ahora
  claramente mejor: dejarlas y marcarlas.** Si igual hubiera que borrar, hay que
  respaldar antes esas seis tablas, no sólo `propiedades`.
- los `UPDATE`: se revierten con el valor anterior que el registro guardó, campo
  por campo. Es un UPDATE inverso, sin pérdida.

### 4b. Revertir la fase entera

Restaurar `public.propiedades` desde el dump de la Fase 0:

```bash
pg_restore --data-only --table=propiedades \
  --dbname="$SUPABASE_DB_URL" eretz_prod_YYYYMMDD_HHMMSS.dump
```

**Cuánto tarda.** Del orden de decenas de minutos sobre 257.073 filas, con la
tabla bloqueada.

**Qué se pierde.** Todo lo que el **pipeline legacy** haya escrito entre el
backup y la restauración. Ése es el costo verdadero y por eso 4b es el último
recurso: en la práctica se usa 4a.

**Consecuencia operativa:** entre la Fase 0 y la Fase 4 no debería correr el
pipeline legacy escribiendo en `propiedades`. Si corre, el dump envejece y 4b
deja de ser una opción limpia.

---

## Fase 5 — Promociones y vínculos

**Cómo se revierte.** UPDATE inverso con los valores anotados. 733 filas, es
inmediato.

**Qué se pierde.** Nada.

---

## Fase 6 — Geografía

**Cómo se revierte.** Sólo se escriben los `SAFE_UPDATE`, o sea filas que estaban
**vacías**. El rollback es ponerlas de nuevo en NULL, con la lista de `id` del
lote.

**Qué se pierde.** Nada: por definición no había valor previo que perder. Ésa es
justamente la razón por la que `CONFLICT` no se escribe.

---

## Fase 7 — Duplicados

Sólo marca. Se revierte borrando la marca. No toca ningún dato de la propiedad.

---

## Fases 0, 2, 3, 8, 9, 10

No escriben. No hay nada que revertir.

---

## Lo que NO tiene rollback

Hay que decirlo con todas las letras, porque es la razón de varias decisiones del
plan:

| acción | por qué no se puede volver atrás |
|---|---|
| fusionar duplicados | se pierde cuál era cuál; por eso la Fase 7 sólo marca |
| desactivación masiva | la fecha original de baja no se recupera; por eso está fuera del plan |
| pisar geografía en `CONFLICT` | el valor productivo se pierde si no se anotó; por eso no se escribe |
| UPDATE que pone NULL sobre un valor existente | el dato se pierde; por eso la Fase 4 es `COALESCE`-safe |
| DELETE de los `NEW` insertados | **borra siete filas, no una**: seis tablas cuelgan de `propiedades` con `ON DELETE CASCADE` |

---

## Prueba del rollback

Un rollback que no se probó es una intención, no un plan.

### Lo que ya está probado

`scripts/ensayo_de_rollback.py`, sobre una base local descartable con las
**28.251 colisiones reales** del dry-run —máscaras de campo reales de
producción, valores reales de las candidatas—:

| variante | valores productivos perdidos |
|---|---|
| `SET campo = nuevo` | **62.280** |
| `SET campo = COALESCE(nuevo, campo)` | **0** |

y la reversión con la imagen previa dejó la tabla **byte a byte** como estaba:
0 filas distintas. El ensayo corre la variante ingenua a propósito: si dejara de
perder datos, el ensayo dejó de probar algo y el script lo denuncia en vez de
pasar en verde. Cinco tests en `tests/test_ensayo_de_rollback.py` lo fijan.

### Lo que falta probar

Lo mismo, pero sobre **datos productivos restaurados**:

1. restaurar el dump de la Fase 0 en una base descartable,
2. correr un lote de 1.000 `UPDATE` con los valores reales,
3. revertirlo y comprobar que las 1.000 filas quedaron byte a byte.

Lo que el ensayo local no puede cubrir es el **contenido**: prueba que ningún
valor presente se pierde, no que los valores que se escriben encima sean los
correctos. Eso necesita el dump, y el dump necesita la credencial.

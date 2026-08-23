# PROPERTY_WRITE_ACCESS_MANIFEST

Permisos mínimos que necesita la ingesta directa de propiedades para escribir en
el pipeline ERETZ. Documento de auditoría: **no se aplicó ningún cambio de
permisos**, no se creó ningún rol y no se tocó ninguna credencial.

Estado actual: `PROPERTY DB WRITE = EXTERNAL ACCESS BLOCKER`.
`INTERNAL_DB_URL` rechaza autenticación (contraseña vencida). El bloqueo afecta
**solo** la escritura de propiedades; todo lo demás de la misión sigue.

---

## 1. Qué hace la ingesta directa, exactamente

Un solo write. La ingesta produce filas normalizadas y las deja en la tabla de
entrada del pipeline; de ahí en adelante los procesos que ya existen siguen su
curso sin cambios.

```sql
INSERT INTO public.propiedades_raw (<23 columnas>)
VALUES (...)
ON CONFLICT (hash_dedup) DO NOTHING
RETURNING id;
```

Es la misma sentencia que ya ejecuta `scripts/import_captured_props_to_neon.py`.
No se inventa una vía nueva.

---

## 2. Tablas

### 2.1 Escritura — una sola

| Tabla | Operación | Por qué |
|---|---|---|
| `public.propiedades_raw` | **INSERT** | Única entrada del pipeline. |

### 2.2 Lectura

| Tabla | Operación | Por qué |
|---|---|---|
| `public.propiedades_raw` | SELECT | Reconciliar lo insertado contra lo enumerado. |
| `public.inmobiliarias_staging` | SELECT | Resolver `canonical_agency_id` → `inmobiliaria_id`. |
| `public.inmobiliarias_main` | SELECT | Igual, para las ya publicadas. |

Las dos últimas son **solo lectura**. La ingesta de propiedades no modifica
inmobiliarias por ningún camino.

### 2.3 Fuera de alcance — no se tocan

`propiedades_staging` · `publish_queue` · `propiedades` (main) ·
`scraping_run_items` · cualquier tabla de inmobiliarias en escritura.

Las transiciones `raw → staging → publicación` las hacen procesos que ya
existen y tienen su propio acceso:

- `validate_raw_properties.py`: `UPDATE propiedades_raw SET status` +
  `INSERT propiedades_staging`
- `build_publish_queue.py`: `UPDATE propiedades_staging SET status='queued'`
- `publish_to_supabase.py`: estados de `publish_queue` y `propiedades_staging`

**Ninguna de esas operaciones pertenece a la ingesta directa.** Pedir permisos
para ellas sería ampliar el alcance sin necesidad.

---

## 3. Sequences

| Sequence | Operación |
|---|---|
| `public.propiedades_raw_id_seq` | `USAGE`, `SELECT` |

Es la secuencia implícita de `id BIGSERIAL PRIMARY KEY`. Sin `USAGE` el INSERT
falla aunque la tabla tenga permiso.

---

## 4. UPDATE: no hace falta

`ON CONFLICT DO NOTHING` resuelve la idempotencia sin actualizar nada. Una
propiedad que cambió de precio se detecta por `fingerprint` en el checkpoint del
connector, fuera de la base, y entra como fila nueva si su URL cambió o se
ignora si no.

Actualizar `propiedades_raw` desde la ingesta pisaría el trabajo de
`validate_raw_properties.py`, que es quien mueve `status` de `raw` a
`validated`/`rejected`. Dos escritores sobre la misma columna de estado es
exactamente el tipo de acoplamiento que conviene no crear.

**Si más adelante hiciera falta**, el caso sería acotado y explícito: refrescar
precio y fotos de filas todavía en `status='raw'`, nunca de las ya validadas.
Eso se pediría aparte, con su justificación.

---

## 5. DELETE: ninguno

La ingesta no borra. Una propiedad que desaparece de la fuente se marca
`POTENTIAL_INACTIVE` en artefactos, y la baja definitiva —cuando la regla se
valide— se hará como cambio de estado, no como borrado. No se pide `DELETE`
sobre ninguna tabla.

---

## 6. Triggers y funciones

No se encontraron triggers ni funciones sobre `propiedades_raw`,
`propiedades_staging` ni `publish_queue` en el esquema versionado. La única
lógica que se dispara en el INSERT es el índice único:

```
CREATE UNIQUE INDEX idx_propiedades_raw_hash_dedup ON public.propiedades_raw(hash_dedup);
```

Ese índice **es** el mecanismo de idempotencia. No debe removerse.

Constraint que valida el INSERT:

```
propiedades_raw_status_chk CHECK (status IN ('raw','validated','rejected','published'))
```

La ingesta siempre inserta `status='raw'`.

---

## 7. Vocabulario que la ingesta debe respetar

Validado en código antes del INSERT (`scripts/ingest_to_pipeline.py`), para que
una fila inválida no aborte la transacción y se lleve el lote entero:

- `moneda` ∈ {`ARS`, `USD`}
- `operacion` ∈ {`venta`, `alquiler`, `alquiler_temporario`, `consultar`, `venta_y_alquiler`}
- `tipo_propiedad` ∈ `ALLOWED_PROPERTY_TYPES`
- `inmobiliaria_id` dentro del rango `INTEGER` (la columna es `INTEGER`, no `BIGINT`)
- `precio > 0` cuando está presente

---

## 8. Concesión mínima propuesta

Siguiendo el patrón de least privilege que ERETZ ya usa para
`eretz_agency_coverage_writer`:

```sql
-- Rol sin login, asumido con SET LOCAL ROLE desde una sesión ya autenticada.
CREATE ROLE eretz_property_ingest_writer NOLOGIN NOINHERIT;

GRANT USAGE ON SCHEMA public TO eretz_property_ingest_writer;

GRANT INSERT, SELECT ON public.propiedades_raw
  TO eretz_property_ingest_writer;
GRANT USAGE, SELECT ON SEQUENCE public.propiedades_raw_id_seq
  TO eretz_property_ingest_writer;

GRANT SELECT ON public.inmobiliarias_staging, public.inmobiliarias_main
  TO eretz_property_ingest_writer;
```

Nada más. Sin `UPDATE`, sin `DELETE`, sin `TRUNCATE`, sin acceso a
`propiedades_staging`, `publish_queue` ni `propiedades`.

**Este SQL no se ejecutó.** Queda como propuesta auditable para que alguien con
autoridad decida.

---

## 9. Verificación después de conceder

Antes de cualquier carga masiva, el canary de escritura comprueba:

1. la identidad con la que se conecta (fuera de cualquier función, porque dentro
   de una `SECURITY DEFINER` se ve la del dueño, no la del llamador);
2. que `INSERT` funcione sobre `propiedades_raw`;
3. que `UPDATE` y `DELETE` **fallen**, que es la prueba de que el permiso es
   mínimo de verdad;
4. que una segunda corrida del mismo lote inserte **cero** filas nuevas;
5. que `insertadas + ya_estaban == aptas`.

`scripts/ingest_to_pipeline.py` ya implementa 2, 4 y 5, y corre en dry run por
defecto: hay que pedirle `--escribir` explícitamente.

---

## 10. Lo que este documento NO hace

- No amplía permisos.
- No crea roles.
- No rota ni reemplaza credenciales.
- No usa `service_role` ni `postgres`.
- No imprime ninguna credencial.

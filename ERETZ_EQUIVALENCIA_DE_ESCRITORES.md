# Equivalencia de escritores: qué puede tocar cada camino

**2026-09-20 · `database_writes: 0` · verificado en PostgreSQL/WASM desechable**

Codex dejó esto abierto: *«writer equivalence: el REST aún se usa; no
broaden allowlist ni retirar REST antes de equivalencia real»*. Acá está la
equivalencia, medida contra el código y comprobada ejecutándola.

Verificación: `node scripts/verify_writer_equivalence.mjs` — 9 checks, más los
17 de `verify_local_postgres.mjs` que siguen pasando. `production_connections: 0`.

---

## La respuesta corta

**No son equivalentes, y la diferencia no es de grado.** El PATCH por REST
puede reasignar una propiedad a otra inmobiliaria y reescribir su hash de
deduplicación, sin comprobar contra qué fila escribe y sin dejar rastro. El
RPC no puede ninguna de esas cosas.

La causa es de diseño, no de configuración:

| | RPC `apply_property_safe_merge` | REST `batch_save_only_changed` |
|---|---|---|
| Qué campos acepta | **lista blanca de 17** | **lista negra de 3** |
| Cómo localiza la fila | `id` + verifica `url`, `hash_dedup`, `fuente_extraccion`, `inmobiliaria_id` | `url=eq.` y nada más |
| Auditoría | obligatoria, misma transacción | **ninguna** |
| Si la fila cambió antes de escribir | levanta `property identity changed before merge` | la pisa |

La lista negra del REST es literalmente esto:

```python
safe_payload = {k: v for k, v in payload.items()
                if k not in ("latitud", "longitud", "url")}
```

y `to_payload()` incluye `inmobiliaria_id`, `hash_dedup`, `fuente_extraccion`
y `estado`. **El riesgo no es latente: esos cuatro campos viajan en el payload
real.**

---

## Qué se inserta

`insert_property_safe` acepta **26 columnas**: `inmobiliaria_id`, `url`,
`url_normalizada`, `hash_dedup`, `id_externo`, `titulo`, `descripcion`,
`precio`, `moneda`, `tipo_propiedad`, `operacion`, `ambientes`, `dormitorios`,
`banos`, `superficie_total`, `superficie_cubierta`, `direccion`, `barrio`,
`ciudad`, `provincia`, `pais`, `latitud`, `longitud`, `imagenes`,
`fuente_extraccion`, `estado`. Cualquier otra clave levanta
`forbidden insert keys`.

### Los dos caminos ni siquiera aceptan el mismo payload

`to_payload()` —el que usan los escritores REST— **no produce
`url_normalizada`**, y el RPC la **exige**: sin ella levanta `safe insert
requires complete identity and audit envelope`. Lo descubrí porque el primer
intento de esta verificación falló ahí.

Tampoco produce `superficie_cubierta`, `id_externo`, `provincia` ni `pais`,
que el RPC sí soporta. O sea que migrar del REST al RPC **no es cambiar la
llamada**: hay que completar el payload.

---

## Qué se actualiza

`apply_property_safe_merge` acepta **17**: `titulo`, `descripcion`, `precio`,
`moneda`, `tipo_propiedad`, `operacion`, `ambientes`, `dormitorios`, `banos`,
`superficie_total`, `superficie_cubierta`, `direccion`, `barrio`, `ciudad`,
`latitud`, `longitud`, `imagenes`.

## Qué nunca se pisa

Las **9** que están en el INSERT y no en el UPDATE: `inmobiliaria_id`, `url`,
`url_normalizada`, `hash_dedup`, `id_externo`, `fuente_extraccion`, `estado`,
**`provincia`** y **`pais`**.

Las cinco primeras son identidad y está bien que sean inmutables. Las dos
últimas abren un hueco.

### HUECO: la ciudad se puede mover de provincia y nada avisa

`ciudad` es actualizable y `provincia` no. Comprobado ejecutándolo: una fila
pasó de `ciudad = Rosario` a `ciudad = Córdoba Capital` conservando su
provincia anterior. **Ninguna regla lo impide.**

No es un defecto del RPC: es la consecuencia directa de su lista blanca, y es
la decisión que Codex marcó como pendiente —*«UPDATE geográfico requiere
acoplar ciudad/provincia/país/coords»*—. Hay tres salidas y ninguna es obvia:

1. agregar `provincia` y `pais` al UPDATE, acoplados a `ciudad` —se mueven
   juntos o no se mueve ninguno—;
2. sacar `ciudad` del UPDATE, y que la geografía sólo se fije al insertar;
3. dejarlo así y aceptar filas incoherentes.

La 3 no. Entre la 1 y la 2 hace falta saber con qué frecuencia una ciudad
cambia legítimamente en una propiedad ya publicada, y ese número no lo tengo.
**Queda abierto con las opciones escritas, no resuelto a ojo.**

---

## NULL y cero

- `insert_property_safe` conserva el **cero** como cero: `precio = 0` y
  `ambientes = 0` se guardan, no se convierten en `NULL`. Verificado por
  `insert_null_zero_and_audit` y por
  `covered_surface_update_preserves_fraction_zero_and_atomic_audit`, que
  también cubre `0` y `90.75` en superficie cubierta.
- Lo **omitido** queda `NULL`, sin defaults inventados
  (`insert_omitted_identity_and_geography_stay_null`).
- El patch de UPDATE **rechaza `null` JSON**: `merge patch cannot contain JSON
  null`. Borrar un valor no se puede hacer por descuido; hay que decidirlo por
  otra vía.

## Identidad

- El RPC exige que `p_source_id` coincida con `inmobiliaria_id`, y en el
  UPDATE además que coincidan `url`, `hash_dedup` y `fuente_extraccion` de la
  fila viva. Un cambio entre la lectura y la escritura aborta.
- Una actualización **cruzada entre agencias** se rechaza
  (`cross_agency_update_rejected`).
- El REST no comprueba nada de esto.

## Auditoría y reversión

- Mutación y auditoría van en la **misma transacción**:
  `mutation_and_audit_roll_back_together`, `invalid_audit_rolls_back_update`.
- **Corregido hoy**: el RPC aceptaba una actualización con auditoría **vacía**.
  Cambiaba campos y no quedaba ninguna fila diciendo cuáles. La *forma* de la
  auditoría ya se validaba —una malformada hace rollback—; lo que faltaba era
  exigir que exista. Ahora `changed_fields > 0` con `audit_rows = 0` levanta
  `merge changed N fields without audit evidence`. Con cero cambios no se
  exige nada, que es lo correcto.
- Reversión: `property_safe_merge_audit_rollback.sql` revoca accesos y
  **preserva la evidencia** (`rollback_migration_revokes_access_preserves_evidence`).
- Los roles públicos no pueden leer ni escribir la auditoría
  (`public_roles_cannot_write_or_read_audit`).

---

## Qué falta para poder retirar el REST

1. **Completar `to_payload()`** con `url_normalizada` —requerida— y decidir
   sobre `superficie_cubierta`, `id_externo`, `provincia`, `pais`.
2. **Resolver el acoplamiento geográfico** entre `ciudad` y `provincia`.
3. **Matriz de consumidores**: quién llama hoy a `save`,
   `batch_save_only_new`, `batch_save_only_changed`, `update_location`,
   `mark_as_inactive` y `save_historial`. Codex ya advirtió que no hay
   equivalencia completa de escritores y que el REST tiene consumidores
   legítimos; retirarlo sin esa matriz sería romper algo que no estoy viendo.
4. **`update_location` y `mark_as_inactive` no tienen equivalente RPC.** El
   primero escribe `latitud`/`longitud` —que el merge sí cubre— pero por otra
   ruta y sin auditoría; el segundo escribe `estado`, que el UPDATE del RPC
   **no permite**. Cerrar el REST hoy dejaría sin camino a la baja de una
   propiedad.

Los cuatro son trabajo local y ninguno necesita tocar producción. El punto 4
es el que más me sorprendió: la función que da de baja una propiedad no tiene
sustituto en el camino seguro.

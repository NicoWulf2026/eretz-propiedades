# ERETZ Propiedades — base de Preview aislada

Fecha: 2026-08-27

## El problema que resuelve

Hoy **Vercel Preview ≠ Database Preview**. Existe un solo proyecto Supabase
(`pggrvzyixyjkhfknpurg`) con las 257.073 publicaciones reales, y
`eretz_preview_ro` es un **rol** dentro de esa única base, no otra base. Su
propio rollback lo dice:

```sql
revoke connect on database postgres from eretz_preview_ro;
```

Es decir: cualquiera que leyera "Preview DB" en un runbook y ejecutara una
migración habría estado tocando el dato real, convencido de lo contrario. Por
eso existe la guarda de destino (`frontend/scripts/db-target-guard.mjs`).

Para experimentar con DDL, índices, materialized views y rollbacks hace falta
una base separada de verdad.

## Acceso: MCP con OAuth, no un token pegado a mano

La documentación oficial de Supabase describe un servidor MCP hospedado con
**dynamic client registration**: no hace falta crear un Personal Access Token
manualmente, el cliente abre el flujo OAuth en el navegador.

Configuración, en `.mcp.json` del repositorio:

```json
{
  "mcpServers": {
    "supabase": {
      "type": "http",
      "url": "https://mcp.supabase.com/mcp?read_only=true&features=docs,account,database,debugging,development,branching"
    }
  }
}
```

Dos decisiones sobre esos parámetros:

- **`read_only=true` de entrada.** La primera conexión sirve para mirar
  —organización, proyectos, plan, versión de PostgreSQL— y para eso no hace
  falta poder escribir. Se quita cuando exista la base de Preview y haya algo
  que escribir *en ella*.
- **Sin `project_ref` todavía.** Acotar a un proyecto es lo correcto para
  trabajar, pero impide las operaciones de cuenta, y justamente la primera
  operación pendiente es **crear** un proyecto. Cuando la Preview exista, se
  agrega `project_ref=<ref-de-preview>` y ahí el alcance queda cerrado sobre
  ella.

No hay ningún secreto en ese archivo: la autorización vive en el flujo OAuth,
no en el repositorio.

### Completar la autorización

Requiere una sesión interactiva. Desde una terminal, en este worktree:

```bash
claude
```

y dentro, `/mcp` → seleccionar **supabase** → autorizar en el navegador.

## Topología: segundo proyecto, no branching

La preferencia inicial era branching. Los números la invierten.

| | Branching | Segundo proyecto |
| --- | --- | --- |
| Plan | **Pro, US$25/mes** | Free |
| Costo por unidad | **US$0,01344 por branch por hora** (~US$9,7/mes si queda encendido) | — |
| Disponible en Free | **no** | sí, hasta **2 proyectos activos** por organización |
| Aislamiento | branch dentro del mismo proyecto | **proyecto separado**: otro `project_ref`, otro host |
| Datos iniciales | ninguno; se siembra | ninguno; se siembra |

**Recomendación: segundo proyecto.** Cuesta cero, y da *más* aislamiento que un
branch —es otro proyecto entero, no una rama del que tiene el dato real—, que
es exactamente lo que este trabajo necesita.

Dos advertencias honestas sobre el plan Free, porque afectan el trabajo:

1. Los proyectos gratuitos **se pausan por inactividad**. Para benchmarks
   sostenidos hay que contar con reactivarlos.
2. Los recursos del Free son menores que los de producción. Los tiempos
   absolutos **no serán comparables** con los de la base real; lo que sí es
   comparable, y es lo que importa acá, son los planes de ejecución y la
   mejora relativa antes/después.

Si más adelante se quiere medir con recursos equivalentes, ahí sí conviene
discutir Pro. Hoy no hace falta.

## El esquema base no está en el repositorio

Hallazgo al preparar el bootstrap, y cambia el orden de trabajo.

`public.propiedades` —la tabla que lee todo el frontend— **no está definida en
ningún archivo del repositorio**. Las migraciones de `supabase/migrations/` son
incrementales y dan por sentado que ya existe. `MIGRATION_ORDER.md` remite a una
*"sanitized schema baseline captured by the definitive audit"*, y esa baseline
tampoco está versionada.

Consecuencia concreta: **hoy no se puede levantar un entorno desde cero con lo
que hay en Git**, ni siquiera con MCP autorizado y un proyecto Preview creado.

Lo que NO se hizo, a propósito: escribir ese `CREATE TABLE` a partir de las
columnas que el código consulta. Serían tipos, nulabilidad, defaults, claves e
índices adivinados, y una base *parecida* es peor que no tener base — los
benchmarks medirían otra cosa y nadie lo notaría.

Lo que sí se hizo: `frontend/scripts/db-schema-contract.mjs` declara el
**contrato** —qué relaciones y columnas necesita la aplicación— derivado de lo
que el código realmente consulta, con un verificador de sólo lectura. Sirve para
comprobar que una Preview recién creada sirve *antes* de invertir horas en
cargarla, y para detectar deriva entre entornos.

Dos tests lo mantienen honesto: uno falla si el SQL de la aplicación menciona una
columna que el contrato no declara —la deriva silenciosa que dejaría de
protegernos sin que nada falle—, y otro falla si el contrato declara columnas que
nadie usa, porque un contrato inflado rechaza bases que servirían.

### El orden real, entonces

El paso 4 del orden de abajo cambia: antes de aplicar migraciones hay que
**capturar la baseline del esquema desde el proyecto actual**, con acceso de sólo
lectura, y versionarla sanitizada. Recién después el bootstrap es reproducible.

## Qué está preparado y espera

Todo lo siguiente está escrito, testeado donde corresponde, y se ejecuta sin
rediseño en cuanto exista el `project_ref` de Preview:

| Artefacto | Qué hace |
| --- | --- |
| `frontend/scripts/db-target-guard.mjs` | impide correr DDL contra el proyecto equivocado |
| `supabase/proposals/20260827_public_postgis_acl_hardening.sql` | P0 de ACL, con preflight y validación en transacción |
| `…_acl_hardening.rollback.sql` | su rollback exacto |
| `…_acl_verify.sql` | verificación de sólo lectura, antes y después |
| `supabase/migrations/20260827120000_quality_gate_eligibility.sql` | schema `eretz_gate` con la invariante como CHECK |
| `supabase/rollbacks/20260827120000_…rollback.sql` | su rollback |
| `frontend/scripts/import-quality-gate.mjs` | importa el manifiesto con swap atómico |

## Orden de ejecución, cuando haya acceso

1. Crear el proyecto de Preview y anotar su `project_ref`.
2. Agregar `project_ref` al `.mcp.json` y quitar `read_only`.
3. Declarar el destino: `ERETZ_DB_TARGET_EXPECT=<ref-preview>` y
   `ERETZ_DB_PRODUCTION_REF=pggrvzyixyjkhfknpurg`. La guarda rechaza el
   segundo aunque alguien lo declare como esperado.
4. Bootstrap del esquema desde `supabase/migrations/`.
5. Sembrar el dataset representativo.
6. ACL P0: aplicar, verificar, **ensayar el rollback**, volver a aplicar.
7. Migración `eretz_gate` e importación del manifiesto.
8. Equivalencia OLD vs NEW antes de tocar el camino de lectura.
9. `EXPLAIN ANALYZE`, índices justificados, benchmarks antes/después.
10. Apuntar Vercel Preview a la base de Preview. **Producción no se toca.**

## Lo que no cambia

- la base real no recibe DDL experimental;
- Data API sigue apagada para el frontend;
- PostgreSQL server-only;
- Quality Gate fail-closed;
- ningún secreto versionado.

# `STAGING_PROMOTION_DRYRUN` — qué pasaría si promoviéramos, medido

**Estado: DRY RUN. Nada ejecutado. `database_writes: 0`.**
Medido el 2026-09-14 contra `inmolink`, sólo lectura, vía MCP.

Esto corrige dos cosas que yo mismo escribí en
`ERETZ_PROMOCION_STAGING_A_MAIN.md` y que la medición no sostiene.

---

## 1. La foto

| | filas |
|---|---:|
| `inmobiliarias_main` | 7.004 |
| `inmobiliarias_staging` | 12.263 |
| promovidas alguna vez (`staging_id_origen` no nulo) | 138 |
| `propiedades` | 257.073 |

## 2. Qué es insertable, por fuente

Comparando por nombre aplastado —minúsculas, sin puntuación ni espacios— contra
`main`:

| fuente | filas | ya en main | homónimas dentro de staging | insertables limpias |
|---|---:|---:|---:|---:|
| `zonaprop_inmobiliarias` | 9.040 | 6 | 198 | 8.838 |
| `excel_colegio_cpi_cordoba` | 2.498 | 138 | 0 | 2.360 |
| `roomix_agency_coverage` | 725 | 32 | 0 | 693 |
| **total** | **12.263** | **176** | **198** | **11.891** |

## 3. La primera corrección: promover 11.891 filas no produce inventario

De esas 11.891 insertables:

| campo | cuántas lo traen |
|---|---:|
| `web` | **4** |
| `telefono_principal` | **0** |
| `url_listado` | **0** |
| `provincia` | 2.360 (todas de Córdoba) |

Una fila promovida sin `web` y sin `url_listado` queda `READY` por FK y sin
nada que scrapear. **La promoción masiva crearía 11.891 inmobiliarias en `main`
y cero propiedades.**

Yo había escrito que la promoción era "el cuello de botella real". Es *un*
cuello de botella —sin FK la cola no las toma— pero destaparlo solo no mueve el
inventario. Faltaba medir qué traían las filas adentro.

## 4. La segunda corrección: `needs_manual_review` no es una señal de calidad

11.396 de 12.263 filas están marcadas `needs_manual_review`. Parecía un filtro
de calidad que habría que respetar. No lo es:

| fuente | filas | marcadas | revisadas por alguien | `ia_es_inmobiliaria` |
|---|---:|---:|---:|---|
| `zonaprop_inmobiliarias` | 9.040 | 9.040 | 0 | NULL en todas |
| `excel_colegio_cpi_cordoba` | 2.498 | 2.356 | 0 | NULL en todas |
| `roomix_agency_coverage` | 725 | 0 | 0 | NULL en todas |

Las dos primeras se dieron de alta el **2026-05-16**, el mismo día, con la marca
puesta de entrada por el import. `revisado_por` es nulo en las 12.263: nadie
revisó nunca una fila. Y `ia_es_inmobiliaria` es NULL en las 12.263, o sea que
**la clasificación por IA no corrió jamás**.

Tratar esa marca como rechazo daba "0 filas promovibles", que es un número
falso: no es un juicio, es un valor por defecto de un import.

## 5. Lo que sí desbloquea inventario

Contado entero, no estimado. Cruzando el artefacto del resolver
(`AGENCY_ID_RESOLUTION_FINAL.jsonl`, las que traen
`STAGING_NAMESPACE_NOT_A_MAIN_FK`) contra nuestras webs verificadas:

```
bloqueadas por staging                4.953
  con UN dominio cualquiera           1.605
  con web AFIRMABLE verificada          680   <- las promovibles con fuente

agencias con web AFIRMABLE              849
  de esas, bloqueadas                   680   (80 %)
```

**680 agencias** están paradas únicamente por la FK y ya tenemos su web
verificada. Esas son las que hay que promover: no son 11.891 filas, son 680, y
son las únicas de las que se puede sacar una propiedad el día después.

Los 1.605 "con dominio conocido" del tablero son otra vara: ahí alcanza con que
haya *un* dominio en la resolución, verificado o no. Los 680 pasaron el
verificador. Las dos cifras son ciertas y miden cosas distintas.

> Una corrección: antes de encontrar el artefacto del resolver estimé este
> número con una muestra de 120 nombres contra la base, y dio 89 % → ~757. El
> conteo entero da 80 % → 680. Vale el conteo.

## 6. El write propuesto, escrito para que se pueda mirar antes

```
alcance:        las 680 agencias con web AFIRMABLE que sólo existen en staging
por fila:       INSERT en inmobiliarias_main con
                  nombre, nombre_normalizado, ciudad, provincia
                  web            <- de AGENCY_OFFICIAL_WEB_VERIFIED.jsonl, no de staging
                  staging_id_origen <- el id de la fila de staging
                  verificada     <- false
reversible:     sí. `delete from inmobiliarias_main where staging_id_origen in (...)`
                mientras ninguna propiedad les cuelgue todavía.
lotes:          de 50, con recuento antes y después
no incluye:     las 198 homónimas dentro de staging, que necesitan una decisión
                por caso y no una regla
```

## 7. Lo que sigue bloqueado

- **La autorización.** Este write no se ejecuta sin que lo pidas: sigue en pie
  `WAITING_USER_ACTION` para cualquier escritura productiva staging→main.
- **Las 198 homónimas** de Zonaprop: dos filas con el mismo nombre aplastado.
  Promover las dos duplica; promover una elige por nosotros.
- **Las ~11.100 restantes**: no tienen web en ninguna parte. Promoverlas no las
  acerca a producir una propiedad, y ensucia `main` con filas vacías.

## 8. Cómo se reproduce

Las consultas son de lectura y están en el historial de esta sesión. Las tres
que sostienen los números de arriba:

1. conteo de filas por tabla y promovidas;
2. clasificación por fuente con nombre aplastado contra `main`;
3. el cruce del artefacto del resolver contra las webs verificadas, entero.

`database_writes: 0` en las tres.

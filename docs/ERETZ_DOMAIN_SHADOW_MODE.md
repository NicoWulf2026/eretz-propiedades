# ERETZ Propiedades — modo sombra del dominio

Fecha: 2026-08-27 · Código en `frontend/src/lib/shadow/`

## Qué es

Correr los motores del dominio —calidad de datos, moderación, puntaje— sobre las
propiedades reales que ya pasan por la aplicación, **para medir qué dirían**.

**No deciden nada.** Ninguna propiedad se oculta, ningún orden cambia, ningún
conteo cambia, ninguna URL cambia. El Quality Gate sigue siendo la única
autoridad de visibilidad.

Existe porque dieciocho módulos de dominio están testeados contra casos que
escribí yo, y eso demuestra que la lógica hace lo que dice — no que sus umbrales
sean razonables. La forma de saberlo sin arriesgar nada es calcular y no
aplicar.

## Cómo se garantiza que no puede cambiar nada

No es una promesa, son tres propiedades estructurales:

1. **`ejecutarShadow` devuelve `void`.** El sitio de llamada no tiene forma de
   usar el resultado para decidir algo, ni hoy ni cuando alguien lo edite dentro
   de seis meses.
2. **`ResumenShadow` no contiene propiedades.** Sólo conteos, códigos y números.
   No hay por dónde filtrar una lista.
3. **Todo está dentro de un `try`.** Un error midiendo no puede romper una
   búsqueda. Un observador que tira abajo lo que observa es peor que no tenerlo.

Hay tests para las tres, incluida la equivalencia del arreglo de propiedades con
la flag encendida y apagada.

## La flag

```
ERETZ_DOMAIN_SHADOW_MODE=true     # apagada por defecto
ERETZ_DOMAIN_SHADOW_SAMPLE=0.1    # opcional; por defecto 1 cuando está encendida
```

Server-only (`import "server-only"`: si alguien la importa desde un componente
de cliente, el build falla). Sin prefijo `NEXT_PUBLIC_`, que la inlinearía en el
bundle.

Sólo el string exacto `"true"` la enciende. No hay `!== "false"`, que es la
forma habitual de que algo se encienda por accidente. Con la flag apagada el
costo es una comparación de strings antes de recorrer el lote.

El muestreo sale del **hash del id**, no de `Math.random()`: con aleatoriedad, la
misma propiedad entraría en la muestra en una request y no en la siguiente, y
comparar dos mediciones dejaría de ser posible.

## Punto de integración

Uno solo: `mapRowsToProperties` en `lib/property-db-service.ts`.

Todo lo que se convierte en `Property` pasa por ahí, así que no hace falta
cablearlo en cards, ficha, mapa ni perfiles — y no puede evaluarse dos veces lo
mismo.

## Hallazgos

### 1. El mapper sanea antes de que el dominio mire

`mapSupabasePropertyToProperty` no traduce: **sanea**.

| Dato crudo | Qué llega al dominio |
| --- | --- |
| Coordenadas fuera de la Argentina | `null` |
| Coordenadas en (0,0) | `null` |
| Precio negativo | `null` |
| Título ausente | `"Propiedad sin título"` |
| Operación ausente | `"consultar"` |
| Tipo desconocido | `"otro"` |

Consecuencias, las dos importantes:

- Tres reglas de `data-quality` —`COORDENADAS_FUERA_DE_RANGO`,
  `COORDENADAS_CERO`, `VALOR_NEGATIVO`— **no pueden dispararse en el camino de
  lectura**. No porque el dato esté bien, sino porque llega convertido en
  ausencia. Cualquier medición del modo sombra **subestima** los problemas del
  dato crudo, y leerla como si midiera la ingesta sería un error.

- Las últimas tres filas obligaron al adaptador a leer la fila cruda además de
  la propiedad mapeada. Sin eso, **ninguna publicación aparecería jamás sin
  título**, y "sin operación" sería indistinguible de "operación a consultar".

Un precio negativo queda indistinguible de "a consultar": la información de que
venía un `-5000` se perdió antes, en el mapeo.

No se corrige leyendo siempre la fila cruda, y es deliberado: el modo sombra
mide **lo que la aplicación ve**, que es lo que decidiría si las reglas se
activaran acá. Medir la calidad del dato crudo es otra pregunta y su lugar es el
pipeline de ingesta.

### 2. El logger descarta en silencio lo que no es escalar

`logEvent` acepta campos extra, pero los que no son string, número o booleano se
borran sin dar error. Loguear el resumen anidado habría escrito una línea casi
vacía y nadie se habría enterado.

Es una **buena defensa** —impide que un objeto anidado cuele datos de una
persona sin pasar por el redactor— y por eso el resumen se aplana en
`aplanarResumen` en vez de aflojar el logger. Hay un test que verifica que todo
campo del aplanado sea escalar.

### 3. Los duplicados no se evalúan

Detectarlos exige comparar contra el resto del catálogo, no mirar una
publicación sola. En modo sombra se pasa `NO_MATCH`, que acá significa **"no
evaluado"**, no "verificado que no lo es".

Consecuencia directa: el único camino a `REJECT` para lo scrapeado es
`DUPLICADO_CONFIRMADO`, así que **el REJECT de scrapeadas da 0 por construcción,
no por medición**. Una lectura que celebre ese 0 estaría leyendo mal.

## Qué se loguea

Una línea por lote, no una por propiedad: 24 líneas por request de listado no
serían legibles.

```
event=domain_shadow_summary route=mapRowsToProperties
evaluadas=24 omitidas=0
mod_allow=18 mod_review=6 mod_reject=0
dq_valid=12 dq_suspicious=8 dq_invalid=2 dq_quarantine=2
score_p10=… score_p50=… score_p90=…
dim_completeness=… dim_consistency=… dim_location=… dim_media=… dim_publisher=…
razon_1="SIN_IMAGENES:14:1001,1002,1003"
origen_SCRAPED="24/6/0"
domain_shadow_ms=2
```

**Nunca viaja**: título, descripción, dirección, teléfono, email, nombre de
agente, texto de búsqueda, URL de la fuente, tokens, DSN. Hay un test que lo
verifica contra una propiedad cargada a propósito con todos esos campos.

**Sí viajan ids de propiedad**, hasta tres por código de razón. Son públicos
—están en la URL de la ficha—, no identifican a ninguna persona, y sin un
ejemplo concreto "este código marca el 20% del catálogo" no se puede
investigar.

## Umbrales diagnósticos

Escriben un `warn` en el log. **No ocultan nada ni cambian nada.**

| Umbral | Valor | Por qué |
| --- | --- | --- |
| `REJECT_ALTO` | > 1% | Un rechazo sobre lo scrapeado esconde inventario real |
| `REVIEW_ALTO` | > 25% | Una de cada cuatro a revisión hace la cola impracticable |
| `RAZON_DOMINANTE` | > 50% | Un solo código marcando la mitad casi siempre es un bug de regla |

## Estado de la medición

**No se midió sobre el catálogo real.** Este entorno no tiene credenciales de
base (`SUPABASE_DATABASE_URL` ausente) y el MCP de Supabase está fuera de
alcance. La distribución real de las 257.073 publicaciones sigue sin conocerse.

Lo que sí se midió es la **calibración de las reglas** contra un corpus de 25
variantes plausibles que cubre monedas, modalidades de precio, tipos, niveles de
confianza geográfica, cantidad de fotos y tipos de publicador. Las proporciones
del corpus son parejas a propósito y **no representan al catálogo**.

Ver `lib/shadow/calibration.test.ts`, que imprime la evidencia al correr.

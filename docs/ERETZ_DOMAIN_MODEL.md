# ERETZ Propiedades — modelo de dominio

Fecha: 2026-08-27 · Código en `frontend/src/domain/`

Todos los módulos son **puros**: sin base, sin red, sin `localStorage`. Eso los
hace testeables de forma exhaustiva y permite construirlos mientras la
ejecución sobre base está congelada (`PATH_B_NO_ADDITIONAL_INFRA_COST`).

Ninguno reemplaza código que hoy funciona. `src/types/property.ts` sigue siendo
el tipo de la capa de presentación; esto es el modelo hacia el que migrar.

## La separación que sostiene todo lo demás

Hoy un único tipo `Property` mezcla tres cosas que cambian por motivos y en
momentos distintos:

| | Qué es | Cambia cuando |
| --- | --- | --- |
| **Propiedad física** | El inmueble del mundo real | Casi nunca |
| **Publicación** | Un aviso de ese inmueble | Baja el precio, cambian las fotos |
| **Publicador** | Quién lo publica | Cambia de inmobiliaria |

Mientras todo venía de scraping y se mostraba de a uno, la fusión no molestaba.
Rompe con tres cosas que vienen:

- la misma propiedad publicada por dos inmobiliarias a dos precios;
- una inmobiliaria corrigiendo su aviso sin tocar el de otra;
- **contar la oferta de un barrio** sin contar tres veces el mismo departamento.

El tercero es el que más importa: si Mercado cuenta avisos en vez de inmuebles,
toda métrica sale inflada por un factor desconocido que además varía por zona
—en zonas caras hay más multi-publicación—, así que ni siquiera es un error
parejo que se pueda descontar después.

## Tres ejes de estado, no uno

El encargo proponía un único ciclo `DRAFT → PENDING → ACTIVE → …`. El código
sugería otro modelo, y se siguió el del código.

`PropertyStatus` hoy vale `activa` / `no_detectada_en_ultimo_scraping` /
`desconocida`. Eso no es un ciclo de vida: es **lo que el scraper vio la última
vez que miró**. Nadie decidió "activa"; se observó.

Para las 257.073 publicaciones scrapeadas el ciclo editorial **no existe**:
ningún publicador apretó "publicar" en ERETZ. Escribirles `lifecycle: PUBLISHED`
inventaría una decisión que nadie tomó, y volvería indistinguible "el dueño la
activó" de "la vimos publicada en otro lado".

| Eje | Qué responde | Aplica a |
| --- | --- | --- |
| Observación | qué vimos | todo lo scrapeado |
| Ciclo editorial | qué decidió quien publica | sólo lo publicado en ERETZ (`null` si no) |
| Moderación | qué decidimos nosotros | todo, independiente de los otros dos |

`NOT_ASSESSED` no es lo mismo que `ALLOWED`: lo no evaluado no está aprobado,
sólo no mirado. Se muestra igual, porque es el estado de todo el catálogo
actual y ocultarlo lo vaciaría — pero queda como decisión visible y no como
descuido.

## Permisos: tres reglas que no se negocian

`domain/permissions.ts`.

1. **Deny by default.** No hay `return true` de cierre. Todo camino de error,
   dato faltante o caso no contemplado termina en `false`.
2. **El tenant sale del recurso, nunca del pedido.** Si el `organizationId`
   contra el que se compara viniera del cliente —query string, body, o la
   organización "seleccionada" en el browser—, cualquiera se declara dueño de lo
   que quiera. Tiene que venir de haber **cargado el recurso** del servidor.
3. **El rol no es el permiso.** Cero `if (role === "ADMIN")` disperso. Los roles
   se traducen a capacidades en un solo lugar, así que cambiar qué puede hacer
   un `MANAGER` es editar una tabla, no auditar la aplicación.

Los tests recorren la **matriz completa rol × capacidad** contra un recurso de
otro tenant: agregar una capacidad y olvidar el chequeo de tenant hace fallar la
suite.

Un recurso sin dueño —una publicación scrapeada no reclamada, o sea las 257k de
hoy— no lo administra nadie. Es lo que impide que reclamar una inmobiliaria
cualquiera dé poder sobre catálogo ajeno.

## Identidad: lo inferido no se presenta como afirmado

Es el hilo común de agentes, duplicados y reclamaciones.

**Agentes.** De `agente_nombre` sabemos una cosa: ese texto apareció en esa
página. No si dos "Juan Pérez" son la misma persona, ni si "Ventas" es una
persona. Publicar un perfil de alguien real, armado por nosotros, sin que lo
sepa ni pueda corregirlo, es un problema de datos personales antes que técnico.
El perfil público exige que la persona lo haya reclamado. Que el **nombre**
aparezca en una ficha, como aparece hoy, es otra cosa y no cambia.

**Duplicados.** Agrupar puede estar mal, así que el agrupamiento es metadato
reversible con evidencia y nunca destruye publicaciones. `POSSIBLE_MATCH` no
agrupa solo, por asimetría de daño: agrupar de más funde dos propiedades y hace
desaparecer oferta real, que nadie ve; agrupar de menos muestra un duplicado,
que es visible y molesto pero no destruye nada.

**Reclamaciones.** La distinción que decide es si la evidencia se puede
falsificar mirando la web pública. El teléfono de una inmobiliaria está a la
vista: saberlo no prueba nada. Recibir un código *en* ese teléfono sí. Conocer
el CUIT o la matrícula nunca aprueba solo. Y una organización que ya tiene dueño
no se reclama por vía automática, por fuerte que sea la evidencia.

## Overrides: tres capas, la del medio es la nueva

`domain/overrides.ts`.

```
SOURCE SNAPSHOT     lo que dice la fuente. Sólo lo escribe el scraper.
EDITORIAL OVERRIDE  lo que corrige el dueño, campo por campo, con autor y fecha.
PUBLISHED VIEW      lo que ve el público. Se CALCULA, no se guarda.
```

Dejar que la inmobiliaria edite la fila directamente falla por dos motivos que
se refuerzan: el scraper vuelve a pasar y le pisa la corrección, así que tendría
fecha de vencimiento; y se pierde de dónde salió el dato, que es lo que hay que
poder responder ante un reclamo.

`sourceUrl` no es corregible: es la prueba de origen. Y solicitar la baja **no
oculta por sí solo** — hacerlo permitiría usar el flujo para borrar competencia.
Abre un caso; la decisión es aparte.

## Sincronización: el problema es que no hay fechas

`domain/sync.ts`.

`getFavorites()` devuelve `string[]`. Sólo ids. Eso hace **indecidible** el caso
central de una fusión: la propiedad 123 está en la nube y no en el navegador,
¿nunca la marqué acá, o la desmarqué?

Se elige unión —conservar— por asimetría de daño: un favorito que reaparece se
quita en un click; uno que desaparece no se nota hasta que alguien lo busca. No
es la respuesta correcta, es la menos mala sin fechas. La correcta son las
lápidas: el modelo ya las soporta, falta que `local-store.ts` las emita.
Mientras tanto `resurrecciones` deja anotado qué entró por unión, para que el
costo sea medible y no invisible.

El plan está separado de la confirmación para que sea imposible limpiar lo local
antes de que la nube confirme.

## Calidad de datos: dos clases de señal

`domain/data-quality.ts`. Detecta y explica; **no corrige**. Corregir un dato
scrapeado es reemplazar lo que dice la fuente por lo que suponemos, y después
nadie distingue el dato real del inventado.

| | Ejemplos | Veredicto |
| --- | --- | --- |
| **Incoherencia interna** | cubierta > total, dormitorios > ambientes, negativos | `INVALID` |
| **Valor atípico** | depto de 12 m², precio de USD 300, 400 años | `SUSPICIOUS` |

La primera es una contradicción aritmética: no depende de ninguna suposición
sobre el mercado. La segunda es un juicio sobre qué es *bastante raro como para
mirarlo* — un monoambiente de 12 m² existe. Por eso los umbrales están todos
juntos, con nombre y configurables.

Faltar campos es `INFO`, no error: tratar como inválida una publicación sin
fotos sacaría del catálogo publicaciones reales.

## Calculadoras: ninguna tasa está escrita

`domain/finance.ts`. Toda tasa, comisión y alícuota es **parámetro**. Los
honorarios y el sellado varían por provincia y la inflación vuelve obsoleto
cualquier número en meses, así que una calculadora con un 3% adentro da un
resultado con apariencia de autoridad que puede estar mal por un factor grande.

Las fracciones mayores que 1 se rechazan: escribir `3` en vez de `0,03` daría
una comisión de 300.000 sobre 100.000 sin que nada falle.

La cuota hipotecaria se ancla contra el valor canónico del sistema francés (USD
100.000 al 6% a 30 años = USD 599,55) y `capacidadDeCompra` se verifica como su
inversa exacta: si el círculo no cierra, una de las dos está mal y las dos
parecen razonables por separado.

**Fuera a propósito:** créditos UVA y comprar-vs-alquilar. Dependen de inflación
y apreciación futuras, así que son simulaciones y no cálculos. Presentarlas
junto a las demás las haría pasar por lo que no son.

## Mercado: metodología antes que UI

`domain/market.ts`. Una estadística mal hecha no se ve mal: "USD 2.340/m² en
Fisherton" se lee con la misma autoridad calculada sobre 800 avisos o sobre 3.

1. **Mediana, no promedio.** Un country de USD 3.000.000 entre veinte
   departamentos de USD 90.000 mueve el promedio un 15% y la mediana nada.
2. **Se cuentan propiedades, no avisos.**
3. **Una sola moneda por serie.** Sin convertir con cotizaciones supuestas.
4. **Si la muestra no alcanza, no se publica.** Sin advertencia al pie: una
   advertencia al lado de un número grande no protege a nadie.

El mínimo se exige sobre la muestra **final**, tras deduplicar y recortar colas.
Con el recorte por defecto, llegar a 30 propiedades finales requiere unas 34 de
entrada.

`diagnosticarMercado()` deja como comprobación ejecutable que hoy **no** se
puede publicar, en vez de una opinión en un documento que envejece. Los dos
bloqueos, medidos sobre producción: no existe resolución de propiedad física, y
sólo el 25,3% de las publicaciones tiene coordenadas (65.033 de 257.073).

## Qué NO se expone

Cumpliendo la regla de no crear UI falsa:

| Módulo | Estado | Por qué |
| --- | --- | --- |
| `publishing.ts` | no enlazado | sin persistencia, un formulario público pierde lo que la persona carga |
| `claim.ts` | no expuesto | sin persistencia no hay expediente |
| `permissions.ts` | no cableado | sin cuentas no hay actor |
| `sync.ts` | no conectado | sin nube no hay con qué fusionar |
| `finance.ts` | sin UI | la lógica está lista; la UI es trabajo aparte |
| `market.ts` | sin páginas | el diagnóstico dice que los datos no alcanzan |

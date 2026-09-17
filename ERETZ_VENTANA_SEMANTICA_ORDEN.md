# El orden de la ventana semántica, con los números medidos

**2026-09-17 · `database_writes: 0` · nada de esto se aplica todavía**

El §87 dice que al cerrar el bulk hay que rankear defectos, calcular presupuestos
de riesgo y abrir **una** ventana. Este documento es ese ranking, armado con lo
medido y no con una fórmula.

---

## Por qué no hay un score

El §51 propone `RISK × AFFECTED_PROPERTIES × REUSE × CERTIFICATION_IMPACT ÷
IMPLEMENTATION_COST`. Aplicado literalmente a los datos de hoy, el primer puesto
se lo lleva `PORTAL_COMO_FUENTE`: **4.010 propiedades afectadas**, más que
cualquier otra familia salvo el cajón sin clasificar.

Y sería exactamente al revés de lo que hay que hacer. Esas 4.010 son inventario
**ajeno**: corregir esas fuentes las **quita** del catálogo. Es trabajo correcto
y urgente, pero el número que lo empuja al primer puesto mide una pérdida, no una
ganancia.

Un score habría escondido eso detrás de una multiplicación. Así que las
`affected_properties` se separan en tres cosas que no se suman entre sí:

| | qué significa |
|---|---|
| **RECUPERA** | propiedades que hoy no tenemos y pasaríamos a tener |
| **CORRIGE** | propiedades que ya tenemos y cuyo dato mejoraría |
| **QUITA** | propiedades que ingerimos mal y dejaríamos de ingerir |

---

## El precio, y una cifra mía que estaba mal

Medido con `presupuesto_de_riesgo.py` sobre las 261 certificaciones alcanzables.
Las horas son la **suma** de lo que ya tardó cada agencia, no una estimación:

| componente | agencias | % | horas (2 workers) |
|---|---:|---:|---:|
| `shared/*` (los seis) | 261 | 100% | **23,9** |
| `generic/common` | 134 | 51% | 15,3 |
| `connector/tokko` | 86 | 33% | 6,2 |
| `strategy/generic/html_catalog` | 49 | 19% | 2,5 |
| `connector/wordpress` | 35 | 13% | 2,0 |

Esta cifra decía **9,5 h** hasta que la verifiqué, y estaba mal: se calculaba
`mediana × cantidad`. La mediana contesta *"¿cuánto tarda una agencia típica?"*;
el costo de rehacerlas todas es la **suma**, y la suma está medida. La
distribución explica la diferencia —mediana 264 s, promedio 660 s, máximo 10.846 s,
y **64 agencias de más de diez minutos que solas aportan 36,3 de las 47,9 horas**
de worker—.

Casi veinticuatro horas para recertificar el universo entero. Sigue siendo
asumible, pero es 2,5 veces lo que dije antes, y eso cambia el criterio:
la pregunta deja de ser *"¿vale la pena invalidar todo?"* y pasa a ser *"¿qué
metemos en las 23,9 horas que vamos a pagar igual?"*.

Porque el radio **no se suma**. Tres arreglos que tocan `shared/*` cuestan las
mismas 23,9 horas que uno. La ventana se paga una vez.

---

## El orden

### P0 — nada

No hay hoy ningún defecto abierto que cumpla P0: no hay COMPLETE falso, no hay
contaminación entre agencias, no hay corrupción. Lo más cerca es la colisión de
ids estables, y se midió que **no** afecta inventario.

### P1 — entran a la ventana, y las tres primeras comparten las mismas 23,9 h

**1. `ambientes` anclado a etiqueta, con límite de palabra**

| | |
|---|---|
| componente | `shared/certifier` → 261 agencias, 23,9 h |
| efecto | **CORRIGE** ~1.600 propiedades de la familia más cara |
| evidencia | el legacy saca 5 de 5 en fichas reales de `bottega`; el conector cierra `EXTRACTION_FAILED` con 41% |
| costo | bajo: la regla existe en `playwright_scraper.py`, se porta adaptada |

`extraccion_transversal_de_atributos` acumula **17 paros y 44,0 h** de cola
parada, la causa más cara del tablero. La señal del certificador **ya dispara**
sobre `Ambientes 5`: el dato se pierde en el extractor, no en la señal (§39).

Va con su prohibición: la regla histórica y la señal actual **las dos** fabrican
`ambientes=1` desde `Monoambiente 1 dormitorio`. Hay tres `xfail` abiertos
esperando este arreglo.

**Y son dos sub-casos opuestos, que un solo arreglo tiene que distinguir.**
Salió de consultar el banco por `bottega` con `ya_lo_vimos.py`:

| | sitio | qué pasa | qué corresponde |
|---|---|---|---|
| **A** | `bottega` | publica `Ambientes 5` rotulado y limpio, y **no lo extraemos** | recuperar el dato |
| **B** | `bartolelli maini` | **no publica ambientes** —publica dormitorios— y la palabra sólo aparece en el menú | que la señal **deje de dispararse** |

En A el fallo es del extractor y `EXTRACTION_FAILED` es correcto. En B el fallo
es de la señal: 28 de 29 "provistos" no existían, y el estado correcto sería
`NOT_PROVIDED`.

Confundirlos hace lo peor de los dos lados. Si sólo se afloja el extractor, B
empieza a inventar un `1` desde el menú; si sólo se endurece la señal, A queda
sin recuperar. Anclar a **etiqueta con límite de palabra** resuelve los dos a la
vez: la etiqueta rotulada se lee, la palabra suelta del menú no.

**2. `barrio`: por qué se rechaza la mitad**

| | |
|---|---|
| componente | validación geográfica → `shared/*`, mismas 23,9 h |
| efecto | **CORRIGE** hasta 159 propiedades sólo en `di maria` |
| evidencia | `barrio` se rechaza el **26,2%** en todo el universo, la tasa más alta de cualquier campo |

No está diagnosticado todavía: se sabe *cuánto* se rechaza, no *por qué*. Entra a
la ventana con el diagnóstico como primer paso, no con un parche.

**3. Descubrir catálogo en `location.href` dentro de funciones**

| | |
|---|---|
| componente | descubrimiento genérico → `generic/common`, 134 agencias, 15,3 h |
| efecto | **RECUPERA** ~365 propiedades sólo en `david rodriguez` |
| alcance | 4 de 38 agencias `SIN_INVENTARIO` medidas |

Verificado que **no es una regresión**: el scraper legacy también da cero contra
esa fuente. Es capacidad nueva.

**4. Enrutado a `generic/sitemap` cuando el camino elegido da cero**

| | |
|---|---|
| efecto | **RECUPERA** 91 propiedades en `franchi` |
| alcance | **1 agencia**, medido |

Se midió la hipótesis de que fuera una familia de Houzez: **1 de 38**.
Refutada. Entra por barato, no por grande.

### P1 aparte — `PORTAL_COMO_FUENTE`, que no es de esta ventana

| | |
|---|---|
| efecto | **QUITA** 4.010 propiedades ajenas |
| componente | **ninguno**: es corrección de DATOS en el registro de fuentes |
| radio de invalidación | **cero huellas** |

Es el número más grande de la tabla y **no necesita ventana semántica**. Se
corrige en el registro, como ya se hizo con seis agencias y con el canario de
cambio de fuente. Está acá para que no se lo confunda con trabajo de conector.

### P2 — después

**Los cuatro TFW que no se leen, y que NO son una familia rota**

| | |
|---|---|
| efecto | **RECUPERA** 30 propiedades comprobadas en `di santo` |
| alcance | **4 de 85** agencias con frontend propio de Tokko |

Medido a raíz del paro de `di santo` el 2026-09-17: **85 agencias** usan TFW y
**78 cierran `CERTIFIED_COMPLETE`**. El conector funciona en el 92%. Con cero
enumeradas hay cuatro —`coldwell banker andes`, `etcheverry`,
`fios consultoria`, `di santo`— y de las cuatro sólo `di santo` tenía inventario
previo (baseline 30).

La conclusión importa más que el número: **no hay que reescribir el conector de
Tokko**. Hay que entender qué tienen de distinto esos cuatro sitios respecto de
los 78 que sí se leen.

Y los cuatro **no son el mismo caso**. `ya_lo_vimos.py` lo sacó a la luz al
buscar precedentes de `di santo`, y verificarlo obligó a corregir dos veces lo
que yo mismo había escrito.

`coldwell banker andes bienes raices` figura como `TOKKO_FRONTEND_PROPIO`.
Primero escribí que **su sitio no es Tokko**, repitiendo su propia diferida, que
decía "PHP plano". Al comprobarlo contra la fuente resultó medio cierto y medio
falso, y la mitad falsa era la mía:

- **es Tokko de verdad.** Sus imágenes salen de
  `static.tokkobroker.com/thumbs/<id>_...` y esos ids coinciden con los de las
  fichas. La clasificación de plataforma está **bien**;
- **pero su frontend es PHP a medida**, no TFW: las fichas viven en
  `ficha.php?id=6699459`, no en las rutas del producto de Tokko. Son **17**, con
  los precios a la vista en el listado.

Lo que está mal entonces no es la plataforma sino el mecanismo:
`TOKKO_FRONTEND_PROPIO` mete en la misma bolsa *"datos de Tokko"* y *"el
frontend propio de Tokko"*, que son cosas distintas. El conector espera lo
segundo y este sitio es lo primero sobre un frontend ajeno.

Y el arreglo es barato, porque el catálogo está en HTML plano: ya existe
`generic/php_query_catalog`, hoy usada por una sola agencia.

Y la cuarta tampoco es lo que parecía. `fios consultoria inmobiliaria` tiene
como fuente registrada:

    https://www.fios.com.ar/emprendimiento-64427-condominio-en-fisherton

Es **la página de un solo emprendimiento**, no el catálogo. La raíz del sitio
—`fios.com.ar/`— enlaza a `propiedades` y está viva. Es la misma clase que
`danisa robledo`, cuya fuente declarada era una ficha suelta dentro de un
marketplace: no falla nada del pipeline, apunta al lugar equivocado.

**Se corrige en el registro de fuentes, sin tocar una huella.**

Así que de los cuatro "TFW que no se leen" queda **uno solo** que de verdad lo
es y de verdad no se lee —`etcheverry`, con el contenedor vacío—, más `di santo`
con el mismo síntoma, uno que necesita otra estrategia y uno que necesita otra
URL. Contarlos como un grupo de cuatro habría llevado a escribir un arreglo de
conector para problemas que en dos casos son de datos.

Es también el primer caso donde el banco de firmas pagó: `etcheverry` se había
diagnosticado el 2026-09-14 y `di santo` se cerró reconociendo la firma en vez
de investigando de cero.

- **id estable colapsado**: 25 agencias, 10 `CERTIFIED_COMPLETE`. No afecta
  inventario hoy; sí afectaría a dedupe y lifecycle, que todavía no corren.
- **heartbeat remoto portado**: radio cero, ataca el 80% del tiempo perdido,
  **bloqueado por autorización de base de datos**.
- **`contador` con separador de miles**: sub-cuenta, y sub-contar es el lado
  seguro. `xfail` abierto.

---

## Lo que NO entra, y por qué

| | motivo |
|---|---|
| re-detección masiva con el detector v2 | acierta **1 de 4**, y ese 1 rutea a la estrategia que ya falla |
| re-detección **dirigida** a las que enumeran cero | se hizo, sobre las 14 con plataforma declarada y cero enumeradas: **1 desacuerdo** (`carlos castaño`, WORDPRESS → LARAVEL). Las otras 13 coinciden, `coldwell banker` incluida con 0,9 de confianza. La plataforma casi nunca es el problema |
| ampliar la lista de hosts-portal | `365litoralargentino` lo usa 1 agencia; 3 de 4 hosts compartidos ya cerrados |
| alinear detector con conector | 19 desacuerdos, 7 de ellos `CERTIFIED_COMPLETE`; no cuesta inventario |
| reinicio automático tras corte por lote | **8 cortes contra 63 paros: recupera el 11%**. Un corte por lote es una salida limpia y planificada, así que reiniciar ahí NO sería el reinicio prohibido tras un STOP sin diagnosticar |

Los cuatro se midieron y los cuatro dieron negativo. Quedan escritos para que no
se vuelvan a investigar, que es el §102.

---

## Antes de abrir la ventana

El §87 fija el orden y conviene respetarlo:

1. snapshot final;
2. consolidar Defect KB — hecho, con 24 agencias reclasificadas y **0
   propiedades movidas**, que es el resultado honesto;
3. consolidar tiempo perdido — hecho: 102,8 h, mediana 8 min, 80% en 9 episodios;
4. rankear — este documento;
5. presupuestos de riesgo — hechos, arriba;
6. **una** ventana, no una por hallazgo;
7. tests, replay histórico, canarios por familia —los 28 ya están congelados—,
   diff de huellas, recertificación dirigida, Regression Gate V2;
8. cerrar y volver al freeze.

El paso que falta y no depende de mí: el bulk sigue abierto. Faltan **766
agencias** de la cola actual, con cierre estimado el **2026-10-11**.

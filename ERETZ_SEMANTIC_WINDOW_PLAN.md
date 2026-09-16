# Plan de la ventana semántica: los dos primeros arreglos, listos y sin aplicar

**2026-09-15. `database_writes: 0`. Nada aplicado al runtime. Ninguna huella
tocada. La ventana se abre por decisión aparte.**

Los tests rojos están escritos y marcados `xfail(strict=True)`: la suite sigue
verde, y **el día que se aplique cualquiera de estos parches la suite se va a
romper**, obligando a quien lo aplique a venir acá a sacar el marcador. Un test
rojo que nadie ve no existe.

---

## 0. EL ORDEN FINAL — cambió, y por qué

**El primero ya no es Blanco. Es `bottai`.**

El §15 fija la regla: un arreglo de inventario con causa demostrada, 200 o más
propiedades realmente recuperables, radio controlable y paquete listo va antes
que Blanco. Bottai cumple las cuatro, y su radio no es "controlable": es
**cero**.

| orden | arreglo | qué recupera | radio de huella | recertificaciones |
|---|---|---|---|---:|
| **1** | `FORMA_DE_FICHA_NO_DECLARADA` (bottai) | **328 propiedades enteras** | **CERO** | 1 |
| 2 | `JSONLD_PRICE_SIN_CURRENCY` (blanco) | 1.206 precios + 1.185 monedas | generic/common | 57 |
| 3 | `OPERACION_SOLO_EN_TITLE` (fenix) | 179 operaciones | generic/common | las mismas 57 |
| aparte | `CATEGORY_PAGE_AS_PROPERTY` | saca 8 páginas falsas | enumeración | otro |

### Por qué bottai va primero aunque sea un número más chico

Porque **no son la misma unidad**. Blanco recupera 1.206 precios de fichas que
ya tenemos; bottai recupera 328 propiedades que hoy no existen para nosotros.
El §11 dice cuál pesa más, y no es el número más grande.

Y porque el precio es incomparable: bottai **no toca una línea de código**. Su
arreglo es declarar `patron_ficha` en el directorio de plataformas, que es un
campo de datos que `_patron_de()` ya lee y que ya habilita a 65 sitios. Cero
huellas cambian, una sola agencia se recertifica.

Blanco, en cambio, invalida 57 certificaciones para beneficiar a una agencia.

### Lo medido, 2026-09-15

```
/inmuebles devuelve 563 KB con 329 rutas distintas /inmueble_<num>
se bajaron tres: HTTP 200, con contenido PROPIO y distinto entre si
   inmueble_1070 -> "MONTEVERA, 4 Hectareas con casa", precio "Consultar"
   inmueble_6067 -> "SAN JERONIMO 1771, Sembrando IX, 3 dormitorios", $2.000.000
con patron_ficha declarado, `_fichas_en` devuelve 328   (hoy devuelve 0)
y NO toma /contacto, /empresa, /quienes-somos ni los fideicomisos
```

**Lo que todavía no está medido**, y hay que medirlo antes de prometer 328
publicables: la forma `/<slug-con-id>` es amplia, así que cada url entra con
`por_forma=True` y el guardián de detalle la valida una por una. Cuántas pasan
ese guardián no se sabe.

### Si bottai se cae en esa medición

El orden vuelve a ser Blanco + Fenix en una sola ventana `generic/common`,
como dice el §16: aplicar A, tests; aplicar B, tests; suite completa; y **una
sola** recertificación de las 57 agencias, no dos.

---

## PRIORIDAD 1 — `JSONLD_PRICE_SIN_CURRENCY` (blanco propiedades)

### Causa raíz

Cuatro pasos, todos verificados en el código y contra la fuente:

1. `_de_json_ld()` lee `offers.price` → `180000.0`, y `offers.priceCurrency`,
   que esta fuente **no publica** → `moneda = None`.
2. `normalize()` hace `precio = datos.get("precio")`, que ya no es `None`.
3. por eso **no entra** al `if precio is None` que baja al texto a buscar
   `U$S 180.000`, que es el único lugar donde está la moneda.
4. más abajo, la guarda *"un número sin moneda no es un precio"* encuentra
   precio sin moneda y **anula el precio**.

La guarda del paso 4 **está bien y no se toca**: entre pesos y dólares hay un
factor de mil. El defecto es del paso 3 — la búsqueda de la **moneda** está
atada a que falte el **precio**, y son dos cosas distintas.

### Cómo se demostró

Predicción falsable, hecha antes de mirar: *"si la ficha trae precio en JSON-LD
y no trae priceCurrency, falla; si no trae precio en JSON-LD, funciona"*.
Contrastada contra el sitio real en 12 fichas —4 que pasaban, 8 que fallaban—:
**acertó en 12 de 12**.

Antes de eso se descartaron dos hipótesis, y descartarlas importa porque las dos
eran plausibles:

- **no es la notación `U$S`**: está contemplada en `agency_certifier.py:82` y
  `a_numero()` la parsea bien en los diez formatos que se probaron;
- **no es el pipeline de texto**: el trazador
  (`scripts/trazar_pipeline_campo.py`) corre las seis etapas reales sobre HTML
  real y muestra que las fichas que fallan y las que funcionan **se comportan
  igual en las seis**.

### Campos que comparte, y uno que no

| campo | ¿mismo arreglo? | recuperable |
|---|---|---:|
| `precio` | sí | 1.206 |
| `moneda` | sí, misma causa | 1.185 |
| `ambientes` | **no, y no es un defecto** | **0** |

`ambientes` figuraba con 1.089 recuperables. No lo son. El certificador cuenta
la fuente como proveedora porque su patrón encuentra `"ambiente 1"` **adentro de
la palabra MONOambiente**, que es una opción del menú de filtros y está idéntica
en las 1.213 fichas. La propiedad publica `Cantidad de dormitorios: 2`, que es
otro campo.

**Era un error de medición, no un arreglo pendiente.** Sumar los tres campos
habría prometido un ROI que no existe.

### Reuso histórico

| clasificación | resultado |
|---|---|
| `ALREADY_PRESENT` | no |
| `REGRESSED` | no |
| `DISCONNECTED` | no |
| `HISTORICAL_HEURISTIC_AVAILABLE` | no |
| **`NEW_FIX_REQUIRED`** | **sí** |

`git log -S "priceCurrency"` y `-S 'datos.get("moneda")'` devuelven un solo
commit: `a7674cd90e`, el que creó el conector genérico. Nunca existió otra
solución, así que no hay nada que reconectar ni que revertir.

### Parche propuesto — NO aplicado

En `connectors/generico.py`, después de tomar el precio del JSON-LD:

```
si hay precio y NO hay moneda:
    buscar en el texto la misma expresion que ya usa el fallback
    y tomar SOLO la moneda de ahi
```

Cuatro líneas. No toca la guarda, no toca `_de_json_ld`, no cambia el orden de
precedencia: el JSON-LD sigue mandando sobre el texto para el precio.

### Antes y después, sobre la muestra

| | hoy | con el parche |
|---|---:|---:|
| fichas con precio | 4 de 1.213 | 1.210 de 1.213 |
| fichas con moneda | 4 de 1.213 | 1.189 de 1.213 |

(el techo son las 1.210 que la fuente publica, no las 1.213)

### Falsos positivos

El riesgo es afirmar una moneda equivocada. Se acota solo: la moneda se toma
del **mismo fragmento de texto donde está el precio**, no de cualquier parte de
la página. Si ese fragmento no aparece, no se afirma nada y el comportamiento
queda igual que hoy.

Lo que **no** cubre: una página que muestre dos precios en monedas distintas
—venta en USD y expensas en ARS—. Ahí el fallback tomaría el primero. No se
observó en las 12 fichas revisadas, y queda anotado como límite conocido.

### Radio de dependencia

```
componente        generic/common
estrategias       14
agencias          57
propiedades     3.748
```

**Éste es el costo real del arreglo**, y es alto: recuperar 1.206 propiedades de
**una** agencia invalida 57 certificaciones que hay que rehacer. Se midió: sólo
`blanco` tiene esta firma hoy —precio y moneda perdiéndose a la par—, así que el
beneficio inmediato es de una sola agencia.

### Rollback

Revertir las cuatro líneas. Las certificaciones hechas con el parche quedan con
otra huella y se recertifican solas al volver atrás; ninguna propiedad se borra.

### Artefactos

- `tests/fixtures/jsonld_price_sin_currency.html`
- `tests/test_jsonld_precio_sin_moneda.py` — 4 verdes, 2 rojos
- `scripts/trazar_pipeline_campo.py` — el trazador de etapas
- `ERETZ_TRAZA_BLANCO.json`

---

## PRIORIDAD 2 — Fenix, que son **dos** arreglos y no uno

No comparten causa: uno es *de dónde se lee un campo*, el otro es *qué se
admite como ficha*. Van separados, con tests separados, y **no se despliegan
juntos**: unirlos ataría dos radios distintos a un solo rollback.

### 2.A — `OPERACION_SOLO_EN_TITLE`

**Causa:** la operación se lee del título editorial, que carga la inmobiliaria a
mano. Si ese título trae la palabra, funciona; si no, el campo queda vacío
aunque la página publique la operación en el título del documento.

```
falla:    "z/ EL BRETE. EDIF. ARAI."                  -> None
funciona: "CASA EN VENTA Z/ AV. SANTA CRUZ Y AV. 115" -> venta
la pagina: "DF621 - Departamento en Venta en Posadas" -> venta
```

**Lo medido antes de proponerlo:**

```
TRUE_RECOVERY          20/20
FALSE_OPERATION_RISK       0   sobre 35 fichas que YA tienen operacion
                               (20 venta + 15 alquiler)
```

Las otras cuatro señales —encabezado, URL canónica, migas de pan, datos
estructurados— recuperaron **0 de 20**. Por eso el arreglo usa una sola.

El caso caro se probó aparte: **las 15 fichas que hoy dicen `alquiler` siguen
diciendo `alquiler`**. Sin esa comprobación el arreglo no se podía proponer:
entre venta y alquiler no hay un error chico.

**Límite:** el fallback es fallback. Si alguna vez el cuerpo dijera `alquiler` y
el título del documento `venta`, gana el cuerpo. Hay un test que lo fija.

**Radio:** `generic/common`, el mismo que el de Blanco.

### 2.B — `CATEGORY_PAGE_AS_PROPERTY`

**El defecto:** de las 502 urls que el sitemap publica, **3 no son fichas** sino
vistas filtradas del catálogo. Las tres entraron al inventario como propiedades,
y `/propiedades/alquiler-departamentos-posadas/` quedó clasificada como
**`venta`**.

**La regla, y por qué son cuatro condiciones.** Cada versión se midió contra las
378 agencias certificadas:

| regla | páginas marcadas |
|---|---:|
| título compartido + sin precio propio | 396 |
| + url sin id numérico | 395 |
| **+ el título es el INSTITUCIONAL del sitio** | **8** |

Las dos primeras marcaban fichas duplicadas legítimas: una propiedad publicada
tres veces tiene el título repetido y a veces no trae precio. Lo que separa a
una vista filtrada es que su título es el **del sitio** —"Fénix Inmobiliaria en
Posadas | Ventas y Alquileres"— y no el de una propiedad.

**Las 8 se revisaron una por una contra la fuente:**

| agencia | páginas | qué son |
|---|---:|---|
| fenix | 3 | vistas filtradas del catálogo |
| baron | 3 | emprendimientos — *"Disponibilidad Unidades"* |
| brunetti | 2 | barrios privados — *"Últimos lotes disponibles"* |

Las ocho son páginas contenedoras y ninguna tiene precio propio. No se detectó
ningún falso positivo, **pero la muestra es de ocho**: la regla marca para
revisión, no descarta en silencio.

**Radio:** enumeración, no extracción. Es otro radio y por eso es otro despliegue.

### Artefactos de Fenix

- `tests/fixtures/operacion_solo_en_title.html`, `tests/test_operacion_desde_title.py`
- `tests/fixtures/pagina_de_categoria.html`, `tests/test_pagina_de_categoria.py`
- `scripts/validar_operacion_fenix.py`, `ERETZ_OPERACION_FENIX.jsonl`

---

## Ranking, dos vistas

`python scripts/ranking_ventana.py` ahora imprime:

- **vista A — `AGENCY_FIELD_RANKING`**: qué arreglar por (agencia, campo). 12
  pares son el 97 % de las **2.859** fichas con un campo recuperable;
- **vista B — `FIX_CLUSTER_RANKING`**: qué arreglo escribir, con su causa
  verificada, su radio y su riesgo.

### La corrección de 1.133 fichas

La primera versión de la vista A decía **3.992** recuperables. Eran 2.859. La
diferencia son 1.133 fichas que el ranking contaba de más, y salió de verificar
el mismo patrón que había fallado en Blanco:

| agencia | campo | descontado | qué encuentra en realidad |
|---|---|---:|---|
| blanco | `ambientes` | 1.089 | `MONOambiente` en el menú de filtros |
| bartolelli maini | `ambientes` | 28 | `Monoambiente 1 dormitorio` en el menú de navegación |
| cuini | `ambientes` | 16 | lo mismo |

El patrón de `ambientes` del certificador no exige límite de palabra antes de
"ambientes", así que encuentra `ambiente 1` **adentro de MONOambiente**. Agregar
un `` lo arregla sin romper nada —se probó contra `3 ambientes` y
`Ambientes: 4`, que siguen matcheando—, pero eso toca `shared/certifier`, que
está bajo freeze.

**`espina propiedades` da 100 % también y NO se descontó**: se descargó su ficha
y su `Ambientes 2` es un atributo real de la propiedad. La lista es de casos
verificados uno por uno, no de sospechas por proporción.

Queda abierto: no se revisaron los demás campos con el mismo criterio. El
`source_provided` de la flota puede estar inflado en otros lados.

Un cluster **no** se arma sumando campos que fallan parecido. Se arma con una
causa verificada contra la fuente. Los que no la tienen se quedan en la vista A.

---

## El paro de 8 horas

La cola quedó detenida 8 h en `fenix` —de 23:49 a 08:15— y nadie lo supo hasta
que alguien fue a mirar los cerrojos a mano.

**El paro estaba bien puesto** y no se relaja: era un defecto transversal real y
diagnosticable. Lo que faltaba era que se viera.

`scripts/vigilante_de_paros.py` da las cuatro marcas que el §12 pide, todas
sacadas de archivos que ya existían, sin infraestructura nueva:

```
STOP_DETECTED_AT      cuando se corre
STOP_SIGNATURE        del AGENCY_CERTIFICATION_STOP.json
QUEUE_PAUSED_AT       de su campo `cuando`
DIAGNOSIS_STARTED_AT  de si esa agencia ya tiene diferida escrita despues
```

Y distingue cuatro estados: `OK`, `PARO_RECIENTE`, `PARO_DIAGNOSTICADO`,
`PARO_DESATENDIDO` —más de 30 min sin diagnóstico— y
`CERO_WORKERS_SIN_BANDERA`, que es el caso peor: nadie certificando y ningún
paro que lo explique.

Cuenta los workers por **proceso vivo**, no por cerrojo presente: un cerrojo
huérfano habría dicho que todo andaba bien mientras la cola estaba parada, que
es exactamente el error que viene a evitar.

Falta lo único que no puedo hacer solo: **que alguien lo corra**. Un vigilante
que hay que acordarse de ejecutar tiene el mismo problema que el paro que viene
a detectar. La opción barata es engancharlo a la misma tarea programada que ya
relanza la cola.

---

## Lo que NO se hizo, a propósito

- no se tocó el extractor productivo;
- no se aplicó ningún parche;
- no se cambió ninguna huella — se verificó después de cada cambio;
- no se detuvieron los workers;
- no hubo writes a la base.

# ERETZ — Bitácora del 2026-09-20

Ejecución autónoma sobre `handoff/codex-unificacion-2026-09-18`.
`database_writes: 0` en todo el día. Sin push, sin deploy, sin producción.

---

## Lo que movió la aguja

**La cola volvió a correr después de 83 h detenida.** Era el problema más caro
del tablero y no era un defecto: era que nadie la relanzaba.

**Se encontró y arregló una pérdida de inventario del 93 % en la familia
Tokko**, que ningún diff de nuestro código podía mostrar porque el cambio fue
del proveedor.

---

## 1. La cola estaba parada el 75 % del tiempo, y la mitad no era por defectos

Medido sobre las 2.501 corridas del historial, uniendo intervalos y contando
como parada cualquier hueco de más de 20 minutos:

| | |
|---|---:|
| Span del historial | 487,6 h |
| Tiempo **activo** | 121,6 h |
| Tiempo **parada** | **366,0 h (75 %)** en 167 episodios |

Y el reparto importa más que el total: **117 de los 167 huecos no coinciden con
ningún paro registrado** y suman **190,6 h — el 52 % de las horas paradas**. No
son defectos: es la cola no corriendo.

Eliminar esa clase de hueco lleva el duty cycle del 25 % al **64 %** medido.

La infraestructura ya existía, apagada: `ERETZ_cola_w0` y `w1` en estado Ready
con `NextRunTime` **vacío** y última corrida del 09/09;
`ERETZ_cola_certificacion` agendada para **2027-09-04**.

**Hecho**: `scripts/relanzar_la_cola.py` + tarea `ERETZ_relanzador` cada 10 min.
No relanza si hay un paro sin diferida firmada **posterior** al paro, si el
archivo de paro es ilegible, o si los dos workers están vivos. Nunca más de 2
workers, comprobado en tres lugares.

---

## 2. Un throughput que yo mismo había inflado

Los 337 primeros cierres del historial incluyen **140 `IDENTITY_PENDING`**, que
se cierran sin bajar una página, y **135 de ellos son de la letra A**, de una
pasada de identidad del 31/08–01/09. De la B en adelante hay cero.

| régimen | activo | cierres | ritmo |
|---|---:|---:|---:|
| Todo el historial | 121,6 h | 337 | 2,77/h |
| **Sólo scraping** | 121,6 h | 197 | **1,62/h** |
| Post anti-retrabajo (8,6 h) | 8,6 h | 23 | 2,67/h, IC 95 % [1,69–4,01] |

Las 766 pendientes son de la G a la Z: no va a haber cierres gratis.

---

## 3. Tokko cambió la paginación y el listado quedaba en 20

El síntoma llegó dos veces con el **mismo número exacto**: `aagaard` declara 295
y enumeramos 20; `abriola` declara 274 y enumeramos 20. Veinte es `POR_PAGINA`.

`aagaard` había cerrado `CERTIFIED_COMPLETE` el 09/09 con **297 y 298** sobre
315 páginas. Se perdió el 93 % de un inventario que sabíamos leer.

**Causa**, leída del HTML de las dos fuentes:

```js
antes:  $.ajax('/Propiedades?o=2,2&p=' + current_page)
ahora:  $.ajax(tfwListingUrl('', {o: '2,2', p: current_page}))
```

Sin url literal, `query_paginacion` quedaba en `None` y `fetch_listing` cortaba
después de la primera página.

**Hecho**: `query_de_paginacion()` en `connectors/tokko.py`. Verificado de punta
a punta contra las dos fuentes: la query queda en `?o=2,2&p=` y la página 2
devuelve **20 ids nuevos**. Radio `connector/tokko`.

### Cuánto estaba en juego

No eran dos agencias. Se bajaron ocho sitios TFW que ya habían cerrado
`CERTIFIED_COMPLETE` y **siete de los siete que respondieron sirven el template
nuevo**; ninguno conserva la forma literal. Tokko lo desplegó en todo su
producto.

| | |
|---|---:|
| TFW `CERTIFIED_COMPLETE` alcanzadas | 77 |
| Propiedades que aportan hoy | **7.951** |
| De ésas, con más de 20 propiedades | 70 |
| Pérdida que el arreglo evita | **~6.445 propiedades** |

Sobre 27.233 enumeradas en total, eso es el **24 % del catálogo**. Y son sólo
las 81 agencias Tokko que la cola alcanzó: hay **875** con `connector: tokko`
declarado.

Sin el arreglo, la pasada que está corriendo ahora habría recertificado cada
una de esas 70 agencias en 20 propiedades, y las que declaran más habrían ido
parando la cola de a una con radio FAMILIA.

### Cómo casi me equivoco, dos veces

Primero sospeché de la candidata, en particular de `read_bounded_response`, que
ahora **rechaza** una respuesta mayor al límite donde antes truncaba en
silencio. Dos controles la descartaron: el certificador viejo da el mismo 20
contra la fuente de hoy, y las páginas pesan 65, 167 y 196 KB contra un límite
de 800.000.

Después escribí una diferida diciendo que el sitio había migrado a JavaScript
—vi AJAX en el documento y me quedé con eso—. **Estaba equivocada**, y la
corrección está firmada en el mismo archivo. Lo que la desmintió no fue releer
el código sino el segundo caso con el número idéntico.

---

## 4. El corte por lote se repetía sobre sí mismo

13 cortes en el log. Los **tres últimos del worker 1** pararon en la misma
agencia (`gomez servicios inmobiliarios`) con **exactamente los mismos cinco
defectos**, y ninguna de las cinco tenía diferida escrita.

Tercera vez que este proyecto lee un registro histórico como si fuera una lista
de pendientes. Las anteriores: el corrector de fuentes, que reaplicó una
propuesta retirada, y los tests con fecha fija.

**Hecho**: memoria de cortes en `defect_triage.py`. Cambia **qué cuenta**, no
qué se registra: el radio, el ranking y los reportes siguen usando el registro
entero. La identidad incluye la huella, así que un cambio de código hace que el
defecto vuelva a contar.

---

## 5. Dos propiedades sin coordenada paraban las dos colas

`abril negocios inmobiliarios`: la fuente publica latitud y longitud en 54
fichas, la extracción falló en **dos**, y paró el padrón entero.

El tope de baja magnitud exigía 4 fichas o menos **y** como mucho el 2 %, y el
2 % es imposible para una agencia chica.

| ratio | casos | |
|---|---:|---|
| ≤ 0,02 | 142 (37 %) | tope viejo |
| ≤ 0,05 | 182 (48 %) | |
| **≤ 0,10** | **245 (64 %)** | **tope nuevo** |
| ≤ 0,25 | 247 (65 %) | |

Entre 0,10 y 0,30 los datos tienen un hueco: el corte está donde está el salto.
Quedaban afuera **240 casos en 29 agencias, el 63 % de todas las fallas
chicas**. Lo que sigue afuera es lo que debe: `cavacini` 3 de 3 y `alder` 4 de 4
son el 100 %.

---

## 5 bis. El arreglo de Tokko, confirmado en producción

La cola lo corrió sola, sin intervención:

| agencia | antes | después |
|---|---|---|
| `aagaard` | 20 | **295 de 295 declaradas** · `CERTIFIED_COMPLETE` |
| `abriola` | 20 | **263 de 263 declaradas** · `CERTIFIED_COMPLETE` |
| `acevedo` | — | 86 de 86 · `CERTIFIED_COMPLETE` |
| `adrian mitre` | — | 42 de 42 · `CERTIFIED_COMPLETE` |
| `agostinelli` | — | 388 de 388 enumeradas |

**+538 propiedades sólo entre `aagaard` y `abriola`**, y todas cerrando contra
su total declarado.

---

## 5 ter. Y la franja imposible entre los dos topes

`agostinelli` enumeró sus 388 completas y **paró las dos colas por ocho
coordenadas de 154** (5,2 %).

El problema no era ninguno de los dos topes sino su intersección: para ser
menor había que cumplir ≤4 fichas **y** ≤2 %. Una agencia chica no pasa el
porcentual (2 de 54 = 3,7 %); una grande no pasa el absoluto (8 de 154 son
ocho fichas). Sólo calificaban los defectos de una o dos fichas sobre bases
enormes.

De los 287 casos históricos con ratio ≤ 0,10, el reparto por cantidad de
fallas tiene un hueco claro entre **9 y 20**: no hay ninguno. El tope absoluto
pasó de 4 a **10**, puesto en ese hueco. Eran 42 casos en 9 agencias.

Cuatro tests viejos afirmaban el tope de 4. Los leí antes de darlos vuelta: lo
que afirmaban era la constante, no un principio. Reescritos con la medición, y
se agregó el borde por el otro lado.

---

## 6. NEXT-001 cerrado, y era endurecimiento y no reparación

Medido sobre el ledger real de 2.501 filas: **0** JSON inválido, **0** filas sin
agencia, **0** agencias donde el último append no es el `checked_at` mayor,
**0** grupos con más de un `status`. Los 35 grupos duplicados difieren **sólo**
en huella, esquema y métricas: son reescrituras del backfill.

**Hecho**: `scripts/ledger_de_certificacion.py`. Selección por `checked_at`,
offsets comparados como instantes, ambigüedad declarada en vez de resuelta a
dedo, y corrupción que falla cerrado. **Radio cero**: es lectura de artefactos,
la misma categoría que `read_jsonl` en `CERTIFIER_OPERACIONALES`.

---

## 7. 61 agencias apuntan a 25 urls compartidas

`https://cir.org.ar/socios` la comparten **diez** agencias: es la lista de
socios de un colegio, no la web de ninguna.

Compartir **host** no es el problema —`buscainmueble.com` aparece en 70
agencias con url propia cada una, que es como funciona un SaaS—. El problema es
la url idéntica.

**El daño hasta hoy es casi nulo**: 24 de los 25 grupos no tienen ni una
certificación ni una propiedad, porque la cola no llegó. Es una mina, no un
incendio.

**Hecho**: `scripts/fuentes_compartidas.py`, que clasifica y propone. 6 grupos
son directorios institucionales, 6 oficinas de red, 1 buscador de portal, 2
posibles duplicados de identidad y **10 quedan sin clasificar a propósito**.

---

## 8. 14 de 49 agencias sin inventario publican fichas que no sabemos leer

`scripts/que_forma_tienen_sus_fichas.py` baja una página por agencia y agrupa
los enlaces por forma:

| forma | enlaces | agencias | ¿la vemos? |
|---|---:|---:|---|
| `/<slug-con-tipo>` | 48 | 3 | no |
| `/<palabra-suelta>/<id>-<slug>` | 11 | 3 | no |
| `/<palabra>-<slug>` | 6 | 2 | no |
| `/<palabra>-<id>-<slug>` | 20 | 1 | no |

`/<palabra>-<id>-<slug>` es la **cuarta** vez que el proyecto tropieza con la
misma suposición —que la palabra abre un segmento—: `bottai inmueble_6076`,
`fios propiedades` relativo, `yacopino busqueda-de-propiedades-en-venta`, y
ahora `/propiedad-9871962-…`.

El subconteo está declarado en un test: 14 es un **piso**, no un total.

---

## 9. Dos agencias recuperadas, y una conclusión mía corregida

| agencia | antes | después |
|---|---|---|
| `coldwell banker andes` | NEEDS_FIX, 0 | **CERTIFIED_COMPLETE, 170** |
| `andrea gianfelice` | NEEDS_FIX, 0 | NEEDS_FIX, **43** |

Dije que las 170 las recuperó reenrutar el conector de `tokko` a `generico`. Lo
verifiqué con un control —el mismo certificador contra una copia del directorio
con `tokko` restaurado— y da **170 idéntico**. Lo que las recuperó fue correr la
candidata: `debe_reintentar_con_generico()` ya cae al genérico desde el
2026-09-02. El reenrutado de `coldwell` se revirtió.

`gianfelice` es distinto y el control lo muestra: con `tokko` da **20**, con
`generico` da **43**. El fallback sólo dispara cuando el conector específico
obtiene **cero**, así que un resultado parcial le tapa el paso a uno mejor. Ese
es un defecto abierto de `shared/certifier`; el reenrutado queda como paliativo
documentado.

---

## Pendientes, con lo que se aprendió hoy

1. **El fallback sólo dispara en cero** (`debe_reintentar_con_generico`).
   `gianfelice` pierde 23 de 43 por esto. Radio `shared/certifier`.
2. **Formas de ficha no reconocidas**: 14 agencias, 10 formas. Radio
   `generic/common`. El arreglo probablemente no sea aflojar el patrón global
   —arrastraría páginas institucionales— sino extender el mecanismo de forma
   verificada por fuente, que ya existe y ya se comprobó sobre 65 sitios.
3. **`discover()` descarta el path de la fuente registrada**: calcula
   `base = scheme://netloc`, así que el catálogo de `fios`
   —`listado.php?…&pagina=N`, 14 páginas, 263 declaradas— no se visita nunca.
4. **25 urls compartidas**: aplicar las 13 clasificadas, mirar las 10 restantes.
5. **`barrio` se rechaza el 26,2 %** y sigue sin diagnóstico.
6. Los P1 heredados de Codex: equivalencia de writers, input GeoRef en la
   huella, `validate_live_agency_identity`.

## Lo que ya no hace falta hacer

- **`ambientes`** era el punto 1 de la ventana semántica, con 23,9 h de radio.
  Está **resuelto en la candidata**: el patrón con límite de palabra rechaza
  «Monoambiente 1 dormitorio» (verificado sobre 8 casos) y `bottega` extrae
  `ambientes` con cobertura 0,77. El ranking de la ventana quedó desactualizado
  a favor nuestro.
- **NEXT-001** ya no bloquea nada.

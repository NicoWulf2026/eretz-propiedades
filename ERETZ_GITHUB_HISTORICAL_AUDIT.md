# Auditoría histórica contra GitHub

**2026-09-16 · sólo lectura · `database_writes: 0` · sin checkout, sin push**

Pregunta que se vino a contestar:

> ¿hay partes del scraper/backend actual que funcionen **peor** que versiones
> anteriores que ya habíamos probado y medido?

Respuesta corta: **PARCIAL, y mucho menos de lo esperado.** Una sola regresión
de comportamiento demostrable, y al mirarla de cerca el que estaba mal era el
histórico. Un solo bloque de trabajo histórico realmente ausente. Y un hueco de
extracción que el legacy sí cubría y los conectores no.

Cómo se hizo, y qué no se tocó
------------------------------

Toda la auditoría es `git fetch` de refs remotos más `git show`, `git diff`,
`git log` y `git cat-file`. **Cero checkout, cero reset, cero cherry-pick, cero
merge.** El worktree activo no se movió: HEAD siguió en `4569cfe5ec` sobre
`feat/roomix-agency-coverage` de punta a punta, los dos workers siguieron
corriendo y las huellas no cambiaron.

---

## A. Refs analizadas

`git ls-remote` sobre `NicoWulf2026/eretz-propiedades`: **12 ramas remotas, 4
tags**. Ninguna asumida: todas verificadas.

El primer hallazgo es estructural y cambia el resto del análisis.

| rama remota | ¿contenida en HEAD local? | commits que HEAD no tiene |
|---|---|---:|
| `main` | **sí, entera** | 0 |
| `release/eretz-private-preview` | **sí, entera** | 0 |
| `claude/roomix-agency-universe-ndvrfu` | no | **2** |
| `feat/parser-detail-url-detection` | no | 1 |
| `pr-be-prod-09e-manifest-runner-hardening` | no | 1 |
| `pr-be-prod-manifest-b-post-pilot-fixes` | no | 1 |
| `feat/retry-run-from-error-items` | no | 1 |
| `feat/scraper-timeout-configurable-env` | no | 1 |
| `feat/fase-b1-publish-robustez` | no | 56 |

`origin/main` está **íntegramente contenida** en el HEAD local, que va 614
commits. Así que la pregunta no es "¿qué no llegó desde main?" —llegó todo—
sino "¿qué se cambió encima?".

Las seis ramas de 1 commit son las versiones **pre-squash** de sus PR. Se
comprobó comparando árboles, no fechas:

- `pr-be-prod-09e-manifest-runner-hardening` vs `fc896b1360` → **diff vacío**;
- `pr-be-prod-manifest-b-post-pilot-fixes` vs `15e81991c0` → **diff vacío**;
- `feat/parser-detail-url-detection` vs `9aa299bde9` → difiere en 9 archivos,
  271 inserciones, **mayoría frontend** (`frontend/src/lib/property-service.ts`),
  fuera del alcance de este bloque.

`feat/fase-b1-publish-robustez` tiene 56 commits propios, pero **su contenido sí
llegó**: de todos sus archivos, los únicos dos que HEAD no tiene son
`scraper/checkpoint_desarrolladoras.txt` y `scraper/checkpoint_inmobiliarias.txt`
—estado generado, no código—.

**Conclusión de esta sección: el único código histórico realmente ausente del
HEAD es el heartbeat.**

---

## B. Los tres commits que el mandato nombra

Los tres son **ancestros del HEAD local**. No hay nada que rescatar de ellos
porque ya están.

| commit | fecha | qué es | ¿en HEAD? |
|---|---|---|---|
| `9aa299bde9` | 2026-06-28 | `fix: improve parser detail URL detection (#6)` | **sí** |
| `fc896b1360` | 2026-07-01 | `feat: harden manifest runner (#7)` | **sí** |
| `15e81991c0` | 2026-07-01 | `fix: manifest duplicate hash conflicts (#8)` | **sí** |

Los cuatro archivos de `9aa299bde9` están presentes hoy:
`scraper/playwright_scraper.py`, `scripts/validate_detail_quality_07d.py`,
`scripts/validate_parser_fix_07b.py` y
`tests/test_parser_detail_url_candidates.py`.

---

## C. La medición que decide: ¿se debilitaron los tests?

El §4 es explícito: un diff grande no demuestra regresión. `playwright_scraper.py`
cambió 894 inserciones y 482 borrados desde `9aa299b`, y eso **no prueba nada**.

Lo que sí prueba algo es si las invariantes que el histórico fijaba siguen
fijadas. Se comparó función por función el conjunto de tests:

| capacidad | tests en el histórico | tests hoy | invariantes históricas borradas |
|---|---:|---:|---:|
| detail URL detection | 16 | **47** | **0** |
| manifest runner | 64 | **84** | **2** |
| timeouts por env | 7 | 7 | 0 |
| retry desde errores | 11 | 11 | 0 |

Los 16 tests del benchmark de detail URL **sobreviven verbatim** —354 líneas
agregadas, **una sola borrada**— y hoy pasan los 47.

En siete días de historia y cuatro capacidades, **sólo dos invariantes
históricas fueron eliminadas**. Las dos son del manifest runner y las dos se
miraron una por una.

---

## D. La única regresión de comportamiento demostrable

### `test_load_existing_urls_tolerates_http_error` — REGRESIÓN CONFIRMADA, Y ESTÁ BIEN

La invariante histórica decía: el precargado de deduplicación **no debe lanzar**
si PostgREST devuelve error. Se reejecutó tal cual contra el código actual:

```
LANZA: RuntimeError  Dedup preflight HTTP 500 for batch starting at 0
VEREDICTO: REGRESION CONFIRMADA
```

El comportamiento cambió. Pero el §14 del mandato avisa que código histórico ≠
código correcto, así que la pregunta siguiente es **qué hacía el histórico con
ese error**, y la respuesta lo da vuelta:

```python
if r.status_code == 200:
    existing.update(...)          # y si no es 200, no hace nada
```

El histórico **se saltaba en silencio** la inmobiliaria que fallaba. El conjunto
`existing` quedaba sin sus URLs, y el llamador trataba **todas sus propiedades
como nuevas**. Un 500 de PostgREST no abortaba la corrida: la convertía en una
corrida que duplica. Y en este proyecto PostgREST **sí** viene devolviendo
errores.

El código actual, además de fallar fuerte, mejora en dos cosas más que nadie
pidió mirar:

| | histórico | actual |
|---|---|---|
| consultas | 1 por inmobiliaria | lotes de 50 |
| paginación | `limit: 10000`, **sin paginar** | `offset` + `order`, pagina hasta agotar |
| ante error HTTP | sigue, sin esas URLs | `RuntimeError` |

El histórico también **truncaba en silencio** a 10.000 filas por agencia.

**Veredicto: el actual gana. El test histórico codificaba una tolerancia
peligrosa y se borró bien.** Clasificación del test: `UNSAFE_NOW`.

### `test_max_execute_limit_is_892` — SUPERSEDED

Fijaba `MAX_EXECUTE_LIMIT == 892` "para autorizar la corrida 09e completa". Es
una compuerta de una corrida puntual, no una invariante durable. Hoy la
constante es `7004`, el universo completo. Borrarlo fue correcto.

---

## E. Regresiones descartadas con evidencia

### `NAVEGACION_SOLO_JAVASCRIPT` — DESCARTADA

Era la sospecha más fuerte. Hoy la cola paró en `david rodriguez propiedades`
porque su catálogo se alcanza por `window.location.href = "propiedades.php"` y
el descubridor sólo cosecha `href=`. Y el legacy **tiene** manejo de `onclick`
(`_onclick_urls`) y hasta un test llamado
`test_parse_cards_accepts_relative_ficha_in_location_href_fixture`. Parecía
capacidad perdida.

Se midió en vez de suponerlo: se corrió el extractor legacy contra la fuente
real que falló hoy.

```
LEGACY sobre https://davidrodriguezprop.com/home/
   candidatos por documento: 0
   propiedades por parse_cards: 0
LEGACY sobre .../propiedades.php
   candidatos por documento: 0
   propiedades por parse_cards: 0
```

**El legacy encuentra cero también.** Cubre `location.href` escrito *dentro de
un atributo `onclick`*; el caso de hoy tiene una indirección más —el `onclick`
llama a una función y la URL está en el cuerpo de esa función—. No es terreno
perdido: es un hueco nuevo.

### Heurísticas geográficas peligrosas — NO REINTRODUCIDAS

Se buscó `nearest-centroid`, `closest_locality` y similares en todo el código
actual. Las dos únicas apariciones de "centroide" son un comentario que explica
por qué **no** se usan. El §12 se cumple.

---

## F. El hueco real: legacy vs conectores en `ambientes`

Esta es la parte que sí vale plata, y es §37/§38 del mandato: el legacy scraper
y los conectores actuales no son el mismo extractor.

`bottega propiedades` cierra hoy con `ambientes` en `EXTRACTION_FAILED` y
cobertura **0,41**. Se bajaron sus fichas reales por HTTP y se aplicó la regla
legacy tal como está escrita hoy en `scraper/playwright_scraper.py`:

```
legacy_ambientes=5   .../site/properties/56...   "...En alquiler Ambientes 5 Dormitorios 3..."
legacy_ambientes=5   .../site/properties/55...   "...Apto credito Sí Ambientes 5 Dormitorios 2..."
legacy_ambientes=4   .../site/properties/55...   "...En venta Ambientes 4 Dormitorios 2..."
legacy_ambientes=3   .../site/properties/52...   "...departamento de 3 ambientes ofrece..."
legacy_ambientes=4   .../site/properties/52...   "...En alquiler Ambientes 4 Dormitorios 3..."
```

**5 de 5, y ninguno es basura**: el valor sale de una etiqueta limpia
`Ambientes N`. La señal del certificador actual **también** dispara sobre ese
texto. O sea: sabemos que el dato está, y lo perdemos en el extractor, no en la
señal. Es §39 puro.

Pero el legacy no se porta a ciegas, porque comparte el defecto abierto:

| caso | legacy | señal actual |
|---|---:|---|
| ficha real de bottega | 5 | `'Ambientes 5'` |
| menú `... Monoambiente 1 dormitorio` | **1** | `'ambiente 1'` |
| menú `Alquileres Departamento Monoambiente 1 dormitorio` | **1** | `'ambiente 1'` |
| texto editorial `de 3 ambientes ofrece` | 3 | `'3 ambientes'` |

Las **dos** reglas fabrican un `1` desde un menú de navegación, que es
exactamente el `xfail` abierto *"el patrón no exige límite de palabra"*. El
legacy no es más seguro; es más **amplio**, y parte de esa amplitud es ruido.

**Acción: `PORT_ADAPTED`, no `PORT_AS_IS`.** Llevar la rama anclada a etiqueta
(`Ambientes\s*N`) con límite de palabra, a la ventana semántica. Afecta la
familia que hoy acumula 19 diferidas de
`extraccion_transversal_de_atributos` y 44 h de cola parada.

---

## G. El trabajo histórico que sí falta: heartbeat

`claude/roomix-agency-universe-ndvrfu` → `5e51042541`,
*"heartbeat remoto de telemetría del crawler"*. **931 líneas, 3 archivos, no
está en HEAD.**

Llega justo donde más duele. La medición de hoy (`ERETZ_TIEMPO_PERDIDO_POR_CAUSA.json`)
dice: 7 días, 58 paros, **102,8 h de cola parada**, mediana de un paro **8
minutos**, y **9 episodios (16%) se llevan el 80% de las horas**, con máximos de
15, 17 y 18 h. Ocho de esos nueve empezaron **entre las 9 y las 16**. El
diagnóstico no es caro; el aviso no llega a donde está la persona.

Sus siete principios, contra el vigilante actual:

| principio del heartbeat | vigilante de hoy |
|---|---|
| JSONL local durable primero | **sí** |
| tabla best-effort después | **no — no hay nada remoto** |
| un error de telemetría nunca frena el crawler | **sí** (se arregló hoy) |
| conexión efímera aislada | n/a |
| throttling por intervalo y delta | **sí** |
| ETA por ventana móvil reciente | **sí** |
| checkpoint local como fuente de verdad | **sí** |

Seis de siete. **El que falta es justo el que la medición señala como el 80% del
costo.**

No se porta ahora, y el motivo no es el freeze: el heartbeat necesita una
migración (`internal_scraping.roomix_agency_crawl_status`), un rol nuevo
(`eretz_roomix_heartbeat_writer`) y escrituras a Supabase. §19, §20 y §21 lo
prohíben sin autorización explícita. Queda como el candidato de port número uno.

Mientras tanto se dejó preparado `scripts/alerta_remota.py`, que cubre el mismo
agujero sin base de datos y **sin activarse solo**: comprobó que en esta máquina
la carpeta OneDrive existe pero **su cliente no está corriendo**, así que declara
el canal `NO_DISPONIBLE` en vez de escribir un archivo que no viaja.

---

## H. Matriz final

| capacidad | histórico | actual | gana | evidencia | acción |
|---|---|---|---|---|---|
| detail URL detection | `9aa299bde9` | HEAD | **ACTUAL** | 16 tests históricos intactos + 31 nuevos, 47 pasan | KEEP |
| manifest dedupe preflight | `fc896b1360` | HEAD | **ACTUAL** | histórico duplicaba en silencio y truncaba a 10k | KEEP |
| `MAX_EXECUTE_LIMIT` | `fc896b1360` | HEAD | **ACTUAL** | 892 era compuerta de una corrida; hoy 7004 | KEEP |
| navegación por JavaScript | `9aa299bde9` | HEAD | **EMPATE (los dos fallan)** | legacy da 0 candidatos sobre la fuente real | NUEVA CAPACIDAD |
| `ambientes` por etiqueta | legacy `_extract_num` | conectores | **HISTÓRICO en recall** | 5/5 en fichas reales vs `EXTRACTION_FAILED` | **PORT_ADAPTED** |
| `ambientes`, límite de palabra | legacy | señal actual | **NINGUNO** | los dos fabrican `1` desde un menú | arreglar los dos |
| heartbeat remoto | `5e51042541` | no existe | **HISTÓRICO** | 931 líneas ausentes; 6/7 principios ya presentes | **PORT_ADAPTED, necesita autorización** |
| timeouts por env | rama | HEAD | **EMPATE** | 7 tests, sin cambios | KEEP |
| retry desde errores | rama | HEAD | **EMPATE** | 11 tests, sin cambios | KEEP |
| publish robustez | `fase-b1` (56 commits) | HEAD | **EMPATE** | sólo faltan 2 checkpoints generados | KEEP |
| heurísticas geo inseguras | histórico | HEAD | **ACTUAL** | no reintroducidas | KEEP |

---

## I. Qué entra a la próxima ventana semántica

Nada se arregla ahora: el bulk sigue activo y el §39 manda backlog, no fix.

| prio | qué | beneficio | radio de invalidación |
|---|---|---|---|
| **P1** | `ambientes` anclado a etiqueta, con límite de palabra | la familia con 19 diferidas y 44 h de cola parada | `shared/certifier` → transversal, alto |
| **P1** | descubrir catálogo en `location.href` dentro de funciones | 4 agencias medidas hoy; `david rodriguez` solo declara ~365 | descubrimiento genérico |
| **P2** | heartbeat remoto portado | el 80% del tiempo perdido | ninguno (control plane) — **espera autorización de DB** |

---

## J. Respuesta explícita

> ¿Existe evidencia de que partes del GitHub histórico funcionen mejor que el
> código actual?

**PARCIAL.**

- **En un caso, sí y está medido:** la extracción de `ambientes` por etiqueta
  plana. El legacy saca 5 de 5 sobre fichas reales de `bottega`; el conector
  actual cierra `EXTRACTION_FAILED` con 41%. Pero la regla histórica arrastra el
  mismo defecto de límite de palabra, así que se porta adaptada, no tal cual.
- **En un caso, falta código entero:** el heartbeat remoto, 931 líneas nunca
  mergeadas, que ataca el 80% del tiempo perdido medido. Bloqueado por
  autorización de base de datos, no por el freeze.
- **En todo lo demás, no.** La única regresión de comportamiento demostrable
  —el preflight de deduplicación— resultó ser una **mejora**: el histórico
  duplicaba en silencio y truncaba a 10.000 filas. Los 16 tests del benchmark de
  detail URL sobreviven intactos y hay 31 más. Las heurísticas geográficas
  peligrosas no volvieron.

El repositorio histórico sirvió acá para lo que el §14 dice que sirve: como
banco de invariantes. Dos de ellas se habían borrado, y mirarlas una por una
demostró que una era peligrosa y la otra caduca. Eso es el resultado, no un
fracaso de la búsqueda.

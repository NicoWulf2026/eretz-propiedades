# Lotes compartidos pendientes

Cambios a archivos de la huella COMPARTIDA (`archivos_de_la_huella()` fuera de un
solo conector). Aplicar cualquiera invalida la certificación de todas las
agencias y reinicia la recertificación (~52 h con 2 workers). Por eso se
acumulan y se aplican juntos, en un momento elegido, no uno por uno.

Nada de esto está aplicado en el worktree que corre la cola.

## `LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch` — APLICADO el 29-09 (`a6746a9338`, política P3)

Preparado y verificado en `D:\INMO CAPITAL\eretz-dev` (suite completa con el
lote aplicado: **3.635 verdes**, 29-09). Aplicar desde la raíz del repo:

    git apply docs/agent/lotes/LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch

| cambio | archivo | efecto medido |
|---|---|---|
| Partes de un aglomerado censal resuelven la localidad, solo dentro de su provincia | `connectors/geografia.py` | +112 fichas con localidad (92 «Necochea» → «Necochea - Quequén»). Un nombre que ya es localidad en algún lado no se toca; en otra provincia sigue sin resolverse, no se vuelve conflicto. |
| Descartes del guardián de forma **sin señal** no cuentan como ficha fallida | `scripts/agency_certifier.py` | 4 agencias salen de NEEDS_FIX (348 propiedades; `bottai` 315, bloqueada por un enlace a `area_cliente.php`). Solo con ≤ max(2, 2 %) descartes, 0 con señal y propiedades leídas: si el guardián descarta todo o mucho, sigue bloqueando. |
| Las casillas del buscador (`<label><input type=checkbox>`) no son datos de la ficha | `connectors/generico.py` | `o feely` (familia wordpress DETENIDA desde el 29-09 04:59): «Tipo de operación: Alquiler/Venta» del buscador Houzez daba la operación por publicada en 74 emprendimientos. |
| El bloque de unidades de Houzez (`Unidades disponibles`, `property-sub-listings-wrap`) corta la ficha del emprendimiento, en la señal y en el extractor | `scripts/agency_certifier.py`, `connectors/generico.py` | misma regla que `UNIDADES`: la operación/precio de una unidad no es la del proyecto. |
| «Provincia: Argentina» leída y rechazada es validación, no campo sin leer | `scripts/agency_certifier.py` | `o feely`: 1 ficha bloqueaba 600. |

Tests: `tests/test_lote_compartido_2026_09_29.py` (10).

Con el lote, `o feely` (600 propiedades) queda sin motivo conocido de NEEDS_FIX y la familia
wordpress se libera sola por cambio de huella.

Después de aplicar: suite completa, commit, y la cola recertifica sola por
cambio de huella (ERETZ AUTOMATION ON).

## Lote 2 — APLICADO el 29-09 (`566d5a2644`): identidad canónica P6, finca/chacra, baja entre corridas

## `LOTE_COMPARTIDO_3_2026-09-29.patch` — PREPARADO (verificado en eretz-dev: 3.697 verdes)

    git apply docs/agent/lotes/LOTE_COMPARTIDO_3_2026-09-29.patch

| cambio | archivo | efecto |
|---|---|---|
| robots.txt se respeta (P11): lo prohibido levanta `RobotsBloqueado` (subclase de `Bloqueado`, `ROBOTS_BLOCKED`); se lee una vez por host; 401/403 = todo prohibido; ilegible = no afirma | `connectors/base.py` | radio a medir sobre la cola (listados, fichas y APIs) antes de aplicar |
| Una página de categoría con doble evidencia (rechazada como contenedora por el extractor Y sin id en la URL) no es ficha fallida | `scripts/run_rollout.py` | `alias` (15 de 71) y `pagano` (3) dejan de parar la cola |
| La suite no sale a leer robots.txt salvo en sus tests | `tests/conftest.py` | — |

Pendientes para el lote 4: conteos en palabras, superficie sin rótulo (fenix), Wix, Strapi en `api.` subdominio (paladino).

## `LOTE_COMPARTIDO_4_2026-09-29.patch` — PREPARADO en CLOUD (29-09 noche), sin aplicar

    git apply docs/agent/lotes/LOTE_COMPARTIDO_4_2026-09-29.patch

| cambio | archivo | efecto |
|---|---|---|
| Conteos escritos con letras en la PROSA («cuatro dormitorios», «un baño»): una única mención por rótulo, con concordancia, sin cotas ni rangos; solo si no hay cifras y la ficha no es tabla de atributos | `connectors/generico.py` (familia generico, y el camino HTML de wordpress) | `pozzobon`, `ente`. Solo agrega datos: el auditor no exige conteos en letras, así que no puede crear NEEDS_FIX. **Radio: REQUIRES_LOCAL** (abajo) |

Tests (en el parche): `tests/test_generico_conteos_en_letras_lote4.py` (16; 6 fallan sin el cambio).
Suite en CLOUD con el parche aplicado: 3.588 passed, 170 skipped (los tests con GeoRef no corren
en CLOUD: correr la suite completa en LOCAL con `ERETZ_REQUIRE_LOCAL_DATA=1`).

Radio a medir en LOCAL antes de decidir (P4): A/B de extracción sobre el HTML cacheado de las
fichas `generico` con `dormitorios`/`banos`/`ambientes` vacíos, con y sin el parche; contar
campos nuevos por agencia y revisar a mano una muestra (buscar falsos: «un dormitorio en suite»
en una casa de varios). Si el beneficio medido es < 300 propiedades y no hay familia bloqueada,
esperar a juntarlo con otro arreglo (P4). No medido en CLOUD: no hay paquetes.

Sin preparar (necesitan el HTML real, que CLOUD no puede bajar por la política de red del
entorno): superficie sin rótulo «50 M² 50 M²» (`fenix`), Strapi propio en `api.` con catálogo
> 800 KB (`paladino`, pide subir `limite_bytes` en `base.py`), Wix (`lucas liprandi`, `dib kai`).
Para prepararlos en CLOUD: dejar en `tests/fixtures/` una ficha real reducida de cada caso
(sin datos personales) y anotarlo acá.

## `LOTE_P10_PROVINCIA_POR_POLIGONO_2026-09-29.patch` — P10, PREPARADO en CLOUD (29-09 noche), sin aplicar

Requisito previo (LOCAL, tiene red al IGN): `python scripts/geo_poligonos_provincias.py` →
`connectors/geometria/provincias_ign.json` (commitearlo: es dato público del IGN, Ley 27.275,
como `argentina_ign.json`). Sin ese archivo el parche aplica pero P10 no actúa (fail-closed).

    git apply docs/agent/lotes/LOTE_P10_PROVINCIA_POR_POLIGONO_2026-09-29.patch

| cambio | archivo | efecto |
|---|---|---|
| Nuevo motivo P10: localidad ÚNICA en el país + coordenada DENTRO del polígono oficial de su provincia (≥ 2 km del límite) + a ≤ 100 km de la localidad → se afirman localidad y provincia | `connectors/geografia.py` (compartido) | casos como `analia requena` («Santa Clara del Mar» + «CABA» de plantilla). Nombre ambiguo, sin coordenada, afuera, en la frontera o sin geometría: sigue el conflicto |
| La provincia publicada queda como evidencia: `extra.provincia_publicada` + `extra.provincia_por_poligono` {política P10, localidad e id, coordenada, procedencia de la geometría} | `connectors/base.py` (compartido) | «la fuente dijo X, ERETZ normalizó Y, por Z» |
| Conflictos VIEJOS que hoy son P10 → dimensiones de la localidad, provincia por geometría, `provincia_publicada_en_conflicto`; resumen `provincia_normalizada_por_poligono_p10` | `scripts/api_snapshot.py` (fuera de la huella) | la snapshot se beneficia sin re-extraer |
| `poligono_provincia.py` y la geometría entran en la huella (ausente = estado propio) | `scripts/agency_fingerprints.py` | aplicar reinicia la recertificación entera (compartido) |

Tests (en el parche): `tests/test_p10_provincia_contradictoria.py` (9) con GeoRef y geometría
SINTÉTICOS: corren en CLOUD. Suite en CLOUD con el parche: 3.589 passed, 170 skipped.
Radio: REQUIRES_LOCAL — con la geometría generada y el parche aplicado en `eretz-dev`, construir
una snapshot candidata y leer `provincia_normalizada_por_poligono_p10` del resumen; revisar a mano
una muestra. Decidir según P4 (es compartido: juntarlo con el lote 4 si conviene).


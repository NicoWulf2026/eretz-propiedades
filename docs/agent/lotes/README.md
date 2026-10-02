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

## Mediciones LOCAL (cuenta B, 2026-10-01)

### Lote 4 original — NO APLICAR
Sobre el corpus real (título + descripción de 32.156 propiedades generico/wordpress): 1.474 campos
nuevos en 1.358 propiedades de 138 agencias, pero en una muestra aleatoria revisada a mano **20 de 45
eran falsos** (44 %): «un ambiente acogedor/moderno» (clima, no conteo: 10), conteos parciales
(«Dormitorio principal… Dos dormitorios», «dos habitaciones secundarias», «P.A: dos dormitorios»),
por unidad («dos casitas de dos dormitorios cada una», «semipisos de un dormitorio») y rangos
«de uno y de dos». El auditor no exige conteos en letras: esos falsos se certificarían.

### Lote 4 v2 (endurecido, en `b/lote5-dev`)
Rótulo único en toda la ficha, sin «un ambiente», sin piso/planta/unidad delante, sin «cada uno» ni
«secundarias» detrás, rangos con «de». Corpus: 826 campos / 750 propiedades / 110 agencias; muestra de
50: ~47 correctos, 2–3 dudosos (complejos), 0 falsos claros. **A/B sobre HTML real** (89 fichas de
74 agencias): se gana el 35 % de lo estimado (las fichas con tabla de atributos no leen letras, por
diseño) → **~290 campos en ~260 propiedades**, 0 valores existentes alterados. P4: < 300 y sin falso
CERTIFIED → se agrupa.

### P10 (parche de CLOUD) — radio casi nulo tal como está
Snapshot candidata con el parche vs sin él (mismos insumos): **2 propiedades** normalizadas por
polígono (636 GEO_CONFLICT en la base; ninguno conserva coordenada en la snapshot). Causa: el margen de
2 km se mide contra TODO borde, costa incluida: 151 de 152 fichas con coordenada de `analia requena`
(Santa Clara del Mar, a 0,7 km del mar) quedan en FRONTERA. Variante medida en `eretz-b-medicion`:
FRONTERA = a menos de 2 km de OTRA provincia (la costa y el límite internacional no hacen dudar entre
provincias). Tests actualizados (incluye General Paz = FRONTERA, Mar del Plata = DENTRO). Radio de la
variante: ver la próxima entrada (snapshot en construcción).

### Lote 5 (en `b/lote5-dev`, sin aplicar; todo con tests y fixtures reales)
| id | cambio | archivo | medido |
|---|---|---|---|
| F1 | número ANTES del rótulo en celdas propias (`<span>1</span><br><span>Baños</span>`), solo si no es el valor de un rótulo anterior y todas las apariciones coinciden | generico | b b: 57 baños |
| F2 | «Cuartos de baño» es el rótulo de baños (RealHomes en castellano) | generico | inversiones |
| F3 | ubicación junto al ícono de mapa en el cuerpo de la ficha; fuera header/nav/pie, tarjetas, contacto, enlaces (oficina en Google Maps), «sucursal/oficina»; cadena «…, Ciudad, Provincia[, Argentina]» | generico | muestra de 95 fichas fallidas: +15 ciudad, +4 provincia; martelliti, analia dulsan, saracena, alfa, franco, b b, masar |
| F4 | «22m frente x 65m fondo» / «14,36 mts de frente por 58» no es superficie | generico | 11 fichas de 10 agencias con un valor INCORRECTO hoy |
| F5 | categoría titulada con la operación sola («Alquiler Temporario») + ≥5 fichas + sin id = contenedora | generico | ana de napoli; 0 falsos positivos en 268 fichas reales |
| F6 | tope de descarga 800 KB → 3 MB y sin reintentar una respuesta que lo excede; ubicación Wix desde `wix-warmup-data` (única dirección «Localidad, Provincia, Argentina») | base, generico | liprandi: 71 fichas que fallaban todas |
| F7 | Strapi v3 propio (`api.<host>/inmuebles`): la ficha cascarón Next.js se arma con el objeto por slug | generico | paladino: 43 de 43 eran «sin contenido»; verificado en vivo |
| L4v2 | conteos en letras endurecidos | generico | ~260 propiedades |
| P10b | P10 con margen solo contra otra provincia, radio 25/10 km | geografia, base, fingerprints, poligono_provincia, api_snapshot | 103 propiedades, 0 falsos positivos |
| F8 | soft-404 demostrado por control (un id inventado por host; minoría de vacías) | run_rollout | 6 agencias / 788 propiedades bloqueadas por fichas vacías |
| F9 | desempate por tercera corrida ante 1–2 fichas editadas por la fuente | agency_certifier | pennacchio 280, cocucci 275, mirasur 135, criscenti 112, fiorio 106… |

Implementado después (F8): soft-404 demostrado por control (pedir una vez por
host la misma forma de URL con un id inventado; si responde igual, la ficha vacía es una baja, P1):
6 agencias / 788 propiedades en NEEDS_FIX solo por fichas vacías (mooswalder 478, mechi cogorno 91,
salerno 54, d amato…).

### Lote compartido 5 — APLICADO el 2026-10-01 (cuenta B, LOCAL; P4: beneficio medido >> 300 propiedades y > 24 h desde el lote 3)
Contenido: F1–F9 + Lote 4 v2 + P10 endurecido (tabla de arriba). Suite LOCAL estricta con el lote:
3.883 passed, 0 failed, 5 skipped (symlinks en Windows y el fail-closed sin geometría).
Canarios reales con el código del lote (certificador completo, dos corridas, salida en scratch):
- verdes (CERTIFIED_COMPLETE el 29-09+, una por estrategia): berraz, de leo, amabile, cocciolo, coelho,
  cristina, baus → siguen COMPLETE (cristina y cocciolo +2 fichas: altas reales). 0 regresiones.
- objetivo: martelliti NEEDS_FIX→COMPLETE (ciudad/provincia 0→100 %), analia dulsan →COMPLETE,
  paladino 0→43 fichas COMPLETE (Strapi v3), lucas liprandi 0→73 COMPLETE (tope 3 MB + ubicación Wix),
  inversiones →BEST_AVAILABLE (inventario chico); b b 83→203 fichas, baños resueltos, provincia
  156/203 (1 falla residual); agostina saracena provincia 0→15/24 (2 fallas residuales); d amato:
  3 fichas vacías > cupo 2 → cupo de F8 subido a máx(3, 3 %); ana de napoli: 6 fichas que expiran
  siempre + techo fantasma 7.777 del directorio (sigue NEEDS_FIX).
- A/B sobre HTML real en dos muestras independientes (95 fichas fallidas + 89 fichas de 74 agencias):
  +49 y +31 campos, 1 valor cambiado (ingrone: baños 1→2, correcto: «2 Cuartos de baño»), 0 regresiones.
- P10 endurecido (margen solo contra otra provincia, ≤ 25 km de la localidad, 10 km si se llama como
  una provincia): snapshot candidata 636 → 531 GEO_CONFLICT; 103 propiedades normalizadas (analia
  requena: Santa Clara del Mar, Mar del Plata, Mar Chiquita → Buenos Aires), 0 falsos positivos
  (agostinelli «Córdoba - Cruz del Eje» queda en conflicto: era la provincia, no la ciudad).
- Hallazgo del certificador: creaba su descargador con 800 KB fijo en dos lugares; ahora usa
  `LIMITE_DE_DESCARGA` (3 MB). `dib kai` (Tokko, portada de 1,85 MB) también lo necesitaba.
Huella: cambian `generico.py`, `base.py`, `run_rollout.py`, `agency_certifier.py`, `geografia.py`,
`poligono_provincia.py` (+ geometría) → recertificación completa por cambio de huella.

### Backlog del LOTE 6 (paros del 01-10 con el lote 5 aplicado; sin implementar, P4)
- aranoa (Synapsis, ficha.php?prop=N): par <p><strong>Rotulo:</strong></p><p>valor</p> en _par_rotulado (provincia/localidad 0/34). 2026-10-01 16:32.
- og:title/og:description como cadena de ubicacion («… Chivilcoy, Resto de la Provincia, Buenos Aires»): 75 fichas (caian 44, benitez ullo 13…).
- ambrosio / corporacion inmobiliaria (detalle.php?id=pN-iN): ubicacion sin rotulo.
- plataforma /content/empresas/<cod>/ (barrio uno, ana barbeito, a campos): '0 inmuebles encontrados. Fin de los resultados' = cero declarado -> NO_INVENTORY_CONFIRMED.
- Houzez <address><i class='houzez-icon icon-pin'>…, CABA, C1428CPD, Argentina</address> (de giorgio): agregar icon-pin a F3 SOLO descartando tramos de codigo postal y validando la ciudad (no 'La Pampa' calle).
- ashardjian (topinmobiliario, *.php por tipo -> detalle.php?ID=N&t=1, 60 fichas): una pagina rechazada como contenedora debe recorrerse como catalogo.
- balsa (Houzez icon-pin 'Machado 740 - San Bernardo'): 8/58 sin provincia. 2do caso Houzez icon-pin -> prioridad.
- bartolini: categorias /<tipo>-en-<operacion>.html rechazadas como contenedoras cuentan como detalle fallido (30); extender el criterio del lote 3.
- bauer (Estatik): li.es-property-field--es_neighborhood / --city / --province con label anidado; lector estructural por clase es-property-field--<campo>.
- bellomo (dl.detail-facts): <dt><i class="bi ..."></i> Ambientes</dt><dd>3</dd>; el icono vacio en la celda del rotulo rompe las parejas estructurales de _cuenta_de_ficha y el texto plano corre los valores (banos=3 cuando la ficha dice 2). Tolerar un icono vacio al comienzo de la celda del rotulo.
### LOTE 6 — APLICADO 2026-10-02 01:22 (`0335f2a`). Primera medicion: 2026-10-01 21:20

Agregados despues de la primera medicion (paros de la noche): wordpress achica la pagina ante el tope con el mensaje del lote 5 y ante 5xx (benitez: 0 -> 128 COMPLETE; el achique estaba MUERTO desde el lote 5), precio de respaldo de wordpress solo del cuerpo de la ficha (RealHomes destacadas al azar: 72/128 no idempotentes; 0 cambios en 64 fichas de 32 agencias wordpress certificadas), «N amb.» como ambientes (bras neves) con la fraccion «1 1/2 AMB.» excluida, coordenada por defecto de Houzez (Miami) anotada como rechazo.

Canarios finales: objetivo bauer, balsa, aranoa, benitez ullo, bartolini (294), benitez (128) COMPLETE; bellomo y de giorgio a 1 ficha (banos sin total en la fuente; coordenada por defecto, ya anotada); caian inventario inestable entre corridas (previo). Verdes 9/9 sin regresion (amabile BLOCKED_EXTERNAL y acosta 67/81: identico con el codigo base = cambio de la fuente). Suite 3912 passed, 5 skipped.

Para el LOTE 7: bigsur (TFW con directorio WORDPRESS: agency_certifier.py lleva el radio a 763, esperar un lote que toque ese archivo), blazquez (WPResidence listing_detail: «Provincia: Zona Oeste» sin anotar el rechazo, ciudad en <a>, descripcion en #longDescription), y lo listado abajo.


Implementado (8 arreglos, 15 tests nuevos, suite 3903 passed / 5 skipped):

| # | Familia | Caso | Arreglo |
|---|---|---|---|
| L6-1 | icono vacio en la celda del rotulo | bellomo (`dl.detail-facts`) | `_cuenta_de_ficha` quita `<i …></i>` vacios antes de leer parejas; antes banos=3 (era el de ambientes) |
| L6-2 | Estatik | bauer | `_campo_estatik`: lector por clase `es-property-field--<campo>` (barrio/ciudad/provincia) |
| L6-3 | Houzez `detail-*` | balsa | `_campo_houzez` (`detail-city`, `detail-state`); «Estado» solo si ES provincia (leal carga «Guaymallen») |
| L6-4 | Houzez `icon-pin` + cadena geocodificada | de giorgio, balsa | `icon-pin` en F3; tramos de codigo postal y «Comuna N» fuera de la cadena |
| L6-5 | Place de schema.org que ES la ficha | de giorgio | Place con url propia cuenta SOLO si no hay nodo concreto (en BuscadorProp va dentro del breadcrumb: cocciolo cambiaba de USD 350.000 a 1.800) |
| L6-6 | Synapsis rotulo en `<strong>` | aranoa | `_par_rotulado` tolera la negrita dentro de la celda |
| L6-7 | CRM TIV Tecnogestion | caian, benitez ullo (75 fichas) | `_ubicacion_tiv`: og:title «Tipo en Op. Barrio, Ciudad, Provincia» + calle de og:description; exige la firma del CRM |
| L6-8 | forma `_<id>_propiedad-inmobiliaria.html` | bartolini | ficha por forma global: sus 30 «fallidas» eran FICHAS reales con 0-2 fotos (no categorias: las 25 categorias ya se descartaban bien) |

Medicion antes de aplicar:

- A/B sobre 368 fichas de 190 agencias certificadas (corpus `l6`): **0 campos perdidos, 0 valores cambiados**, 8 ganados (2 regresiones encontradas en la primera pasada y corregidas: L6-3 y L6-5).
- RADIO: todas las estrategias `generico` -> **358 agencias** (151 certificadas, 181 NEEDS_FIX).
- COSTO: la cola YA esta recertificando `generico` por la huella del lote 5; solo **50** agencias ya pasaron con esa huella. Aplicar ahora cuesta 50 recertificaciones extra (~4 h de reloj a 12,6/h); esperar cuesta otra pasada completa de 358 (~28 h) y crece ~12 agencias por hora de espera. P4 -> aplicar en cuanto los canarios den verde.
- Canarios: 8 objetivo + 9 verdes con el codigo de la rama, salida aislada (`_b_scratch/canarios6`).

Quedan en el backlog (no entran en el lote 6):

- TIV `/content/empresas/` (barrio uno, ana barbeito, a campos): el «0 inmuebles encontrados» es el marcador ANTES de que el JS cargue la grilla (`#FinResultados` oculto, `#CargarMasListado`). Tomarlo como cero declarado seria un FALSO CERO: idea descartada. La grilla viene de `POST /Buscar/CargaMasInmueblesParam`; requiere diseño aparte.
- ashardjian: las categorias `venta<tipo>.php` listan ~50 fichas, pero sus fichas salen con el nombre de la agencia como titulo y sin tipo/ciudad, y la portada enlaza ids muertos. Necesita lector propio, no solo seguir categorias.
- url oficial profunda (bener `/tasaciones/villa-real`: la credencial Xintel esta en la portada; leba, castro bienes raices): buscar plataforma/credencial tambien en la raiz del mismo host. o keefe e inmobiliaria integral: url de OTRO dominio = DATA_FIX de directorio.
- ambrosio / corporacion inmobiliaria: ubicacion sin rotulo (sin evidencia suficiente para una regla).

El backlog vivo por familia, ordenado por impacto, ya no se escribe a mano: `python scripts/backlog_de_lote.py` (ver arriba de esta seccion).

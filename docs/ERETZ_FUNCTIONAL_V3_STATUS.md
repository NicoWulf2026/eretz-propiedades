# ERETZ FUNCTIONAL V3 — Estado de implementación

## Anexo 2 — UX Integration · cierre de PARTIAL + mapa avanzado (2026-08-10)

Commits: `34388691d6` (4 bloques UI), `171fed37aa` (multi-zona), `ddd738b850`
(historial de precio). Gates: typecheck 0, lint 0, **Vitest 139/139**, build OK,
npm audit 0.

**PASS END-TO-END (local, con tests):**
- Input NL en el explorador: texto→filtros server-side, `?nl=` preservado, no
  interpretado visible, sin inventar. Integración testeada (+3) + parser (+9).
- Ocultar visitadas (N): toggle + filtro de vista local + señal "Vista" en card.
- Colecciones: `/colecciones` (CRUD+ver+quitar) + `CollectionPicker` en ficha. +2.
- NoResults inteligente: acciones contextuales (precio/sin-precio/dorm/amb/ubicación/
  zona). +2.
- Multi-zona del mapa (consulta+URL): rectángulo + radio (haversine) OR en
  `buildWhere`, chips removibles por zona. +6 tests. **Sin PostGIS.**

**IMPLEMENTED IN CODE / REMOTE (BROWSER) QA PENDING:**
- **Dibujo de zona en canvas** (rectángulo/radio/polígono UI): la capa de consulta
  y URL está lista y testeada; la interacción de dibujo sobre el canvas requiere QA
  de navegador sobre el Preview. **Polígono libre** además requiere PostGIS
  point-in-polygon validado contra la DB viva → diferido.

**IMPLEMENTED IN CODE / DB MIGRATION PENDING (reconciliación honesta, sección 13):**
Estas funciones tienen **código + tests**, pero su persistencia real depende de
tablas que **no existen aún en la DB de la app** y que **no se pudieron ejecutar**
(el entorno local no tiene `DATABASE_URL`/credencial de DB — dependencia humana,
no timidez):
- **Reclamo de perfil** (`/api/claims`) → tabla `perfil_claims`.
- **Reportes** (`/api/reports`) → tabla `reportes_publicacion`.
- **Grupos de duplicados** (`duplicates.ts`, +8 tests) → tabla `propiedad_duplicados`.
- **Historial de precio** (read-model + ficha) → tabla `listing_price_history`
  (+ flag `ERETZ_PRICE_HISTORY=1` + pipeline de actualización que inserte).
Los endpoints validan y responden hoy (el UX funciona), pero **no persisten** hasta
ejecutar las migraciones con un rol de escritura. Migraciones auditadas, idempotentes,
aditivas, sin RLS/grants nuevos, sin tocar tablas congeladas.

**"Mismo edificio":** cubierto por "Otras publicaciones (misma dirección exacta +
ciudad)" en la ficha (`getOtherPublications`), señal data-backed prudente. La
elevación a entidad "edificio" con confidence usa la infra de `duplicates.ts`
(pendiente de persistencia, ver arriba).

**DEFERRED — dependencia externa real:** tiempos de viaje (proveedor de routing no
elegido); índice de mercado completo (V4); alertas reales / seguir-precio con
notificación (Phase B / cuentas).

**Acción humana pendiente:** (1) credencial de DB para ejecutar las 4 migraciones y
QA de persistencia; (2) `ERETZ_VERCEL_BYPASS` para la batería remota.

---

## Anexo — Functional UX Integration (2026-08-10, aprendizajes de Roomix)

Segunda tanda de la misión, incorporando patrones de Roomix **sin copiar** (map-first
y neutralidad de ERETZ intactos). Commits `7a389607ad` (NL/visitadas/colecciones/badge)
y `ea586f68db` (contacto por intención/publicado-por/analítica). Gates: typecheck 0,
lint 0, **Vitest 126/126**, build OK, npm audit 0.

**IMPLEMENTADO (con tests):**
- **Parser NL** (`lib/nl-search.ts`): texto→filtros estructurados; **nunca inventa**
  (términos sin dato → `notInterpreted`), a diferencia del bug de Roomix. +9 tests.
- **Visitadas** (marca al abrir ficha) y **colecciones nombrables** locales (crear/
  renombrar/eliminar/agregar/quitar), sin cuenta. +3 tests. No reemplazan favoritos.
- **Badge "Más filtros (N)"** con conteo real de filtros activos.
- **Compositor de contacto por intención** (checkboxes + texto libre → mensaje sólo
  con lo elegido, `contactMessageWithTopics`, +3 tests), multicanal y neutral.
- **"Publicado por" linkeable** al perfil `/inmobiliaria/[slug]` + "Ver sus propiedades".
- **Analítica**: abstracción `track()` ya existente ampliada con los eventos del brief.

**BASELINE ya cumplido (verificado, no reimplementado):** sort labels explícitos
(no "Opción N"); contacto multicanal (WhatsApp/tel/email/web/original) con neutralidad;
favoritos/comparar/ocultas/recientes **sin login**; restauración de estado; 404 real
(`notFound()`); filtros con counts correctos; directorio inmobiliarias/agentes + claim
por-perfil; multi-ubicación OR; precio Con/Consultar/Todas; tri-state NULL-safe; cercanía.

**PARCIAL (lógica/infra lista; falta integración UI):** control global "Ocultar
visitadas (N)" en la toolbar y señal "Vista" en la card (store listo, `isVisited`);
página/UI de colecciones (store listo); wiring del parser NL a un input opcional en el
explorador (parser + tests listos); empty-state con acciones explícitas ampliado.

**DEFERRED — dependencia técnica/dato/proveedor real (no timidez):**
- **Mapa avanzado** (polígono/radio/multi-zona/dibujo): requiere predicados PostGIS
  validados contra DB viva + QA de navegador sobre canvas; tocar el path del mapa a
  ciegas arriesga `mapCount=62549` congelado. → etapa remota.
- **Historial de precios**: no hay serie temporal de precios en el dato. → cuando exista.
- **Tiempos de viaje**: requiere proveedor externo de routing (no elegido/activado).
- **Índice de mercado completo**: DEFERRED TO V4 (arquitectura de navegación preparada).
- **Alertas reales / seguir-precio con notificación**: DEFERRED TO ACCOUNTS (Phase B).

---

Documento vivo de alcance de la misión *Functional V3*. Clasifica cada bloque
como **IMPLEMENTADO** (esta iniciativa, con tests y gates), **BASELINE**
(ya existía y se verificó en Phase A), **INFRA LISTA** (código + tests listos,
activación pendiente de un recurso), **PARCIAL/DATA-LIMITED** (limitación real de
datos tras intentarlo) o **REMOTO/HUMANO** (requiere Preview + credenciales +
QA de navegador, indisponibles localmente).

Principio (secciones 83–85): *máxima implementación real, sin fingir checks
verdes*. `buildWhere` y demás piezas SÍ se evolucionaron cuando una función lo
requería, de forma controlada, con tests, sin pérdida silenciosa de propiedades,
preservando semántica NULL-safe, cursor keyset estable y counts.

## Baseline preservado (invariantes)

- `count/totalCount = 193615`, `mapCount = 62549`, `withoutMapCount = 131066`.
- `/propiedad/106835` → 200 + "Disponibilidad no confirmada".
- Cursor keyset estable (desempate por id), filtros server-side, 6 modos,
  restauración por URL, Quality Gate como única autoridad de visibilidad.
- Gates de esta entrega: **typecheck 0 · lint 0 · Vitest 111/111 · build OK · npm audit 0**.

## IMPLEMENTADO en esta misión (commits locales, sin push)

1. **Funciones locales** (`feat(local)`): favoritos, vistas recientes, búsquedas
   recientes, ocultas, comparar 2–4. Store SSR-safe/reactivo/acotado, hook,
   `/favoritos`, `/comparar` (tabla NULL-safe: "Sin información" nunca 0/No),
   endpoint `by-ids` gate-filtrado. **+13 tests.**
2. **Filtros server** (`feat(filters)`): multi-ubicación OR (URL, chips
   removibles, dedup, tope 10); precio Todas/Con precio/A consultar (nunca excluye
   consultar); orden por cercanía (`nearest`, punto de referencia, cursor-safe);
   tri-state NULL-safe (infra). **+14 tests.**
3. **Buscador universal** (`feat(search)`): autocomplete agrupado con agente e
   **ID ERETZ** (coincidencia directa a la ficha, gate-autorizada), orden por
   prioridad de categoría.
4. **Directorio de inmobiliarias** (`feat(directorio)`): `/inmobiliarias`
   (listado + búsqueda), `/inmobiliaria/[slug]` (perfil público, incluye NO
   reclamadas, listado gate-aplicado), reclamo `/reclamar` + `POST /api/claims`
   (nunca auto-aprueba). Slugs id-al-final. **+9 tests.**
5. **Agentes** (`feat(agentes)`): `/agentes` y `/agente/[slug]` derivados de
   `agente_nombre` (sólo datos reales; vacío si no hay datos, sin inventar).
6. **Duplicados** (`feat(duplicados)`): módulo puro blocking + scoring +
   confianza HIGH/POSSIBLE/NO_MATCH + union-find (no O(n²), transitivo, conserva
   publicaciones); "otras publicaciones en la misma dirección" en la ficha. **+8 tests.**
7. **Reportar** (`feat(reportar)`): `ReportButton` + `POST /api/reports` (señal,
   no auto-modifica ni oculta). **+4 tests.**

## BASELINE (verificado, ya presente desde Phase A)

- Ficha completa: galería, precio, specs, publicador, contacto multicanal
  (WhatsApp/tel/email/web), aviso original, compartir (Web Share + copiar),
  similares, "volver a resultados" con restauración de scroll/selección.
- Ciclo de vida (2 estados reales): `availabilityLabel`/`isAvailabilityConfirmed`
  (Disponible vs Disponibilidad no confirmada); ausencia ≠ vendida/alquilada.
- Mapa: clusters, "Buscar en esta zona" (rectángulo), ubicación actual,
  persistencia de zona en URL, "quitar zona" (chip), "sólo con ubicación".
- Reporte/baja/corrección: `/baja-o-correccion`.

## INFRA LISTA (código + migración, activación pendiente de escritura en DB)

- **Reclamo de perfil** y **reportes**: endpoints validan y acusan recibo; la
  persistencia vive en `public.perfil_claims` y `public.reportes_publicacion`
  (migraciones idempotentes, NO ejecutadas). El preview es de sólo lectura, así
  que persisten cuando exista un rol con INSERT.
- **Grupos de duplicados**: `public.propiedad_duplicados` (migración, NO
  ejecutada); la lógica de scoring/agrupación ya está en `src/lib/duplicates.ts`.
- **Tri-state apto crédito**: parse + query NULL-safe + chip completos; el control
  UI se muestra cuando `apto_credito` deje de ser ~100% NULL en el catálogo.

## PARCIAL / DATA-LIMITED (limitación real de datos)

- **Ciclo de vida extendido** (retirada/vendida/alquilada/republicada): el dato
  `estado` sólo distingue `activa` / `no_detectada_en_ultimo_scraping` /
  `desconocida`. No hay señal de venta/alquiler/retiro/republicación en la base,
  así que no se inventan estados. Infra de presentación lista para estados más
  ricos cuando el scraping los aporte.
- **Propiedad física vs publicación vs publicador**: modelado aditivo iniciado
  vía duplicados (agrupa publicaciones de la misma propiedad) + "otras
  publicaciones". El conteo físico consolidado requiere ejecutar el agrupado
  sobre la base (persistencia en `propiedad_duplicados`), pendiente de escritura.
- **Desarrollos/emprendimientos** en el buscador: no existe columna de desarrollo.

## REMOTO / HUMANO (requiere Preview + credenciales + QA de navegador)

- **Mapa avanzado — dibujo** (polígono libre, radio, punto+distancia, MÚLTIPLES
  zonas OR simultáneas, quitar zonas individuales): requiere predicados
  geométricos (PostGIS) validados contra la base viva y QA de navegador sobre un
  Preview. Tocar el path del mapa a ciegas arriesga el baseline `mapCount=62549`.
  Gated a la etapa de validación remota.
- **Batería de validación remota final**: requiere un Preview desplegado con estos
  commits + `ERETZ_VERCEL_BYPASS`. Localmente no hay `VERCEL_TOKEN`, CLI de Vercel
  ni bypass; `/api/properties/counts` debe devolver `193615/193615` antes de
  cualquier batería.

## FUERA DE ALCANCE (explícito en el brief)

Login/Google/cuentas/panel SaaS/billing/CRM/chat/ML/IA/Liquid Glass/rediseño.
La arquitectura queda preparada para conectarse a cuentas a futuro.

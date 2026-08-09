# ERETZ FUNCTIONAL V3 — Estado de implementación

Documento vivo de alcance de la misión *Functional V3*. Clasifica cada bloque
como **IMPLEMENTADO** (esta iniciativa, con tests y gates), **BASELINE**
(ya existía y se verificó en Phase A), **PARCIAL**, **DIFERIDO** (fuera de
alcance seguro para una sola sesión, requiere feature nueva + validación) o
**BLOQUEADO** (requiere una acción humana / recurso indisponible).

Principio rector (secciones 83–85 del brief): *máxima implementación real, sin
fingir checks verdes*. No se toca el baseline server-side frágil (conteos, RLS,
Quality Gate) salvo adiciones aditivas y aisladas.

## Baseline preservado (invariantes)

- `count=193615`, `totalCount=193615`, `mapCount=62549`, `withoutMapCount=131066`.
- `/propiedad/106835` → 200 + "Disponibilidad no confirmada" (nunca activa falsa).
- Paginación cursor sin duplicados · filtros server-side · 6 modos · restauración URL.
- Quality Gate como única autoridad de visibilidad · Data API OFF · sólo servidor.
- Gates de esta entrega: **typecheck 0 · lint 0 · Vitest 76/76 · build OK · npm audit 0**.

Las funciones locales son 100% cliente sobre ese baseline: no alteran conteos,
WHERE, RLS ni gate.

## IMPLEMENTADO (commit `feat(local): favorites recent hidden compare`)

| Función | Detalle | Prueba |
|---|---|---|
| Favoritos | Toggle ☆/★ en cada tarjeta; página `/favoritos` | 9 tests store |
| Vistas recientes | `RecentViewTracker` en la ficha; listado con limpiar | store |
| Búsquedas recientes | Registro en `ExplorerClient` (`describeSearch`); quitar/limpiar | 4 tests label |
| Ocultas | Ocultar ✕ + placeholder "Mostrar de nuevo"; restaurar una/todas | store |
| Comparar 2–4 | Toggle ⇄ (tope 4, aviso al llenar); `/comparar` tabla NULL-safe | store |
| Datos frescos | `/api/properties/by-ids` + `getPropertiesByIds` (gate-filtrado, capado a 60, orden preservado) | build |
| Navegación | Enlace "Favoritos" (desktop + mobile) | — |

Notas de diseño:
- SSR-safe (lecturas vacías en servidor; valor real en efecto → sin mismatch de hidratación).
- Reactivo vía `CHANGE_EVENT` + evento `storage` (multi-pestaña).
- Acotado por lista (favoritos 500, recientes 40, búsquedas 20, ocultas 1000, comparar 4).
- **"Sin información" nunca equivale a 0 ni a "No"** en la comparación.
- `/favoritos` y `/comparar` son `noindex, nofollow`.
- Arquitectura preparada para que una cuenta futura importe/sincronice (datos planos, namespaced `eretz:*`).

## BASELINE (verificado, ya presente desde Phase A)

- Autocomplete agrupado (`/api/properties/suggestions`, `SearchAutocomplete`).
- Ficha completa: galería, precio, specs, publicador, contacto, aviso original,
  estado, compartir, similares (`getRelatedProperties`).
- "Volver a resultados" con restauración de scroll/selección (`sessionStorage`).
- Contacto multicanal (`ContactActions`: WhatsApp/tel/email/web) — ERETZ como agregador neutral.
- Compartir (`shareProperty`: Web Share API + copiar enlace).
- Reporte/baja/corrección: `/baja-o-correccion`.
- Ciclo de vida: `availabilityLabel`/`isAvailabilityConfirmed` (Disponible vs
  Disponibilidad no confirmada); `estado` real preservado; ausencia ≠ vendida/alquilada.

## PARCIAL

- **Multi-ubicación (OR):** no implementado. El filtro de ubicación es
  provincia/ciudad/barrio simple. Requiere modificar `buildWhere`/`property-sql`
  (baseline congelado) + tests de cursor; se difiere por riesgo.
- **Tri-estado (Sí/No/Sin información):** la query ya es NULL-safe, pero la UI de
  amenities/booleanos es de 2 estados. Falta el control ternario explícito.

## DIFERIDO (feature server nueva; requiere deploy + validación)

- Directorio `/inmobiliarias` + `/inmobiliaria/[slug]` + flujo de *claim* (pending/approved/rejected).
- Agentes `/agentes` + `/agente/[slug]`.
- Dibujo en mapa (rectángulo/polígono/radio/ubicación actual/multi-zona) + "Buscar en esta zona".
- Infraestructura de duplicados (blocking + scoring + confianza HIGH/POSSIBLE/NO_MATCH).
- Conteo propiedad-física vs publicación (hoy no se altera 193615).

## BLOQUEADO (acción humana / recurso indisponible)

- **Batería de validación remota final:** requiere un nuevo Preview desplegado con
  estos cambios + `ERETZ_VERCEL_BYPASS`. La variable estaba ausente y no se realizó
  un nuevo deploy. Pendiente de autorización explícita de deploy + bypass disponible.

## FUERA DE ALCANCE (explícito en el brief)

Login/Google/cuentas/panel SaaS/billing/CRM/chat/ML/IA/Liquid Glass/rediseño
estético. La arquitectura local queda preparada para conectarse a cuentas a futuro.

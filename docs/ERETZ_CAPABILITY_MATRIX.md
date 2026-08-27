# ERETZ Propiedades — Matriz de capacidades

Fecha de corte: 2026-08-27

**Estrategia vigente: `PATH_B_NO_ADDITIONAL_INFRA_COST`.** No se crea una base de
Preview ni un branch pago. Todo lo que exige modificar experimentalmente la base
queda en `DEFERRED_DB_EXECUTION`, conservado y listo. Ver
[ERETZ_PREVIEW_DB.md](ERETZ_PREVIEW_DB.md).

Fuente de verdad para alcance y readiness. `READY` significa que puede abordarse con los contratos actuales; no significa que ya esté implementado.

| Capability | Status | Frontend | Backend | DB | Auth | Data quality | Security | Priority | Effort | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Explorer desktop | IMPLEMENTED | Completo | Server-only | Lectura | No requerida | Gate aplicado | Preview protegido | P0 | S | Falta QA del commit exacto más reciente en Vercel. |
| Búsqueda y filtros | PARTIAL | Completo | Funcional | Consultas costosas | No requerida | Texto heterogéneo | Server-only | P0 | L | La búsqueda normalizada provoca scans; faltan facets precalculadas. |
| Conteos | PARTIAL | Completo | Filtra gate en Node | Transfiere IDs/coords | No requerida | Gate versionado | No expone dataset | P0 | L | Principal riesgo de latencia fría. |
| Mapa y clusters | IMPLEMENTED | Completo | Clustering existente | Coordenadas read-only | No requerida | 74,92% sin ubicación | Sin Data API cliente | P1 | M | Comunica high/approximate/doubtful/none sin inventar exactitud. |
| Confianza geográfica | IMPLEMENTED | Completo | Clasificación determinista | No persistida | No requerida | Metadata limitada | Sin writes | P1 | M | Requiere provenance persistente para evolucionar. |
| Cards V2 | IMPLEMENTED | Completo | Contratos actuales | Lectura | No requerida | Nulls respetados | Sin secretos | P1 | S | Desktop validado; mobile congelado. |
| Ficha V2 | IMPLEMENTED | Completo | Server-only | Lectura | No requerida | Historia limitada | Gate fail-closed | P0 | M | Nunca presenta null como false/0. |
| Mi ERETZ local | IMPLEMENTED | Completo | No existe | localStorage | No requerida | Sólo sesión local | Riesgo acotado al dispositivo | P1 | M | Guardadas, colecciones, comparar, historial y búsquedas. |
| Cuenta y sincronización | BLOCKED_AUTH | Preparado conceptualmente | Falta | Falta modelo | Contratos listos, sin proveedor | N/A | Requiere RLS y sesión SSR | P1 | XL | `domain/auth.ts` define el puerto sin atarse a proveedor; `domain/sync.ts` resuelve el merge local-nube con lápidas y separa plan de confirmación. Explorar sigue anónimo. |
| Inmobiliarias públicas | PARTIAL | Listado/perfil | Lectura | 7.004 registros | No requerida | Logo 0,49%; descripción 0% | Server-only | P1 | L | 45,50% tiene publicaciones activas. |
| Agentes públicos | BLOCKED_DATA | Vista derivada | Lectura | No hay entidad formal | No requerida | 25,25% ruido aparente | Server-only | P1 | L | `domain/agent.ts` modela la identidad en cuatro estados; el perfil público exige que la persona lo reclame. 507 nombres normalizados; relación profesional no persistida. |
| Miniportales | BLOCKED_BACKEND | No existe | Falta tenancy/branding | Falta schema | Requiere roles | Cobertura profesional débil | Aislamiento multi-tenant | P2 | XL | Debe tener default elegante y branding acotado. |
| Roles profesionales | BLOCKED_AUTH | No existe | Motor puro listo, sin cablear | Falta membership/ACL | Obligatoria | Falta ownership | Riesgo alto multi-tenant | P1 | XL | `domain/permissions.ts`: deny by default, tenant tomado del recurso cargado, matriz rol-capacidad recorrida completa en tests. Falta persistencia de membresías. |
| Publicación manual | BLOCKED_BACKEND | **No enlazada a propósito** | Falta workflow | Falta persistencia | Obligatoria para publicar | `domain/publishing.ts` validado | Antiabuso requerido | P1 | XL | Validación completa y testeada, deliberadamente sin exponer: sin persistencia, un formulario público pierde lo que la persona carga. |
| Importación desde web | NEEDS_DECISION | No existe | Falta pipeline | Falta staging/provenance | Profesional | Fuente heterogénea | SSRF/abuso/copyright | P2 | XL | No implementar sin contrato y límites explícitos. |
| Reportes de publicación | PARTIAL | Formulario/API | Writer opcional + freno de abuso | Tabla preparada, 0 filas | No requerida | Datos aportados | Tasa y dedupe en memoria; sin cola | P0 | L | 503 cerrado sin writer. El freno es por proceso: badén, no control distribuido. Falta expediente, estados y cola. |
| Baja/corrección | PARTIAL | Flujo por email | Sin expediente | Sin workflow | No requerida | No estructurada | Spam/trazabilidad pendientes | P0 | M | Requiere cola, estados y auditoría para beta pública. |
| Quality Gate (runtime) | IMPLEMENTED | Nunca se expone | Blob privado, cache | Elegibilidad fuera de DB | No requerida | Fingerprint/checksum | Fail-closed | P0 | M | Funciona hoy filtrando en Node. |
| Quality Gate (en DB) | READY_FOR_DB_EXECUTION | N/A | Importador con swap atómico | Migración `eretz_gate` escrita, no aplicada | No requerida | Checksum + freno por caída sospechosa | Fail-closed por INNER JOIN | P0 | M | Escrito y testeado; no aplicado. Requiere entorno de prueba. |
| Data API browser-side | IMPLEMENTED | Cero requests | OFF | N/A | N/A | N/A | Objetivo cumplido | P0 | XS | No reactivar para el frontend público. |
| ACL PostGIS | READY_FOR_DB_EXECUTION | N/A | N/A | Grants P0 directos | anon/auth afectados | N/A | Remediación lista, NO ejecutada | P0 | S | **Vigente y verificado el 2026-08-27: 24 de 24 privilegios de escritura para `anon` y `authenticated`.** SQL, rollback y verificador listos. No se aplica sin entorno donde ensayar el rollback. |
| Observabilidad | PARTIAL | Estados recuperables | Request ID + log JSON por request en las 7 rutas | Sin métricas | Incidentes no medidos | Sin métricas de calidad | Sin alertas/SLO | P0 | L | Primera capa hecha con stdout, sin proveedor. Falta agregación, p50/p95, SLO, alertas y runbooks. |
| SEO/indexación pública | READY | Metadata base | robots/sitemap por implementar | Elegibilidad necesaria | Rutas privadas noindex | Duplicados importan | Preview debe seguir noindex | P0 | M | Estrategia definida; no habilitada. |
| Historial de precios | PARTIAL | Ficha lo consume | Lectura | 5.636 eventos | No requerida | Sólo 5.243 propiedades | Server-only | P2 | L | Sin fecha_publicacion global y sin serie madura. |
| ERETZ Mercado | BLOCKED_DATA | No existe | Agregaciones faltantes | Historia insuficiente | No requerida | **Metodología definida** | Anti-inferencia | P2 | XL | `domain/market.ts` fija mediana, deduplicación por inmueble, recorte de colas y N mínimo. `diagnosticarMercado` deja como comprobación ejecutable que hoy NO se puede publicar. |
| Detección de duplicados | PARTIAL | Señal en ficha | Scorer existente | Tabla formal vacía | No requerida | Varias señales disponibles | No fusionar automático | P1 | XL | `domain/property-entity.ts` formaliza la separación y hace del agrupamiento metadato reversible con evidencia. POSSIBLE_MATCH nunca agrupa solo. Falta persistir entidades. |
| Geocoding/provenance | BLOCKED_DATA | Copy honesto | Pipeline faltante | Sin provider/precision/date | No requerida | 74,92% none | Rate/cost/privacy | P1 | XL | Requiere cola, cache, proveedor y revisión de confianza. |
| Calculadoras | PARTIAL | **No existe UI** | `domain/finance.ts` completo | No necesita | No requerida | Ninguna tasa escrita en el módulo | No asesoramiento implícito | P2 | L | Lógica implementada y anclada contra valores canónicos. Falta sólo la UI. UVA y comprar-vs-alquilar excluidos: dependen de proyecciones, son simulaciones y no cálculos. |
| Recomendaciones | PARTIAL | Relacionadas básicas | Regla actual | Sin features maduras | No requerida | Duplicados afectan | Ranking neutral | P2 | XL | Nunca pago para alterar ranking orgánico. |
| Modelo de dominio | IMPLEMENTED | Tipos disponibles | Módulos puros | No toca DB | Contratos listos | Separa inferido de afirmado | Tenancy por diseño | P1 | L | Propiedad física, publicación y publicador separados, con tres ejes de estado ortogonales. No reemplaza `Property`: es el modelo hacia el que migrar. |
| Calidad de datos | IMPLEMENTED | No expuesto | `domain/data-quality.ts` | No toca DB | No requerida | Detecta, no corrige | Sin efectos | P1 | M | Separa incoherencias internas (INVALID) de valores atípicos (SUSPICIOUS). Umbrales juntos y configurables. |
| Overrides editoriales | BLOCKED_BACKEND | No existe | `domain/overrides.ts` | Falta persistencia | Requiere claim aprobado | Fuente inmutable | `sourceUrl` no corregible | P1 | XL | Snapshot mas overrides da una vista publicada que se calcula, no se guarda. Conserva trazabilidad ante reclamos. |
| Reclamación de inmobiliarias | BLOCKED_AUTH | No existe | `domain/claim.ts` | Falta persistencia | Obligatoria | Evidencia clasificada por fuerza | Sesgo al falso negativo | P1 | XL | Conocer un dato público nunca aprueba solo; sólo controlar un canal. Una organización con dueño nunca va por vía automática. |
| IA | DEFERRED | No necesaria | Sin proveedor | No necesaria | Opcional | Requiere grounding | Costos/privacidad | P3 | XL | Producto debe funcionar completamente sin IA. |
| Monetización | NEEDS_DECISION | No existe | Sin billing | Sin plan/entitlements | Obligatoria | N/A | Pagos/compliance | P3 | XL | Diseñar después; sin ranking pago. |
| Mobile V2 | DEFERRED | Congelado | Contratos reutilizables | Sin cambio | Igual que desktop | Igual que desktop | Igual que desktop | P2 | XL | Evitar romper responsive; no abrir alcance todavía. |
| Release/rollback público | BLOCKED_BACKEND | Preview disponible | Sin pipeline público aprobado | Restore no probado aquí | Operativa | Gate crítico | Producción no autorizada | P0 | L | Requiere canary, SLO, incidentes y rollback ejercitado. |

## Convenciones

- **IMPLEMENTED**: existe y fue validado en el alcance indicado.
- **PARTIAL**: existe una parte útil, pero faltan garantías o capacidades esenciales.
- **READY**: diseño y dependencias permiten iniciar el trabajo sin una decisión estratégica adicional.
- **BLOCKED_DATA / BLOCKED_BACKEND / BLOCKED_AUTH**: la dependencia indicada impide prometer la capacidad.
- **DEFERRED**: fuera de prioridad deliberadamente.
- **NEEDS_DECISION**: requiere una decisión de producto, comercial, legal o de proveedor.
- **READY_FOR_DB_EXECUTION**: terminado, testeado y NO aplicado. Espera un entorno
  donde probar el cambio antes de tocar la base real. No es `IMPLEMENTED`: una
  migración escrita no es una migración aplicada.

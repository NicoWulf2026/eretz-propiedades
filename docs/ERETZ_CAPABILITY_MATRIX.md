# ERETZ Propiedades — Matriz de capacidades

Fecha de corte: 2026-08-27

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
| Cuenta y sincronización | BLOCKED_AUTH | Preparado conceptualmente | Falta | Falta modelo | Falta proveedor/contrato | N/A | Requiere RLS y sesión SSR | P1 | XL | Explorar seguirá siendo anónimo; migrará estado local tras consentimiento. |
| Inmobiliarias públicas | PARTIAL | Listado/perfil | Lectura | 7.004 registros | No requerida | Logo 0,49%; descripción 0% | Server-only | P1 | L | 45,50% tiene publicaciones activas. |
| Agentes públicos | BLOCKED_DATA | Vista derivada | Lectura | No hay entidad formal | No requerida | 25,25% ruido aparente | Server-only | P1 | L | 507 nombres normalizados; relación profesional no persistida. |
| Miniportales | BLOCKED_BACKEND | No existe | Falta tenancy/branding | Falta schema | Requiere roles | Cobertura profesional débil | Aislamiento multi-tenant | P2 | XL | Debe tener default elegante y branding acotado. |
| Roles profesionales | BLOCKED_AUTH | No existe | Falta autorización | Falta membership/ACL | Obligatoria | Falta ownership | Riesgo alto multi-tenant | P1 | XL | Owner/admin/manager/agent/editor/viewer. |
| Publicación manual | BLOCKED_BACKEND | No existe | Falta workflow | Falta modelo publicación física | Obligatoria para publicar | Validación pendiente | Antiabuso requerido | P1 | XL | Particular, inmobiliaria y agente; origen siempre registrado. |
| Importación desde web | NEEDS_DECISION | No existe | Falta pipeline | Falta staging/provenance | Profesional | Fuente heterogénea | SSRF/abuso/copyright | P2 | XL | No implementar sin contrato y límites explícitos. |
| Reportes de publicación | PARTIAL | Formulario/API | Writer opcional | Tabla preparada, 0 filas | No requerida | Datos aportados | Sin rate limit/cola | P0 | L | En modo obligatorio falla 503 cerrado si no hay writer. |
| Baja/corrección | PARTIAL | Flujo por email | Sin expediente | Sin workflow | No requerida | No estructurada | Spam/trazabilidad pendientes | P0 | M | Requiere cola, estados y auditoría para beta pública. |
| Quality Gate | IMPLEMENTED | Nunca se expone | Blob privado, cache | Elegibilidad fuera de DB | No requerida | Fingerprint/checksum | Fail-closed | P0 | M | Debe integrarse a conteos DB sin exponer IDs excluidos. |
| Data API browser-side | IMPLEMENTED | Cero requests | OFF | N/A | N/A | N/A | Objetivo cumplido | P0 | XS | No reactivar para el frontend público. |
| ACL PostGIS | PARTIAL | N/A | N/A | Grants P0 directos | anon/auth afectados | N/A | Remediation no ejecutada | P0 | S | SQL y rollback preparados; requiere autorización/canary remoto. |
| Observabilidad | BLOCKED_BACKEND | Estados recuperables | Logs básicos | Sin métricas | Incidentes no medidos | Sin métricas de calidad | Sin alertas/SLO | P0 | L | Primera capa: request IDs, JSON/redacción, métricas y runbooks. |
| SEO/indexación pública | READY | Metadata base | robots/sitemap por implementar | Elegibilidad necesaria | Rutas privadas noindex | Duplicados importan | Preview debe seguir noindex | P0 | M | Estrategia definida; no habilitada. |
| Historial de precios | PARTIAL | Ficha lo consume | Lectura | 5.636 eventos | No requerida | Sólo 5.243 propiedades | Server-only | P2 | L | Sin fecha_publicacion global y sin serie madura. |
| ERETZ Mercado | BLOCKED_DATA | No existe | Agregaciones faltantes | Historia insuficiente | No requerida | Muestra/metodología pendientes | Anti-inferencia | P2 | XL | No publicar métricas sin N mínimo, outliers y metodología. |
| Detección de duplicados | PARTIAL | Señal en ficha | Heurísticas mínimas | Tabla formal vacía | No requerida | Varias señales disponibles | No fusionar automático | P1 | XL | Separar propiedad física, publicación y publicador. |
| Geocoding/provenance | BLOCKED_DATA | Copy honesto | Pipeline faltante | Sin provider/precision/date | No requerida | 74,92% none | Rate/cost/privacy | P1 | XL | Requiere cola, cache, proveedor y revisión de confianza. |
| Calculadoras | READY | No existe | Sólo configuración | Sin persistencia inicial | No requerida | Tasas externas explícitas | No asesoramiento implícito | P2 | L | Comenzar con cálculos deterministas y supuestos visibles. |
| Recomendaciones | PARTIAL | Relacionadas básicas | Regla actual | Sin features maduras | No requerida | Duplicados afectan | Ranking neutral | P2 | XL | Nunca pago para alterar ranking orgánico. |
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

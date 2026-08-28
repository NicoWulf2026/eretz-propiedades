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
| Miniportales | BLOCKED_BACKEND | **Sin editor a propósito** | `domain/miniportal.ts` completo | Falta persistencia | Requiere claim aprobado | Config por defecto completa | Cerrado en los tres niveles | P2 | XL | Plantilla de lista, colores `#rrggbb` estricto, secciones como unión discriminada. Cero CSS/JS/HTML arbitrario. `normalizarConfig` nunca falla: sin config la página se ve bien igual. Contraste WCAG validado. |
| Roles profesionales | BLOCKED_AUTH | No existe | Motor puro listo, sin cablear | Falta membership/ACL | Obligatoria | Falta ownership | Riesgo alto multi-tenant | P1 | XL | `domain/permissions.ts`: deny by default, tenant tomado del recurso cargado, matriz rol-capacidad recorrida completa en tests. Falta persistencia de membresías. |
| Publicación manual | READY_FOR_BACKEND | Wizard completo tras flag, **sin enlazar** | `lib/publication/` con servicio y contrato | Falta el adaptador de persistencia | Obligatoria para publicar | Validación, moderación y sugerencias | Tenant del actor cargado; idempotencia | P1 | XL | Flujo entero de punta a punta contra un adaptador en memoria. **No hay botón de publicar**: no existe dónde guardar. Falta implementar `PublicationRepository`. Ver [ERETZ_PUBLICATION_ARCHITECTURE.md](ERETZ_PUBLICATION_ARCHITECTURE.md). |
| Importación desde web | NEEDS_DECISION | No existe | Falta pipeline | Falta staging/provenance | Profesional | Fuente heterogénea | SSRF/abuso/copyright | P2 | XL | No implementar sin contrato y límites explícitos. |
| Reportes de publicación | PARTIAL | Formulario/API | Writer opcional + freno de abuso | Tabla preparada, 0 filas | No requerida | Datos aportados | Tasa y dedupe en memoria; sin cola | P0 | L | 503 cerrado sin writer. El freno es por proceso: badén, no control distribuido. Falta expediente, estados y cola. |
| Baja/corrección | PARTIAL | Flujo por email | Sin expediente | Sin workflow | No requerida | No estructurada | Spam/trazabilidad pendientes | P0 | M | Requiere cola, estados y auditoría para beta pública. |
| Quality Gate (runtime) | IMPLEMENTED | Nunca se expone | Blob privado, cache | Elegibilidad fuera de DB | No requerida | Fingerprint/checksum | Fail-closed | P0 | M | Funciona hoy filtrando en Node. |
| Quality Gate (en DB) | READY_FOR_DB_EXECUTION | N/A | Importador con swap atómico | Migración `eretz_gate` escrita, no aplicada | No requerida | Checksum + freno por caída sospechosa | Fail-closed por INNER JOIN | P0 | M | Escrito y testeado; no aplicado. Requiere entorno de prueba. |
| Data API browser-side | IMPLEMENTED | Cero requests | OFF | N/A | N/A | N/A | Objetivo cumplido | P0 | XS | No reactivar para el frontend público. |
| ACL PostGIS | READY_FOR_DB_EXECUTION | N/A | N/A | Grants P0 directos | anon/auth afectados | N/A | Remediación lista, NO ejecutada | P0 | S | **Vigente y verificado el 2026-08-27: 24 de 24 privilegios de escritura para `anon` y `authenticated`.** SQL, rollback y verificador listos. No se aplica sin entorno donde ensayar el rollback. |
| Observabilidad | PARTIAL | Estados recuperables | Request ID + log JSON en las 7 rutas; `Cronometro` disponible | Sin métricas | Incidentes no medidos | Sin métricas de calidad | Sin alertas/SLO | P0 | L | El cronómetro de sub-tiempos existe y está testeado, **sin cablear a las rutas**: hacerlo toca las 7 y se decide aparte. Falta agregación, p50/p95, SLO, alertas y runbooks. |
| SEO/indexación pública | READY | Metadata base | `domain/seo.ts`: política, canónicas y sitemap | Elegibilidad necesaria | Rutas privadas noindex | Duplicados importan | Preview sigue noindex, sin cambios | P0 | M | Fail-closed: el primer chequeo es producción, así que no puede activarse por accidente. Una ficha que el Gate excluye no se indexa. `robots.ts` y `sitemap.ts` **no se tocaron** y sus tests siguen pasando. |
| Historial de precios | PARTIAL | Ficha lo consume | `domain/history.ts` + lectura | 5.636 eventos | No requerida | Sólo 5.243 propiedades | Server-only | P2 | L | Seis fechas separadas: `firstSeenAt` nunca se usa como publicación. Un cambio entre dos observaciones lleva INTERVALO y no fecha —con scraping semanal, fijarla es un error de hasta siete días—. Con menos de dos observaciones no se afirma "sin cambios". |
| ERETZ Mercado | BLOCKED_DATA | No existe | Agregaciones faltantes | Historia insuficiente | No requerida | **Metodología definida** | Anti-inferencia | P2 | XL | `domain/market.ts` fija mediana, deduplicación por inmueble, recorte de colas y N mínimo. `diagnosticarMercado` deja como comprobación ejecutable que hoy NO se puede publicar. |
| Detección de duplicados | PARTIAL | Señal en ficha | Scorer existente | Tabla formal vacía | No requerida | Varias señales disponibles | No fusionar automático | P1 | XL | `domain/property-entity.ts` formaliza la separación y hace del agrupamiento metadato reversible con evidencia. POSSIBLE_MATCH nunca agrupa solo. Falta persistir entidades. |
| Geocoding/provenance | BLOCKED_DATA | Copy honesto | Pipeline faltante | Sin provider/precision/date | No requerida | 74,92% none | Rate/cost/privacy | P1 | XL | `domain/geography.ts` define procedencia y separa precisión de confianza: alta confianza sobre un centroide de ciudad no habilita un punto en el mapa. No traduce alias de ciudad (ya está `city_normalization_rules`); provincias sí, y "Buenos Aires" a secas queda AMBIGUA en vez de resolverse en silencio. |
| Calculadoras | IMPLEMENTED | `/calculadoras`: hub y 5 pantallas | `domain/finance.ts` completo | No necesita | No requerida | Ninguna tasa escrita ni precargada | Sin red: aritmética local | P2 | L | Cinco funcionando, con desglose, fórmula y supuestos. 21 E2E y Axe sin violaciones. UVA y comprar-vs-alquilar siguen fuera, y el hub publica el motivo. |
| Recomendaciones | PARTIAL | Relacionadas ordenadas | `domain/recommendations.ts` cableado | Sin features maduras | No requerida | Duplicados afectan | Sin campos comerciales en el tipo | P2 | XL | Antes tomaba los primeros 4 de la provincia; ahora puntúa lo ya traído, sin consultas nuevas. Cableado con `minimo: 0` para mejorar sólo el orden y no vaciar la sección. Falta UI de "Similar porque…". |
| Modelo de dominio | IMPLEMENTED | Tipos disponibles | Módulos puros | No toca DB | Contratos listos | Separa inferido de afirmado | Tenancy por diseño | P1 | L | Propiedad física, publicación y publicador separados, con tres ejes de estado ortogonales. No reemplaza `Property`: es el modelo hacia el que migrar. |
| Calidad de datos | SHADOW_VALIDATED | No expuesto | `domain/data-quality.ts` + modo sombra | No toca DB | No requerida | Detecta, no corrige | Sin efectos | P1 | M | Separa incoherencias internas (INVALID) de atípicos (SUSPICIOUS). **Hallazgo:** el mapper sanea coordenadas inválidas y negativos a `null` antes del dominio, así que tres reglas no se disparan en el camino de lectura. |
| Overrides editoriales | BLOCKED_BACKEND | No existe | `domain/overrides.ts` | Falta persistencia | Requiere claim aprobado | Fuente inmutable | `sourceUrl` no corregible | P1 | XL | Snapshot mas overrides da una vista publicada que se calcula, no se guarda. Conserva trazabilidad ante reclamos. |
| Reclamación de inmobiliarias | BLOCKED_AUTH | No existe | `domain/claim.ts` | Falta persistencia | Obligatoria | Evidencia clasificada por fuerza | Sesgo al falso negativo | P1 | XL | Conocer un dato público nunca aprueba solo; sólo controlar un canal. Una organización con dueño nunca va por vía automática. |
| Moderación automática | SHADOW_VALIDATED | **Sin efecto sobre visibilidad** | `domain/moderation.ts` + modo sombra | No toca DB | No requerida | Determinista y explicable | Sesgo a no ocultar | P1 | L | Cableada en modo sombra tras flag apagada por defecto: **calcula y no decide**. Cero falsos positivos sobre corpus plausible de 25 variantes. NO es enforcement. |
| Quality score | SHADOW_VALIDATED | **Sin efecto sobre orden** | `domain/quality-score.ts` + modo sombra | No toca DB | No requerida | Explicable por dimensión | No es ranking | P1 | M | Medido en sombra: p50 = 0,763 sobre corpus plausible. La dimensión `media` es la que más lo arrastra. Sigue sin ordenar, filtrar ni decidir elegibilidad. |
| Alertas y búsquedas guardadas | BLOCKED_AUTH | No existe | `domain/alerts.ts` | Falta persistencia | Obligatoria | Reusa `PropertyFilters` | Nada se envía | P2 | XL | El emparejador devuelve INDETERMINADO cuando el filtro necesita la base, nunca `false`: decir "no coincide" sin saber produce alertas que nunca llegan. |
| Analítica profesional | BLOCKED_BACKEND | Sin panel | `domain/professional-analytics.ts` | Sin colector | Contexto anónimo | Sin métricas fabricadas | No guarda texto de búsqueda | P2 | L | Se guarda la FORMA de la búsqueda, no su contenido: una búsqueda libre puede traer una calle con altura o un nombre propio. |
| Expedientes de reporte | BLOCKED_BACKEND | Formulario actual | `domain/reports.ts` | Tabla preparada, 0 filas | No requerida | Estados y auditoría | Antiabuso = `BASIC_LOCAL_MITIGATION` | P0 | L | Aceptar y resolver separados. Un rechazo puede reabrirse. El limitador in-memory NO se presenta como control distribuido. |
| Estado del sistema | READY | N/A | `domain/health.ts` | N/A | N/A | N/A | **Sin endpoint a propósito** | P1 | S | Un /health público enumera dependencias y dice cuándo el sistema está débil. Sin dependencias evaluadas devuelve UNAVAILABLE, no HEALTHY. |
| Revisión legal | NEEDS_DECISION | Páginas rotuladas borrador | N/A | N/A | N/A | N/A | 3 exposiciones inventariadas | P0 | M | [LEGAL_REVIEW_REQUIRED.md](LEGAL_REVIEW_REQUIRED.md) separa hecho técnico de decisión legal. La mayor: nombres de agentes publicados sin consentimiento. |
| Modo sombra del dominio | IMPLEMENTED | Ninguna | `lib/shadow/` tras flag OFF | **No escribe nada** | No requerida | Mide sin corregir | Log agregado, sin PII | P1 | M | Único punto de integración en `mapRowsToProperties`. `ejecutarShadow` devuelve `void`: no hay por dónde usar el resultado. Overhead medido: ~48 µs por propiedad. |
| IA | DEFERRED | No necesaria | Sin proveedor | No necesaria | Opcional | Requiere grounding | Costos/privacidad | P3 | XL | Producto debe funcionar completamente sin IA. |
| Monetización | NEEDS_DECISION | No existe | Sin billing | Sin plan/entitlements | Obligatoria | N/A | Pagos/compliance | P3 | XL | Diseñar después; sin ranking pago. |
| Mobile V2 | DEFERRED | Congelado | Contratos reutilizables | Sin cambio | Igual que desktop | Igual que desktop | Igual que desktop | P2 | XL | Evitar romper responsive; no abrir alcance todavía. |
| Release/rollback público | BLOCKED_BACKEND | Preview disponible | Checklist de 14 puntos verificables | Rollback de base DEFERRED | Operativa | Gate crítico | Producción no autorizada | P0 | L | Documentado APP PREVIEW ≠ DB STAGING, que es la confusión que originó el bloqueo. Requiere canary, SLO, incidentes y rollback ejercitado de verdad. |

## Convenciones

- **IMPLEMENTED**: existe y fue validado en el alcance indicado.
- **PARTIAL**: existe una parte útil, pero faltan garantías o capacidades esenciales.
- **READY**: diseño y dependencias permiten iniciar el trabajo sin una decisión estratégica adicional.
- **BLOCKED_DATA / BLOCKED_BACKEND / BLOCKED_AUTH**: la dependencia indicada impide prometer la capacidad.
- **DEFERRED**: fuera de prioridad deliberadamente.
- **NEEDS_DECISION**: requiere una decisión de producto, comercial, legal o de proveedor.
- **READY_FOR_BACKEND**: el flujo está completo y probado de punta a punta contra un
  adaptador en memoria. Falta **sólo** conectar la persistencia real; no hay que
  rediseñar nada. No es `IMPLEMENTED`: todavía no se puede usar.
- **LOCAL_ONLY**: funciona, y sólo en el dispositivo de quien lo usa. No se
  sincroniza ni promete una cuenta.
- **SHADOW_VALIDATED**: la lógica corre sobre datos que pasan por la aplicación y se
  mide qué diría, pero **no decide nada**: no oculta, no ordena, no filtra. No es
  `ACTIVE_ENFORCEMENT` y no debe leerse como tal.
- **READY_FOR_DB_EXECUTION**: terminado, testeado y NO aplicado. Espera un entorno
  donde probar el cambio antes de tocar la base real. No es `IMPLEMENTED`: una
  migración escrita no es una migración aplicada.

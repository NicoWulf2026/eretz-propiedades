# ERETZ Propiedades — Roadmap post UX/UI V2

Fecha de corte: 2026-08-27

Escala de esfuerzo relativa: XS, S, M, L, XL. No representa días ni fechas comprometidas.

## Principios invariables

- Explorar propiedades no requiere cuenta.
- El ranking orgánico no se vende ni se altera por pago.
- Propiedad física, publicación y publicador son entidades distintas.
- Una coordenada aproximada nunca se presenta como exacta.
- Datos desconocidos no se convierten en `false` o `0`.
- Preview permanece protegido y `noindex`; producción exige autorización separada.
- El navegador no accede a Supabase Data API ni recibe secretos PostgreSQL/Blob.

## P0 — antes de beta pública

| Orden | Objetivo | Estado actual | Dependencias | Frontend | Backend / DB | Seguridad / riesgo | Esfuerzo |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 1 | Retirar writes PostGIS de `anon/authenticated` | SQL y rollback preparados, no ejecutados | Autorización remota y canary PostGIS | Sin cambio | REVOKE mínimo en 3 objetos | P0: escritura directa innecesaria | S |
| 2 | Validar el commit exacto publicado en Preview | Checkpoint publicado; Preview exacto no creado por falta de autorización Vercel CLI | Sesión Vercel autorizada | QA completa desktop | Deployment privado `iad1` | Evitar probar un SHA distinto | M |
| 3 | Hacer conteos y facets escalables | Gate filtrado en Node; frío hasta ~20 s | Diseño de relación privada versionada | Copy/cargas discretas | Conteo/facets en DB, cache por fingerprint | No exponer exclusiones; riesgo de regresión | L |
| 4 | Indexar búsqueda y recencia | Seq scans y sort completo | Medición de workload y SQL revisado | Contrato compatible | GIN/FTS/columnas ordenables | Índices online/canary; costo de write | L |
| 5 | Persistir y operar reportes/correcciones | API parcial, email y 0 reportes | Writer aprobado, cola operativa | Estados honestos | Dedupe, rate limit, auditoría, workflow | Spam, abuso y retiro indebido | L |
| 6 | Observabilidad mínima de beta | Logs Vercel y errores sanitizados | Convención de eventos/SLO | Errores y estados medibles | Request ID, logs JSON, latencias, alertas | Redacción de PII/secretos | L |
| 7 | Preparar indexación pública | Todo sigue `noindex`; estrategia definida | Criterio de publicabilidad y revisión legal | Canonical/metadata | sitemap/robots por ambiente | Duplicados y URLs faceteadas | M |
| 8 | Cerrar calidad mínima publicable | Cobertura desigual y outliers extremos | Reglas por fuente/campo | Copy y fallback | cuarentena/validación no destructiva | Datos engañosos | L |
| 9 | Ensayar release, rollback e incidentes | Preview protegido funciona | SLO, responsables, backups/restore | Smoke suite | canary y rollback ejercitado | Riesgo operacional público | L |

## P1 — producto completo

| Orden | Objetivo | Estado actual | Dependencias | Frontend | Backend / DB | Seguridad / riesgo | Esfuerzo |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 10 | Cuentas y sincronización | Mi ERETZ local completo | Decidir auth/schema y consentir migración | Login opcional, sync transparente | sesiones SSR, RLS, colecciones/historial | takeover, CSRF, privacidad | XL |
| 11 | Tenancy y roles profesionales | Perfiles públicos parciales | Modelo de organización/membership | Administración por rol | owner/admin/manager/agent/editor/viewer | aislamiento tenant/IDOR | XL |
| 12 | Entidad profesional y limpieza de agentes | 7.004 inmobiliarias; agentes derivados | Identidad/claim/merge humano | Perfiles honestos | agencias, sucursales, agentes, relaciones | suplantación y claims | L |
| 13 | Publicación manual segura | No existe | Auth, ownership y contrato editorial | Formulario y borradores | publicación/origen/media/validación | spam, abuso, PII | XL |
| 14 | Importación profesional | No existe | Contrato, límites y decisión de producto | Wizard y reportes | staging, fetch seguro, provenance | SSRF/copyright/rate limits | XL |
| 15 | Geocoding con provenance | Modelo de confianza runtime | Proveedor/costos aprobados | Copy de precisión | cola, cache, provider, precision/date | costo, rate limit, privacidad | XL |
| 16 | Modelo de propiedad física/duplicados | Señales, tabla vacía | Dataset de evaluación y umbrales | Explicación, no fusión silenciosa | entity resolution auditable | falsos positivos | XL |

## P2 — crecimiento

| Orden | Objetivo | Estado actual | Dependencias | Riesgo | Esfuerzo |
| ---: | --- | --- | --- | --- | --- |
| 17 | Miniportales profesionales | Sin tenancy/branding | P1 roles y datos profesionales | personalización insegura/SEO duplicado | XL |
| 18 | Alertas y búsquedas sincronizadas | Sólo local | Cuentas, jobs y email | spam y entregabilidad | L |
| 19 | ERETZ Mercado | Historia insuficiente | series, moneda, outliers y N mínimo | métricas engañosas | XL |
| 20 | Calculadoras contextuales | No implementadas | supuestos configurables y disclaimers | asesoramiento implícito | L |
| 21 | Recomendaciones explicables | Relacionadas básicas | dedupe y features confiables | burbuja/ranking opaco | XL |
| 22 | Analytics profesional | No existe | tenancy, eventos y privacidad | exposición competitiva/PII | L |
| 23 | Mobile V2 | Congelado | desktop estable y research propio | duplicar deuda UX | XL |

## P3 — futuro

| Orden | Objetivo | Condición previa | Riesgo | Esfuerzo |
| ---: | --- | --- | --- | --- |
| 24 | IA para intención, resumen o comparación | producto base medido, proveedor aprobado, fallback | costo, privacidad, alucinación | XL |
| 25 | Suscripciones y entitlements | valor profesional probado, decisión comercial/legal | pagos, soporte, compliance | XL |
| 26 | Publicidad separada del ranking | política editorial pública y etiquetado inequívoco | erosión de confianza | L |

## Arquitecturas propuestas

### Cuentas

Mantener exploración anónima y estado local. Al registrarse, migrar guardadas, colecciones, comparaciones, historial y búsquedas mediante una operación idempotente, explícita y reversible. Las sesiones deben resolverse server-side; toda tabla personal requiere `user_id`, RLS de propietario y auditoría de operaciones sensibles.

### Profesionales y miniportales

Separar `organization`, `branch`, `professional`, `membership`, `role`, `branding` y `publisher_identity`. Una propiedad/publicación admite múltiples agentes por tabla de relación. Los claims nunca confieren ownership sin verificación. Branding debe usar tokens con límites, no CSS arbitrario.

### Publicaciones

Separar `physical_property`, `listing`, `publisher` y `listing_source`. Registrar `scraped`, `manual`, `imported` u otro origen. Validar identidad de publicador, operación, tipo, condición de precio, moneda, geografía, descripción, contacto e imágenes; aplicar rate limit, spam scoring, URLs seguras y dedupe sin revisión manual obligatoria.

### Geocoding

Pipeline asíncrono con dirección normalizada, hash de cache, proveedor, versión, fecha, resultado, precisión, confidence, intentos y error. No reemplazar una ubicación previa sin conservar provenance. Las fallas terminan en `none`, no en un centroide presentado como exacto.

### Duplicados

- `CONFIRMED`: declaración/relación determinista aprobada.
- `HIGH_CONFIDENCE`: combinación fuerte de dirección, coordenadas, superficies, imágenes y contacto sin contradicción.
- `POSSIBLE`: señales parciales para revisión o agrupación explicable.
- `NO_MATCH`: contradicción o evidencia insuficiente.

Nunca fusionar por una señal aislada. Conservar cada publicación y su publicador aunque varias correspondan a la misma propiedad física.

### Mercado

Publicar sólo segmentos con muestra mínima documentada. Usar mediana, percentiles, outliers explícitos, moneda separada y series comparables. No convertir ARS/USD sin fuente, fecha y metodología. Mostrar disponibilidad de oferta, no afirmar precios de cierre.

### Calculadoras

Comenzar con fórmulas deterministas: cuota/capacidad, gastos, comisión, precio por m² y rentabilidad. Tasas, inflación y tipo de cambio deben ser entradas del usuario o valores configurados con fuente/fecha; nunca supuestos ocultos.

### Seguridad y antiabuso

El contenido público no puede hacerse imposible de extraer. Mitigar con límites de paginación, cache, rate limiting por patrón, WAF/bot management cuando corresponda, endpoints mínimos, detección de enumeración, observabilidad y respuesta a abuso. No perjudicar SEO ni navegación legítima.

## Top 10 de deuda técnica real

1. Conteos que transfieren el universo de IDs/coords y filtran el Quality Gate en Node.
2. Búsqueda textual normalizada por request sin índice utilizable.
3. Orden de recencia que fuerza scan y sort del inventario.
4. Grants PostGIS directos y objetos/extensiones/backups históricos en `public`.
5. Políticas RLS legacy dormidas que podrían reabrir exposición si vuelve Data API.
6. Ausencia de observabilidad estructurada, métricas, alertas y runbooks.
7. CSS global grande y capas históricas que elevan riesgo de regresión visual.
8. Contratos profesionales sin entidad de agente, tenancy ni ownership formal.
9. Calidad numérica sin cuarentena: outliers extremos en ambientes, superficies, baños y expensas.
10. Tests E2E acoplados a datos/Preview real sin un contrato estable de muestras QA versionadas y seguras.

## Beta readiness

### Beta privada — YES WITH CONDITIONS

Preview protegido, grupo limitado, monitoreo manual, writer opcional explícitamente deshabilitado y QA del SHA exacto. Resolver el ACL P0 antes de cualquier reapertura de Data API.

### Beta pública — NO

Requiere completar P0: ACL, performance, reportes antiabuso, observabilidad, indexación, calidad mínima, legal/privacidad y runbook de incidentes.

### Producción pública — NO

Además: release/rollback y restore probados, ownership operativo, SLO, monitoreo continuo, gestión profesional/autenticación segura cuando se habiliten y criterio de retirada/publicación ejercitado.

## Próximo bloque grande recomendado

**Beta pública segura: hardening DB + Quality Gate/conteos + observabilidad/reportes + readiness de indexación.**

Es un solo bloque coherente: elimina la exposición ACL P0, mueve elegibilidad/conteos a una arquitectura escalable, agrega telemetría y respuesta operativa, cierra reportes antiabuso y deja SEO activable por ambiente. No incluye producción, autenticación de usuarios, monetización ni geocoding masivo.

# ERETZ — plan derivado de la auditoría en curso

Fecha: 2026-09-18. Candidato local `codex/eretz-unified-audit`, no aprobación
productiva ni cierre de la misión. Evidencia cuantificada y limitaciones en
`ERETZ_UNIFICATION_EVIDENCE.md`.

## Estado comprobado

| Capacidad | Estado | Evidencia / pendiente |
|---|---|---|
| Preservación de historia/worktrees | Implementada | Candidato aislado; ocho originales conservados |
| Comparación histórica | Parcial | 39 refs inventariadas; replays comparables limitados, no benchmark nacional |
| URL detection compartida | Implementada y probada | Histórico recuperado con protección de tenant |
| Conectores y certificación | Implementados, validación parcial | Casos offline y dos controles vivos; falta cohorte fresca del HEAD |
| Identidad de fuentes | Mejorada, cobertura parcial | Dominio/oficina/perfil separados; long tail pendiente |
| Inventario vs corrección del dato | Separados | Determinismo no certifica geografía; contradicciones explícitas retenidas |
| Null/zero e incompletas | Probados por fronteras | Raw/staging, API, presentación; cero precio/superficie sólo fixture |
| Imágenes | Política corregida, revisión pendiente | Frecuencia sin evidencia no excluye; falta revisión visual de cohorte real |
| Workers/locks/heartbeat | Controles locales PASS | Falta soak con cohortes reales y fallos inducidos |
| SQL de merge/auditoría/rollback | Validado localmente | Diecisiete controles PGlite con CHECK/FK/tipos observados; no prueba de deployment/concurrencia alojada |
| API combinada/mapa/batch/agencia | Integrada localmente | Snapshot real y contratos probados; staging accesible pendiente |
| Detail histórico numérico | Bloqueado por datos | Crosswalk de IDs público↔hash vacío; no inventar aliases |
| Frontend F7 | Integrado sin rediseño | Tests/typecheck/build; browser QA candidato pendiente |
| Publicación única | Parcial | Hay consumidores reales del escritor REST histórico; equivalencia con RPC pendiente |

Últimos controles: 2633 tests backend PASS (157,01 s, XML de identidad actual),
sin fallos/errores/skips. Operación desconocida se almacena NULL
según el CHECK público observado; superficie cubierta ya se preserva en el
RPC candidato. La consulta REST de identidad no convierte fallo/rango parcial
en propiedad nueva. Persisten diferencias de campos/invalidación y no se
autoriza retirar ese consumidor todavía.

INSERT RPC ahora conserva id_externo/provincia/pais entregados como texto nullable,
sin defaults inventados. UPDATE geográfico acoplado e invalidación justificada
de valores históricos siguen pendientes; no reemplazar todavía el escritor REST
con payload enriquecido por un RPC suponiendo equivalencia de todas las columnas.

Paquetes y registro histórico ya rechazan corrupción, ausencia de archivos y
conteos contradictorios antes de derivar snapshots/ausencias. Replay del mismo
log: 201 desapariciones, 77 reapariciones; máximo de ausencias observadas al final
corregido de 1 a 32 por incremento continuado. No es prueba de bajas reales ni
habilitación productiva; fuente/completitud/fingerprint actuales siguen pendientes.

Descarga GeoRef valida recursos/totales/IDs/offsets antes de tocar referencias;
fallos de descarga no dejan una actualización parcial. Publicación multiarchivo
frente a kill/disco, hashes físicos vs texto LF y proveniencia de datos GeoRef
en certificación siguen abiertos. Los seis recursos originales conservan sus
conteos/hash lógico: discrepancia CRLF de bytes no equivale a geografía corrupta.
Diff exige recursos/manifiestos/conteos/hashes verificados, y no autoriza reemplazo.
Namespaces de agencias no son iguales: cero coincidencias PK pública con IDs
de origen en 7004 filas. No construir aliases ni FK suponiendo igualdad numérica.

Normalizador consume referencias verificadas. Fingerprint schema=5 incluye
geo_reference. Backfill no promueve cierres históricos idempotentes a huella
actual ni --refresh-safe sobreescribe evidencia vencida; sólo métricas sin
recertificación sobre código ya compatible. Queue exige prueba granular/versionada
de código para éxito; defectos antiguos desconocidos no reciben amnistía. Falta
proveniencia de datos GeoRef/identidad actuales: código vigente no prueba verdad.

La cola real ahora comprueba identidad del catálogo antes de reutilizar evidencia:
un viejo pending/block de identidad no tapa una fuente ahora READY, un fallo al
resolver no habilita éxito cached, y cierres de parser requieren URL/FK observado
iguales y ejecutables. No es un crosswalk hacia PK públicas ni aprobación del
lifecycle; faltan continuidad temporal, referencia geográfica capturada y política
de refresh de éxitos. Ledger corrupto/último resultado ambiguo requiere revisión.

## Matriz de consumidores y eliminación

Las referencias siguientes son consumidores ejecutables observados, no sólo
menciones en documentación. No borrar entrypoints con consumidores activos.

| Ruta | Consumidor actual | Frontera compartida / sustitución | Decisión actual |
|---|---|---|---|
| `scraper/scraper_propiedades.py` | `run_daily_pipeline`, `publish_to_supabase`, `validate_raw_properties`, `geocode_staging` | URLs/modelo/network; detector de imágenes reexportado | STILL_USED; no eliminar monolito entero |
| `scripts/publish_to_supabase.py` | `run_daily_pipeline` | Join raw/staging por agencia/hash; identidad ambigua bloqueada | STILL_USED; merge/audit atómico aún no equivalente |
| `scripts/run_manifest.py` | `run_quality_manifest_batches` | Playwright compartido y RPC safe merge existente | STILL_USED; probar equivalencia antes de converger entrypoint |
| `scripts/run_rollout.py` | `agency_certifier`, cola de certificación | Conectores, contrato/geografía/fingerprint compartidos | Runtime candidato de certificación; no duplicar extractores |
| `scripts/canario_brave_50_v2.py` | `brave_250` | Mismo resolver V2 y política de red | STILL_USED; carga de entorno explícita del CLI |
| `scripts/canario_brave_50.py` | Comparación A/B histórica | Muestra histórica reproducible | Control de evaluación, no pipeline productivo alternativo |
| `scripts/apply_page_image_filter.py` | CLI de artefactos | Misma política de assets; no umbral de exclusión independiente | Herramienta offline; copia distinta, no recertifica agencia |
| `frontend/src/lib/property-db-service.ts` | `property-service` para IDs históricos | API v2 cuando existe identidad resoluble | STILL_USED acotado; retirar con crosswalk probado |
| `frontend/src/lib/agency-bridge.ts` y `db-writer.ts` | Directorio profesional / escrituras existentes | No equivalentes a catálogo de propiedades | No declarar muertos ni reemplazar por snapshot |

## Cierre de la unificación (antes de otra etapa grande)

Revisión adicional de tooling local no integrado: `run_faceted_scraping.py`
duplica la generación de candidatos ya consumida desde
`scraper/faceted_discovery.py`, su parámetro workers no se utiliza y su informe
atribuye cero enlaces a JS-only sin demostrarlo. No portarlo como segundo
scraper. Tanto ese CLI como el helper de paginación no consumido generan
`/pagina-N` incluso al detectar `/page/N`: registrar esa familia antes de
habilitar el helper; no afirmar recuperación de paginación por copiarlo.
`dry_run_politica.py` aporta trazabilidad de campos conservados, pero sus
firmas cortas y coordenadas aproximadas no prueban igualdad ni verdad geográfica.
No usar sus decisiones como autorización productiva ni ejecutar sus escrituras.

Triage estático actual: 85 Python sin trackear en el worktree original, 45 en
root como herramientas ad hoc; todos parsean, seis rutas también existen en el
candidato y cuatro son idénticas. Siete tienen indicadores sintácticos estrechos
de escritura; no es un análisis completo de efectos ni un permiso de ejecución.
`apply_diagnostic_backfill` bloquea --commit y genera SQL para un RUN_ID
histórico: no portarlo como clasificador actual. `run_scraping_autofix_continuous`
orquesta import/validación/geocoding y posee estado/lock propio; no iniciar una
segunda operación paralela ni reemplazar los locks atómicos ya probados por
esas banderas. Hay consumidores reales de los campaigns desde
run_targeted_coverage_diagnostic/run_targeted_playwright_diagnostic: todavía
no son SAFE_TO_REMOVE. Sus artefactos diagnósticos no equivalen a certificación.

1. Terminar revisión de tooling local no integrado por riesgo/capacidad, no
   incorporar scripts uno a uno sólo por existir. Mantener evidencia de descarte.
2. Comparar caminos de publicación REST/RPC: cobertura de campos, idempotencia,
   auditoría y fallos parciales. Unificar únicamente con equivalencia demostrada.
3. Revisar selección temporal de paquetes: empates, timestamps, procedencia y
   vigencia de fingerprint. Un paquete histórico legible no es certificación
   fresca ni autorización de publicación.
4. Completar controles de contradicción JSON-LD/prosa y contaminación de imágenes
   sin convertir texto de oficina/footer en ubicación de todas las propiedades.
5. Cohorte fresca representativa por familia: dos corridas, verdad del dato
   contrastada y reporte por fila contra mejores baselines comparables.
6. Repetir suite completa, wheel instalado, contratos/API y browser QA permitido.
   Actualizar veredicto final sólo con esas pruebas, no con cantidad de tests.

## Backend beta confiable

No exige terminar las inmobiliarias nacionales. Requiere un conjunto declarado
de fuentes verificadas, catálogo fiel a sus observaciones, errores controlados,
contratos estables y operación recuperable. Bloqueos relevantes:

- Cohorte fresca y soak operacional con gates del HEAD actual.
- Bridge histórico de IDs con datos reales autorizados, si esas URLs entran al scope.
- Staging separado y validación de transacciones/RLS/roles a través de PostgREST.
- Browser QA y entorno API accesible de staging; no confundir snapshot local con staging.

El envío CRM, publicación manual persistida, sync cloud de colecciones y mobile
premium no se convierten en requisitos beta por intuición: necesitan scope de
producto explícito. Display de contacto sólo usa datos públicos existentes.

## Producción

Después de beta: un único escritor aprobado, backup/restore probado, identidad
de deployment/configuración, credenciales mínimas, rate/volume limits, operación
supervisada y ensayo de rollback de una corrida controlada. Producción, DNS,
publicación y push definitivo siguen requiriendo autorización del usuario.
El canary con INSERT/ROLLBACK puede consumir secuencias: no es lectura pura.

## Cobertura nacional y estimación

Los 2.501 intentos / 429 agencias / 20,31 días incluyen reintentos y STOP. Las
21,12 agencias distintas/día no son altas verificadas/día; extrapolarlas al
padrón daría una fecha falsa. La mediana registrada de dos corridas (215,4 s)
no incluye toda la espera ni demuestra calidad. No existe aún ETA nacional
defendible con estas medidas.

El reporte operativo ya no llama certified a primeras corridas NEEDS_FIX ni
publicadas a propiedades enumeradas. Diferencia intento nuevo/primer cierre
exitoso registrado, reutiliza el criterio en ventanas de ETA y señala duraciones
faltantes. Replay de 48 h: 26 intentos nuevos vs 8 primeros éxitos; 0,54/h anterior
mal etiquetado vs 0,17/h corregido. Sigue siendo estatus histórico registrado,
no throughput vigente con calidad/código/fuente verificados ni prueba de publicación.
Historial ilegible bloquea fechas; cinco ventanas leen un solo log/reloj (~0,789 s
en la medición local frente a ~4,52 s con cinco lecturas).

El presupuesto observado de suites backend completas varía ~2,6–6,5 minutos local,
aparte de lint/build/replays; no es una estimación de días de desarrollo.
Para actualizar plazos se debe medir una cohorte fresca durante varias jornadas:
altas netas verificadas/día, tasa de corrección por familia, revisiones humanas,
requests, latencias, STOP internos/externos y coste de revalidación. El ETA por
familia será pendientes / throughput neto observado, con intervalo y bloqueos
externos separados. Cobertura long tail sigue después de beta por familias,
sin recuperar inventario de Zonaprop ni Argenprop.

No iniciar ciegamente una nueva reconstrucción: primero cerrar evidencia y
decidir el scope beta con el veredicto completo de esta misión.

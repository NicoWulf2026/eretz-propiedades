# ERETZ Propiedades — políticas permanentes (decididas por el usuario el 2026-09-29)

Fuente: ronda única de decisiones del 29-09. Son reglas de la misión, no casos.
Un caso nuevo que cae en una política se resuelve con la política, sin preguntar.
Solo se vuelve a preguntar ante una decisión genuinamente nueva, irreversible o de
alto impacto, no cubierta aquí y sin salida conservadora; e incluso entonces se
sigue con otra tarea segura mientras tanto.

Reglas generales:
- Cobertura nacional y beta son tracks separados: ninguno bloquea al otro.
- Un bloqueo externo (credencial, cuenta, pago, dominio, abogado, acción productiva)
  se marca (`BLOCKED_EXTERNAL_*` / `EXTERNAL_*_REQUIRED`) y se sigue con otra cosa.
- Decisión técnica reversible: la resuelve el agente.
- Reportar una fase no es detenerse.

---

## A. Operación inmediata

### P1 — Retiros de la snapshot
- **REMOVED** solo con evidencia inequívoca de muerte en la URL de la ficha: 404, 410,
  redirección permanente fuera de la ficha, o **soft-404 demostrado** (página genérica
  detectada por evidencia de contenido, no solo por el status).
- Una ficha **viva** no se retira por faltar en dos inventarios.
- 3 ausencias confiables → INACTIVE/REMOVED según `ERETZ_PROPERTY_LIFECYCLE.md`.
- Una ausencia de catálogo nunca equivale a una propiedad inexistente.
- Se preserva la procedencia del motivo de retiro (qué, cuándo, con qué evidencia).
- Verificación cortés y automática; revisión manual solo de ambiguas.
- Implementación: `scripts/verificar_retiros.py` + `api_snapshot.py --retiros-verificados`.

### P2 — Despliegue automático de la snapshot LOCAL
Autorizado cuando pasan TODOS: `integrity_check` ok; QA de API 14/14 con el estado de la
servida; 0 filas del exterior publicables; 0 precios simbólicos; 0 GEO_CONFLICT en el mapa;
altas/bajas/reemplazos explicados por políticas aprobadas; duplicados probables auditados;
respaldo con hash de la anterior; rollback automático probado; Regression Gate verde.
Si falla uno: no se despliega. **No** autoriza deploy público, writes a Supabase, DNS ni
cambios remotos.

### P3 — Lote compartido del 29-09
Aplicado de inmediato (baseline → patch → tests → replay → canarios; luego huella →
invalidación → recertificación).

### P4 — Cambios futuros a la huella compartida
- Puede producir falso CERTIFIED o pérdida sistémica → se aplica en cuanto pasa test/replay/canario.
- Resto: se agrupa hasta que ocurra cualquiera de: beneficio medido ≥ 300 propiedades;
  24 h desde el último lote y hay al menos un arreglo validado de valor; una familia bloqueada
  lo justifica; esperar desperdicia más recertificación que aplicar.
- Nunca reiniciar una pasada por arreglos cosméticos o de radio mínimo. Decidir por costo
  esperado de recertificación vs beneficio.

### P5 — Workers
Máximo **3** (nunca más sin nueva política). Adaptativo 1–3: 3 si la medición lo mejora.
Nunca dos workers sobre el mismo host a la vez si sube el riesgo; mismo ritmo por sitio;
no se evaden 403/429. Se miden throughput, paros, 403/429, tiempos y recursos. Si 3 empeora
bloqueo, estabilidad o throughput neto → vuelve a 2. Comparación documentada.

### P6 — Cobertura nacional fuera de `main`
CERTIFICAR ≠ PROMOVER A MAIN ≠ PUBLICAR EN PRODUCCIÓN.
- Fase 1: certificar por identidad canónica las agencias con id canónico, web oficial
  verificada e identidad de confianza alta (~960), sin promoverlas.
- Fase 2: el resto de webs oficiales cuando su identidad quede demostrada.
- Ambigua → IDENTITY_REVIEW. Nunca atribuir inventario por aproximación.

### P7 — Descubrimiento pago de webs
Máximo **USD 10 por mes**. Cada corrida registra proveedor, costo, agencias buscadas y
resultados útiles. Guardrail local que corta la fase paga al llegar al límite.
- Implementación: `scripts/search_provider.py` (`cobrar`, `registrar_corrida`), dentro de
  cada proveedor pago antes de cada pedido HTTP. Costo por consulta DECLARADO en
  `ERETZ_SEARCH_COSTO_USD_<PROVEEDOR>` (sin declarar no se busca); libro
  `ERETZ_SEARCH_SPEND.jsonl` (o `ERETZ_SEARCH_SPEND_LEDGER`); mes calendario de Argentina;
  `ERETZ_SEARCH_TOPE_MENSUAL_USD` solo puede bajar el tope.

## B. Producto y calidad

### P8 — Calidad mínima publicable
Se publica toda propiedad real con identidad válida, URL oficial válida, sin exclusión, no
del exterior y sin evidencia de artefacto/no-propiedad. La falta de precio, fotos,
operación, tipo o ubicación no la elimina; el ranking puede penalizar la completitud y la
interfaz comunica la ausencia. Nunca inventar valores.

### P9 — Propiedades sin título
Título derivado solo con datos reales: «{tipo} en {operación} · {localidad}» o la
combinación parcial disponible. Sin datos suficientes: «Propiedad sin título». Solo web;
mobile congelado.

### P10 — Provincia publicada contradictoria
Si la localidad resuelve inequívocamente, la coordenada cae en el polígono oficial (IGN) de
la provincia de esa localidad, y localidad + coordenada coinciden → prevalecen para la
geografía normalizada. La provincia publicada se conserva como evidencia en conflicto
(«la fuente dijo X, ERETZ normalizó Y, por evidencia Z»). Nunca inferir provincia solo por
el nombre si hay ambigüedad.

### P11 — robots.txt
Se respeta en listados, fichas y endpoints/APIs descubiertos. Prohibido → no se accede y se
registra `ROBOTS_BLOCKED`. No se evade. Es política operativa, no conclusión legal.

### P12 — Bajas en producción
Se activan con la regla de P1, solo después de backup + restore probado:
backup fresco → restore verificado → dry-run → conjunto exacto → rollback preparado.

### P13 — Misma propiedad en varias agencias
Publicaciones independientes; nunca fusionar ids de agencias distintas. «También publicada
por…» es una capa de producto posterior a la beta, no parte del modelo canónico.

### P14 — Revisión legal
Beta privada (acceso protegido + noindex) avanza sin revisión legal externa. Lanzamiento
público/indexable requiere revisión legal previa de lo documentado en
`docs/LEGAL_REVIEW_REQUIRED.md`.

### P15 — Agentes y fotos
Se muestra la agencia; no el nombre personal del agente como dato de ERETZ. Imágenes: se
referencia el origen oficial, no se copian ni re-alojan, se conserva la procedencia; si una
deja de estar disponible no se inventa reemplazo.

### P16 — Criterios de salida
**BETA CLOSED**: (1) snapshot confiable bajo las políticas vigentes; (2) lifecycle básico
correcto (exterior excluido, retiros según P1, duplicados controlados, geo fail-closed);
(3) ventana semántica relevante cerrada; (4) recertificación requerida completa para el
cohorte de beta; (5) Regression Gate de ese cohorte verde; (6) API v2 alojada en un entorno
de beta accesible; (7) Preview conectado al backend correcto; (8) QA de navegador
end-to-end sobre el SHA exacto; (9) 0 P0 conocidos de seguridad o integridad; (10) rollback
de aplicación/snapshot definido. NO requiere cobertura nacional, long tail, indexación,
dominio final ni revisión legal de lanzamiento.

**PRODUCTION READY** agrega: backup real; restore real probado; writer equivalence
demostrada; migraciones preparadas y probadas; RLS/grants endurecidos; lifecycle productivo
preparado; rollback completo probado; observabilidad mínima; seguridad cerrada; revisión
legal para lanzamiento público; estrategia de dominio/DNS; cutover ensayado.
PRODUCTION READY ≠ PRODUCTION DEPLOYED.

## C. Producción e infraestructura

### P17 — Backup y restore
Autorizado instalar solo los clientes oficiales de PostgreSQL (pg_dump, pg_restore, psql).
No se resetea ni rota una contraseña productiva para conseguir acceso: primero una
credencial válida ya disponible, luego una conexión de Supabase sin exponerla, luego una
dedicada/read-only; si hace falta rotar → `EXTERNAL_ACTION_REQUIRED`. Nunca imprimir,
commitear, documentar ni loguear secretos. Con credencial: pg_dump → checksum → conteos →
restore en entorno DESECHABLE → checks → prueba de recuperación. Nunca restore en producción.

### P18 — Rol escritor
Preparar SQL exacto, permisos mínimos, rollback, test y runbook. No crearlo en producción.

### P19 — Writes productivos
Con BACKUP FRESCO + RESTORE VERIFICADO + ROLLBACK PROBADO quedan preautorizadas las clases
estructurales que reducen superficie: migraciones aditivas, endurecimiento de RLS, REVOKE de
permisos innecesarios. Siempre dry-run → diff → rollback → ejecución → validación.
Writes de datos (url_normalizada, promoción, merges, bajas, actualizaciones) por lote con
dry-run fresco y evidencia. Nunca abrir permisos ni ampliar `anon`.

### P20 — Promoción staging → main
Después de backup/restore, por lotes: identidad validada, dry-run, conteos, diff, rollback,
post-check. Primero alta confianza; una dudosa queda fuera sin frenar el lote.

### P21 — API v2 remota para beta
Objetivo ≤ USD 10/mes (Railway, Fly.io o equivalente) con la arquitectura actual (FastAPI +
snapshot SQLite en volumen persistente). Si hace falta cuenta/pago → preparar todo y marcar
`EXTERNAL_ACCOUNT_REQUIRED`.

### P22 — Vercel / QA de Preview
Acceso de mínimo privilegio (token limitado al proyecto o bypass de Preview). Sin acceso:
todo el QA local y `BLOCKED_EXTERNAL_VERCEL_ACCESS`. Con acceso: probar el SHA exacto.

### P23 — Dominio, DNS, indexación
DNS final lo hace el usuario o una acción explícita. Beta en Preview/subdominio técnico,
protegido y noindex. `noindex` solo se retira después de PRODUCTION READY + revisión legal +
decisión explícita. Dominio final: `EXTERNAL_PRODUCT_DECISION`.

### P24 — Integración a `main`
Si el merge a `main` no dispara ninguna acción productiva (deploy, publicación, migración,
integración externa): PR + suite + Regression Gate + checks → merge automático si todo está
verde, sin force push, sin borrar historia, preservando la rama de handoff y con tag de
recuperación. Si puede disparar producción: PR verde y `READY_FOR_MAIN_MERGE`, sin merge.

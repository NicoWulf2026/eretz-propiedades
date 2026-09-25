# ERETZ — handoff para el próximo agente

Leer primero `docs/agent/CURRENT_STATE.md`.

## Reglas que no se negocian

- Máximo 2 workers pesados. Nunca más. Un diagnóstico que corre
  `_procesar_con` con 2–3 fichas por agencia no es un worker; una
  certificación completa sí.
- Nada productivo sin el usuario: ni writes a Supabase, ni migraciones, ni
  RLS/grants, ni deploy, ni DNS, ni restore, ni merge a `main`. Se preparan y
  se anotan en `CURRENT_STATE.md` → «READY_FOR_PRODUCTION_ACTION».
- Push sólo a `handoff/codex-unificacion-2026-09-18`. Sin force push, sin
  `reset --hard`, sin `clean` destructivo.
- Fail-closed: no certificar en falso, no inventar datos ni geografía, no
  mezclar agencias. Una propiedad real incompleta sobrevive.
- Zonaprop/Argenprop (y ningún portal) son fuentes de inventario.

## Cómo tocar código de la huella sin certificar en falso

Los workers corren con `pythonw.exe`, lanzados por `ERETZ_relanzador` desde
`eretz-unified`. Desde `f0556f8dc6` cada worker para entre agencias si
cambió en disco un archivo de `archivos_de_la_huella()`, y un resultado que
se produjo durante el cambio queda sin `strategy_fingerprint`. Entonces:

1. Editar, testear, commitear. Los workers se detienen solos al terminar la
   agencia en curso y el relanzador los levanta con el código nuevo en ≤10 min.
2. Si hubiera un worker ANTERIOR a `f0556f8dc6` (sin guarda), primero pedir
   relanzamiento con una bandera `OPERACION` y esperar a que pare.
3. Agrupar cambios compartidos: cada cambio en `shared/*` invalida todas las
   certificaciones vigentes.

## Trampas de herramienta que ya costaron

- `Path.write_text()` y `sed -i` de Git Bash reescriben los finales de línea
  de un archivo tracked entero. Editar con la herramienta Edit, o leer/escribir
  en binario. Chequear siempre `git diff --numstat` antes de commitear.
- El heredoc de Bash sin comillas se come barras invertidas: usar `<<'EOF'`.
- Un 200 en la ficha no prueba que la propiedad siga publicada: sólo el
  catálogo lo decide.
- Para buscar workers por proceso filtrar por `run_agency_certification_queue`
  en la línea de comandos: corren como `pythonw.exe`.

## Próximas tareas, en orden de impacto medido

0. **Verificar el orden de la cola** (`4f377ad210` rotación + `f742f35255`
   nuevas intercaladas desde el inicio; relanzado 25-09 01:17). Medir: la
   mitad de los resultados deberían ser agencias nunca certificadas, y 0 h en
   agencias repetidas el mismo día. Agrupar cambios de huella.
1. **`NEEDS_FIX` por fichas que no bajan** (30 agencias, 25 con esa única
   razón). Las fallas son las MISMAS en las dos corridas: sistemáticas, no
   pasajeras. Casi todos los resultados son del 21-09, anteriores a los
   arreglos del 23; diagnóstico liviano con el código de hoy en
   `scratchpad/diag_detalles.py`. Separar lo ya arreglado de lo que sigue.
2. **Corridas que no terminan en estado OK** (29) y **cero inventario no
   demostrado** (27): siguientes clases de `NEEDS_FIX` por tamaño.
3. **Regression Gate**: `python scripts/comparar_con_linea_base.py
   --linea-base _regresion/ANTES_DEL_LOTE_2026-09-24.jsonl --desde
   2026-09-24T11:39:00`. Mirar `pendientes_de_revision`; cada pérdida se baja
   de la fuente y se firma en `_regresion/REVISADAS.jsonl` (agencia, url,
   campo, tipo, veredicto, evidencia). Una pérdida que el código de hoy
   produce y el de la línea base no, sobre el MISMO HTML, es regresión real.
4. Ítem 18(b): la operación que sólo existe en la ruta del catálogo
   (`bottai` 180, `constant` 24, `pozzobon` 7). Es un cambio de enumeración
   de `generico`: más riesgoso que su retorno actual.
5. **Guardia de título repetido**: DESCARTADA con medición (25-09). De las 9
   agencias con un título en ≥50 % de sus fichas, la mitad son títulos del
   sitio que `generico` ya resuelve (`0bd66ac5e5`) y el resto incluye títulos
   legítimos repetidos («casa» 7 de 8 en `pozzobon`): vaciarlos sería un
   NEEDS_FIX injusto. Páginas de aterrizaje: resueltas en `generico`
   (`cfd040385a`, `a8f4c13e3e`); queda sólo `fenix` (grilla por JavaScript).
5b. `wordpress` (Houzez): conteos con punto final («1.») no se leen
   (`gustavo teruel`). Radio medido: 1 de 26 agencias `wordpress` (52 fichas
   sondeadas). Bajo retorno; «Si.» NO es un conteo.
5c. **Señal de fuente = extractor** (diseño). Para `operacion`, la señal del
   auditor llama a las mismas funciones que el extractor: lo que el extractor
   no ve, el auditor lo cuenta como «no provisto» y la agencia pasa COMPLETE.
   Así pasaron `altos`, `amadeo`, `caruso`, `emir`; parcheado para la
   etiqueta en `896238f7ae`. El arreglo de fondo es una señal más amplia que
   el extractor (que vea «Venta/Alquiler» rotulados aunque el extractor no
   pueda decidir), aceptando más NEEDS_FIX. Medir antes.
5e'. **Señal de precio con «Consultar»** (auditor, compartido): en `wasi` el
   campo estructurado dice «Precio de alquiler: Consultar» y la descripción
   trae montos (por unidad, alquiler anual). El auditor cuenta el precio como
   provisto y la agencia cae en NEEDS_FIX; dos seguidas dispararon el «corte
   por lote» que detiene TODA la cola (`casamia`, `domus`, 25-09 06:23;
   diferida firmada 06:25). Radio medido: 3 fichas en 3 agencias de 1.326
   fichas wasi (casamia, domus, varesse). Bajo; agrupar con la próxima
   ventana compartida.
5e. Señal de operación sin precio: RESUELTO en `da4df01820`. Quedan para
   la próxima ventana compartida: 5 (título repetido) y re-evaluar
   `ficha_sin_contenido` después del descarte de descripciones.
5d. **Próximo lote de `generico`** — decisión 25-09 08:30: NO aplicar solos;
   cada ítem afecta a UNA agencia y un cambio en `generico` invalida toda la
   familia. Agruparlos con el próximo cambio de `generico` que lo justifique.
   (agrupar; cada cambio de huella cuesta
   recertificaciones). Plantilla de `fios` (diferida firmada 25-09 00:36):
   descripción en `.property-description .show-more` sin rótulo; 7 páginas
   de categoría en singular (`/Casa-en-venta`, título «Casa», precio de la
   grilla) que la regla de plural no alcanza; 1 foto de OTRA propiedad por
   ficha en 192 fichas (IDs de Tokko distintos, fuera de enlaces). Radio
   medido: sólo `fios`. Falla cerrada mientras tanto.
   Listados/categorías como fichas (`bottai`, `conti`, `cannone`, `fios`):
   RESUELTO en `a8f4c13e3e`. Xintel por HTML (`cannone`): RESUELTO en
   `960a148e44`.
   Y `cantale`: la operación es una etiqueta suelta «Venta» junto al tipo
   (`PROP-75947 Vendido / Venta Departamento`), sin «En»; el menú dice lo
   mismo como enlaces. Distinguir etiqueta (span/div) de enlace de menú.
   `elgart` (`CommercialRealEstate`): RESUELTO en `2a63479959`.
5f. **Precio tomado de un monto accesorio** (`generico`, respaldo por texto):
   `caruso` guarda USD 15.000 que es «Opcional: cochera (valor: U$S 15.000)»;
   la ficha no publica precio propio. Muestra de 10 fichas cuyo precio coincide
   con un monto precedido por cochera/expensas/seña/cuota: 8 correctas
   (coincidencias), 1 falsa, 1 ambigua. Riesgo bajo; no se tocó. Si se
   aborda: no tomar como precio un monto precedido por «opcional»/«cochera
   (valor».
5g. Frescura desde NEEDS_FIX: RESUELTO en `609c0f5e82` (sólo la snapshot;
   quality gate e image_contamination siguen con cierres certificados).
   Criterio: identidad READY y TODOS los motivos de campo; campos EXTRACTED
   con valor presente; precio+moneda juntos; sin su `extra`. Medido: 4.678
   filas en 33 agencias, 0 pérdidas. Snapshot además: título = nombre de la
   agencia repetido (`89e69cc75b`, 1.980 filas) y eslogan corto repetido
   (`cbf1f330de`, 898 filas).
5h. **Alinear el runner con la snapshot** (próxima ventana compartida,
   `run_rollout` es huella global): `descartar_descripciones_compartidas`
   exige ≥40 caracteres sin justificación registrada; la snapshot ya no. Hoy
   no muerde con el código vigente (los paquetes de `fdc` y `ciam` extraen
   las descripciones reales); `diaz collins` trae su eslogan en 2 de 12.
5i. `VARIANTE_NO_SOPORTADA` del 25-09 (6 agencias `generico`): SPAs sin
   inventario en el HTML. `armanino`: React que consulta la API de Tokko con
   una clave embebida en su bundle — **decisión: no se usan claves ajenas
   extraídas de un sitio**; queda no soportada. `dacal`: Vue contra su API
   propia (`api.<dominio>/api/v1`), radio 1. `gestionato`: SPA que enlaza a
   portales. `bergo` responde vacío. `diego martin`: Wix. Todas radio 1;
   bajo retorno salvo que aparezca una familia.
6. Ítem 12 (`SIN_INVENTARIO` con dos significados): defecto de nombre, no de
   decisión; bajo retorno.
7. Beta del backend (ver `docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta
   confiable»): cohorte fresca con el HEAD actual —la está produciendo la
   cola—, staging separado, QA de browser, puente histórico de IDs
   (`BLOCKED_EXTERNAL_CREDENTIAL`: necesita datos productivos).

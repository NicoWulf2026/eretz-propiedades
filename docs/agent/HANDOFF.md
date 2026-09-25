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
5. **Guardia de título repetido** (runner, `shared`: próxima ventana
   compartida). Un título idéntico en ≥ la mitad de las fichas de una agencia
   es el del sitio, igual que la descripción. Hoy nada impide que certifique:
   `cortes` era COMPLETE con 23 títulos «Cortes Propiedades» (arreglado en
   `generico`, `0bd66ac5e5`, pero la guardia falta para la próxima plantilla).
   Otras 5 agencias con el mismo patrón ya salen NEEDS_FIX por otra razón.
   Páginas de aterrizaje: las de categoría con grilla (`casablanca`,
   `cbdestino`) ya van a revisión en `generico` (`cfd040385a`). Queda `fenix`
   (3): su grilla se arma con JavaScript (1 enlace visible) y la regla no la
   alcanza. Causa de fondo, compartida: `run_rollout` evalúa
   `ficha_sin_contenido` por ficha (~569/602) ANTES de
   `descartar_descripciones_compartidas` (~621), y el eslogan del sitio cuenta
   como contenido. Re-evaluar después del descarte.
   `floorSize` sigue sin usarse (no dice total o cubierta).
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
5e. **Próximo lote compartido (auditor)**: la señal de `operacion` llama a
   `_operacion_en_la_ficha(texto)` SIN precio, así que el estado consumado
   («OBSERVACIONES: ALQUILADA» en una venta de US$ 400.000) la da por provista y
   la agencia cae en NEEDS_FIX injusto (`arquitectura inmobiliaria`, paro
   25-09 01:44, diferida firmada). Arreglo: pasarle si el texto tiene precio
   (`SOURCE_SIGNALS['precio']`), igual que el extractor. Agrupar con 5 (título
   repetido) y la re-evaluación de `ficha_sin_contenido`.
5d. **Próximo lote de `generico`** (agrupar; cada cambio de huella cuesta
   recertificaciones). Plantilla de `fios` (diferida firmada 25-09 00:36):
   descripción en `.property-description .show-more` sin rótulo; 7 páginas
   de categoría en singular (`/Casa-en-venta`, título «Casa», precio de la
   grilla) que la regla de plural no alcanza; 1 foto de OTRA propiedad por
   ficha en 192 fichas (IDs de Tokko distintos, fuera de enlaces). Radio
   medido: sólo `fios`. Falla cerrada mientras tanto.
   Además `bottai`: páginas de resultados de búsqueda guardadas como fichas
   (`inmuebles_list_Venta_seleccione_…`, título «BOTTAI Inmobiliaria», precio de
   un aviso). La agencia está NEEDS_FIX, pero el dato es falso.
   Y `cantale`: la operación es una etiqueta suelta «Venta» junto al tipo
   (`PROP-75947 Vendido / Venta Departamento`), sin «En»; el menú dice lo
   mismo como enlaces. Distinguir etiqueta (span/div) de enlace de menú.
6. Ítem 12 (`SIN_INVENTARIO` con dos significados): defecto de nombre, no de
   decisión; bajo retorno.
7. Beta del backend (ver `docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta
   confiable»): cohorte fresca con el HEAD actual —la está produciendo la
   cola—, staging separado, QA de browser, puente histórico de IDs
   (`BLOCKED_EXTERNAL_CREDENTIAL`: necesita datos productivos).

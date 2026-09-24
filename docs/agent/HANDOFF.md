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
5. `_de_json_ld`: `numberOfRooms`/`numberOfBedrooms`/`numberOfBathroomsTotal`
   ya se leen (`af8be5820c`); faltan `additionalProperty` (PropertyValue
   «Ambientes»/«Dormitorios», caso `baron`) y `floorSize`. Toca `generico`:
   próxima ventana.
6. Ítem 12 (`SIN_INVENTARIO` con dos significados): defecto de nombre, no de
   decisión; bajo retorno.
7. Beta del backend (ver `docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta
   confiable»): cohorte fresca con el HEAD actual —la está produciendo la
   cola—, staging separado, QA de browser, puente histórico de IDs
   (`BLOCKED_EXTERNAL_CREDENTIAL`: necesita datos productivos).

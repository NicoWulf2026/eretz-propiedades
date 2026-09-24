# ERETZ — handoff para el próximo agente

Leer primero `docs/agent/CURRENT_STATE.md`.

## Reglas que no se negocian

- Máximo 2 workers pesados. Nunca más.
- Nada productivo sin el usuario: ni writes a Supabase, ni migraciones, ni
  RLS/grants, ni deploy, ni DNS, ni restore, ni merge a `main`. Se preparan y
  se anotan en `CURRENT_STATE.md` → «READY_FOR_PRODUCTION_ACTION».
- Push sólo a `handoff/codex-unificacion-2026-09-18`. Sin force push, sin
  `reset --hard`, sin `clean` destructivo.
- Fail-closed: no certificar en falso, no inventar datos ni geografía, no
  mezclar agencias. Una propiedad real incompleta sobrevive.
- Zonaprop/Argenprop no son fuentes de inventario.

## Trampas de herramienta que ya costaron

- `Path.write_text()` y `sed -i` de Git Bash reescriben los finales de línea
  de un archivo tracked entero. Editar con la herramienta Edit, o leer/escribir
  en binario. Chequear siempre `git diff --numstat` antes de commitear.
- El heredoc de Bash sin comillas se come barras invertidas: usar `<<'EOF'`.
- Un 200 en la ficha no prueba que la propiedad siga publicada: sólo el
  catálogo lo decide.

## Próximas tareas, en orden de impacto medido

1. Confirmar que la pasada de `ERETZ_relanzador` de las 11:14 corrió con
   `pythonw` y dejó «arranca pid» + «plan en …» en `relanzador.log`. Si el
   vigilante (`_vigilante.bat`) también muestra muertes silenciosas, darle el
   mismo tratamiento.
2. Mirar el resultado de `alagna propiedades` (w0, recertificando): es el
   canario del arreglo de JSON-LD de `generico`.
3. Ítem 18(b): la operación que sólo existe en la ruta del catálogo
   (`bottai` 180, `constant` 24, `pozzobon` 7). Tokko ya lo resuelve con
   `RUTAS_POR_OPERACION`; `generic/html_catalog` no arrastra la procedencia.
4. Ítem 19: `compare_runs` compara URLs crudas (`www` contra sin `www`);
   `hash_dedup` ya las unifica. Ver `ERETZ_LA_COLA_NO_AVANZA_2026-09-21.md`.
5. `_de_json_ld` lee `dorm`/`banos`/`sup_*` que nunca se escriben: los
   atributos de schema.org (`numberOfRooms`, `floorSize`) no se usan.
6. Semantic Window, Regression Gate, backend beta, production readiness.

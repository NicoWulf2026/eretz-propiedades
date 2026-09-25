# ERETZ — handoff

Para retomar desde una sesión nueva: arrancar Claude Code en `D:\INMO CAPITAL\eretz-unified`.
Reglas: `CLAUDE.md` + `.claude/rules/` (cargan solas). Estado: `docs/agent/CURRENT_STATE.md`.
Historia: Git (versión anterior de este archivo: `git show 6ee927bb80:docs/agent/HANDOFF.md`).

## Recién cerrado (25-09)
- Snapshot: frescura desde NEEDS_FIX por campos (`609c0f5e82`), títulos y eslóganes del sitio
  (`89e69cc75b`, `cbf1f330de`, `b8d1f52eef`). v4d construida y verificada (ver CURRENT_STATE).
- Portales/directorios como web oficial READY: `proppies`, `propia`, `liderprop`, `lujanprop`,
  `aspenbienesraices`, `mercado-unico`, `smartservices.uy`, `365litoralargentino.com`
  (`62dbc899c4`, `eeabc94083`).
- `generico`: fotos del visor como respaldo (`forchino` 0→3/3) y `/cdn-cgi/` nunca es ficha
  (`6ee927bb80`).
- Optimización de Claude Code (ver `docs/agent/CLAUDE_CODE_OPTIMIZATION.md`).

## Corriendo
- Cola con 2 workers + relanzador + vigilante (CURRENT_STATE). No hace falta mirarla salvo paradas.

## No rehacer
- Guardia de título repetido en el runner: descartada con medición (títulos legítimos repetidos).
- `armanino`: su inventario sale de la API de Tokko con una clave embebida en su bundle →
  **no se usan claves ajenas**; queda no soportada.
- `estela d onofrio` «wordpress → SIN_INVENTARIO» en el diagnóstico liviano: el certificador tiene
  respaldo a `generico`; no es defecto.
- Categorías en singular (`fios /Casa-en-venta`): ya cubiertas por `_es_pagina_contenedora`.
- 5h (mínimo de 40 caracteres en `descartar_descripciones_compartidas`): radio 0 en los paquetes
  vigentes; alinear solo en una ventana compartida futura.

## Próxima prioridad (por impacto medido)
1. **NEEDS_FIX por fichas que no bajan / corridas no OK / cero inventario no demostrado** (117
   NEEDS_FIX): clasificar con el código de hoy (el diagnóstico liviano está en el scratchpad de la
   sesión: `_procesar_con` con 3 fichas). Pendientes de `generico` identificados: `benitez` (fotos
   por JS), `cometto` (enumera categorías `propiedades_ver2.php`), `del parque` (`og:type=article`
   en fichas reales), `bunader` (enumera listados), `alianza` (descripción como lista `<ul>` bajo un
   acordeón «Descripción»; diferida firmada 12:00).
2. **Regression Gate** tras cada tanda de recertificaciones (comando en `.claude/rules/scraper.md`).
3. Lote compartido del auditor (una sola ventana): señal de precio «Consultar» en `wasi` (3
   fichas), señal de operación más amplia que el extractor (5c), `ficha_sin_contenido`.
4. `generico` de radio chico (agrupar): `fios` (descripción `.show-more`, foto ajena por ficha),
   `cantale` (etiqueta «Venta» suelta), precio accesorio de `caruso` (5f), operación solo en la
   ruta del catálogo (`bottai` 180, `constant` 24, `pozzobon` 7).
5. Beta del backend (`docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta confiable»): cohorte fresca,
   staging separado, QA de browser; el puente histórico de IDs necesita datos productivos
   (`BLOCKED_EXTERNAL_CREDENTIAL`).

## Trampas actuales
- Un cambio de huella sin commitear lo levantan los workers al relanzarse: commitear enseguida.
- Los paquetes NEEDS_FIX con motivos solo de campo alimentan la snapshot: un cambio de extractor
  cambia lo servido en la próxima construcción.

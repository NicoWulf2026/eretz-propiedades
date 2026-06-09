# Working tree recovery inventory - ETAPA 5A

Fecha: 2026-06-08
Rama: fix/scraping-diagnostics-batch
HEAD esperado: 17465478f fix(geocoding): use agency location context for staging geocoding

## Reglas aplicadas

- No se borro nada.
- No se importo nada.
- No se ejecuto geocoding.
- No se publico Supabase.
- No se toco .env.
- Este reporte solo clasifica el working tree para evitar commits accidentales.

## Resumen

- Entradas git status --porcelain -z -uall: 2734
- docs/obsidian: 22
- reportes utiles: 2317
- scripts auxiliares utiles: 22
- scratch/temp files: 4
- codigo real del scraper/pipeline: 5
- archivos peligrosos/no commiteables: 364

## Interpretacion para commit

- Commit ETAPA 5A permitido: solo reportes/ids generados en `reports/scraping_runs/import_controlado_20260608/`.
- No incluir `docs/obsidian`, scratch en raiz, JSON pesados, `.obsidian`, ni codigo nuevo no relacionado.
- `scraper/faceted_discovery.py` y scripts no underscored parecen codigo real/pipeline, pero no pertenecen a ETAPA 5A.
- Reportes historicos bajo `reports/` pueden ser utiles, pero no se deben mezclar en el commit de esta etapa.

## docs/obsidian

Total: 22

- ` M` `docs/obsidian/00 - General/00 - Panel principal InmoCapital.md` (2213 bytes)
- ` M` `docs/obsidian/00 - General/00 - Índice rápido.md` (1677 bytes)
- ` M` `docs/obsidian/00 - General/13 - Estado actual para ChatGPT o Codex.md` (6603 bytes)
- ` M` `docs/obsidian/01 - Estrategia/01 - Visión y estrategia.md` (4122 bytes)
- ` M` `docs/obsidian/02 - Producto/02 - Producto y funcionalidades.md` (3316 bytes)
- ` M` `docs/obsidian/03 - Desarrollo técnico/03 - Desarrollo técnico.md` (3300 bytes)
- ` M` `docs/obsidian/04 - Base de datos/04 - Supabase y base de datos.md` (4456 bytes)
- ` M` `docs/obsidian/05 - Scraping/05 - Scraping.md` (4321 bytes)
- ` M` `docs/obsidian/06 - Marketing/06 - Marketing y marca.md` (2566 bytes)
- ` M` `docs/obsidian/07 - Finanzas/07 - Finanzas y modelo de negocio.md` (2608 bytes)
- ` M` `docs/obsidian/08 - Legal/08 - Legal y riesgos.md` (2372 bytes)
- ` M` `docs/obsidian/09 - Prompts/09 - Prompts útiles.md` (5713 bytes)
- ` M` `docs/obsidian/10 - Seguimiento/10 - Decisiones importantes.md` (5129 bytes)
- ` M` `docs/obsidian/10 - Seguimiento/11 - Pendientes.md` (4138 bytes)
- ` M` `docs/obsidian/10 - Seguimiento/12 - Errores y soluciones.md` (2661 bytes)
- `??` `docs/obsidian/00 - General/14 - Estado vigente 2026-06-04.md` (7230 bytes)
- `??` `docs/obsidian/03 - Desarrollo técnico/Frontend estado 2026-06-04.md` (1857 bytes)
- `??` `docs/obsidian/04 - Base de datos/Neon readiness 2026-06-04.md` (2225 bytes)
- `??` `docs/obsidian/05 - Scraping/Scraping autofix cierre 2026-06-04.md` (2393 bytes)
- `??` `docs/obsidian/10 - Seguimiento/Politicas de calidad y publicacion.md` (2545 bytes)
- `??` `docs/obsidian/10 - Seguimiento/Roadmap actual 2026-06-04.md` (2639 bytes)
- `??` `docs/obsidian/11 - Registro diario/2026-06-04 - Registro diario.md` (3060 bytes)

## reportes utiles

Total: 2317

| grupo | archivos | tamano aprox bytes |
| --- | ---: | ---: |
| `reports/audits/auditoria_tecnica_inmocapital_20260604_162339.md/` | 1 | 29127 |
| `reports/audits/full_project_audit_20260606_1023/` | 14 | 111613 |
| `reports/scraping_autofix/autofix_resume.md/` | 1 | 1680 |
| `reports/scraping_autofix/batch_20260531_1219/` | 15 | 15071 |
| `reports/scraping_autofix/batch_20260531_1219_after.md/` | 1 | 557 |
| `reports/scraping_autofix/batch_20260531_1219_before.md/` | 1 | 497 |
| `reports/scraping_autofix/batch_20260531_1219_errors.md/` | 1 | 660 |
| `reports/scraping_autofix/batch_20260531_1219_fixed.md/` | 1 | 565 |
| `reports/scraping_autofix/batch_20260531_1219_remaining.md/` | 1 | 681 |
| `reports/scraping_autofix/batch_20260531_1314/` | 8 | 14376 |
| `reports/scraping_autofix/batch_20260531_1314_after.md/` | 1 | 404 |
| `reports/scraping_autofix/batch_20260531_1314_before.md/` | 1 | 353 |
| `reports/scraping_autofix/batch_20260531_1314_errors.md/` | 1 | 424 |
| `reports/scraping_autofix/batch_20260531_1314_fixed.md/` | 1 | 255 |
| `reports/scraping_autofix/batch_20260531_1314_remaining.md/` | 1 | 327 |
| `reports/scraping_autofix/batch_20260531_1341/` | 11 | 24729 |
| `reports/scraping_autofix/batch_20260531_1341_after.md/` | 1 | 447 |
| `reports/scraping_autofix/batch_20260531_1341_before.md/` | 1 | 282 |
| `reports/scraping_autofix/batch_20260531_1341_errors.md/` | 1 | 536 |
| `reports/scraping_autofix/batch_20260531_1341_fixed.md/` | 1 | 244 |
| `reports/scraping_autofix/batch_20260531_1341_remaining.md/` | 1 | 323 |
| `reports/scraping_autofix/batch_20260531_1438/` | 12 | 23828 |
| `reports/scraping_autofix/batch_20260531_1438_after.md/` | 1 | 412 |
| `reports/scraping_autofix/batch_20260531_1438_before.md/` | 1 | 272 |
| `reports/scraping_autofix/batch_20260531_1438_errors.md/` | 1 | 479 |
| `reports/scraping_autofix/batch_20260531_1438_fixed.md/` | 1 | 257 |
| `reports/scraping_autofix/batch_20260531_1438_remaining.md/` | 1 | 284 |
| `reports/scraping_autofix/batch_20260531_1556/` | 12 | 25045 |
| `reports/scraping_autofix/batch_20260531_1556_after.md/` | 1 | 406 |
| `reports/scraping_autofix/batch_20260531_1556_before.md/` | 1 | 179 |
| `reports/scraping_autofix/batch_20260531_1556_errors.md/` | 1 | 14221 |
| `reports/scraping_autofix/batch_20260531_1556_fixed.md/` | 1 | 2729 |
| `reports/scraping_autofix/batch_20260531_1556_remaining.md/` | 1 | 290 |
| `reports/scraping_autofix/batch_20260531_1719/` | 14 | 25962 |
| `reports/scraping_autofix/batch_20260531_1719_after.md/` | 1 | 490 |
| `reports/scraping_autofix/batch_20260531_1719_before.md/` | 1 | 300 |
| `reports/scraping_autofix/batch_20260531_1719_errors.md/` | 1 | 13343 |
| `reports/scraping_autofix/batch_20260531_1719_fixed.md/` | 1 | 2901 |
| `reports/scraping_autofix/batch_20260531_1719_remaining.md/` | 1 | 374 |
| `reports/scraping_autofix/batch_20260531_1849/` | 9 | 6786 |
| `reports/scraping_autofix/batch_20260531_1849_after.md/` | 1 | 487 |
| `reports/scraping_autofix/batch_20260531_1849_before.md/` | 1 | 284 |
| `reports/scraping_autofix/batch_20260531_1849_errors.md/` | 1 | 14108 |
| `reports/scraping_autofix/batch_20260531_1849_fixed.md/` | 1 | 2183 |
| `reports/scraping_autofix/batch_20260531_1849_remaining.md/` | 1 | 371 |
| `reports/scraping_autofix/batch_20260531_2021/` | 3 | 3924 |
| `reports/scraping_autofix/batch_20260531_2057/` | 26 | 30847 |
| `reports/scraping_autofix/batch_20260531_2057_after.md/` | 1 | 454 |
| `reports/scraping_autofix/batch_20260531_2057_before.md/` | 1 | 228 |
| `reports/scraping_autofix/batch_20260531_2057_errors.md/` | 1 | 9325 |
| `reports/scraping_autofix/batch_20260531_2057_fixed.md/` | 1 | 5332 |
| `reports/scraping_autofix/batch_20260531_2057_remaining.md/` | 1 | 333 |
| `reports/scraping_autofix/batch_20260531_2332/` | 12 | 18598 |
| `reports/scraping_autofix/batch_20260531_2332_after.md/` | 1 | 449 |
| `reports/scraping_autofix/batch_20260531_2332_before.md/` | 1 | 583 |
| `reports/scraping_autofix/batch_20260531_2332_errors.md/` | 1 | 386 |
| `reports/scraping_autofix/batch_20260531_2332_fixed.md/` | 1 | 303 |
| `reports/scraping_autofix/batch_20260531_2332_remaining.md/` | 1 | 525 |
| `reports/scraping_autofix/batch_20260601_0048/` | 45 | 48532 |
| `reports/scraping_autofix/batch_20260601_0048_after.md/` | 1 | 276 |
| `reports/scraping_autofix/batch_20260601_0048_before.md/` | 1 | 499 |
| `reports/scraping_autofix/batch_20260601_0048_errors.md/` | 1 | 320 |
| `reports/scraping_autofix/batch_20260601_0048_fixed.md/` | 1 | 254 |
| `reports/scraping_autofix/batch_20260601_0048_remaining.md/` | 1 | 388 |
| `reports/scraping_autofix/batch_20260601_0712/` | 50 | 44728 |
| `reports/scraping_autofix/batch_20260601_0712_after.md/` | 1 | 543 |
| `reports/scraping_autofix/batch_20260601_0712_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_0712_errors.md/` | 1 | 188 |
| `reports/scraping_autofix/batch_20260601_0712_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_0712_remaining.md/` | 1 | 265 |
| `reports/scraping_autofix/batch_20260601_1008/` | 13 | 22393 |
| `reports/scraping_autofix/batch_20260601_1008_after.md/` | 1 | 528 |
| `reports/scraping_autofix/batch_20260601_1008_before.md/` | 1 | 247 |
| `reports/scraping_autofix/batch_20260601_1008_errors.md/` | 1 | 256 |
| `reports/scraping_autofix/batch_20260601_1008_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_1008_remaining.md/` | 1 | 333 |
| `reports/scraping_autofix/batch_20260601_1152/` | 35 | 36907 |
| `reports/scraping_autofix/batch_20260601_1152_after.md/` | 1 | 541 |
| `reports/scraping_autofix/batch_20260601_1152_before.md/` | 1 | 247 |
| `reports/scraping_autofix/batch_20260601_1152_errors.md/` | 1 | 62 |
| `reports/scraping_autofix/batch_20260601_1152_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_1152_remaining.md/` | 1 | 142 |
| `reports/scraping_autofix/batch_20260601_1718/` | 18 | 18718 |
| `reports/scraping_autofix/batch_20260601_1718_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260601_1718_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_1718_errors.md/` | 1 | 101 |
| `reports/scraping_autofix/batch_20260601_1718_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_1718_remaining.md/` | 1 | 181 |
| `reports/scraping_autofix/batch_20260601_1944/` | 11 | 10471 |
| `reports/scraping_autofix/batch_20260601_1944_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260601_1944_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_1944_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260601_1944_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_1944_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260601_2103/` | 12 | 11334 |
| `reports/scraping_autofix/batch_20260601_2103_after.md/` | 1 | 538 |
| `reports/scraping_autofix/batch_20260601_2103_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_2103_errors.md/` | 1 | 42 |
| `reports/scraping_autofix/batch_20260601_2103_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_2103_remaining.md/` | 1 | 122 |
| `reports/scraping_autofix/batch_20260601_2227/` | 9 | 8810 |
| `reports/scraping_autofix/batch_20260601_2227_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260601_2227_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_2227_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260601_2227_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_2227_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260601_2326/` | 14 | 12645 |
| `reports/scraping_autofix/batch_20260601_2326_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260601_2326_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260601_2326_errors.md/` | 1 | 42 |
| `reports/scraping_autofix/batch_20260601_2326_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260601_2326_remaining.md/` | 1 | 122 |
| `reports/scraping_autofix/batch_20260602_0124/` | 11 | 10464 |
| `reports/scraping_autofix/batch_20260602_0124_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_0124_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0124_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260602_0124_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0124_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260602_0229/` | 11 | 10278 |
| `reports/scraping_autofix/batch_20260602_0229_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_0229_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0229_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260602_0229_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0229_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260602_0334/` | 13 | 11893 |
| `reports/scraping_autofix/batch_20260602_0334_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_0334_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0334_errors.md/` | 1 | 76 |
| `reports/scraping_autofix/batch_20260602_0334_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0334_remaining.md/` | 1 | 156 |
| `reports/scraping_autofix/batch_20260602_0447/` | 23 | 20070 |
| `reports/scraping_autofix/batch_20260602_0447_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_0447_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0447_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260602_0447_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0447_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260602_0622/` | 51 | 38868 |
| `reports/scraping_autofix/batch_20260602_0622_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_0622_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0622_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260602_0622_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0622_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260602_0759/` | 47 | 35726 |
| `reports/scraping_autofix/batch_20260602_0759_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_0759_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0759_errors.md/` | 1 | 91 |
| `reports/scraping_autofix/batch_20260602_0759_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0759_remaining.md/` | 1 | 171 |
| `reports/scraping_autofix/batch_20260602_0927/` | 44 | 33436 |
| `reports/scraping_autofix/batch_20260602_0927_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_0927_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_0927_errors.md/` | 1 | 68 |
| `reports/scraping_autofix/batch_20260602_0927_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_0927_remaining.md/` | 1 | 148 |
| `reports/scraping_autofix/batch_20260602_1054/` | 10 | 9681 |
| `reports/scraping_autofix/batch_20260602_1054_after.md/` | 1 | 535 |
| `reports/scraping_autofix/batch_20260602_1054_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1054_errors.md/` | 1 | 75 |
| `reports/scraping_autofix/batch_20260602_1054_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1054_remaining.md/` | 1 | 155 |
| `reports/scraping_autofix/batch_20260602_1141/` | 24 | 19683 |
| `reports/scraping_autofix/batch_20260602_1141_after.md/` | 1 | 537 |
| `reports/scraping_autofix/batch_20260602_1141_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1141_errors.md/` | 1 | 76 |
| `reports/scraping_autofix/batch_20260602_1141_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1141_remaining.md/` | 1 | 156 |
| `reports/scraping_autofix/batch_20260602_1247/` | 34 | 26819 |
| `reports/scraping_autofix/batch_20260602_1247_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_1247_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1247_errors.md/` | 1 | 75 |
| `reports/scraping_autofix/batch_20260602_1247_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1247_remaining.md/` | 1 | 155 |
| `reports/scraping_autofix/batch_20260602_1403/` | 45 | 34164 |
| `reports/scraping_autofix/batch_20260602_1403_after.md/` | 1 | 538 |
| `reports/scraping_autofix/batch_20260602_1403_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1403_errors.md/` | 1 | 64 |
| `reports/scraping_autofix/batch_20260602_1403_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1403_remaining.md/` | 1 | 144 |
| `reports/scraping_autofix/batch_20260602_1533/` | 28 | 22269 |
| `reports/scraping_autofix/batch_20260602_1533_after.md/` | 1 | 537 |
| `reports/scraping_autofix/batch_20260602_1533_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1533_errors.md/` | 1 | 101 |
| `reports/scraping_autofix/batch_20260602_1533_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1533_remaining.md/` | 1 | 181 |
| `reports/scraping_autofix/batch_20260602_1639/` | 38 | 29285 |
| `reports/scraping_autofix/batch_20260602_1639_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_1639_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1639_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260602_1639_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1639_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260602_1753/` | 32 | 25354 |
| `reports/scraping_autofix/batch_20260602_1753_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260602_1753_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1753_errors.md/` | 1 | 119 |
| `reports/scraping_autofix/batch_20260602_1753_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1753_remaining.md/` | 1 | 199 |
| `reports/scraping_autofix/batch_20260602_1856/` | 34 | 26967 |
| `reports/scraping_autofix/batch_20260602_1856_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_1856_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_1856_errors.md/` | 1 | 42 |
| `reports/scraping_autofix/batch_20260602_1856_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_1856_remaining.md/` | 1 | 122 |
| `reports/scraping_autofix/batch_20260602_2003/` | 40 | 30426 |
| `reports/scraping_autofix/batch_20260602_2003_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_2003_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_2003_errors.md/` | 1 | 97 |
| `reports/scraping_autofix/batch_20260602_2003_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_2003_remaining.md/` | 1 | 177 |
| `reports/scraping_autofix/batch_20260602_2123/` | 22 | 18445 |
| `reports/scraping_autofix/batch_20260602_2123_after.md/` | 1 | 536 |
| `reports/scraping_autofix/batch_20260602_2123_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_2123_errors.md/` | 1 | 75 |
| `reports/scraping_autofix/batch_20260602_2123_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_2123_remaining.md/` | 1 | 155 |
| `reports/scraping_autofix/batch_20260602_2219/` | 38 | 29390 |
| `reports/scraping_autofix/batch_20260602_2219_after.md/` | 1 | 538 |
| `reports/scraping_autofix/batch_20260602_2219_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_2219_errors.md/` | 1 | 125 |
| `reports/scraping_autofix/batch_20260602_2219_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_2219_remaining.md/` | 1 | 205 |
| `reports/scraping_autofix/batch_20260602_2333/` | 38 | 29772 |
| `reports/scraping_autofix/batch_20260602_2333_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260602_2333_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260602_2333_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260602_2333_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260602_2333_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260603_0100/` | 36 | 28120 |
| `reports/scraping_autofix/batch_20260603_0100_after.md/` | 1 | 538 |
| `reports/scraping_autofix/batch_20260603_0100_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0100_errors.md/` | 1 | 68 |
| `reports/scraping_autofix/batch_20260603_0100_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0100_remaining.md/` | 1 | 148 |
| `reports/scraping_autofix/batch_20260603_0208/` | 38 | 29935 |
| `reports/scraping_autofix/batch_20260603_0208_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260603_0208_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0208_errors.md/` | 1 | 95 |
| `reports/scraping_autofix/batch_20260603_0208_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0208_remaining.md/` | 1 | 175 |
| `reports/scraping_autofix/batch_20260603_0334/` | 29 | 23265 |
| `reports/scraping_autofix/batch_20260603_0334_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260603_0334_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0334_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260603_0334_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0334_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260603_0436/` | 52 | 39054 |
| `reports/scraping_autofix/batch_20260603_0436_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260603_0436_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0436_errors.md/` | 1 | 64 |
| `reports/scraping_autofix/batch_20260603_0436_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0436_remaining.md/` | 1 | 144 |
| `reports/scraping_autofix/batch_20260603_0605/` | 41 | 30924 |
| `reports/scraping_autofix/batch_20260603_0605_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260603_0605_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0605_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260603_0605_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0605_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260603_0714/` | 47 | 35918 |
| `reports/scraping_autofix/batch_20260603_0714_after.md/` | 1 | 539 |
| `reports/scraping_autofix/batch_20260603_0714_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0714_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260603_0714_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0714_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260603_0828/` | 49 | 37380 |
| `reports/scraping_autofix/batch_20260603_0828_after.md/` | 1 | 540 |
| `reports/scraping_autofix/batch_20260603_0828_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0828_errors.md/` | 1 | 82 |
| `reports/scraping_autofix/batch_20260603_0828_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0828_remaining.md/` | 1 | 162 |
| `reports/scraping_autofix/batch_20260603_0943/` | 31 | 21247 |
| `reports/scraping_autofix/batch_20260603_0943_after.md/` | 1 | 534 |
| `reports/scraping_autofix/batch_20260603_0943_before.md/` | 1 | 249 |
| `reports/scraping_autofix/batch_20260603_0943_errors.md/` | 1 | 41 |
| `reports/scraping_autofix/batch_20260603_0943_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_0943_remaining.md/` | 1 | 118 |
| `reports/scraping_autofix/batch_20260603_1125/` | 17 | 14650 |
| `reports/scraping_autofix/batch_20260603_1125_after.md/` | 1 | 546 |
| `reports/scraping_autofix/batch_20260603_1125_before.md/` | 1 | 259 |
| `reports/scraping_autofix/batch_20260603_1125_errors.md/` | 1 | 101 |
| `reports/scraping_autofix/batch_20260603_1125_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1125_remaining.md/` | 1 | 181 |
| `reports/scraping_autofix/batch_20260603_1157/` | 20 | 16865 |
| `reports/scraping_autofix/batch_20260603_1157_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_1157_before.md/` | 1 | 260 |
| `reports/scraping_autofix/batch_20260603_1157_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260603_1157_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1157_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260603_1235/` | 17 | 14688 |
| `reports/scraping_autofix/batch_20260603_1235_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_1235_before.md/` | 1 | 260 |
| `reports/scraping_autofix/batch_20260603_1235_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260603_1235_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1235_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260603_1316/` | 23 | 18621 |
| `reports/scraping_autofix/batch_20260603_1316_after.md/` | 1 | 546 |
| `reports/scraping_autofix/batch_20260603_1316_before.md/` | 1 | 260 |
| `reports/scraping_autofix/batch_20260603_1316_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260603_1316_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1316_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260603_1400/` | 21 | 17741 |
| `reports/scraping_autofix/batch_20260603_1400_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_1400_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1400_errors.md/` | 1 | 168 |
| `reports/scraping_autofix/batch_20260603_1400_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1400_remaining.md/` | 1 | 248 |
| `reports/scraping_autofix/batch_20260603_1443/` | 12 | 11535 |
| `reports/scraping_autofix/batch_20260603_1443_after.md/` | 1 | 549 |
| `reports/scraping_autofix/batch_20260603_1443_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1443_errors.md/` | 1 | 148 |
| `reports/scraping_autofix/batch_20260603_1443_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1443_remaining.md/` | 1 | 228 |
| `reports/scraping_autofix/batch_20260603_1516/` | 17 | 15060 |
| `reports/scraping_autofix/batch_20260603_1516_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_1516_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1516_errors.md/` | 1 | 115 |
| `reports/scraping_autofix/batch_20260603_1516_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1516_remaining.md/` | 1 | 195 |
| `reports/scraping_autofix/batch_20260603_1556/` | 18 | 15653 |
| `reports/scraping_autofix/batch_20260603_1556_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_1556_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1556_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260603_1556_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1556_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260603_1636/` | 19 | 16415 |
| `reports/scraping_autofix/batch_20260603_1636_after.md/` | 1 | 549 |
| `reports/scraping_autofix/batch_20260603_1636_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1636_errors.md/` | 1 | 97 |
| `reports/scraping_autofix/batch_20260603_1636_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1636_remaining.md/` | 1 | 177 |
| `reports/scraping_autofix/batch_20260603_1713/` | 30 | 23249 |
| `reports/scraping_autofix/batch_20260603_1713_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_1713_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1713_errors.md/` | 1 | 102 |
| `reports/scraping_autofix/batch_20260603_1713_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1713_remaining.md/` | 1 | 182 |
| `reports/scraping_autofix/batch_20260603_1755/` | 35 | 26187 |
| `reports/scraping_autofix/batch_20260603_1755_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_1755_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1755_errors.md/` | 1 | 61 |
| `reports/scraping_autofix/batch_20260603_1755_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1755_remaining.md/` | 1 | 141 |
| `reports/scraping_autofix/batch_20260603_1846/` | 24 | 19447 |
| `reports/scraping_autofix/batch_20260603_1846_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_1846_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1846_errors.md/` | 1 | 87 |
| `reports/scraping_autofix/batch_20260603_1846_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1846_remaining.md/` | 1 | 167 |
| `reports/scraping_autofix/batch_20260603_1935/` | 21 | 17356 |
| `reports/scraping_autofix/batch_20260603_1935_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_1935_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_1935_errors.md/` | 1 | 90 |
| `reports/scraping_autofix/batch_20260603_1935_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_1935_remaining.md/` | 1 | 170 |
| `reports/scraping_autofix/batch_20260603_2019/` | 18 | 15025 |
| `reports/scraping_autofix/batch_20260603_2019_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_2019_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2019_errors.md/` | 1 | 75 |
| `reports/scraping_autofix/batch_20260603_2019_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2019_remaining.md/` | 1 | 155 |
| `reports/scraping_autofix/batch_20260603_2103/` | 18 | 15106 |
| `reports/scraping_autofix/batch_20260603_2103_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_2103_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2103_errors.md/` | 1 | 83 |
| `reports/scraping_autofix/batch_20260603_2103_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2103_remaining.md/` | 1 | 163 |
| `reports/scraping_autofix/batch_20260603_2142/` | 21 | 17563 |
| `reports/scraping_autofix/batch_20260603_2142_after.md/` | 1 | 548 |
| `reports/scraping_autofix/batch_20260603_2142_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2142_errors.md/` | 1 | 96 |
| `reports/scraping_autofix/batch_20260603_2142_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2142_remaining.md/` | 1 | 176 |
| `reports/scraping_autofix/batch_20260603_2223/` | 14 | 12633 |
| `reports/scraping_autofix/batch_20260603_2223_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_2223_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2223_errors.md/` | 1 | 90 |
| `reports/scraping_autofix/batch_20260603_2223_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2223_remaining.md/` | 1 | 170 |
| `reports/scraping_autofix/batch_20260603_2249/` | 15 | 13551 |
| `reports/scraping_autofix/batch_20260603_2249_after.md/` | 1 | 549 |
| `reports/scraping_autofix/batch_20260603_2249_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2249_errors.md/` | 1 | 153 |
| `reports/scraping_autofix/batch_20260603_2249_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2249_remaining.md/` | 1 | 233 |
| `reports/scraping_autofix/batch_20260603_2322/` | 12 | 8617 |
| `reports/scraping_autofix/batch_20260603_2322_after.md/` | 1 | 547 |
| `reports/scraping_autofix/batch_20260603_2322_before.md/` | 1 | 261 |
| `reports/scraping_autofix/batch_20260603_2322_errors.md/` | 1 | 41 |
| `reports/scraping_autofix/batch_20260603_2322_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260603_2322_remaining.md/` | 1 | 118 |
| `reports/scraping_autofix/batch_20260604_0917/` | 1 | 2910 |
| `reports/scraping_autofix/batch_20260604_1055/` | 44 | 32688 |
| `reports/scraping_autofix/batch_20260604_1055_after.md/` | 1 | 505 |
| `reports/scraping_autofix/batch_20260604_1055_before.md/` | 1 | 223 |
| `reports/scraping_autofix/batch_20260604_1055_errors.md/` | 1 | 41 |
| `reports/scraping_autofix/batch_20260604_1055_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260604_1055_remaining.md/` | 1 | 121 |
| `reports/scraping_autofix/batch_20260604_1131/` | 8 | 9661 |
| `reports/scraping_autofix/batch_20260604_1131_after.md/` | 1 | 504 |
| `reports/scraping_autofix/batch_20260604_1131_before.md/` | 1 | 223 |
| `reports/scraping_autofix/batch_20260604_1131_errors.md/` | 1 | 131 |
| `reports/scraping_autofix/batch_20260604_1131_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260604_1131_remaining.md/` | 1 | 211 |
| `reports/scraping_autofix/batch_20260604_1154/` | 1 | 1852 |
| `reports/scraping_autofix/batch_20260604_1154_after.md/` | 1 | 630 |
| `reports/scraping_autofix/batch_20260604_1154_before.md/` | 1 | 224 |
| `reports/scraping_autofix/batch_20260604_1154_errors.md/` | 1 | 124 |
| `reports/scraping_autofix/batch_20260604_1154_fixed.md/` | 1 | 131 |
| `reports/scraping_autofix/batch_20260604_1154_remaining.md/` | 1 | 201 |
| `reports/scraping_autofix/batch_20260604_1446/` | 5 | 9340 |
| `reports/scraping_autofix/batch_20260604_1446_after.md/` | 1 | 505 |
| `reports/scraping_autofix/batch_20260604_1446_before.md/` | 1 | 224 |
| `reports/scraping_autofix/batch_20260604_1446_errors.md/` | 1 | 189 |
| `reports/scraping_autofix/batch_20260604_1446_fixed.md/` | 1 | 165 |
| `reports/scraping_autofix/batch_20260604_1446_remaining.md/` | 1 | 269 |
| `reports/scraping_autofix/batch_20260604_1702/` | 1 | 1827 |
| `reports/scraping_autofix/batch_20260604_1713/` | 1 | 12423 |
| `reports/scraping_autofix/batch_20260604_1915/` | 1 | 23557 |
| `reports/scraping_autofix/batch_20260604_1943/` | 1 | 22881 |
| `reports/scraping_autofix/batch_20260604_2020/` | 1 | 23253 |
| `reports/scraping_autofix/batch_20260604_2101/` | 1 | 23932 |
| `reports/scraping_autofix/batch_20260604_2138/` | 1 | 22388 |
| `reports/scraping_autofix/batch_20260604_2236/` | 1 | 20997 |
| `reports/scraping_autofix/batch_20260604_2341/` | 1 | 19936 |
| `reports/scraping_autofix/batch_20260605_0925/` | 1 | 1965 |
| `reports/scraping_autofix/batch_20260605_0932/` | 1 | 4788 |
| `reports/scraping_autofix/batch_20260605_1019/` | 1 | 47218 |
| `reports/scraping_autofix/batch_20260605_1656/` | 1 | 1247 |
| `reports/scraping_autofix/batch_20260605_1716/` | 1 | 9135 |
| `reports/scraping_autofix/batch_20260605_1857/` | 1 | 3730 |
| `reports/scraping_autofix/batch_20260605_1914/` | 1 | 1126 |
| `reports/scraping_autofix/batch_20260605_1919/` | 1 | 2124 |
| `reports/scraping_autofix/batch_20260605_1932/` | 1 | 975 |
| `reports/scraping_autofix/batch_20260605_1938/` | 1 | 1826 |
| `reports/scraping_autofix/batch_20260605_1959/` | 1 | 1572 |
| `reports/scraping_autofix/batch_20260605_2002/` | 1 | 18680 |
| `reports/scraping_autofix/batch_20260606_0956/` | 1 | 1334 |
| `reports/scraping_autofix/batch_20260606_0959/` | 1 | 1105 |
| `reports/scraping_autofix/batch_20260606_1129/` | 1 | 3080 |
| `reports/scraping_autofix/batch_20260606_1137/` | 1 | 1403 |
| `reports/scraping_autofix/batch_20260606_2235/` | 1 | 968 |
| `reports/scraping_autofix/batch_20260606_2245/` | 1 | 775 |
| `reports/scraping_autofix/batch_20260607_0527/` | 1 | 1335 |
| `reports/scraping_autofix/batch_20260607_0550/` | 1 | 893 |
| `reports/scraping_autofix/batch_20260607_0556/` | 1 | 896 |
| `reports/scraping_autofix/batch_20260608_1953/` | 1 | 1987 |
| `reports/scraping_autofix/batch_20260608_2003/` | 1 | 953 |
| `reports/scraping_autofix/batch_final_retest.out/` | 1 | 1409 |
| `reports/scraping_autofix/batch_fix1b.out/` | 1 | 1679 |
| `reports/scraping_autofix/batch_run1.out/` | 1 | 5685 |
| `reports/scraping_autofix/before_after_fix2_fix1b.md/` | 1 | 6874 |
| `reports/scraping_autofix/before_after_no_property_links_20260529.md/` | 1 | 2903 |
| `reports/scraping_autofix/before_after_remaining_families_20260529.md/` | 1 | 3717 |
| `reports/scraping_autofix/before_after_requires_playwright_20260529.md/` | 1 | 2156 |
| `reports/scraping_autofix/before_after_sin_propiedades_20260529.md/` | 1 | 2872 |
| `reports/scraping_autofix/before_after_timeout_20260529.md/` | 1 | 4083 |
| `reports/scraping_autofix/final_after_vnext_pending_validate_drain_01.md/` | 1 | 590 |
| `reports/scraping_autofix/final_batch_20260601_0951.md/` | 1 | 345 |
| `reports/scraping_autofix/final_pending_correctable_20260601_1149.md/` | 1 | 1096 |
| `reports/scraping_autofix/final_vnext_20260603_1125.md/` | 1 | 1149 |
| `reports/scraping_autofix/final_vnext_geocode_drain_01.md/` | 1 | 760 |
| `reports/scraping_autofix/final_vnext_geocode_drain_02.md/` | 1 | 760 |
| `reports/scraping_autofix/final_vnext_geocode_drain_03.md/` | 1 | 760 |
| `reports/scraping_autofix/final_vnext_geocode_drain_04.md/` | 1 | 763 |
| `reports/scraping_autofix/final_vnext_geocode_drain_05.md/` | 1 | 760 |
| `reports/scraping_autofix/final_vnext_validate_drain_01.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_02.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_03.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_04.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_05.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_06.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_07.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_08.md/` | 1 | 606 |
| `reports/scraping_autofix/final_vnext_validate_drain_09.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_10.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_11.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_12.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_13.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_14.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_15.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_16.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_17.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_18.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_19.md/` | 1 | 608 |
| `reports/scraping_autofix/final_vnext_validate_drain_20.md/` | 1 | 629 |
| `reports/scraping_autofix/final_vnext_validate_drain_21.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_22.md/` | 1 | 596 |
| `reports/scraping_autofix/final_vnext_validate_drain_23.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_24.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_25.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_26.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_27.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_28.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_29.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_30.md/` | 1 | 636 |
| `reports/scraping_autofix/final_vnext_validate_drain_31.md/` | 1 | 610 |
| `reports/scraping_autofix/final_vnext_validate_drain_32.md/` | 1 | 593 |
| `reports/scraping_autofix/final_vnext_validate_drain_33.md/` | 1 | 590 |
| `reports/scraping_autofix/fix1a_remax/` | 1 | 4400 |
| `reports/scraping_autofix/geocode_imported_staging_20260531_1205.md/` | 1 | 801 |
| `reports/scraping_autofix/geocode_imported_staging_20260531_1206.md/` | 1 | 779 |
| `reports/scraping_autofix/geocode_imported_staging_20260531_1208.md/` | 1 | 748 |
| `reports/scraping_autofix/geocode_imported_staging_20260605_1458.md/` | 1 | 828 |
| `reports/scraping_autofix/geocode_imported_staging_20260605_1459.md/` | 1 | 771 |
| `reports/scraping_autofix/geocode_imported_staging_20260606_1757.md/` | 1 | 758 |
| `reports/scraping_autofix/geocode_imported_staging_20260607_1444.md/` | 1 | 806 |
| `reports/scraping_autofix/geocode_imported_staging_20260607_1448.md/` | 1 | 828 |
| `reports/scraping_autofix/geocode_imported_staging_20260607_1550.md/` | 1 | 831 |
| `reports/scraping_autofix/geocode_imported_staging_20260607_2237.md/` | 1 | 763 |
| `reports/scraping_autofix/geocode_imported_staging_20260608_2049.md/` | 1 | 759 |
| `reports/scraping_autofix/geocode_imported_staging_verify_after_commit.md/` | 1 | 726 |
| `reports/scraping_autofix/geocode_quality_root_fix_dryrun_20260604_1004.md/` | 1 | 798 |
| `reports/scraping_autofix/global_audit_20260601_1001.md/` | 1 | 14087 |
| `reports/scraping_autofix/global_audit_20260601_1004.md/` | 1 | 14409 |
| `reports/scraping_autofix/global_audit_after_pending2_20260603_2340.md/` | 1 | 3313 |
| `reports/scraping_autofix/global_audit_after_pending_20260601_1151.md/` | 1 | 5703 |
| `reports/scraping_autofix/global_audit_after_vnext_20260603_1125.md/` | 1 | 6988 |
| `reports/scraping_autofix/global_final_report_20260601_0951.md/` | 1 | 485 |
| `reports/scraping_autofix/global_final_report_20260603_2340.md/` | 1 | 892 |
| `reports/scraping_autofix/import_captured_20260531_1141.md/` | 1 | 865 |
| `reports/scraping_autofix/import_captured_20260531_1142.md/` | 1 | 903 |
| `reports/scraping_autofix/import_captured_20260531_1145.md/` | 1 | 880 |
| `reports/scraping_autofix/import_captured_20260605_1332.md/` | 1 | 1897 |
| `reports/scraping_autofix/import_captured_20260605_1336.md/` | 1 | 1900 |
| `reports/scraping_autofix/import_captured_20260605_1341.md/` | 1 | 1890 |
| `reports/scraping_autofix/import_captured_20260606_24_extractor_fix.md/` | 1 | 1680 |
| `reports/scraping_autofix/import_captured_20260607_0624.md/` | 1 | 1736 |
| `reports/scraping_autofix/import_captured_20260608_2014.md/` | 1 | 1645 |
| `reports/scraping_autofix/import_captured_check_after_fix.md/` | 1 | 865 |
| `reports/scraping_autofix/import_captured_check_after_timeout.md/` | 1 | 865 |
| `reports/scraping_autofix/import_captured_verify_after_commit.md/` | 1 | 937 |
| `reports/scraping_autofix/import_quality_root_fix_remax_after_20260604_1004.md/` | 1 | 805 |
| `reports/scraping_autofix/import_quality_root_fix_retest_20260604_0917.md/` | 1 | 1058 |
| `reports/scraping_autofix/master_progress.md/` | 1 | 873140 |
| `reports/scraping_autofix/properties_readiness_audit_20260604_0853.md/` | 1 | 5990 |
| `reports/scraping_autofix/scraping_quality_root_fix_20260604_1010.md/` | 1 | 7660 |
| `reports/scraping_autofix/status_20260529_1503.md/` | 1 | 2994 |
| `reports/scraping_autofix/status_20260529_1511.md/` | 1 | 3937 |
| `reports/scraping_autofix/status_20260529_1528.md/` | 1 | 2832 |
| `reports/scraping_autofix/status_20260529_1626.md/` | 1 | 1757 |
| `reports/scraping_autofix/status_20260529_1805.md/` | 1 | 3926 |
| `reports/scraping_autofix/status_20260529_2025.md/` | 1 | 3406 |
| `reports/scraping_autofix/status_20260529_2055.md/` | 1 | 4509 |
| `reports/scraping_autofix/status_20260529_2115.md/` | 1 | 5205 |
| `reports/scraping_autofix/status_20260529_2145.md/` | 1 | 5187 |
| `reports/scraping_autofix/status_20260530_1836.md/` | 1 | 6876 |
| `reports/scraping_autofix/status_20260531_1309.md/` | 1 | 1866 |
| `reports/scraping_autofix/status_20260531_1340.md/` | 1 | 1496 |
| `reports/scraping_autofix/status_20260531_1440.md/` | 1 | 1319 |
| `reports/scraping_autofix/status_20260531_1556.md/` | 1 | 1322 |
| `reports/scraping_autofix/status_20260531_1722.md/` | 1 | 1544 |
| `reports/scraping_autofix/status_20260531_2005.md/` | 1 | 1402 |
| `reports/scraping_autofix/status_20260531_2042.md/` | 1 | 1804 |
| `reports/scraping_autofix/status_20260531_2312.md/` | 1 | 1479 |
| `reports/scraping_autofix/status_20260601_0046.md/` | 1 | 2331 |
| `reports/scraping_autofix/status_20260601_0712.md/` | 1 | 2073 |
| `reports/scraping_autofix/status_20260601_0949.md/` | 1 | 812 |
| `reports/scraping_autofix/status_20260601_1124.md/` | 1 | 865 |
| `reports/scraping_autofix/status_20260601_1717.md/` | 1 | 687 |
| `reports/scraping_autofix/status_20260601_1939.md/` | 1 | 724 |
| `reports/scraping_autofix/status_20260601_2102.md/` | 1 | 685 |
| `reports/scraping_autofix/status_20260601_2226.md/` | 1 | 664 |
| `reports/scraping_autofix/status_20260601_2325.md/` | 1 | 685 |
| `reports/scraping_autofix/status_20260602_0121.md/` | 1 | 666 |
| `reports/scraping_autofix/status_20260602_0228.md/` | 1 | 685 |
| `reports/scraping_autofix/status_20260602_0333.md/` | 1 | 684 |
| `reports/scraping_autofix/status_20260602_0446.md/` | 1 | 699 |
| `reports/scraping_autofix/status_20260602_0621.md/` | 1 | 711 |
| `reports/scraping_autofix/status_20260602_0759.md/` | 1 | 685 |
| `reports/scraping_autofix/status_20260602_0927.md/` | 1 | 715 |
| `reports/scraping_autofix/status_20260602_1053.md/` | 1 | 692 |
| `reports/scraping_autofix/status_20260602_1140.md/` | 1 | 694 |
| `reports/scraping_autofix/status_20260602_1246.md/` | 1 | 697 |
| `reports/scraping_autofix/status_20260602_1402.md/` | 1 | 698 |
| `reports/scraping_autofix/status_20260602_1531.md/` | 1 | 686 |
| `reports/scraping_autofix/status_20260602_1639.md/` | 1 | 722 |
| `reports/scraping_autofix/status_20260602_1752.md/` | 1 | 711 |
| `reports/scraping_autofix/status_20260602_1855.md/` | 1 | 743 |
| `reports/scraping_autofix/status_20260602_2002.md/` | 1 | 665 |
| `reports/scraping_autofix/status_20260602_2122.md/` | 1 | 720 |
| `reports/scraping_autofix/status_20260602_2218.md/` | 1 | 695 |
| `reports/scraping_autofix/status_20260602_2333.md/` | 1 | 747 |
| `reports/scraping_autofix/status_20260603_0059.md/` | 1 | 684 |
| `reports/scraping_autofix/status_20260603_0207.md/` | 1 | 690 |
| `reports/scraping_autofix/status_20260603_0334.md/` | 1 | 718 |
| `reports/scraping_autofix/status_20260603_0435.md/` | 1 | 710 |
| `reports/scraping_autofix/status_20260603_0604.md/` | 1 | 688 |
| `reports/scraping_autofix/status_20260603_0713.md/` | 1 | 685 |
| `reports/scraping_autofix/status_20260603_0827.md/` | 1 | 684 |
| `reports/scraping_autofix/status_20260603_0941.md/` | 1 | 706 |
| `reports/scraping_autofix/status_20260603_1018.md/` | 1 | 656 |
| `reports/scraping_autofix/status_20260603_1156.md/` | 1 | 731 |
| `reports/scraping_autofix/status_20260603_1235.md/` | 1 | 718 |
| `reports/scraping_autofix/status_20260603_1316.md/` | 1 | 718 |
| `reports/scraping_autofix/status_20260603_1359.md/` | 1 | 691 |
| `reports/scraping_autofix/status_20260603_1443.md/` | 1 | 800 |
| `reports/scraping_autofix/status_20260603_1515.md/` | 1 | 781 |
| `reports/scraping_autofix/status_20260603_1556.md/` | 1 | 747 |
| `reports/scraping_autofix/status_20260603_1635.md/` | 1 | 719 |
| `reports/scraping_autofix/status_20260603_1713.md/` | 1 | 730 |
| `reports/scraping_autofix/status_20260603_1755.md/` | 1 | 733 |
| `reports/scraping_autofix/status_20260603_1846.md/` | 1 | 692 |
| `reports/scraping_autofix/status_20260603_1933.md/` | 1 | 719 |
| `reports/scraping_autofix/status_20260603_2019.md/` | 1 | 722 |
| `reports/scraping_autofix/status_20260603_2103.md/` | 1 | 707 |
| `reports/scraping_autofix/status_20260603_2142.md/` | 1 | 714 |
| `reports/scraping_autofix/status_20260603_2223.md/` | 1 | 728 |
| `reports/scraping_autofix/status_20260603_2249.md/` | 1 | 721 |
| `reports/scraping_autofix/status_20260603_2322.md/` | 1 | 786 |
| `reports/scraping_autofix/status_20260603_2337.md/` | 1 | 669 |
| `reports/scraping_autofix/status_20260604_1130.md/` | 1 | 630 |
| `reports/scraping_autofix/status_20260604_1151.md/` | 1 | 719 |
| `reports/scraping_autofix/status_20260604_1506.md/` | 1 | 778 |
| `reports/scraping_autofix/validate_imported_raw_20260531_1159.md/` | 1 | 613 |
| `reports/scraping_autofix/validate_imported_raw_20260531_1202.md/` | 1 | 612 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1408.md/` | 1 | 670 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1418.md/` | 1 | 675 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1428.md/` | 1 | 668 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1430.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1431.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1432.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1433.md/` | 1 | 628 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1434.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1435.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1436.md/` | 1 | 607 |
| `reports/scraping_autofix/validate_imported_raw_20260605_1437.md/` | 1 | 590 |
| `reports/scraping_autofix/validate_imported_raw_20260606_1742.md/` | 1 | 684 |
| `reports/scraping_autofix/validate_imported_raw_20260607_0710.md/` | 1 | 614 |
| `reports/scraping_autofix/validate_imported_raw_20260607_1546.md/` | 1 | 589 |
| `reports/scraping_autofix/validate_imported_raw_20260607_1547.md/` | 1 | 587 |
| `reports/scraping_autofix/validate_imported_raw_verify_after_commit.md/` | 1 | 593 |
| `reports/scraping_autofix/validate_quality_root_fix_dryrun_20260604_1004.md/` | 1 | 589 |
| `reports/scraping_diagnostics/` | 14 | 29345 |
| `reports/scraping_runs/block2_extractor_missing_selector_run_20260607/` | 11 | 75458 |
| `reports/scraping_runs/captured_inventory_20260605_1313/` | 1 | 5343 |
| `reports/scraping_runs/captured_inventory_20260605_1317/` | 1 | 1155 |
| `reports/scraping_runs/captured_inventory_20260605_1318/` | 1 | 1236 |
| `reports/scraping_runs/captured_inventory_20260605_1326/` | 1 | 1237 |
| `reports/scraping_runs/captured_inventory_20260605_1328/` | 1 | 1889 |
| `reports/scraping_runs/detail_location_enrichment_20260605_1516/` | 1 | 2429 |
| `reports/scraping_runs/detail_location_enrichment_20260605_1528/` | 1 | 2449 |
| `reports/scraping_runs/detail_location_enrichment_20260605_1547/` | 1 | 1643 |
| `reports/scraping_runs/detail_location_enrichment_20260605_1548/` | 1 | 1630 |
| `reports/scraping_runs/extractor_missing_selector_diagnosis_20260605/` | 1 | 7110 |
| `reports/scraping_runs/extractor_missing_selector_fix_20260605_1931/` | 2 | 9156 |
| `reports/scraping_runs/faceted_discovery_20260605_1615/` | 1 | 9994 |
| `reports/scraping_runs/faceted_discovery_test_20260605/` | 2 | 1858 |
| `reports/scraping_runs/faceted_expanded_test_20260605_1715/` | 2 | 11578 |
| `reports/scraping_runs/faceted_integration_test_20260605/` | 1 | 4503 |
| `reports/scraping_runs/failures_batch_20260604_1055.md/` | 1 | 1554 |
| `reports/scraping_runs/failures_batch_20260604_1131.md/` | 1 | 16706 |
| `reports/scraping_runs/failures_batch_20260604_1154_partial.md/` | 1 | 7641 |
| `reports/scraping_runs/failures_batch_20260604_1446.md/` | 1 | 17906 |
| `reports/scraping_runs/geocoding_readiness_20260605_1445/` | 1 | 5118 |
| `reports/scraping_runs/import_controlado_20260608/` | 1 | 67880 |
| `reports/scraping_runs/overnight_20260604_1914/` | 4 | 20786 |
| `reports/scraping_runs/playwright_enrichment_dryrun_20260605/` | 1 | 1946 |
| `reports/scraping_runs/progress_every_2h.md/` | 1 | 4551 |
| `reports/scraping_runs/progressive_run_summary_20260604_1206.md/` | 1 | 10147 |
| `reports/scraping_runs/retry_recoverables_20260605_1958/` | 1 | 1898 |
| `reports/scraping_runs/run_all_agencies_20260604_135640_recommendations.md/` | 1 | 2243 |
| `reports/scraping_runs/run_all_agencies_20260604_135640_summary.md/` | 1 | 2471 |
| `reports/scraping_runs/run_all_agencies_20260604_135806_recommendations.md/` | 1 | 2243 |
| `reports/scraping_runs/run_all_agencies_20260604_135806_summary.md/` | 1 | 2471 |
| `reports/scraping_runs/scraper_full_improvement_20260605_2011/` | 9 | 28636 |
| `reports/scraping_runs/scraper_local_improvement_20260606_0954/` | 3 | 3318 |
| `reports/scraping_runs/seoaneriera_retry_20260605_1931/` | 1 | 826 |
| `reports/scraping_runs/staging_quality_audit_20260605_1505/` | 1 | 4859 |
| `reports/scraping_runs/xtipo_global_candidates_20260605_1855/` | 1 | 4958 |
| `reports/scraping_runs/xtipo_global_expanded_20260605_1914/` | 1 | 2039 |
| `reports/scraping_runs/xtipo_retry_timeout_20260605_1914/` | 1 | 1287 |

Muestras markdown/csv relevantes:
- `reports/audits/auditoria_tecnica_inmocapital_20260604_162339.md`
- `reports/audits/full_project_audit_20260606_1023/audit_consistency_check.md`
- `reports/audits/full_project_audit_20260606_1023/data_pipeline_audit.md`
- `reports/audits/full_project_audit_20260606_1023/data_quality_audit.md`
- `reports/audits/full_project_audit_20260606_1023/documentation_audit.md`
- `reports/audits/full_project_audit_20260606_1023/executive_summary.md`
- `reports/audits/full_project_audit_20260606_1023/frontend_audit.md`
- `reports/audits/full_project_audit_20260606_1023/historical_errors_audit.md`
- `reports/audits/full_project_audit_20260606_1023/master_scraper_improvement_plan.md`
- `reports/audits/full_project_audit_20260606_1023/next_5_prompts.md`
- `reports/audits/full_project_audit_20260606_1023/performance_scalability_audit.md`
- `reports/audits/full_project_audit_20260606_1023/project_map.md`
- `reports/audits/full_project_audit_20260606_1023/scraper_audit.md`
- `reports/audits/full_project_audit_20260606_1023/scraper_strategy_families.md`
- `reports/audits/full_project_audit_20260606_1023/source_policy_audit.md`
- `reports/scraping_autofix/autofix_resume.md`
- `reports/scraping_autofix/batch_20260531_1219/batch_report.md`
- `reports/scraping_autofix/batch_20260531_1219/geocode_commit.md`
- `reports/scraping_autofix/batch_20260531_1219/geocode_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1219/geocode_dry_run_after_filter.md`
- `reports/scraping_autofix/batch_20260531_1219/import_commit.md`
- `reports/scraping_autofix/batch_20260531_1219/import_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_1.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_2.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_3.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_4.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_5.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_6.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_7.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_commit_8.md`
- `reports/scraping_autofix/batch_20260531_1219/validate_dry_run_100.md`
- `reports/scraping_autofix/batch_20260531_1219_after.md`
- `reports/scraping_autofix/batch_20260531_1219_before.md`
- `reports/scraping_autofix/batch_20260531_1219_errors.md`
- `reports/scraping_autofix/batch_20260531_1219_fixed.md`
- `reports/scraping_autofix/batch_20260531_1219_remaining.md`
- `reports/scraping_autofix/batch_20260531_1314/batch_report.md`
- `reports/scraping_autofix/batch_20260531_1314/geocode_commit.md`
- `reports/scraping_autofix/batch_20260531_1314/geocode_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1314/geocode_dry_run_after_filter.md`
- `reports/scraping_autofix/batch_20260531_1314/import_commit.md`
- `reports/scraping_autofix/batch_20260531_1314/import_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1314/validate_commit.md`
- `reports/scraping_autofix/batch_20260531_1314/validate_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1314_after.md`
- `reports/scraping_autofix/batch_20260531_1314_before.md`
- `reports/scraping_autofix/batch_20260531_1314_errors.md`
- `reports/scraping_autofix/batch_20260531_1314_fixed.md`
- `reports/scraping_autofix/batch_20260531_1314_remaining.md`
- `reports/scraping_autofix/batch_20260531_1341/batch_report.md`
- `reports/scraping_autofix/batch_20260531_1341/geocode_commit.md`
- `reports/scraping_autofix/batch_20260531_1341/geocode_commit_2.md`
- `reports/scraping_autofix/batch_20260531_1341/geocode_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1341/geocode_dry_run_after_filter.md`
- `reports/scraping_autofix/batch_20260531_1341/geocode_pending_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1341/import_commit.md`
- `reports/scraping_autofix/batch_20260531_1341/import_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1341/validate_commit_1.md`
- `reports/scraping_autofix/batch_20260531_1341/validate_commit_2.md`
- `reports/scraping_autofix/batch_20260531_1341/validate_commit_3.md`
- `reports/scraping_autofix/batch_20260531_1341_after.md`
- `reports/scraping_autofix/batch_20260531_1341_before.md`
- `reports/scraping_autofix/batch_20260531_1341_errors.md`
- `reports/scraping_autofix/batch_20260531_1341_fixed.md`
- `reports/scraping_autofix/batch_20260531_1341_remaining.md`
- `reports/scraping_autofix/batch_20260531_1438/batch_report.md`
- `reports/scraping_autofix/batch_20260531_1438/geocode_commit.md`
- `reports/scraping_autofix/batch_20260531_1438/geocode_commit_2.md`
- `reports/scraping_autofix/batch_20260531_1438/geocode_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1438/geocode_dry_run_after_filter.md`
- `reports/scraping_autofix/batch_20260531_1438/import_commit.md`
- `reports/scraping_autofix/batch_20260531_1438/import_dry_run.md`
- `reports/scraping_autofix/batch_20260531_1438/validate_commit_1.md`
- `reports/scraping_autofix/batch_20260531_1438/validate_commit_2.md`
- `reports/scraping_autofix/batch_20260531_1438/validate_commit_3.md`
- `reports/scraping_autofix/batch_20260531_1438/validate_commit_4.md`
- `reports/scraping_autofix/batch_20260531_1438/validate_commit_5.md`
- `reports/scraping_autofix/batch_20260531_1438_after.md`
- `reports/scraping_autofix/batch_20260531_1438_before.md`
- `reports/scraping_autofix/batch_20260531_1438_errors.md`

## scripts auxiliares utiles

Total: 22

- `??` `scripts/_build_captured_manifest.py` (4797 bytes)
- `??` `scripts/_check_partials_untouched.py` (2475 bytes)
- `??` `scripts/_check_pending_geocoding.py` (2806 bytes)
- `??` `scripts/_check_staging_state.py` (1690 bytes)
- `??` `scripts/_classify_js_api_candidates.py` (5592 bytes)
- `??` `scripts/_create_full_address_csv.py` (1781 bytes)
- `??` `scripts/_diagnose_missing_selector.py` (7816 bytes)
- `??` `scripts/_dryrun_local.py` (14977 bytes)
- `??` `scripts/_extract_xtipo_candidates.py` (8872 bytes)
- `??` `scripts/_faceted_domain_diagnostic.py` (18397 bytes)
- `??` `scripts/_generate_playwright_targets.py` (3118 bytes)
- `??` `scripts/_geocoding_readiness_audit.py` (10786 bytes)
- `??` `scripts/_inventory_analysis.py` (9934 bytes)
- `??` `scripts/_run_validate_batches.ps1` (1460 bytes)
- `??` `scripts/_select_no_property_links_candidates.py` (10717 bytes)
- `??` `scripts/_staging_quality_audit.py` (17292 bytes)
- `??` `scripts/_test_faceted_import.py` (1750 bytes)
- `??` `scripts/_verify_geocoding_result.py` (2436 bytes)
- `??` `scripts/diagnose_scraping_errors.py` (27514 bytes)
- `??` `scripts/export_scraping_errors.py` (6364 bytes)
- `??` `scripts/generate_batch_failure_report.py` (21343 bytes)
- `??` `scripts/generate_scraping_run_audit_reports.py` (41409 bytes)

## scratch/temp files

Total: 4

- `??` `_audit_sim.py` (7319 bytes)
- `??` `_deep_scan_npl.py` (6362 bytes)
- `??` `_deep_scan_results.json` (35608 bytes)
- `??` `reports/scraping_runs/progressive_100_20260604_1153.pid` (7 bytes)

## codigo real del scraper/pipeline

Total: 5

- `??` `scraper/faceted_discovery.py` (10315 bytes)
- `??` `scripts/enrich_staging_missing_location_from_detail.py` (36178 bytes)
- `??` `scripts/run_faceted_scraping.py` (27900 bytes)
- `??` `scripts/run_internal_scraping_batch.py` (32524 bytes)
- `??` `scripts/run_scraping_autofix_continuous.py` (55820 bytes)

## archivos peligrosos/no commiteables

Total: 364

| grupo | archivos | tamano aprox bytes |
| --- | ---: | ---: |
| `docs/obsidian/` | 4 | 6794 |
| `reports/scraping_autofix/autofix_state.json/` | 1 | 2718 |
| `reports/scraping_autofix/batch_20260531_1219/` | 1 | 19776 |
| `reports/scraping_autofix/batch_20260531_1314/` | 1 | 32795 |
| `reports/scraping_autofix/batch_20260531_1341/` | 1 | 66116 |
| `reports/scraping_autofix/batch_20260531_1438/` | 1 | 67191 |
| `reports/scraping_autofix/batch_20260531_1556/` | 1 | 66317 |
| `reports/scraping_autofix/batch_20260531_1719/` | 1 | 65744 |
| `reports/scraping_autofix/batch_20260531_1849/` | 1 | 58214 |
| `reports/scraping_autofix/batch_20260531_2021/` | 1 | 7826 |
| `reports/scraping_autofix/batch_20260531_2057/` | 1 | 64281 |
| `reports/scraping_autofix/batch_20260531_2332/` | 1 | 43770 |
| `reports/scraping_autofix/batch_20260601_0048/` | 1 | 65472 |
| `reports/scraping_autofix/batch_20260601_0712/` | 1 | 37253 |
| `reports/scraping_autofix/batch_20260601_1008/` | 1 | 56020 |
| `reports/scraping_autofix/batch_20260601_1152/` | 1 | 66677 |
| `reports/scraping_autofix/batch_20260601_1718/` | 1 | 32524 |
| `reports/scraping_autofix/batch_20260601_1944/` | 1 | 16411 |
| `reports/scraping_autofix/batch_20260601_2103/` | 1 | 16898 |
| `reports/scraping_autofix/batch_20260601_2227/` | 1 | 16599 |
| `reports/scraping_autofix/batch_20260601_2326/` | 1 | 16701 |
| `reports/scraping_autofix/batch_20260602_0124/` | 1 | 16567 |
| `reports/scraping_autofix/batch_20260602_0229/` | 1 | 16632 |
| `reports/scraping_autofix/batch_20260602_0334/` | 1 | 16587 |
| `reports/scraping_autofix/batch_20260602_0447/` | 1 | 16716 |
| `reports/scraping_autofix/batch_20260602_0622/` | 1 | 16459 |
| `reports/scraping_autofix/batch_20260602_0759/` | 1 | 16563 |
| `reports/scraping_autofix/batch_20260602_0927/` | 1 | 16541 |
| `reports/scraping_autofix/batch_20260602_1054/` | 1 | 14994 |
| `reports/scraping_autofix/batch_20260602_1141/` | 1 | 15608 |
| `reports/scraping_autofix/batch_20260602_1247/` | 1 | 16629 |
| `reports/scraping_autofix/batch_20260602_1403/` | 1 | 16526 |
| `reports/scraping_autofix/batch_20260602_1533/` | 1 | 16199 |
| `reports/scraping_autofix/batch_20260602_1639/` | 1 | 16721 |
| `reports/scraping_autofix/batch_20260602_1753/` | 1 | 16645 |
| `reports/scraping_autofix/batch_20260602_1856/` | 1 | 17084 |
| `reports/scraping_autofix/batch_20260602_2003/` | 1 | 16315 |
| `reports/scraping_autofix/batch_20260602_2123/` | 1 | 15973 |
| `reports/scraping_autofix/batch_20260602_2219/` | 1 | 16284 |
| `reports/scraping_autofix/batch_20260602_2333/` | 1 | 16602 |
| `reports/scraping_autofix/batch_20260603_0100/` | 1 | 17081 |
| `reports/scraping_autofix/batch_20260603_0208/` | 1 | 17125 |
| `reports/scraping_autofix/batch_20260603_0334/` | 1 | 16492 |
| `reports/scraping_autofix/batch_20260603_0436/` | 1 | 16770 |
| `reports/scraping_autofix/batch_20260603_0605/` | 1 | 16910 |
| `reports/scraping_autofix/batch_20260603_0714/` | 1 | 16740 |
| `reports/scraping_autofix/batch_20260603_0828/` | 1 | 16611 |
| `reports/scraping_autofix/batch_20260603_0943/` | 1 | 6093 |
| `reports/scraping_autofix/batch_20260603_1125/` | 1 | 16930 |
| `reports/scraping_autofix/batch_20260603_1157/` | 1 | 16518 |
| `reports/scraping_autofix/batch_20260603_1235/` | 1 | 16635 |
| `reports/scraping_autofix/batch_20260603_1316/` | 1 | 17014 |
| `reports/scraping_autofix/batch_20260603_1400/` | 1 | 17128 |
| `reports/scraping_autofix/batch_20260603_1443/` | 1 | 16714 |
| `reports/scraping_autofix/batch_20260603_1516/` | 1 | 17488 |
| `reports/scraping_autofix/batch_20260603_1556/` | 1 | 16957 |
| `reports/scraping_autofix/batch_20260603_1636/` | 1 | 17289 |
| `reports/scraping_autofix/batch_20260603_1713/` | 1 | 16972 |
| `reports/scraping_autofix/batch_20260603_1755/` | 1 | 16979 |
| `reports/scraping_autofix/batch_20260603_1846/` | 1 | 17154 |
| `reports/scraping_autofix/batch_20260603_1935/` | 1 | 17065 |
| `reports/scraping_autofix/batch_20260603_2019/` | 1 | 16453 |
| `reports/scraping_autofix/batch_20260603_2103/` | 1 | 16826 |
| `reports/scraping_autofix/batch_20260603_2142/` | 1 | 17158 |
| `reports/scraping_autofix/batch_20260603_2223/` | 1 | 17305 |
| `reports/scraping_autofix/batch_20260603_2249/` | 1 | 16827 |
| `reports/scraping_autofix/batch_20260603_2322/` | 1 | 1989 |
| `reports/scraping_autofix/batch_20260604_0917/` | 1 | 14053 |
| `reports/scraping_autofix/batch_20260604_1055/` | 1 | 654 |
| `reports/scraping_autofix/batch_20260604_1131/` | 1 | 16215 |
| `reports/scraping_autofix/batch_20260604_1154/` | 1 | 5311 |
| `reports/scraping_autofix/batch_20260604_1446/` | 1 | 41401 |
| `reports/scraping_autofix/batch_20260604_1702/` | 1 | 8001 |
| `reports/scraping_autofix/batch_20260604_1713/` | 1 | 81643 |
| `reports/scraping_autofix/batch_20260604_1915/` | 1 | 169212 |
| `reports/scraping_autofix/batch_20260604_1943/` | 1 | 177694 |
| `reports/scraping_autofix/batch_20260604_2020/` | 1 | 179346 |
| `reports/scraping_autofix/batch_20260604_2101/` | 1 | 179630 |
| `reports/scraping_autofix/batch_20260604_2138/` | 1 | 185754 |
| `reports/scraping_autofix/batch_20260604_2236/` | 1 | 206638 |
| `reports/scraping_autofix/batch_20260604_2341/` | 1 | 178449 |
| `reports/scraping_autofix/batch_20260605_0925/` | 1 | 13648 |
| `reports/scraping_autofix/batch_20260605_0932/` | 1 | 36118 |
| `reports/scraping_autofix/batch_20260605_1019/` | 1 | 440552 |
| `reports/scraping_autofix/batch_20260605_1656/` | 1 | 6922 |
| `reports/scraping_autofix/batch_20260605_1716/` | 1 | 75702 |
| `reports/scraping_autofix/batch_20260605_1857/` | 1 | 28390 |
| `reports/scraping_autofix/batch_20260605_1914/` | 1 | 6060 |
| `reports/scraping_autofix/batch_20260605_1919/` | 1 | 12519 |
| `reports/scraping_autofix/batch_20260605_1932/` | 1 | 1875 |
| `reports/scraping_autofix/batch_20260605_1938/` | 1 | 11050 |
| `reports/scraping_autofix/batch_20260605_1959/` | 1 | 6429 |
| `reports/scraping_autofix/batch_20260605_2002/` | 1 | 153184 |
| `reports/scraping_autofix/batch_20260606_0956/` | 1 | 4696 |
| `reports/scraping_autofix/batch_20260606_0959/` | 1 | 1957 |
| `reports/scraping_autofix/batch_20260606_1129/` | 1 | 20581 |
| `reports/scraping_autofix/batch_20260606_1137/` | 1 | 6238 |
| `reports/scraping_autofix/batch_20260606_2235/` | 1 | 5532 |
| `reports/scraping_autofix/batch_20260606_2245/` | 1 | 1841 |
| `reports/scraping_autofix/batch_20260607_0527/` | 1 | 10882 |
| `reports/scraping_autofix/batch_20260607_0550/` | 1 | 4501 |
| `reports/scraping_autofix/batch_20260607_0556/` | 1 | 4519 |
| `reports/scraping_autofix/batch_20260608_1953/` | 1 | 19753 |
| `reports/scraping_autofix/batch_20260608_2003/` | 1 | 1792 |
| `reports/scraping_autofix/global_audit_20260601_1001.json/` | 1 | 3116 |
| `reports/scraping_autofix/global_audit_20260601_1004.json/` | 1 | 1200 |
| `reports/scraping_autofix/global_audit_after_pending_20260601_1151.json/` | 1 | 966 |
| `reports/scraping_diagnostics/` | 13 | 131421 |
| `reports/scraping_runs/extractor_missing_selector_fix_20260605_1931/` | 7 | 300223 |
| `reports/scraping_runs/faceted_expanded_test_20260605_1715/` | 49 | 1608589 |
| `reports/scraping_runs/faceted_integration_test_20260605/` | 7 | 659091 |
| `reports/scraping_runs/no_property_links_expanded_20260605_1958/` | 100 | 2859705 |
| `reports/scraping_runs/retry_recoverables_20260605_1958/` | 3 | 42186 |
| `reports/scraping_runs/scraper_local_improvement_20260606_0954/` | 3 | 73437 |
| `reports/scraping_runs/seoaneriera_retry_20260605_1931/` | 1 | 21287 |
| `reports/scraping_runs/sprint_autonomo_20260607/` | 34 | 1679696 |
| `reports/scraping_runs/xtipo_global_candidates_20260605_1855/` | 22 | 792215 |
| `reports/scraping_runs/xtipo_global_expanded_20260605_1914/` | 9 | 244135 |
| `reports/scraping_runs/xtipo_retry_timeout_20260605_1914/` | 6 | 396595 |

## Archivos ETAPA 5A esperados para commit acotado

- `reports/scraping_runs/import_controlado_20260608/working_tree_recovery_inventory.md`
- `reports/scraping_runs/import_controlado_20260608/staging_ids_done_etapa5a.csv`
- `reports/scraping_runs/import_controlado_20260608/staging_ids_publishqueue_candidates_etapa5a.csv`
- `reports/scraping_runs/import_controlado_20260608/etapa5a_publish_queue_dryrun_summary.md`

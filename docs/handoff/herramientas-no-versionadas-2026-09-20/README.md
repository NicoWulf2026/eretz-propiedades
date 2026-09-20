# Herramientas que nunca estuvieron en Git — cuarentena, no candidata

**Esto NO es parte de la candidata unificada.** Es un rescate.

## Qué son

39 archivos que vivían sin versionar en el worktree
`D:\INMO CAPITAL\Inmo-Capital-main` (rama `release/eretz-private-preview`) y que
**no existen en ningún commit del repositorio**, en ninguna rama, local o
remota. Se comprobó uno por uno con `git log --all -- <ruta>`: de los 45
archivos no-scratch que había sin versionar, 6 sí figuraban en la historia y
estos 39 no. Si la máquina se perdía, se perdían.

Están acá con su ruta original relativa a la raíz del repo, para que se vea de
dónde salieron y a dónde volverían si alguna vez se los adopta.

- 5 documentos `ERETZ_*.md`
- 31 scripts `scripts/*.py`
- 3 tests `tests/*.py`

## Lo que NO significa que estén acá

No fueron revisados, ni ejecutados, ni portados, ni medidos durante la
unificación. Codex los dejó anotados como problema abierto #10 de su handoff:
se les hizo parse de AST y nada más. Copiarlos a este directorio los preserva;
no los aprueba.

**No los ejecutes para "ver qué hacen".** Varios tocan producción por su
nombre y por su contenido: `apply_diagnostic_backfill.py`,
`apply_universe_cleanup.py`, `apply_url_listado_update_pr_be_url_06d.py`,
`enqueue_deactivations.py`, `backup_productivo.py`, `prod_preflight_09a.py`,
`diff_produccion.py`, `ensayo_de_rollback.py`. Escribir en producción sigue
requiriendo autorización explícita del usuario.

Y una advertencia concreta que ya está medida, del handoff de Codex:
`run_faceted_scraping.py` **duplica el discovery**, tiene un worker sin uso y
una paginación inventada. No portarlo como segundo crawler. El descubrimiento
de URLs de ficha es uno solo y vive en `scraper/detail_urls.py`.

## Secretos

Se escanearon los 39 antes de copiarlos, buscando JWT (`eyJ...`), tokens
`sbp_`, cadenas de conexión con contraseña embebida y asignaciones literales a
`api_key` / `service_role` / `password` / `token`. Las dos únicas coincidencias
—`scripts/diagnose_scraping_errors.py:162` y
`scripts/export_scraping_errors.py:50`— son referencias a variables que se leen
de `os.environ`, no valores. No hay credenciales en estos archivos.

## Qué quedó afuera a propósito

- `DATA_QUALITY/` — 35 CSV, **436 MB**, exportaciones de datos productivos.
  No va a GitHub. Se regenera contra la base; sigue en
  `D:\INMO CAPITAL\Inmo-Capital-main\DATA_QUALITY`.
- Los `_*.py`, `_*.json`, `_batch*_output.txt` — unos 63 archivos de scratch de
  sesiones viejas (diagnósticos de tandas, verificaciones de grupos, volcados de
  lotes). Son salidas de un momento, no herramientas. Siguen en su worktree.

## Si alguien los adopta

Uno por uno, con la misma vara que el resto: leerlo, entender qué frontera
toca, escribirle un test que muerda, y recién ahí moverlo a `scripts/`. La
alternativa —moverlos en bloque porque "ya estaban"— es exactamente cómo
aparecen los segundos crawlers.

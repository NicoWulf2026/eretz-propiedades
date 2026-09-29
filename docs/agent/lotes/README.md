# Lotes compartidos pendientes

Cambios a archivos de la huella COMPARTIDA (`archivos_de_la_huella()` fuera de un
solo conector). Aplicar cualquiera invalida la certificación de todas las
agencias y reinicia la recertificación (~52 h con 2 workers). Por eso se
acumulan y se aplican juntos, en un momento elegido, no uno por uno.

Nada de esto está aplicado en el worktree que corre la cola.

## `LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch`

Preparado y verificado en `D:\INMO CAPITAL\eretz-dev` (suite completa con el
lote aplicado: **3.632 verdes**, 29-09). Aplicar desde la raíz del repo:

    git apply --ignore-whitespace docs/agent/lotes/LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch

(`--ignore-whitespace` porque los archivos del repo tienen fin de línea CRLF.)

| cambio | archivo | efecto medido |
|---|---|---|
| Partes de un aglomerado censal resuelven la localidad, solo dentro de su provincia | `connectors/geografia.py` | +112 fichas con localidad (92 «Necochea» → «Necochea - Quequén»). Un nombre que ya es localidad en algún lado no se toca; en otra provincia sigue sin resolverse, no se vuelve conflicto. |
| Descartes del guardián de forma **sin señal** no cuentan como ficha fallida | `scripts/agency_certifier.py` | 4 agencias salen de NEEDS_FIX (348 propiedades; `bottai` 315, bloqueada por un enlace a `area_cliente.php`). Solo con ≤ max(2, 2 %) descartes, 0 con señal y propiedades leídas: si el guardián descarta todo o mucho, sigue bloqueando. |

Tests: `tests/test_lote_compartido_2026_09_29.py` (7).

Después de aplicar: suite completa, commit, y la cola recertifica sola por
cambio de huella (ERETZ AUTOMATION ON).

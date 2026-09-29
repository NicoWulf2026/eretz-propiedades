# Lotes compartidos pendientes

Cambios a archivos de la huella COMPARTIDA (`archivos_de_la_huella()` fuera de un
solo conector). Aplicar cualquiera invalida la certificación de todas las
agencias y reinicia la recertificación (~52 h con 2 workers). Por eso se
acumulan y se aplican juntos, en un momento elegido, no uno por uno.

Nada de esto está aplicado en el worktree que corre la cola.

## `LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch` — APLICADO el 29-09 (`a6746a9338`, política P3)

Preparado y verificado en `D:\INMO CAPITAL\eretz-dev` (suite completa con el
lote aplicado: **3.635 verdes**, 29-09). Aplicar desde la raíz del repo:

    git apply docs/agent/lotes/LOTE_COMPARTIDO_PENDIENTE_2026-09-29.patch

| cambio | archivo | efecto medido |
|---|---|---|
| Partes de un aglomerado censal resuelven la localidad, solo dentro de su provincia | `connectors/geografia.py` | +112 fichas con localidad (92 «Necochea» → «Necochea - Quequén»). Un nombre que ya es localidad en algún lado no se toca; en otra provincia sigue sin resolverse, no se vuelve conflicto. |
| Descartes del guardián de forma **sin señal** no cuentan como ficha fallida | `scripts/agency_certifier.py` | 4 agencias salen de NEEDS_FIX (348 propiedades; `bottai` 315, bloqueada por un enlace a `area_cliente.php`). Solo con ≤ max(2, 2 %) descartes, 0 con señal y propiedades leídas: si el guardián descarta todo o mucho, sigue bloqueando. |
| Las casillas del buscador (`<label><input type=checkbox>`) no son datos de la ficha | `connectors/generico.py` | `o feely` (familia wordpress DETENIDA desde el 29-09 04:59): «Tipo de operación: Alquiler/Venta» del buscador Houzez daba la operación por publicada en 74 emprendimientos. |
| El bloque de unidades de Houzez (`Unidades disponibles`, `property-sub-listings-wrap`) corta la ficha del emprendimiento, en la señal y en el extractor | `scripts/agency_certifier.py`, `connectors/generico.py` | misma regla que `UNIDADES`: la operación/precio de una unidad no es la del proyecto. |
| «Provincia: Argentina» leída y rechazada es validación, no campo sin leer | `scripts/agency_certifier.py` | `o feely`: 1 ficha bloqueaba 600. |

Tests: `tests/test_lote_compartido_2026_09_29.py` (10).

Con el lote, `o feely` (600 propiedades) queda sin motivo conocido de NEEDS_FIX y la familia
wordpress se libera sola por cambio de huella.

Después de aplicar: suite completa, commit, y la cola recertifica sola por
cambio de huella (ERETZ AUTOMATION ON).

## Lote 2 — acumulando (política P4: se aplica al llegar a ≥300 propiedades, 24 h con un arreglo
de valor, una familia bloqueada, o si esperar desperdicia más recertificación)

| arreglo | archivo (huella) | radio medido | estado |
|---|---|---|---|
| «finca» y «chacra» como tipo (→ terreno), después de los tipos existentes | `connectors/base.py` | 67 fincas + 60 chacras sin tipo; 12 fincas como «oficina» (menú) | a implementar |
| Una baja entre corridas (404 en la 1, fuera del listado en la 2) no es ficha fallida | `scripts/agency_certifier.py` | `emir elhelou` (1 de 26) | a implementar |
| Conteos en palabras («cuatro dormitorios», «un baño») | `connectors/generico.py` | pozzobon, fenix (DEFECTO_PENDIENTE en el gate) | a medir |
| Superficie «50 M² 50 M²» sin rótulo (fenix) | `connectors/generico.py` | 1 ficha | a medir |
| Wix: `limite_bytes` y lector de registros CMS | `connectors/base.py` | 2 agencias (liprandi 71) | postergado |
| robots.txt en el descargador (P11) | `connectors/base.py` | 0 fichas prohibidas medidas; cumplimiento | a implementar |
| Cortesía por backend compartido (Tokko: cientos de dominios, un límite) | runner / descargador | 1.241 respuestas 429 con 6 hilos por dominio (verificador) | a medir con la prueba de 3 workers |

# Auditoria de cobertura nacional — 2026-10-08

Solo lectura. Sin cambios de codigo ni de cola. Scripts y salida cruda:
`E:\ERETZ Propiedades\_b_scratch\sprint\auditoria_cobertura_2026-10-08\` (`auditoria_cobertura.py`, `auditoria.json`,
`porque_no_servidas.py`, `perdida_global.py`, `url_en_pre.py`). La identidad se calcula con la MISMA `resolve_identity`
que usa la cola (`--ready`); el ledger con `vigentes_por_agencia`; la servida es `sprint_rc5` (77.740 filas).

## 0. Hay dos universos, no uno

| Universo | Que es | Tamano |
|---|---|---|
| **MAIN** | `public.inmobiliarias_main` en produccion (copia local de solo lectura: `SUPABASE_RECONCILIATION.sqlite3`) | **7.004** ids |
| **CANONICO** | padron de scraping (roomix), el que la cola certifica | **6.597** identidades |

- De las 6.597 canonicas: **1.095 RESOLVED** a un id de MAIN, **5.428 NOT_FOUND_IN_ERETZ** (no existen en MAIN), **74 AMBIGUOUS**.
- De los 7.004 de MAIN: **1.118** quedan vinculados a una identidad canonica; **5.886 no tienen identidad canonica**
  (519 de ellos tienen avisos en produccion). 999 ids de MAIN tienen avisos en alguna relacion de produccion
  (`public.propiedades`: 836 agencias).
- Las 913 servidas: **619 por FK de MAIN** y **294 canonicas sin FK** (P6, identidad por web verificada).

El "7.004 vs 913" mezcla los dos universos. La reconciliacion de abajo es sobre el CANONICO (el que se puede scrapear hoy);
el puente MAIN <-> CANONICO es un frente propio (seccion 6).

## 1. Embudo excluyente (6.597 canonicas)

| Estado (primero que aplica) | Agencias | Servidas | Filas servidas |
|---|---:|---:|---:|
| 01 Identidad conflictiva (AMBIGUOUS 74, web de atribucion ambigua 22, DUPLICATE_OR_CONFLICT 3; union) | 97 | 2 | 170 |
| 02 Sin web propia (perfil de portal 390, pagina de oficina de red 79, no inmobiliaria 23, web ajena) | 645 | 3 | 586 |
| 03 Sin web identificada | 3.476 | 1 | 50 |
| 04 Web identificada, identidad sin verificar (NOT_FOUND_IN_ERETZ sin web canonica verificada): fuera de `--ready` | 568 | 0 | 0 |
| 05 READY pendiente (en cola, sin resultado) | 694 | 103 | 10.699 |
| 06 Procesada — CERTIFIED_COMPLETE | 673 | 648 | 49.255 |
| 06 Procesada — CERTIFIED_BEST_AVAILABLE | 88 | 74 | 3.479 |
| 06 Procesada — NEEDS_FIX | 294 | 68 | 12.137 |
| 06 Procesada — BLOCKED_EXTERNAL | 59 | 13 | 1.332 |
| 06 Procesada — NO_INVENTORY_CONFIRMED | 2 | 1 | 32 |
| 06 Procesada — IDENTITY_PENDING | 1 | 0 | 0 |
| **Total** | **6.597** | **913** | **77.740** |

Solo **1.816** canonicas salen READY para la cola (las que tienen web oficial verificada y FK de MAIN o web canonica
verificada); 4.109 IDENTITY_PENDING y 672 BLOCKED_EXTERNAL nunca entran.

## 2. Indicadores complementarios (se superponen)

| # | Indicador | Valor |
|---|---|---|
| 1 | Padron total | MAIN 7.004 / CANONICO 6.597 |
| 2 | Duplicadas o identidad conflictiva | 97 (canonico) |
| 3 | Con sitio web identificado | 3.065 |
| 4 | Sin sitio web identificado | 3.532 |
| 5 | Pendientes | 694 en cola READY + 4.786 fuera de la cola (568 + 3.476 + 645 + 97) |
| 6 | Ya procesadas (resultado vigente en el ledger) | 1.270 (1.270 paquetes en disco) |
| 7 | CERTIFIED_COMPLETE | 676 |
| 8 | CERTIFIED_BEST_AVAILABLE | 89 |
| 9 | NEEDS_FIX | 314 |
| 10 | IDENTITY_PENDING | 4.109 por identidad (vista de la cola) / 116 como cierre en el ledger |
| 11 | BLOCKED_EXTERNAL | 672 por identidad / 73 como cierre en el ledger |
| 12 | Sin inventario confirmado | 2 NO_INVENTORY_CONFIRMED; 6 certificadas con 0 fichas; 91 NEEDS_FIX con "cero no demostrado" |
| 13 | Con propiedades en preingestion | 1.724 con filas; 550 con filas CANDIDATE (58.427) |
| 14 | Con propiedades servidas | 913 (77.740 filas) |
| 15 | Excluidas y motivo | seccion 3 |

Hay mas servidas que certificadas porque la servida conserva filas ya servidas sin muerte demostrada (P1/P8): 103 agencias
READY todavia sin cierre (linaje de la preingestion) y 68 NEEDS_FIX conservadas.

## 3. Exclusiones y la PERDIDA MASIVA encontrada

### 3.1 Certificadas (765) con 0 filas servidas: 41, todas explicadas
| Motivo | Agencias |
|---|---:|
| Perdida del constructor (3.2): sus URLs estan en la preingestion como AGENCY_ID_UNRESOLVED | 17 |
| Certificadas DESPUES de construir rc5 (entran en la proxima candidata) | 11 |
| Regla de URL con query string (`rechazo:query_string`, `id_derivado_de_query`): 365 filas | 6 |
| Certificadas con 0 fichas (sin inventario publicado) | 5 |
| WEB_AJENA (perfil de plataforma; correcto) | 2 |

### 3.2 PERDIDA MASIVA ACCIDENTAL — 21.189 filas certificadas sin servir, 290 agencias
**Si existe.** No es de scraping: es del constructor de la snapshot. `snapshot_certificadas.decidir` descarta una fila
certificada si su URL (`url_ya_en_preingestion`) o su numero de aviso (`numero_de_url_ya_visto`) ya figura en la
preingestion **en cualquier estado**. Para las agencias canonicas sin FK (P6), la preingestion del 03-09 tiene esas URLs
como `AGENCY_ID_UNRESOLVED / CANONICAL_AGENCY_NOT_RESOLVED` (de cuando la agencia no estaba resuelta): no son servibles.
La fila fresca se descarta por "ya conocida" y la vieja no se sirve: el inventario certificado nunca llega.

- 16.267 por URL + 4.922 por numero = **21.189 filas** (20.226 de agencias CERTIFIED_COMPLETE, 963 de BEST_AVAILABLE),
  **290 agencias**; equivale al 27 % de la servida actual.
- Ejemplos verificados: `brick` COMPLETE 551/551 -> **26 servidas**; `grupo banker` 850/850 -> 145; `darquier` 570/570 -> 10.
- Arreglo (fuera de la huella, sin recertificar): esas dos reglas deben mirar solo filas servibles (CANDIDATE), como ya
  hace `mismo_aviso_url_nueva`. Entra por una candidata nueva con todas las compuertas.

### 3.3 Otras observaciones
- `re max actitud`: 4 filas servidas de `remax-urbana.com.ar` (posible web de otra oficina) -> verificar identidad.
- Century 21 `szlit` y `revolution` (582 filas) se sirven desde su pagina de oficina en la red: correcto por politica.

## 4. Las 913: esperado + una perdida accidental

- **A nivel agencias, las 913 son la consecuencia esperada de las reglas**: solo 1.816 de 6.597 tienen identidad READY,
  1.117 de esas ya se procesaron, y el 68 % certifica. No falta un bloque de agencias por error.
- **A nivel inventario hay una perdida accidental grande (3.2)**: 21.189 filas certificadas en 290 agencias, 17 de ellas
  con 0 servidas.

## 5. Problemas tecnicos (NEEDS_FIX vigentes)
- Por familia: generic/html_catalog 88, generic/sitemap 55, wordpress 50, generic/no_inventory 42, tokko 29,
  generic/unknown 26, generic/xintel 14, tiv 4, category_html 3, tokko_proxy/mapaprop/wasi 1.
- Por razon: campos no extraidos 125, corrida sin estado OK 98, cero no demostrado 91, fichas fallidas 71,
  segunda corrida no idempotente 38, inventarios distintos entre corridas 32, colapso >80 % contra la linea base 31.
- Por componente del ultimo triaje: extraccion de baja magnitud 77, fuente inaccesible 38, variante no soportada 34,
  extraccion transversal 34, guardian de forma 24, inventario inestable 20, declarado > enumerado 19.

## 6. Ritmo y proyecciones (medidas, no supuestas)
- Cierres por dia (2 workers): 87-236, ~165 de media; **agencias nuevas por dia: 55-60** (el resto es recertificacion por
  cambios de huella).
- Pool que hoy puede entrar a la cola: 694 READY pendientes. Lo demas necesita identidad/web antes de scrapear.

| Meta (procesadas) | Que hace falta | Estimacion |
|---|---|---|
| 1.500 | +230 del pool READY | 2-4 dias |
| 3.000 | +1.730: los 694 READY + verificar web de 568 + ~470 por descubrimiento | 2,5-4 semanas |
| 5.000 | +3.730: exige web verificada para ~2.500 de las 3.476 sin web (rendimiento del descubrimiento no medido) | 2-3 meses, cota incierta |
| 7.000 | No existe en el CANONICO (6.597; 645 sin web propia, 97 conflictivas). Llegar a MAIN 7.004 exige el puente MAIN<->CANONICO para 5.886 ids | frente de identidad aparte |

Detalle y plan de aceleracion: lo absorbe el plan de la mision definitiva (08-10).

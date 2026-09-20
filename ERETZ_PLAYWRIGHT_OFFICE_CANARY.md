# ERETZ - Playwright Office Canary

Fecha de actualizacion: 2026-09-15  
Repositorio: `D:\INMO CAPITAL\Inmo-Capital-main`  
Rama: `release/eretz-private-preview`  
HEAD de referencia: `9461fab0195b84eb4fee99ca0a9195225c0081fe`  
Modo: read-only / no DB writes / no merge / no deploy / no parser change.

## 1. Estado de seguridad

El working tree ya estaba sucio al iniciar esta etapa. No se revirtieron ni
pisaron cambios ajenos.

Stop condition vigente para navegador:

- RAM total: 15,92 GB.
- RAM libre medida: ~1,8 GB.
- Proceso activo: `python -u scripts\run_agency_certification_queue.py --ready --workers 2 --worker 1 --limit 0`.
- Procesos Playwright/Chromium ya activos.

Decision: no ejecutar canary Playwright 25/149 mientras esta condicion siga
activa. Abrir otro navegador aumentaria riesgo operacional y violaria el
criterio de no presionar la maquina.

## 2. Universo canonico materializado

Fuente exacta encontrada:

`D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_OFFICE_PAGES_VALIDADAS.jsonl`

Filtro canonico:

- `clase = NO_OFFICIAL_WEB_FOUND`

Salida local generada:

`_scratch/office_202_empty_canonical.csv`

Resumen:

| metrica | valor |
|---|---:|
| filas | 149 |
| agencias unicas | 149 |
| URLs unicas | 147 |
| avisos esperados | 42.454 |

Distribucion por red:

| red | agencias |
|---|---:|
| REMAX | 137 |
| CENTURY21 | 8 |
| COLDWELL_BANKER | 2 |
| KELLER_WILLIAMS | 2 |

Distribucion por forma de URL:

| forma | agencias |
|---|---:|
| `remax.com.ar/<slug>` | 65 |
| `global.remax.com/.../agents` | 26 |
| `global.remax.com/.../offices` | 7 |
| `remax.com.ar/listings...` | 10 |
| Century 21 | 8 |
| Coldwell Banker | 2 |
| Keller Williams | 2 |
| otras/no clasificadas por forma simple | 29 |

Nota sobre campos historicos: el artefacto fuente registra la clasificacion
`NO_OFFICIAL_WEB_FOUND`, la URL candidata y `avisos_observados`; no registra en
cada fila el status HTTP original ni bytes originales. En el manifest se dejan
como `UNKNOWN_NOT_RECORDED` para no inventar mediciones.

## 3. Canary anterior de 10: descartado como evidencia canonica

Archivo anterior:

`_scratch/wave0_playwright_office_canary_20260914.csv`

Resumen anterior:

| classification | count |
|---|---:|
| `RECOVERED_BY_RENDER` | 6 |
| `PARSER_GAP_AFTER_RENDER` | 1 |
| `NOT_LISTING_SOURCE` | 3 |

Cruce contra el universo canonico 149:

| cruce | resultado |
|---|---:|
| overlap por `agency_id` | 0/10 |
| overlap por URL | 0/10 |

Conclusion: esa muestra demostro que Playwright funciona y que hay casos
recuperables por render, pero no permite inferir recuperacion sobre las 149
agencias canonicas. Debe quedar como prueba de capacidad, no como metrica de
cobertura.

## 4. Canary 25 canonico preparado

Salida preparada:

`_scratch/office_202_empty_canary25_manifest.csv`

Resumen:

| metrica | valor |
|---|---:|
| filas | 25 |
| agencias unicas | 25 |
| URLs unicas | 25 |
| avisos esperados cubiertos | 8.694 |

Distribucion por red:

| red | agencias |
|---|---:|
| REMAX | 13 |
| CENTURY21 | 8 |
| COLDWELL_BANKER | 2 |
| KELLER_WILLIAMS | 2 |

Incluye todas las redes no-REMAX y una muestra REMAX por peso y forma de URL.
Top de la muestra:

| avisos | red | agencia | URL |
|---:|---|---|---|
| 1.276 | REMAX | Remax Solutions | `https://www.remax.com.ar/solutions` |
| 1.126 | REMAX | RE/MAX Focus | `https://global.remax.com/es/propiedades/uruguay/oficina/venta/pando/800-francisco-menezes-15600/940101193-49` |
| 1.124 | REMAX | RE/MAX Premium | `https://global.remax.com/en/agents/argentina/palermo-nuevo/pedro-reh/421831287` |
| 1.067 | REMAX | RE/MAX UNO - San Isidro | `https://www.remax.com.ar/uno` |
| 975 | REMAX | Remax Roble | `https://www.remax.com.ar/roble` |
| 955 | REMAX | RE/MAX Data Work | `https://www.remax.com.ar/datawork` |

## 5. Runner read-only con checkpoint

Script preparado:

`_scratch/office_browser_canary.py`

Propiedades:

- salida CSV con checkpoint/resume por `agency_id`;
- sin DB writes;
- sin screenshots;
- un browser/context secuencial;
- bloqueo de `image`, `font`, `media`;
- medicion HTTP por `requests`;
- medicion renderizada con Playwright;
- clasificacion en:
  - `RECOVERED_BY_RENDER`;
  - `PARSER_GAP_AFTER_RENDER`;
  - `EMPTY_IN_REAL_BROWSER`;
  - `EXTERNAL_ANTIBOT`;
  - `NEEDS_CONNECTOR`;
  - `NOT_LISTING_SOURCE`;
  - `ERROR` via notas si falla browser/parser.

Comando seguro cuando la maquina este liberada:

```powershell
$env:MAX_ACTIVE_BROWSERS='1'
python _scratch/office_browser_canary.py --input _scratch/office_202_empty_canary25_manifest.csv --output _scratch/office_202_empty_canary25_results.csv
```

Escalado permitido solo si el canary 25 termina estable:

```powershell
$env:MAX_ACTIVE_BROWSERS='1'
python _scratch/office_browser_canary.py --input _scratch/office_202_empty_canonical.csv --output _scratch/office_202_empty_149_results.csv
```

## 6. Evidencia RE/MAX local existente

Artefactos externos inspeccionados:

- `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_REMAX_SITEMAP_SONDEO.jsonl`
- `D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\ERETZ_REMAX_CANARIO.jsonl`

Resumen:

| artefacto | resultado |
|---|---|
| sitemap sondeo | 35 oficinas observadas, 31 en padron, 4 fuera de padron |
| canario RE/MAX listing | 200/200 filas como `ANTIBOT_DESAFIO_WAF`, bytes 1.971 |

Lectura: RE/MAX necesita tratamiento separado entre:

- sitemap/catalogo con atribucion de oficina;
- fichas con WAF/202 deterministico;
- paginas de oficina que pueden ser home institucional, ficha agente, ficha global o slug local.

## 7. Decision actual

`PLAYWRIGHT_OFFICE: CANARY_PREPARED_NOT_RUN`

Motivos:

1. Ya existe universo canonico 149/42.454.
2. La muestra anterior 10 no cruza con ese universo.
3. El canary 25 canonico y el runner estan listos.
4. La maquina esta bajo stop condition: poca RAM libre y procesos Playwright/queue activos.
5. Ejecutar ahora daria una medicion ruidosa y con riesgo operacional.

## 8. Siguiente paso exacto

1. Esperar ventana sin worker `run_agency_certification_queue` ni Playwright
   activo.
2. Confirmar RAM libre razonable antes de abrir browser.
3. Ejecutar solo canary 25 con `MAX_ACTIVE_BROWSERS=1`.
4. Clasificar los 25 en los buckets anteriores.
5. Decidir si:
   - Playwright recupera listings reales;
   - el problema es parser sobre DOM renderizado;
   - son paginas institucionales sin inventario;
   - requieren conector de red;
   - hay anti-bot/202 que no conviene atacar ahora.

No se ejecuto:

- push;
- deploy;
- merge;
- cherry-pick;
- rebase;
- reset;
- DB writes;
- Supabase writes;
- migraciones;
- workers productivos;
- cambios de parser;
- fingerprint changes;
- extractor semantico.

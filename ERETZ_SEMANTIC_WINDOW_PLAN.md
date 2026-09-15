# ERETZ - Semantic Window Plan

Fecha: 2026-09-15  
Modo: plan previo, no implementado.  
Objetivo: ordenar que cambios semanticos conviene hacer despues de medir
canaries, minimizando radio de huella y evitando invalidar trabajo certificado.

## 1. Principio

No se activa extractor semantico ni se toca parser/fingerprint durante la cola
activa. La ventana semantica debe ser una fase separada, con fixtures,
canaries y radio de invalidacion explicito.

## 2. Precondiciones

Antes de abrir la ventana:

1. Working tree entendido y sin mezclar cambios ajenos.
2. Cola/worker productivo detenido por decision explicita, no por este plan.
3. Manifest canonico 149 ya materializado.
4. Canary 25 ejecutado y clasificado.
5. Decision escrita sobre que familias entran:
   - parser gap DOM;
   - RE/MAX sitemap;
   - RE/MAX office/global;
   - Century21;
   - Coldwell;
   - Keller Williams.
6. Fixtures locales por familia.
7. Tests antes de cambiar codigo.

## 3. Ranking preliminar

| prioridad | candidato | impacto | radio esperado | decision actual |
|---:|---|---|---|---|
| 1 | Parser detail URL gaps medidos en DOM renderizado | alto si canary los confirma | bajo/medio | esperar canary 25 |
| 2 | RE/MAX sitemap/catalogo con atribucion por office id | alto, ~25.000 fichas legibles estimadas | familia nueva | planificar conector nuevo |
| 3 | Normalizacion de URL inicial con paginado/filtros | medio/alto por errores ya documentados | medio | fixtures primero |
| 4 | Tokko/PHP plano variante no soportada | medio, casos claros en runbook | medio | tests por casos |
| 5 | Century21/Coldwell/Keller | menor volumen que RE/MAX pero concentrado | familia nueva | investigar despues de RE/MAX |
| 6 | Soft-404/home institucional | mejora calidad, no cobertura bruta | bajo | solo clasificador/diagnostico |

## 4. Radio de huella esperado

### Parser detail URL DOM

Alcance:

- `scraper/playwright_scraper.py`
- tests en `tests/test_parser_detail_url_candidates.py`

Radio:

- bajo si se limita a discovery de links dentro de DOM renderizado;
- medio si cambia heuristicas genericas compartidas.

Gate:

- fixtures con falsos positivos globales;
- confirmar que no aumenta parser links en home/global sin identidad de oficina.

### RE/MAX sitemap/catalogo

Alcance recomendado:

- estrategia nueva, por ejemplo `generic/remax_sitemap` o conector dedicado;
- no mezclar en parser generico;
- no escribir a DB sin decision de dedupe/fuente ganadora.

Radio:

- familia nueva solamente;
- no deberia invalidar las 374 certificadas existentes si no toca shared/base.

Gates:

- office id estable;
- mapping office id/name/slug contra padron;
- dedupe entre red y web propia;
- muestra de fichas legibles vs WAF/202 deterministico.

### Normalizacion de URL inicial

Problema:

- algunas webs registradas empiezan en pagina interna con paginado/filtros y
  pierden inventario.

Radio:

- medio, porque cambia punto de partida del scraping.

Gate:

- fixtures por caso real;
- antes/despues sobre agencias afectadas;
- no tocar fuentes que ya certificaron completo sin evidencia.

### Tokko/PHP variante no soportada

Problema:

- hay casos donde el inventario existe en PHP plano o variantes Tokko y el
  conector actual enumera cero.

Radio:

- medio si se agrega variante de conector;
- bajo si se agrega diagnostico previo.

Gate:

- fixtures de `/ficha.php?id=...`;
- conteo esperado local;
- no aplicar sobre todo Tokko sin muestra.

## 5. Candidatos fuera de ventana actual

No hacer ahora:

- frontend;
- mobile;
- cambios visuales;
- fingerprint global;
- merge de ramas historicas;
- Playwright masivo;
- bypass anti-bot;
- Supabase writes;
- publish/promocion;
- analisis estadistico en DB productiva.

## 6. Secuencia propuesta

### Ventana 1 - parser gap probado

1. Ejecutar canary 25.
2. Separar `PARSER_GAP_AFTER_RENDER`.
3. Crear fixtures HTML de esos casos.
4. Agregar tests rojos.
5. Implementar minimo cambio.
6. Re-ejecutar canary del subset.
7. Documentar radio.

### Ventana 2 - RE/MAX sitemap

1. Releer sitemap y muestras sin DB writes.
2. Medir office coverage contra padron.
3. Definir dedupe/fuente ganadora.
4. Crear conector/estrategia aislada.
5. Tests con fixtures de ficha legible y ficha WAF/202.
6. Canary local.
7. Recien despues proponer cola productiva.

### Ventana 3 - redes restantes

1. Century21: confirmar sitemap 404 y buscar endpoint publico.
2. Coldwell: confirmar corte de conexion y alternativa.
3. Keller: medir si hay fuente listable.
4. No prometer volumen sin medicion.

## 7. Checklist antes de activar cualquier cambio

- [ ] El cambio tiene tests unitarios/fixtures.
- [ ] El cambio tiene muestra antes/despues.
- [ ] El cambio declara estrategia/conector afectado.
- [ ] El cambio no toca DB productiva.
- [ ] El cambio no invalida certificaciones fuera de su familia.
- [ ] Hay rollback simple.
- [ ] Hay reporte de falsos positivos.

## 8. Decision actual

`SEMANTIC_WINDOW: NOT_STARTED`

La proxima accion no es implementar semantica. Es correr el canary 25 canonico
en una ventana segura y usar sus buckets para decidir que semantica vale la
pena tocar.

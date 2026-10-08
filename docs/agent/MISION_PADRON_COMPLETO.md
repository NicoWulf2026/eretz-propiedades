# MISION — Todo el padron, todo el inventario, todos los datos (plan 2026-10-08)

Derivado de la auditoria de cobertura (`AUDITORIA_COBERTURA_NACIONAL_2026-10-08.md`) y de la auditoria del sistema
(evidencia citada en cada punto; scripts en `_b_scratch/sprint/auditoria_cobertura_2026-10-08/`).

## 1. Estado real (medido el 08-10)
- **Dos padrones que no se hablan.** MAIN (`inmobiliarias_main`, produccion) = 7.004 agencias, 5.210 con web cargada
  (74 %), 3.187 con avisos activos (auditoria 27-08). CANONICO (roomix, el que scrapea la cola) = 6.597, de las cuales solo
  1.095 estan vinculadas a MAIN; 5.886 agencias de MAIN no tienen identidad canonica y 5.428 canonicas no estan en MAIN.
- **Lo que se sirve hoy:** 913 agencias / 77.740 propiedades (API local, `sprint_rc5`). Produccion (Supabase) tiene
  257.073 publicaciones historicas de calidad heterogenea (ciudad 43 %, coordenadas 25 %, 0 % fecha de publicacion,
  duplicados) cargadas por el pipeline A legado; esta congelada desde agosto: la credencial de escritura falla (READY #1).
- **La cola** solo toma agencias con identidad READY (1.816 de 6.597). Proceso 1.270; certifica el 68 %.
- **Perdida accidental:** 21.189 filas certificadas en 290 agencias no llegan a la snapshot (regla del constructor).
- **Capacidad:** 2 workers saturados: 286 horas-worker en octubre para 1.372 certificaciones; ~165 cierres/dia pero solo
  55-60 agencias NUEVAS/dia: ~2/3 se va en recertificar por cambios de huella, porque cada certificacion baja el
  catalogo completo DOS veces y no hay almacen de paginas: cambiar el extractor obliga a volver a bajar todo.
- **Datos por propiedad:** el modelo tipado tiene 19 campos. Antiguedad (41k fichas), condicion (27k), orientacion (20k),
  cocheras (16k), disposicion (16k), plantas (14k), expensas (11,7k), apto credito (7k), codigo de origen (34k) y fecha de
  modificacion (7,5k) YA se leen y quedan en `extra`: no llegan ni a la snapshot ni a la API.

## 2. Por que no scrapeamos las ~7.000
1. Identidad: 4.786 canonicas nunca entran a la cola (3.476 sin web, 568 con web sin verificar, 645 solo portal, 97
   conflictivas) y 5.886 agencias de MAIN no tienen identidad canonica. **Es el cuello principal, no el scraper.**
2. Capacidad mal usada: doble descarga por certificacion + recertificacion por red ante cada cambio de extractor.
3. Familias sin soporte: 294 NEEDS_FIX (html_catalog 88, sitemap 55, wordpress 50, sin inventario 42, tokko 29...).
4. Ingestion cortada: el pipeline nuevo termina en una SQLite local; la base no recibe nada desde agosto.
5. Modelo de datos chico: lo que se lee no se modela ni se sirve.

## 3. Obstaculos tecnicos principales
Identidad/descubrimiento de webs; almacen de paginas inexistente; concurrencia por proceso (2-3) en vez de por host;
certificacion que duplica el trafico; plantillas no leidas (rotulos con marcado, mapas por JS, catalogos por JS,
conteos en prosa); constructor con reglas que pierden filas; base de produccion inaccesible.

## 4. Arquitectura propuesta
```
REGISTRO UNIFICADO DE INMOBILIARIAS (MAIN ∪ CANONICO ∪ hosts de avisos historicos; resolucion de entidades)
  └─ DESCUBRIMIENTO DE WEB (fuentes gratis primero; pago al final) + VERIFICACION automatica
       └─ DETECCION DE PLATAFORMA (Tokko, WordPress+temas, Wasi, KiteProp, Xintel/Amaira, Site Builder, RealHomes...)
            └─ CRAWLER POR HOST (asincrono, N hosts en paralelo, 1 pedido por host, robots, backoff 403/429)
                 └─ ALMACEN DE PAGINAS (crudo + metadatos, por URL y fecha, comprimido, en E:)
                      └─ EXTRACCION offline por familia + generica (JSON-LD, APIs publicas, render JS si hace falta)
                           └─ NORMALIZACION + VALIDACION + AUDITOR (publicado vs extraido) + CERTIFICACION v2
                                └─ BASE LOCAL ERETZ (Postgres 17, migraciones aditivas, procedencia por campo)
                                     ├─ SNAPSHOT/API (derivados)
                                     └─ SINCRONIZACION a produccion (rol escritor P18) cuando haya credencial
```

## 5. Que conservo
Conectores y su conocimiento acumulado (tokko, wordpress, wasi, generico con ~60 variantes), auditor de senales y
triaje, ledger, geografia canonica (poligonos, georef), politicas P1-P24 (retiros con muerte demostrada, fail-closed,
robots, portales no son fuente), compuertas P2/Regression Gate, API v2 + frontend, tests (4.073).

## 6. Que cambio
- **Certificacion v2:** el catalogo se descarga UNA vez; la segunda pasada es de enumeracion (barata) + muestra de fichas.
  La idempotencia se mide sobre la enumeracion y la muestra, no sobre una segunda descarga completa.
- **Recertificacion por replay:** cambiar un extractor re-extrae desde el almacen; la red solo se usa para frescura
  (sitemap lastmod, ETag/If-Modified-Since, enumeracion).
- **Concurrencia por host** en lugar de 2 procesos: el limite de cortesia es por sitio, no global.
- **Modelo de datos ampliado** (punto 10) y snapshot/API que lo sirven.
- **Base local como sistema de registro** del pipeline nuevo; la snapshot deja de ser el final de la tuberia.
- **Constructor:** reglas de "ya conocida" solo contra filas servibles (arregla las 21.189).
- **Huella:** se mantiene como identidad del extractor, pero invalida por replay, no por re-crawl.

## 7. Que automatizo
Union de padrones y deduplicacion de agencias; verificacion de webs; deteccion de plataforma; asignacion de conector;
crawl y frescura; replay ante cambios; triaje de defectos con agrupacion por familia; construccion de candidata +
compuertas; carga a la base local; tablero de cobertura y alarma de "agencia olvidada".

## 8. Como llego a todas las inmobiliarias
Orden por costo: (a) webs que ya existen en datos propios: `inmobiliarias_main.web` (5.210; requiere lectura de
produccion), hosts de avisos historicos (999 agencias de MAIN, 519 sin identidad canonica), candidatas sin verificar
(863 canonicas con 1-3 candidatas), 568 con web sin verificar; (b) verificacion automatica (abrir la pagina, nombre,
telefono, dominio .ar); (c) busqueda paga solo para el remanente (requiere aprobar gasto). Las que no tengan web propia
quedan con estado terminal demostrado (NO_INDEPENDENT_WEBSITE con evidencia), nunca "pendiente" para siempre.

## 9. Catalogo completo por inmobiliaria
Enumeracion multi-fuente y cruzada: sitemap + listado paginado + API publica del sitio; prueba positiva de fin de
catalogo (ya existe); total declarado vs enumerado; dos enumeraciones independientes; ninguna cota artificial (sin
MAX por agencia; presupuesto por tiempo, reanudable).

## 10. Mas campos
Tipar y servir: cocheras, toilettes, suites, plantas, superficies (descubierta, semicubierta, terreno), frente, fondo,
antiguedad, condicion/estado, orientacion, disposicion, expensas (+moneda), apto credito, codigo de origen, agente,
fecha de publicacion/modificacion, estado de la fuente (reservado/alquilado), amenities/servicios (lista), videos, tour
virtual, planos. Procedencia por campo. Auditor "publicado vs extraido" extendido a cada campo nuevo.

## 11. Ingreso automatico a la base
Cada corrida certificada se carga sola a la base local (upsert por identidad de aviso, historial de cambios, nunca
DELETE: retiro = cambio de estado con evidencia). La snapshot y la API se derivan de la base. La sincronizacion a
produccion usa el rol escritor de minimo privilegio con migraciones aditivas (READY #1-#3): se ejecuta en cuanto haya
credencial, con backup + restore probado antes.

## 12. Capacidad necesaria
Medido: ~105 fichas por agencia y ~3,6 s por ficha con cortesia de 1,5 s por host. Con una sola descarga y 16 hosts en
paralelo: ~5.000 agencias x ~110 pedidos = ~550k pedidos ≈ 1-2 dias de crawl efectivo. El crawl NO es el cuello; lo son
identidad, plantillas y la ingenieria de este plan. Disco: E: 872 GB libres (almacen estimado < 50 GB comprimido).

## 13. Como mido el avance (tablero diario)
Embudo del registro unificado (cada agencia en exactamente un estado), agencias con inventario certificado, propiedades
reales, cobertura por campo (publicado vs extraido), frescura, NEEDS_FIX por familia, perdidas del constructor = 0.

## 14. Ninguna agencia olvidada
Invariante automatica: |registro| = |MAIN ∪ CANONICO ∪ nuevas| y cada agencia tiene estado + proxima accion + fecha;
una agencia sin cambio de estado en N dias aparece en la alarma. El embudo se recalcula en cada corrida.

## 15. Mantenimiento
Recrawl por frescura (lastmod/ETag); deteccion de cambio de plataforma o de dominio (redirecciones, colapso de
enumeracion); altas nuevas desde MAIN y desde hosts nuevos vistos en avisos; triaje por familia con replay.

## 16. Fecha objetivo
**30-11-2026: todo el registro unificado abordado** (cada agencia con web certificada o con estado terminal demostrado)
y el pipeline FUENTE -> BASE automatico. Hitos medibles:
- 12-10: beta (informe final del sprint) + arreglo de las 21.189 filas en candidata.
- 19-10: registro unificado + descubrimiento con fuentes propias + verificacion automatica corriendo.
- 26-10: almacen de paginas + crawler por host + certificacion v2 en paralelo a la cola actual.
- 02-11: modelo de datos ampliado de punta a punta (extraccion -> base local -> snapshot -> API).
- 15-11: >= 3.000 agencias procesadas; familias NEEDS_FIX principales resueltas.
- 30-11: registro completo abordado.
Dependencias externas que pueden mover la fecha: lectura de produccion (web de 5.210 agencias), credencial de
escritura (READY #1) y aprobacion de gasto de busqueda para el remanente sin web.

## Reglas que no cambian
No borrar la base. No inventar datos. No cargar filas a mano: toda propiedad entra por el scraper. Fail-closed.
Portales no son fuente. robots.txt. Acciones productivas irreversibles: con backup + restore probado y confirmacion.

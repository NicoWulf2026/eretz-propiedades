# ERETZ — handoff

Para retomar desde una sesión nueva: arrancar Claude Code en `D:\INMO CAPITAL\eretz-unified`.
Reglas: `CLAUDE.md` + `.claude/rules/` (cargan solas). Estado: `docs/agent/CURRENT_STATE.md`.
Historia: Git (`git log --since=2026-09-25`).

## Recién cerrado (25-09)
- Snapshot: frescura desde NEEDS_FIX por campos, títulos/eslóganes del sitio; v4d verificada.
- Portales/directorios como web oficial READY (8 dominios) — `62dbc899c4`, `eeabc94083`.
- `generico`: fotos del visor, `/cdn-cgi/` (`6ee927bb80`); ambientes del título (`0ee0882403`,
  117 fichas); `addressNeighborhood` como barrio (`2961c3ec68`).
- `wasi`: «Habitaciones:» = dormitorios y el parser `scripts/wasi_fingerprint.py` entra en la
  huella (`942e0825e2`). Test general: todo módulo propio que importa un conector está en su huella.
- Geografía compartida: la «ciudad» publicada que es el departamento de la localidad publicada como
  barrio (`fenix` Capital→Posadas, 512 fichas; 7 más, todas correctas) — `2961c3ec68`.
- Gate 14:3x: 200 agencias; 3 pérdidas revisadas y firmadas (alpha ×2 CORRECCION, varesse arreglado).
- Diferidas firmadas 16:0x: `garcia andreu` (rangos de emprendimiento), `domus propiedades` (bloqueo
  puntual), `fj lujan` (TFW mal ruteado), `garbero` (1 ficha + taxonomía como ficha).
- Optimización de Claude Code: `docs/agent/CLAUDE_CODE_OPTIMIZATION.md`.

## Corriendo
- Cola con 2 workers + relanzador + vigilante. Mirarla solo si hay paradas.

## No rehacer
- Guardia de título repetido en el runner: descartada con medición.
- `armanino`: API de Tokko con clave embebida en su bundle → **no se usan claves ajenas**.
- `estela d onofrio`: el certificador tiene respaldo a `generico`; el diagnóstico liviano no.
- `building`: las 220 «fichas» imagen del 21-09 ya no se enumeran con el código de hoy (81 URLs, 3/3 ok).
- `corporacion`, `cannone`: ya resueltos por el código de hoy; se recertifican solos.
- 5h (mínimo de 40 caracteres en el runner): radio 0 en los paquetes vigentes.

## Próxima prioridad (por impacto medido)
1. **Ventana compartida del auditor/certificador** (`shared/certifier`, invalida todo; hacerla en
   un solo commit):
   - ruteo: sondear la portada y usar `tokko` si es TFW (`static.tokkobroker.com/tfw`) —
     `fj lujan` (98→2 por ruteo), `coldwell banker destino`; 4.244 agencias sin plataforma detectada;
   - señal de fuente: un rango «N - M» no es valor provisto (`garcia andreu`); «Consultar» en el
     precio estructurado de `wasi` (3 fichas); señal de operación más amplia que el extractor (5c).
2. **NEEDS_FIX no idempotentes** (21): la mayoría difiere en `descripcion` (ferrari 149/157,
   bottega 22/30) o por entidades HTML en `titulo` (bondar, dorsoli). Script de medición:
   comparar `properties_run1/2.jsonl` por `hash_dedup`. Ver si la descripción varía en la fuente.
3. **Lote `generico` de radio chico** (agrupar): `bardi` dirección/barrio como pares rótulo/valor
   (90 fichas); taxonomías WordPress como ficha (`/estado-propiedad/`, `garbero`); `cometto`
   (categorías `propiedades_ver2.php`); `del parque` (`og:type=article` en fichas reales);
   `bunader` (enumera listados); `alianza` (descripción `<ul>` bajo acordeón); `fios`
   (`.show-more`, foto ajena); `cantale` («Venta» suelta); precio accesorio `caruso`; operación
   solo en la ruta del catálogo (`bottai` 180, `constant` 24).
4. Regression Gate tras cada tanda (comando en `.claude/rules/scraper.md`).
5. Beta del backend (`docs/ERETZ_UNIFICATION_PLAN.md` § «Backend beta confiable»).

## Trampas actuales
- Un cambio de huella sin commitear lo levantan los workers al relanzarse: commitear enseguida.
- Un archivo que la guarda de workers VIEJOS no vigila (p. ej. uno recién agregado a la huella)
  no los detiene: pedir relanzamiento con bandera `OPERACION` (formato en `relanzar_la_cola.py`).
- Los paquetes NEEDS_FIX con motivos solo de campo alimentan la snapshot.

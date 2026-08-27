# Release process

Este documento describe el procedimiento. **No autoriza desplegar a producción**:
la aprobación humana explícita sigue siendo un paso, no un trámite.

Un release candidate exige CI de backend y frontend en verde, cero hallazgos de
dependencias de severidad alta, un set de migraciones aditivo revisado, un plan
de recuperación, ningún error de scraper interno sin resolver, y aprobación
humana explícita para cambios de producción.

## 1. Antes de proponer un release

Se corren en el worktree, sobre el commit exacto que se va a desplegar:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
npm run test
npm run test:e2e      # requiere Preview levantado
npm run test:a11y
```

Y del lado backend, lo mismo que corre CI (`.github/workflows/ci.yml`):
`compileall`, `pytest`, `ruff`, `mypy`, `pip_audit`, y la guarda que bloquea
`verify=False`.

Además, antes de cada commit: diff revisado, escaneo de secretos, y `_scratch`
fuera del árbol versionado.

## 2. Qué se registra

- SHA exacto del commit.
- Hashes de los artefactos.
- Versión y fingerprint del Quality Gate (`ERETZ_PREVIEW_GATE_SHA256`,
  `ERETZ_PREVIEW_GATE_FINGERPRINT`). Un release que cambia el gate cambia lo que
  se ve: no es un detalle de configuración.
- Migraciones incluidas, con su rollback correspondiente.

## 3. Preview

El Preview es privado y **fail-closed para indexación**: `robots()` devuelve
`disallow: /` y el layout emite `noindex, nofollow, nocache, noarchive,
nosnippet`. No existe una variable que habilite indexación en esta fase, y esa
ausencia es deliberada. Hay tests que lo fijan.

Sobre el Preview se verifica: cabeceras de seguridad, Explorer, mapa, ficha,
búsqueda, conteos, y que no salga **ninguna** request browser-side a Supabase
Data API.

## 4. Aprobación

Producción requiere una persona que apruebe el SHA concreto. No se aprueba "la
rama".

## 5. Rollback de aplicación

El artefacto anterior vuelve a promoverse. Es la vía rápida y no depende de
reconstruir nada.

Un rollback de aplicación **no deshace un cambio de base**. Si el release
incluyó una migración, ver el punto siguiente antes de dar el incidente por
cerrado.

## 6. Rollback de base

Toda migración entra con su rollback al lado, y el par vive junto:

```
supabase/migrations/<ts>_<nombre>.sql
supabase/rollbacks/<ts>_<nombre>.rollback.sql
```

Reglas que no se negocian:

- **Aditivo primero.** Una migración que sólo agrega puede convivir con la
  versión anterior de la aplicación, y entonces el rollback de aplicación
  alcanza por sí solo.
- **Nada destructivo en el mismo release que lo deja de usar.** Primero se
  despliega el código que ya no lee la columna; el `DROP` va en un release
  posterior. Si los dos van juntos, el rollback de aplicación deja al código
  viejo leyendo algo que ya no existe.
- **El rollback se ensaya antes**, no durante el incidente.
- **Un rollback puede reabrir una exposición.** El de ACL PostGIS restaura
  privilegios de escritura para `anon`/`authenticated`: es su trabajo, y quien
  lo ejecute tiene que saberlo antes.

Cuando el rollback no es viable —datos ya escritos con el formato nuevo— la
salida es una migración hacia adelante que corrija, o un restore de backup
probado. No se improvisa sobre producción.

## 7. Cambios de ACL y permisos

Van por `supabase/proposals/`, no por el pipeline normal, y necesitan
autorización explícita.

Antes: correr el verificador de sólo lectura y guardar la salida.
Después: correrlo otra vez y comparar.

```bash
psql "$ERETZ_PREVIEW_RO_URL" -f supabase/proposals/20260827_public_postgis_acl_verify.sql
```

## 8. Feature flags

Cuando una capacidad pueda quedar a medias entre despliegues, entra apagada
detrás de una variable de entorno server-only, y se enciende en un cambio
aparte. Así el apagado no necesita un redeploy.

No se usan flags para tapar trabajo incompleto en la UI: si una función todavía
no funciona de verdad, no se muestra el botón.

## 9. Después del release

Smoke test de sólo lectura y revisión de los logs estructurados: cada request
deja una línea JSON con `route`, `status`, `outcome` y `durationMs`, y cada
respuesta lleva su `x-request-id`. Un pico de `outcome: server_error` justo
después de promover es la señal para volver atrás.

## Qué falta para que esto sea un proceso de producción

Lo de arriba está documentado y es ejercitable, pero todavía **no fue ejercitado
de punta a punta**. Antes de una beta pública faltan: un rollback ensayado de
verdad, un restore de backup probado, alertas sobre la tasa de error, y SLO
declarados. Sin eso, esto es un procedimiento, no una garantía.

# ERETZ Propiedades

ERETZ consolida publicaciones de inmobiliarias argentinas mediante **Pipeline A**
y las publica desde Supabase a un frontend Next.js. El repositorio contiene el
scraper Python, herramientas operativas y de calidad, migraciones SQL y el
frontend público.

## Estado de seguridad

- Pipeline B y las escrituras en Neon están fuera del flujo autorizado.
- El máximo operativo es `MAX_ACTIVE_BROWSERS=2`.
- La verificación TLS es obligatoria.
- Las URLs externas pasan por una política central anti-SSRF.
- No se desactivan propiedades durante auditorías o corridas de calidad.
- El sitio debe permanecer `noindex` hasta aprobación humana.

## Inicio local

1. Copiar `.env.example` a `.env` y completar los secretos fuera de Git.
2. Crear un entorno virtual.
3. Instalar `python -m pip install -r requirements.lock`.
4. Instalar Chromium con `python -m playwright install chromium` solo si la
   tarea requiere navegador.
5. Ejecutar `python -m pytest` desde la raíz.
6. Para el frontend: `cd frontend`, `npm ci`, `npm run lint`,
   `npm run typecheck`, `npm test` y `npm run build`.

La operación, reanudación, migraciones y respuesta a incidentes se documentan
en `docs/`.

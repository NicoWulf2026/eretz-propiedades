# ERETZ Propiedades

ERETZ consolida publicaciones de inmobiliarias argentinas mediante **Pipeline A**
y las publica desde Supabase a un frontend Next.js. El repositorio contiene el
scraper Python, herramientas operativas y de calidad, migraciones SQL y el
frontend público.

## Estructura

- `frontend/` — aplicación pública Next.js (App Router, TypeScript, Tailwind).
- `scraper/` — scraper Python (Playwright) y pipelines de ingesta.
- `scripts/` — herramientas operativas y de calidad.
- `migrations/` y `supabase/migrations/` — migraciones SQL (historial preservado).
- `tests/` — pruebas del backend/scraper (`python -m pytest`).
- `docs/` — documentación operativa; `docs/obsidian/` conserva notas históricas.

## Catálogo, Quality Gate y acceso

- El catálogo público lo define un **Quality Gate privado** aplicado en la capa de
  aplicación (server-only); es la única autoridad de visibilidad.
- El acceso a la base es **server-only**; la **Data API de Supabase está OFF**.
- El scraping productivo **no** se ejecuta desde el frontend.
- El Preview está protegido por **Vercel Authentication** y permanece `noindex`.
- **Production no forma parte de esta fase.**

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

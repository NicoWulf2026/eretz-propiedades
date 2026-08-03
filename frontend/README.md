# ERETZ Propiedades — frontend público

Beta local del buscador inmobiliario de ERETZ Propiedades. Usa Next.js App Router, TypeScript,
Tailwind CSS, Supabase público y Leaflet.

## Desarrollo

1. Copiar `.env.local.example` a `.env.local`.
2. Completar `SUPABASE_URL` y `SUPABASE_ANON_KEY` (rol `anon`, nunca `service_role`).
3. Para el preview local, activar `ERETZ_PREVIEW_QUALITY_GATE=true` y apuntar
   `ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH` al manifest operativo fuera de `public/` y de Git.
4. Mantener `NEXT_PUBLIC_SITE_INDEXING=false` durante la beta.
5. Ejecutar:

```bash
npm install
npm run dev
```

Rutas principales:

- `/`: home y buscador principal.
- `/propiedades`: búsqueda, filtros, orden y paginación por cursor.
- `/propiedad/[id]`: detalle, galería, mapa y contacto directo.
- `/contacto`, `/baja-o-correccion`, `/privacidad`, `/terminos`.

## Gates

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm audit
```

El servidor utiliza exclusivamente el contrato `anon` autorizado de `public.propiedades`; no hay
`service_role`, RPC privadas, autenticación, pagos ni captura propia de leads. Las variables
`SUPABASE_*` son server-only. Las variantes `NEXT_PUBLIC_*` se conservan únicamente por
compatibilidad local y no deben configurarse en un preview remoto.

## Preparación de despliegue

Configurar `NEXT_PUBLIC_SITE_URL` con el dominio canónico antes del build. Habilitar
`NEXT_PUBLIC_SITE_INDEXING=true` solamente tras aprobar dominio, contenido legal y lanzamiento.
La configuración incluye headers de seguridad, robots, sitemap y metadata OpenGraph.

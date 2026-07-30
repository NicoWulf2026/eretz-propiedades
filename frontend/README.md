# ERETZ Propiedades — frontend público

Beta local del buscador inmobiliario de ERETZ Propiedades. Usa Next.js App Router, TypeScript,
Tailwind CSS, Supabase público y Leaflet.

## Desarrollo

1. Copiar `.env.local.example` a `.env.local`.
2. Completar `NEXT_PUBLIC_SUPABASE_URL` y `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. Mantener `NEXT_PUBLIC_SITE_INDEXING=false` durante la beta.
4. Ejecutar:

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

El navegador utiliza exclusivamente el contrato anon autorizado de `public.propiedades`; no hay
`service_role`, RPC privadas, autenticación, pagos ni captura propia de leads.

## Preparación de despliegue

Configurar `NEXT_PUBLIC_SITE_URL` con el dominio canónico antes del build. Habilitar
`NEXT_PUBLIC_SITE_INDEXING=true` solamente tras aprobar dominio, contenido legal y lanzamiento.
La configuración incluye headers de seguridad, robots, sitemap y metadata OpenGraph.


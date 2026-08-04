# ERETZ Propiedades — frontend público

Beta local del buscador inmobiliario de ERETZ Propiedades. Usa Next.js App Router, TypeScript,
Tailwind CSS, PostgreSQL server-only y Leaflet.

## Desarrollo

1. Copiar `.env.local.example` a `.env.local`.
2. Completar `SUPABASE_DATABASE_URL` con un usuario de base de datos de solo lectura. Nunca usar prefijo `NEXT_PUBLIC_`.
3. Para el preview local, activar `ERETZ_PREVIEW_QUALITY_GATE=true` y apuntar
   `ERETZ_PREVIEW_GATE_ASSIGNMENTS_PATH` al manifest operativo fuera de `public/` y de Git.
4. Ejecutar:

```bash
npm install
npm run dev
```

Rutas principales:

- `/`: explorador mapa-primero.
- `/propiedades`: alias funcional del explorador, con filtros, viewport y cursor.
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

El navegador sólo consulta rutas de ERETZ. El servidor abre transacciones PostgreSQL `READ ONLY`,
aplica el Quality Gate privado y serializa contratos públicos mínimos. No hay PostgREST, cliente
Supabase, `service_role`, autenticación, pagos ni captura propia de leads.

## Preparación de despliegue

Configurar `NEXT_PUBLIC_SITE_URL` con la URL privada antes del build. Phase A permanece siempre
`noindex`; robots bloquea todo y el sitemap no emite URLs. Un lanzamiento público requiere un cambio
de código explícito, revisión legal y autorización separada.

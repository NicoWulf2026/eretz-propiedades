---
paths:
  - "frontend/**"
---
# Frontend

- Mobile está congelado: no cambiar layouts ni componentes móviles.
- Identidad visual vigente: `docs/ERETZ_IDENTITY_V1.md` (base clara, verde de marca, terracota de
  selección). No reintroducir el violeta de Roomix ni el navy/oro.
- `frontend/AGENTS.md` trae reglas de UX previas al rebranding (dice «Inmocapital»): la marca es
  ERETZ Propiedades.
- Gates antes de commitear: `npm run typecheck`, `npm run lint`, `npm test` (Vitest); e2e con
  `npm run test:e2e` cuando cambie un flujo.
- La API que consume es `api/v2.py` sobre la snapshot local; el contrato está en `api/` y
  `docs/API_V2_CONVERGENCE.md`.
- Deploy (Vercel) es una acción productiva: no se ejecuta sola.

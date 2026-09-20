# ERETZ Frontend Current State

Audit date: 2026-09-15  
Mode: inspection and documentation only. This report is the only file created or modified.  
Scope: desktop web at 1440, 1366, 1280 and 1024 px. Mobile remains frozen.  
Canonical target: `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a\frontend` at `ea7708f79fdc1a535d10f8f68322b5c2ce386668`.

# Frontend Discovery

## All Frontend Candidates

Discovery covered every registered Git worktree, every local/recorded-remote/tag ref containing a `frontend` tree, and nearby directories under `D:\INMO CAPITAL` containing `package.json` or Next.js configuration. Eight physical candidates are worktrees of the same repository and remote, `https://github.com/NicoWulf2026/eretz-propiedades.git`. No independent second frontend repository was found. Of 38 refs, 29 contain `frontend`; those reduce to nine distinct frontend trees.

| ID | Path / ref | Branch and HEAD | Frontend tree | State | Assessment |
|---|---|---|---|---|---|
| F1 | `D:\INMO CAPITAL\Inmo-Capital-main\frontend` | `release/eretz-private-preview` · `9461fab0` | `20bb81e4` | Parent dirty; frontend clean | Old release frontend |
| F2 | `D:\INMO CAPITAL\eretz-audit\frontend` | detached · `8521d470` | `20bb81e4` | Parent dirty; frontend clean | Same frontend as F1 |
| F3 | `D:\INMO CAPITAL\eretz-integration\frontend` | `integrate/eretz-pre-main` · `bd3f37c` | `83f04af4` | Clean | Roomix Fidelity baseline |
| F4 | `D:\INMO CAPITAL\eretz-main\frontend` | `main` · `e9630f5f` | `83f04af4` | Clean | Same as F3 and Roomix tag |
| F5 | `D:\INMO CAPITAL\eretz-rescue\frontend` | `integrate/release-dirty-recovery` · `b6c326b0` | `83f04af4` | Clean | Same as F3/F4 |
| F6 | `D:\INMO CAPITAL\eretz-agency\frontend` | `feat/roomix-agency-coverage` · `5e7a338e` | `2a610d34` | Parent dirty; frontend clean | Roomix plus temporary agency write bridge |
| F7 | `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a\frontend` | `feat/eretz-frontend-phase-a` · `ea7708f7` | `15b5ec6e` | Clean; 15 ahead / 0 behind recorded remote | **Canonical candidate** |
| F8 | `D:\INMO CAPITAL\Inmo-Capital-api-v2-cutovers\frontend` | `feat/eretz-api-v2-cutovers` · `806d5a59` | `20bb81e4` | Clean | Backend cutover worktree with stale frontend |
| F9 | `feat/fe-b-beta-safety-foundation:frontend` | `eb2d2494` | `791ff...` | Branch-only | Early beta shell |
| F10 | `feat/fe-c1-server-side-search:frontend` | `bb7ccabf` | `64fd...` | Branch-only | Divergent early search experiment |
| F11 | `checkpoint/main-pre-integration:frontend` | `4aef4b88` | `213730...` | Ref-only | Roomix predecessor |
| F12 | `feat/monorepo-frontend-integration:frontend` | `ebf29037` | `b021...` | Branch-only | Earliest ERETZ shell |

No `git fetch` was performed because the mission forbids repository mutations. “Remote” means the locally recorded remote-tracking ref. F7's recorded remote is `04e63a2895bfd3dc68725734eeb0567f78e91342`; F7 is 15 commits ahead and zero behind it.

## Git / Worktree Topology

```text
F12 early monorepo → F9 beta-safety
                       ├─ F10 divergent server-search
                       └─ F11 pre-integration → F1/F2/F8 old release tree
                                              └─ Roomix tag → F3/F4/F5
                                                               ├─ F6 temporary agency bridge
                                                               └─ F7 Roomix + UX/UI V2 + API v2 frontend cutover
```

F10 is not an ancestor of F7. Its five exclusive search patches are historical and functionally superseded. API v2 backend contracts live in F8's branch/worktree while the consuming frontend lives in F7.

## Branch Relationships

| Relationship | Evidence |
|---|---|
| F1 = F2 = F8 frontend | Tree `20bb81e4` |
| F3 = F4 = F5 = Roomix baseline | Tree `83f04af4` |
| Roomix → F6 | Temporary agency bridge only |
| Roomix → F7 | Ancestry plus later fidelity, consolidation and V2 commits |
| Recorded remote F7 → local F7 | 15 commits ahead, zero behind |
| F10 ↔ F7 | Diverged; five F10-only patches |

## Candidate Comparison

| Area | F1/F2/F8 | F3/F4/F5 | F6 | F7 | Verdict |
|---|---|---|---|---|---|
| Architecture | Legacy | Roomix App Router | Roomix + temporary bridge | Strongest typed boundaries/tests | F7 |
| Roomix Fidelity | Pre-fidelity | Exact baseline | Baseline | Baseline plus deliberate V2 evolution | F7 product; F3–F5 reference |
| Explorer/map/cards/detail | Limited | Substantial legacy | Same | Most complete and accessible | F7 |
| Mi ERETZ/professionals | Limited | Present | Present | Most complete | F7 |
| API v2 | None | None | None | Partial/hybrid cutover | F7 |
| Tests | Sparse | Moderate | Moderate | 92 Vitest files + 5 E2E files | F7 |

## Unique Work and Salvage Decision

- **KEEP F7:** only complete UX/UI V2 plus additive API v2 frontend boundary and regression suite.
- **REFERENCE F3/F4/F5:** immutable Roomix visual lineage.
- **DO NOT SALVAGE F6 bridge:** preview-only operational tooling with write/elevation semantics, not public frontend architecture.
- **DO NOT MERGE F10 wholesale:** early search work is superseded by F7.
- **F8 is a dependency, not a frontend candidate:** its backend supplies contracts expected by F7; its frontend is old.
- No code was copied, merged or changed.

## Roomix Fidelity Distribution

Roomix Fidelity is materially preserved in F7. Tree `83f04af4` remains the exact comparison point. F7 contains the Roomix closure, prior CSS consolidation and deliberate UX/UI V2 refinements. Unused `HomeHero`/`HomeSections` are dormant historical surfaces; restoring them is a product decision.

## Vercel Association

F3, F4, F6 and F7 have local linkage to Vercel project `eretz-propiedades` (`prj_pPFVJ8cPst5NMjJ7iWvWTQr9oRLR`). F7 has `frontend/vercel.json` with region `iad1`. Linkage does not prove deployed SHA. No Vercel setting, deployment, domain or environment was changed.

# Canonical Frontend Audit

## 1. Executive Summary

F7 is the best canonical frontend: Next.js 16 App Router, React 19, strict TypeScript, mature desktop UX/UI V2, extensive tests, Roomix lineage, provider-neutral analytics events and a server-only API v2 boundary. It is not beta-complete because the cutover is hybrid and depends on a separate backend branch/deployment.

Estimate: **80–85% structurally complete for a private desktop beta**, but **65–75% operationally ready** until API v2 deployment alignment, geographic confidence, province filtering, hybrid identity and remote Preview validation close. No P0 frontend defect was proven. P1 groups: deployment/contract coupling, manual province filter loss, confidence regression and API v2 map free-text backend failure.

## 2. Repository / Worktree / Branch / HEAD

- Audit worktree: `D:\INMO CAPITAL\Inmo-Capital-main`, `release/eretz-private-preview`, HEAD `9461fab0195b84eb4fee99ca0a9195225c0081fe`.
- Canonical worktree: `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a`, `feat/eretz-frontend-phase-a`, HEAD `ea7708f79fdc1a535d10f8f68322b5c2ce386668`.
- Canonical worktree and `frontend/` are clean.
- Audit-root dirtiness is pre-existing and preserved. This report is the only authorized audit artifact.

## 3. Frontend Architecture

Next.js `16.2.12`, React `19.2.4`, TypeScript 5, App Router and Tailwind 4. There are 19 page routes, 8 route handlers, 297 tracked frontend files, 266 TS/TSX/CSS source files and 38 client-boundary files. Server Components are default. Public discovery uses a server-only API v2 client with runtime validation, 10 s timeout, abort, no-store, adapters and a presentation boundary. Data remains hybrid: API v2 for discovery/canonical identities; legacy PostgreSQL for numeric historical details and professional/reporting capabilities. No middleware/proxy layer exists.

## 4. Route Inventory

Build exposes `/`, `/propiedades`, `/propiedad/[id]`, `/mi-eretz`, `/favoritos`, `/colecciones`, `/comparar`, `/inmobiliarias`, agency claim/profile routes, `/agentes`, agent profile, `/calculadoras` plus five calculators, `/contacto`, `/baja-o-correccion`, legal pages, global 404, robots, sitemap, OG image and eight API handlers. `/internal/publicar-preview` is feature-flagged/preparatory, not a publishing backend.

## 5. Component Inventory

Core surfaces exist for App Shell, Explorer, autocomplete/filters, cards, Leaflet map, detail/gallery/contact, Mi ERETZ local workspace, professional directories/profiles, calculators and resilient states. Complexity concentrates in Explorer coordination, map interaction, `property-db-service.ts` (1,013 lines) and global CSS.

## 6. Design System

The navy/white/gold Roomix-derived language is coherent. `globals.css` has 2,934 lines and layered historical overrides. Static analysis found seven referenced but undeclared variables: `--blue-700`, `--font-display`, `--font-sans` (Next injects it at runtime), `--navy`, `--navy-800`, `--surface`, `--surface-sunken`.

## 7. Roomix Fidelity Status

**KEEP AND REFINE.** F7 preserves Roomix and improves hierarchy, density, map integration and accessibility. Do not rebuild or blindly restore the old landing page.

## 8. Home

`/` intentionally renders the map-first Explorer. The unresolved strategic question is immediate exploration versus marketing/SEO landing. `HomeHero` and `HomeSections` are unused.

## 9. Search / Autocomplete

Autocomplete is debounced (260 ms), abortable, cached, keyboard accessible and explicit about states. It preserves locality, municipality, department, province and neighborhood. A cold E2E run produced one 504 under concurrent snapshot load; all four targeted autocomplete/keyboard cases then passed in 41.18 s.

## 10. Results

Results support relevance, pagination, view modes and explicit loading/error/empty/exhaustion states. Outages no longer become zero. API v2 uses offset; `/propiedades` copy still mentions cursor pagination.

## 11. Property Cards

Cards are compact, responsive and accessible, preserving price, location, publisher, favorites and comparison. Mapping now preserves legitimate numeric zero. Native `<img>` fallback tolerates heterogeneous sources but lacks Next Image optimization/responsive sizes.

## 12. Filters

Visible filters mostly align with API v2 and real facets. **P1:** `FilterForm` exposes manual `provincia`; validation accepts it, but `propertyFiltersToCatalogQuery` ignores `filters.province` without typed `selectedArea`. The chip can appear active while results are not province-filtered.

## 13. URL State

Supported query, filters, sort, page, mode, selection and viewport serialize. Unsupported legacy filters are rejected. P2: `replaceState`-managed mode/selection lack complete `popstate` synchronization, so Back/Forward can stale duplicated client state. Hover does not write URL.

## 14. Sorting

Relevance is the preserved default; price ordering exists. The UI exposes the finite ranked API window instead of implying infinite coverage.

## 15. Map

Leaflet provides progressive density, clusters, price markers, selected/hover states, keyboard access, card↔marker, “Buscar en esta zona”, fullscreen and outage/no-location states. **P1:** every API v2 map point is mapped to `locationConfidence: "approximate"`; high/doubtful are lost. **Backend blocker:** text-query map requests fail in F8 with `sqlite3.OperationalError: ambiguous column name: titulo`.

## 16. Property Detail

Canonical nonnumeric IDs use API v2; numeric historical IDs use legacy PostgreSQL. Canonical not-found/unavailable are distinguished. API v2 omits several legacy-rich fields (address, dates, expenses, garages, amenities, land area, mortgage, agent), so canonical detail is honest but thinner.

## 17. Gallery

Gallery includes thumbnails, fullscreen, keyboard/Escape, focus and fallbacks. Image delivery remains the main performance debt.

## 18. Agency Information

Directories/profiles remain legacy-DB capabilities. API v2 exposes agency identity/contact separately, but canonical property detail hides the profile link behind `legacyIdentity`. F6's bridge is not a product solution.

## 19. Contact

Phone/email/WhatsApp are conditional and do not invent data. Reporting/correction persistence is environment-dependent and legacy.

## 20. Loading / Empty / Error States

Loading, empty, unavailable, map outage, missing listing, no mapped properties and partial saved-list failures are distinguished. Quality Gate/Blob fail-closed behavior exists in source; remote configuration was not revalidated.

## 21. Fixtures / Mocks

Fixtures cover typed geography, API schemas/adapters, null/zero semantics, ranked boundaries and errors. One E2E hardcodes `42.536` sales while the current snapshot returns `42.267`; this is a brittle test-data contract, not a UI failure.

## 22. API Integration

Server-only routes consumed: `/v2/buscar`, `/v2/propiedades/mapa`, `/v2/propiedades/{id}`, `/v2/agencias/{id}`, POST `/v2/propiedades/batch`, `/v2/areas`, `/v2/barrios`, `/v2/sugerencias`, `/v2/filtros`. Contracts include `eretz_api_property_v1` and `eretz_ranking_tecnico_v1`. No API credential reaches browser code.

## 23. Backend Contract Mismatches

1. F7 depends on contracts in separate F8 branch/deployment.
2. Map DTO lacks confidence evidence and forces approximate.
3. Property DTO is narrower than legacy detail.
4. Canonical agency identity does not fully integrate with legacy profiles.
5. `/v2/propiedades/mapa` text search has ambiguous SQL.
6. Mutable facet totals conflict with exact E2E values.
7. Numeric/canonical IDs produce different history/related/duplicate capabilities.

## 24. Tests

- Vitest: 91 files passed, 1 skipped; 1,227 tests passed, 4 skipped (1,231 total), 232.79 s.
- Playwright full: 62 passed, 7 skipped, 3 failed, 591.32 s.
- Targeted autocomplete rerun: 4 passed, 3 deselected, 41.18 s.
- Stable failure: stale facet count. Two autocomplete failures were cold-backend 504/cascade and passed on rerun.
- Seven skips: publication wizard flag off. Remote smoke remains conditional on `ERETZ_API_V2_SMOKE_URL`.

## 25. Accessibility

Keyboard/focus, `aria-pressed`, combobox/listbox, map/list alternative, gallery Escape and live states have broad coverage. No source-level serious/critical issue was proven. No fresh authenticated remote Axe result is claimed.

## 26. SEO

Preview-safe noindex/robots remains. Public canonical base, site URL, filtered URLs, sitemap scope and route policy need launch configuration. Cursor wording is stale.

## 27. Analytics

Neutral events cover search, filters, sort, suggestions, result open, zero/error, view, gallery, contact and share. No provider/consumer is installed: this is a contract, not operational observability.

## 28. Performance

Strengths: RSC default, bounded map, abortable search, caches, no speculative detail prefetch, no browser DB access. Risks: cold snapshot calls exceeded 10 s under concurrency; facets intermittently returned 503/504; native images are unoptimized; global CSS is large; legacy PostgreSQL coexists with v2. Fix map SQL correctness first.

## 29. CSS / Styling Architecture

Preserve prior consolidation. Define/migrate six genuine missing tokens (excluding runtime `--font-sans`), inventory dead overrides and modularize gradually. No wholesale rewrite.

## 30. Dead Code / Duplication

Likely areas: unused Roomix home, natural-language component used only by tests, legacy/v2 parallel data paths, Mi ERETZ compatibility routes and duplicated URL/client state. Require usage evidence before deletion.

## 31. Vercel Configuration

F7 is linked to `eretz-propiedades`; `vercel.json` pins `iad1`. Environment names, not values: `SUPABASE_DATABASE_URL`, `ERETZ_API_V2_BASE_URL`, private Quality Gate/Blob variables, `BLOB_READ_WRITE_TOKEN`, `NEXT_PUBLIC_SITE_URL`. `.env.local` contains only Vercel OIDC and was never printed. Deployed SHA is unknown.

## 32. Build / Typecheck / Lint Results

- `npm run lint`: PASS.
- `npm run typecheck`: PASS.
- `npm run build`: PASS; Next 16.2.12/Turbopack, compile 33.8 s, TS 21 s, 20 static pages in 3.9 s.
- `git diff --check`: PASS.
- Canonical tree after validation: clean.

## 33. KEEP / REFINE / REPLACE Matrix

| Area | Decision | Reason |
|---|---|---|
| F7 architecture/UX V2 | KEEP | Strongest coherent implementation |
| Roomix baseline | KEEP as reference | Proven lineage |
| API v2 client/adapters | KEEP + REFINE | Correct direction, contract gaps |
| Explorer/cards/map/detail | REFINE | Mature, targeted gaps |
| Global CSS | REFINE incrementally | Valuable but layered |
| Hybrid legacy/v2 | REPLACE gradually | Identity/capability inconsistency |
| F6 bridge | REJECT | Temporary write tooling |
| Exact mutable E2E counts | REPLACE | Brittle assertion |

## 34. Completion Matrix

| Capability | State | Remaining |
|---|---|---|
| App Shell/desktop UX | MOSTLY DONE | Remote visual acceptance |
| Search/autocomplete | MOSTLY DONE | Cold latency/capacity |
| Filters | PARTIAL | Province contract |
| Results/cards | MOSTLY DONE | Images, remote QA |
| Map | PARTIAL | Confidence and backend SQL |
| Detail/contact | PARTIAL | DTO richness/hybrid identity |
| Mi ERETZ | FRONTEND DONE | Auth persistence future |
| Professionals | PARTIAL | Backend ownership/API |
| States/a11y | MOSTLY DONE | Remote Axe/manual |
| API v2 cutover | PARTIAL | Aligned deployment; retire legacy |
| Public SEO | NOT READY | Launch policy |

## 35. P0/P1/P2/P3 Findings

- **P0:** none proven in frontend.
- **P1:** v2 frontend depends on separate unproven backend deployment.
- **P1:** manual province filter is displayed but adapter drops it.
- **P1:** confidence becomes approximate; `GEO_CONFLICT` is discarded.
- **P1 backend:** map + free text fails on ambiguous `titulo`.
- **P2:** hybrid identity/capabilities; incomplete popstate; cold timeouts; thin canonical DTO; missing CSS tokens; unoptimized images; stale exact-count E2E.
- **P3:** dead historical surfaces, recent-category semantics, stale cursor copy.

## 36. Critical Path to Beta

1. Deploy one compatible v2 contract and prove private Preview configuration.
2. Fix map text-search SQL with regression test.
3. Preserve confidence evidence through DTOs/adapters.
4. Fix/remove manual province path.
5. Define hybrid ID/professional behavior.
6. Replace mutable exact-count assertions.
7. Run authenticated remote E2E/Axe/network/visual QA.
8. Close image/CSS/public SEO before public beta.

## 37. Backend Dependencies

Reachable F8 API; fixed map SQL; confidence metadata; richer detail or reduced contract; stable professional identity/contact; latency/caching budgets. Auth and persistent Mi ERETZ remain future decisions.

## 38. Recommended Next Frontend Action

Run one large **API v2 contract-hardening and private-preview acceptance block** across F7/F8: freeze DTOs, fix map text search, restore confidence, correct province filtering, replace brittle assertions, deploy only a private compatible Preview and run full authenticated desktop acceptance. Do not redesign UX or merge historical frontends.

## 39. Open Questions / Unknowns

- Which v2 SHA/dataset serves the next Preview?
- Is hybrid numeric/canonical identity temporary?
- Which evidence will support geographic confidence?
- Should `/` remain Explorer or become SEO landing?
- Which professional capabilities enter v2 before public beta?
- What image pipeline is acceptable?
- Which consumer receives analytics events?

## 40. Evidence / Important File Paths

- Canonical: `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a\frontend`
- API boundary: `src/lib/api-v2/`
- Filter defect: `src/components/search/FilterForm.tsx`, `src/lib/api-v2/property-boundary.ts`
- Confidence flattening: `src/lib/api-v2/property-boundary.ts`
- Hybrid detail: `src/app/propiedad/[id]/page.tsx`
- Legacy data: `src/lib/property-db-service.ts`
- Styles: `src/app/globals.css`
- Backend dependency: `D:\INMO CAPITAL\Inmo-Capital-api-v2-cutovers\api\v2.py`
- E2E: `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a\frontend\e2e`
- Vercel: `D:\INMO CAPITAL\Inmo-Capital-frontend-phase-a\frontend\vercel.json`
- Report: `D:\INMO CAPITAL\Inmo-Capital-main\ERETZ_FRONTEND_CURRENT_STATE.md`

No source, test, configuration, data, Git history, remote or deployment was modified.

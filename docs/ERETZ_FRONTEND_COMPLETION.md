# ERETZ frontend completion

Verified 2026-09-08 on `feat/eretz-frontend-phase-a` from frontend baseline
`c7f3da67e8`. Backend evidence came from the clean read-only worktree
`D:\INMO CAPITAL\Inmo-Capital-api-v2-cutovers` at `806d5a5928` and its prepared
58,427-property snapshot. No backend file was modified.

## Cutover state

| Public flow | State | Read path | Remaining dependency |
|---|---|---|---|
| Home discovery | Ready | API v2 autocomplete/areas/barrios/facets | None |
| Explorer list/count | Ready | `/v2/buscar` | Ranked offsets remain contractually capped at 200 |
| Explorer map | Partial | `/v2/propiedades/mapa` | Backend must fix `q + viewport` ambiguous `titulo` SQL failure |
| Canonical detail | Ready | `/v2/propiedades/{id}` | None for core property presentation |
| Agency display | Ready | `/v2/agencias/{agency_id}` | Backend currently reports public contact channels unavailable |
| Contact | Beta display only | Agency display plus verified `source_url` | No contact-action/CRM endpoint exists |
| Favorites/compare/collections hydration | Ready for canonical IDs | `POST /v2/propiedades/batch` | Numeric historical IDs retain a bounded legacy bridge |

The public data boundary is DTO, runtime validation, domain adaptation, then
presentation. It preserves null versus zero, distinct locality/municipality/
department labels, missing coordinates, item-level partial data and typed error
semantics. Unknown or duplicate URL parameters are rejected rather than
silently broadening a search. Price ranges and price sorts require currency.

## Verified legacy-removal matrix

| Legacy path | Consumers before | API replacement | Consumers after | Decision |
|---|---|---|---|---|
| Public property search/count | Explorer routes and unused home helper | `/v2/buscar` | 0 | Removed from live flows |
| Public map search | Map route | `/v2/propiedades/mapa` | 0 | Removed from live flow; backend bug remains visible |
| Canonical detail | Detail route | `/v2/propiedades/{id}` | 0 | Removed |
| Canonical saved-list hydration | By-IDs route | `/v2/propiedades/batch` | 0 | Removed |
| Numeric historical detail/by-IDs | Existing public URLs/local storage | No verified aliases in snapshot | 2 bounded consumers | Retain |
| Agency/agent directories and profiles | Public professional routes | v2 only provides agency summary by ID | Existing consumers | Retain |
| Claims/reports/admin writes | Mutation flows | No v2 replacement | Existing consumers | Retain |

The unused `home-data.ts` helper and obsolete public facade exports were removed
after repository-wide consumer checks. Internal legacy query functions used by
historical detail, relationship features or their regression tests remain.

## Quality evidence

- Typecheck: pass.
- ESLint: pass.
- Vitest after cutover and cleanup: 1,227 passed, 4 skipped.
- Production build: pass after the main cutover.
- Focused browser discovery/detail regression: pass after correcting the
  canonical 404 expectation.
- Playwright: discovery/UX 17 passed; Phase A 23 passed; calculators 21 passed
  across the full run plus focused rerun; internal publication wizard 4 passed
  and 7 skipped because its preview flag is intentionally off.
- Real data: combined `casa` search returned total 17,108 and 24 items; page 9
  succeeded and page 10 was rejected before a backend call; canonical detail,
  agency display and mixed canonical/historical batch partial-data behavior
  rendered as expected.
- Desktop browser: Explorer verified at 1440, 1366 and 1280 without horizontal
  overflow or console errors. Existing Playwright coverage supplies narrower
  viewport checks.

## Readiness blockers

Beta and launch cannot be declared while the synchronized map contract fails
for normal text searches and no remotely accessible staging API is verified for
a Vercel Preview. Contact action is out of scope until a backend endpoint exists;
the beta-safe display path links to a real public channel or the original
publication and never claims that ERETZ sent a message.

The existing Vercel project link was verified as `eretz-propiedades`
(`prj_pPFVJ8cPst5NMjJ7iWvWTQr9oRLR`). Its Preview environment does not contain
`ERETZ_API_V2_BASE_URL`; no deployment was created because that would publish a
knowingly unconfigured catalog rather than an acceptance candidate.

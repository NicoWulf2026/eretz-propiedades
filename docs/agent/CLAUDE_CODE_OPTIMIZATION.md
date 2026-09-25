# Claude Code — optimización de contexto para ERETZ

**OPTIMIZATION COMPLETE** — 2026-09-25. Medido = MEDIDO; estimado = ESTIMADO; sin dato = DESCONOCIDO.

## BEFORE / AFTER
| componente | antes | después |
|---|---|---|
| cwd de las sesiones | `Inmo-Capital-main` (legacy, `gitStatus` del repo equivocado) | `eretz-unified` |
| plugins cargados en el repo | 23 activos + 5 que fallan al cargar (MEDIDO, `claude plugin list`) | 9 activos (MEDIDO) |
| descripciones de skills en contexto | ~84.000 caracteres ≈ 21.000 tokens (ESTIMADO, techo) | ~17.000 ≈ 4.300 tokens (ESTIMADO) |
| agentes de plugins en contexto | ~5.000–8.900 tokens (ESTIMADO) | ~1.800 tokens (ESTIMADO) |
| servidores MCP de plugins | 21 declarados, 8 con aviso de error/auth por sesión (MEDIDO) | 1 (`vercel`, pide auth) |
| hooks por herramienta | ai-plugins, hookify, agentforce (Pre/PostToolUse, UserPromptSubmit) | ninguno de esos |
| revisión LLM por commit/push/Stop | 30 sesiones completas en ~15 h (MEDIDO) | apagada (`ENABLE_CODE_SECURITY_REVIEW=0`) |
| CLAUDE.md que carga al inicio | 0 | 47 líneas, 3,2 KB ≈ 800 tokens |
| rules | 0 | 3, todas condicionadas por `paths` (0 al inicio) |
| MEMORY.md cargado | 2,3 KB, 14 entradas (Inmo-Capital-main) | 0,3 KB, 1 entrada (eretz-unified) |
| `docs/agent/CURRENT_STATE.md` | 366 líneas, 23 KB (bitácora) | 50 líneas, 2,6 KB (estado) |
| `docs/agent/HANDOFF.md` | 156 líneas, 9 KB | 50 líneas, 3,3 KB |

TOKEN ESTIMATE (contexto recurrente atribuible a configuración, sin herramientas del sistema):
antes ~28.000–35.000 tokens; después ~7.500–8.500. ESTIMATED SAVING por sesión:
conservador ~10.000 (si Claude Code ya recortaba el listado de skills con algún presupuesto,
DESCONOCIDO), realista ~20.000, optimista ~27.000. Aparte: ~30 sesiones LLM diarias menos.
Releer CURRENT_STATE al retomar: ~6.000 → ~700 tokens.
MANUAL_MEASUREMENT_PENDING: `/context` desde una sesión interactiva en `eretz-unified`.

## PLUGINS
Deshabilitados solo para este repo (y para el legacy) en `.claude/settings.local.json`, sin
desinstalar: 42crunch, activecampaign, adobe-for-creativity, agentforce-adlc, agent-sdk-dev,
ai-plugins, aikido, airtable, airwallex-agentos, airwallex-dev, aiven, alloydb-omni,
amazon-selling-partner, hookify (sin reglas definidas) y los cuatro de `anthropic-agent-skills`
que duplicaban `document-skills` (los cinco fallan al cargar hoy por manifiestos en conflicto).
Activos: superpowers, vercel, pr-review-toolkit, code-review, code-simplifier, feature-dev,
commit-commands, typescript-lsp, security-guidance (solo avisos por patrones).

## SKILLS
- 8 skills de usuario idénticas byte a byte a las de `superpowers` → movidas a
  `~/.claude/skills-archivadas/duplicadas-de-superpowers-2026-09-25/`.
- Manuales en este repo (`skillOverrides: user-invocable-only`, siguen con `/nombre`):
  deploy-to-vercel, vercel-optimize, performance-optimization, security-and-hardening,
  spec-driven-development, frontend-design, frontend-ui-engineering, react-best-practices,
  web-design-guidelines, playwright-cli, supabase.
- Automática: supabase-postgres-best-practices + las de los plugins activos.
- `skillOverrides` no aplica a skills de plugins (documentación oficial).

## HOOKS / MCP
Quedan: security-guidance (SessionStart, avisos por patrones en ediciones; LLM apagado),
superpowers (inyección al inicio), vercel (SessionStart/End). MCP: solo `vercel`; no se
autenticó nada para silenciar avisos. Revisión de seguridad manual: `/security-review` o el
plugin `code-review` cuando corresponda.

## CLAUDE.MD / RULES / MEMORY
- `CLAUDE.md`: reglas universales, sin `@imports`.
- `.claude/rules/scraper.md` (`connectors/**`, `scraper/**`, `scripts/**`, `tests/**`),
  `frontend.md` (`frontend/**`), `database.md` (`supabase/**`, `migrations/**`, `**/*.sql`, …).
- Memoria operativa nueva: `~/.claude/projects/D--INMO-CAPITAL-eretz-unified/memory/` (solo perfil
  de usuario; lo demás está en CLAUDE.md/rules o en Git). Memoria legacy: índice corto y 13
  entradas archivadas en `_archivo_2026-09-25/`.

## OBSIDIAN
Vault: `eretz-unified/docs/` (índice en `docs/INDEX.md`). `docs/.obsidian/` ignorado por Git. La
memoria de Claude queda fuera. No se movió ninguna nota (las carpetas `03_`, `05_`, `06_` no son
duplicados y están enlazadas por ruta).

## ROLLBACK
Backup completo en `~/.claude/backups/eretz-optimizacion-2026-09-25/` (settings.json,
.claude.json, installed_plugins/known_marketplaces, memoria legacy, skills de usuario, settings
local del repo legacy; sin credenciales).
1. Plugins/env/skillOverrides: borrar `eretz-unified/.claude/settings.local.json` y restaurar
   `Inmo-Capital-main/.claude/settings.local.json` desde el backup.
2. Skills: mover de vuelta `~/.claude/skills-archivadas/duplicadas-de-superpowers-2026-09-25/*`
   a `~/.claude/skills/`.
3. Memoria legacy: mover `_archivo_2026-09-25/*` a `memory/` y restaurar `MEMORY.md` del backup.
4. Lo versionado (CLAUDE.md, rules, docs): `git revert` del commit de la optimización.

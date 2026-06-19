# Panel principal ERETZ Propiedades

Ultima actualizacion: 2026-06-09

Este panel es la puerta de entrada a la documentacion vigente del proyecto. Si una nota vieja contradice este panel o las notas enlazadas, tomar este panel como referencia actual y conservar la nota vieja como contexto historico.

## Estado actual

- [[14 - Estado vigente 2026-06-04]]
- [[13 - Estado actual para ChatGPT o Codex]]

## Resumen ejecutivo

ERETZ Propiedades es una plataforma proptech para centralizar, ordenar, normalizar y analizar informacion inmobiliaria proveniente de inmobiliarias y desarrolladoras. Alcance: Argentina completa.

La plataforma no vende propiedades directamente. Organiza datos, muestra el mercado con foco en mapa y deriva al usuario a la publicacion original o a la inmobiliaria.

**Foco actual: FASE 1 — Scrapers + base de datos.**

Orden de desarrollo: Scrapers/DB → Frontend publico → Panel inmobiliarias → Carga manual → Marketing → Monetizacion.

## Decisiones y roadmap

- [[Roadmap 2026-06-09]] ← roadmap vigente
- [[10 - Decisiones importantes]] ← decisiones 1-21
- [[00 - Decisiones oficiales]] ← scrapers/DB

## Scrapers y base de datos (03_SCRAPERS_DB)

- [[00 - Decisiones oficiales]]
- [[03 - Modelo de datos propiedades]]
- [[08 - Estados de propiedades]]
- [[07 - Deduplicacion]]
- [[06 - Batches diarios]]
- [[10 - Geocoding]]

## Panel de inmobiliarias (05_PANEL_INMOBILIARIAS)

- [[00 - Decisiones]] (panel inmobiliarias)

## Marketing (06_MARKETING)

- [[Estrategia general]]

## Datos y auditorias

- [[Neon readiness 2026-06-04]]
- [[04 - Supabase y base de datos]]
- [[Scraping autofix cierre 2026-06-04]]
- [[Politicas de calidad y publicacion]]

## Desarrollo y producto

- [[03 - Desarrollo técnico]]
- [[Frontend estado 2026-06-04]]
- [[02 - Producto y funcionalidades]]
- [[01 - Visión y estrategia]]

## Seguimiento

- [[11 - Pendientes]]
- [[12 - Errores y soluciones]]
- [[09 - Prompts útiles]]

## Reglas de seguridad vigentes

- No tocar `.env`.
- No borrar datos.
- No publicar masivamente a Supabase.
- No tocar `publish_queue` con commit sin autorizacion.
- No correr `publish_to_supabase.py` sin autorizacion.
- No correr `run_daily_pipeline.py --commit` sin autorizacion.
- No hacer commit ni push sin autorizacion.
- No cambiar esquema de base de datos sin autorizacion.
- No inventar datos faltantes.
- No pisar datos buenos con datos peores.

## Marca

Usar siempre `ERETZ Propiedades`.

No usar `Inmocapital`, `INMOCAPITAL` ni `ERETZ Propiedades` como nombre de marca.

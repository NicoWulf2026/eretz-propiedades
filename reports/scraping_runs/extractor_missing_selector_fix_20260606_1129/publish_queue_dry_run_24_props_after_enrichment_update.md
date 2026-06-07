# Publish Queue Dry-Run — post-enrichment update (24 props)

- Fecha: 2026-06-07
- Tipo: **DRY-RUN** — sin commit
- Comando: `build_publish_queue.py --dry-run --limit 30 --ids-file publish_queue_ids_24_props.csv`
- IDs evaluados: 81036–81059 (24 staging IDs, tanda completa)
- Condición: `min_score=60`, `allow_pending_geo=False`
- Estado: post-enrichment (Watson precios actualizados, Campos títulos ricos aplicados)

---

## Resultado del script

```
filas_leidas   = 24
encoladas      = 14  (priority=2)
ya_en_cola     = 0
omitidas:
  skip_geocoding_pending  = 8
  skip_geocoding_failed   = 2
accion_final   = rollback  ← DRY-RUN, sin cambios
```

---

## Detalle fila por fila

| staging_id | Agencia | Título | Precio | Moneda | Geo | Score | Resultado |
|---|---|---|---|---|---|---|---|
| **81036** | Innoacafayate | Haras La Querencia 800 Hectareas | 1,450,000 | USD | pending | 100 | SKIP — geo_pending |
| **81037** | Innoacafayate | Depto en Salta sobre avenida Chile | 65,000 | USD | skipped | 95 | ENCOL priority=2 |
| **81038** | Innoacafayate | Casa Pueblo Nuevo Mza. 21 | 42,000 | USD | pending | 100 | SKIP — geo_pending |
| **81039** | Innoacafayate | Propiedad en calle Ex Colon | 75,000 | USD | skipped | 95 | ENCOL priority=2 |
| **81040** | Innoacafayate | Lote Barrio Ribera 1 | 50,000 | USD | skipped | 95 | ENCOL priority=2 |
| **81041** | Innoacafayate | Pueblo Nuevo Mza. 69 dos lotes | None | ARS | pending | 80 | SKIP — geo_pending |
| **81042** | Innoacafayate | Pueblo Nuevo Mza. 46 | None | ARS | pending | 80 | SKIP — geo_pending |
| **81043** | Innoacafayate | Lote en calle Chacabuco. Cafayate | 57,000 | USD | skipped | 95 | ENCOL priority=2 |
| **81044** | Innoacafayate | Pueblo Nuevo Mza. 127 | None | ARS | pending | 80 | SKIP — geo_pending |
| **81045** | Innoacafayate | Lotes en calle Los Andes | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81046** | Innoacafayate | Hotel Texas | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81047** | Innoacafayate | Local calle Salta 329 | 450,000 | ARS | **failed** | 100 | SKIP — geo_failed |
| **81048** | Innoacafayate | Casa Vertientes 57, Cafayate | None | ARS | **failed** | 80 | SKIP — geo_failed |
| **81049** | Innoacafayate | Local Calchaqui esq. Arnaldo Echart | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81050** | Innoacafayate | Depto Calchaqui esq. Arnaldo Echart | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81051** | Innoacafayate | Deptos Guemes Sur | 600,000 | ARS | skipped | 95 | ENCOL priority=2 |
| **81052** | Innoacafayate | Casa Lamadrid | 400,000 | ARS | skipped | 95 | ENCOL priority=2 |
| **81053** | CamposDelAmapa | **Departamento Loventué Muy buen acceso 6.000 ha Cria** ✨ | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81054** | CamposDelAmapa | **Limay Mahuida Oportunidad 15.000 ha Cria** ✨ | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81055** | CamposDelAmapa | **Departamento Chalileo Oportunidad 30.000 ha Cria** ✨ | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81056** | CamposDelAmapa | **Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura** ✨ | None | ARS | skipped | 75 | ENCOL priority=2 |
| **81057** | Watson | Casa en zona Centro. Excelente ubicación | **88,000** 💰 | **USD** | pending | 65 | SKIP — geo_pending |
| **81058** | Watson | Casa de categoría en Quintas de Betbeder | None | ARS | pending | 65 | SKIP — geo_pending |
| **81059** | Watson | Casa en esquina en zona Centro | **125,000** 💰 | **USD** | pending | 65 | SKIP — geo_pending |

✨ = título enriquecido por Fix E (esta sesión)  
💰 = precio enriquecido por Fix G (esta sesión)

---

## Las 14 encolables (priority=2)

| staging_id | Agencia | Precio | Geo | Score |
|---|---|---|---|---|
| 81037 | Innoacafayate | 65,000 USD | skipped | 95 |
| 81039 | Innoacafayate | 75,000 USD | skipped | 95 |
| 81040 | Innoacafayate | 50,000 USD | skipped | 95 |
| 81043 | Innoacafayate | 57,000 USD | skipped | 95 |
| 81045 | Innoacafayate | None | skipped | 75 |
| 81046 | Innoacafayate | None | skipped | 75 |
| 81049 | Innoacafayate | None | skipped | 75 |
| 81050 | Innoacafayate | None | skipped | 75 |
| 81051 | Innoacafayate | 600,000 ARS | skipped | 95 |
| 81052 | Innoacafayate | 400,000 ARS | skipped | 95 |
| **81053** | **CamposDelAmapa** | None | skipped | 75 |
| **81054** | **CamposDelAmapa** | None | skipped | 75 |
| **81055** | **CamposDelAmapa** | None | skipped | 75 |
| **81056** | **CamposDelAmapa** | None | skipped | 75 |

---

## Las 10 excluidas — motivos

### 5 excluidas — geocoding_status = pending (Innoacafayate, calles específicas)

| staging_id | Título | Score | Nota |
|---|---|---|---|
| 81036 | Haras La Querencia 800 Hectareas | 100 | Direccion específica → geocoding pendiente |
| 81038 | Casa Pueblo Nuevo Mza. 21 | 100 | Dirección específica |
| 81041 | Pueblo Nuevo Mza. 69 dos lotes | 80 | Sin precio + geo_pending |
| 81042 | Pueblo Nuevo Mza. 46 | 80 | Sin precio + geo_pending |
| 81044 | Pueblo Nuevo Mza. 127 | 80 | Sin precio + geo_pending |

Causa: requieren geocoding real (calles de Cafayate). Nominatim no cubre → necesitan Google Maps API.

### 2 excluidas — geocoding_status = failed

| staging_id | Título | Score | Nota |
|---|---|---|---|
| 81047 | Local calle Salta 329 | 100 | Geocoding falló con Nominatim |
| 81048 | Casa Vertientes 57, Cafayate | 80 | Geocoding falló |

Causa: Nominatim sin cobertura callejera de Cafayate. Podrían re-intentarse con Google Maps API. También son publicables como priority=2 si se resetea geocoding_status → pending → skipped.

### 3 excluidas — geocoding_status = pending (Watson, sin ubicación)

| staging_id | Título | Precio | Nota |
|---|---|---|---|
| 81057 | Casa en zona Centro | **88,000 USD** 💰 | Sin ciudad/provincia — Watson no expone ubicación |
| 81058 | Casa de categoría en Quintas de Betbeder | None | Sin precio (genuino) + sin ubicación |
| 81059 | Casa en esquina en zona Centro | **125,000 USD** 💰 | Sin ciudad/provincia |

Causa: Watson CMS no expone ciudad/provincia en HTML ni en JSON-LD. Las props tienen precio correcto (Fix G), pero sin ubicación el geocoding queda en `pending`. Opciones:
- Geocodificar con Google Maps API (si se permite consulta por "Sin Isidro / GBA")
- O marcar como `geocoding_status=skipped` para permitir publicación sin coordenadas

---

## Impacto del enrichment en el publish_queue

### Campos del Amapa (81053-81056) — antes vs después

| staging_id | Título antes del enrichment | Título después (publicable) |
|---|---|---|
| 81053 | "Campo en venta en La Pampa" | **"Departamento Loventué Muy buen acceso 6.000 ha Cria"** |
| 81054 | "Campo en venta en La Pampa" | **"Limay Mahuida Oportunidad 15.000 ha Cria"** |
| 81055 | "Campo en venta en La Pampa" | **"Departamento Chalileo Oportunidad 30.000 ha Cria"** |
| 81056 | "Campo en venta en La Pampa" | **"Departamento Toay Bosque abierto 600 ha Ganaderia y Agricultura"** |

Estas 4 props ya estaban en la lista de encolables antes del enrichment (geo=skipped), pero con título genérico. Ahora entrarían con títulos ricos y descriptivos. **Impacto: mejora de calidad en 4 props ya encolables.**

### Watson (81057, 81059) — antes vs después

| staging_id | Precio antes | Precio después | Cambio en publish_queue |
|---|---|---|---|
| 81057 | None | **88,000 USD** | Sin cambio — sigue SKIP (geo_pending) |
| 81059 | None | **125,000 USD** | Sin cambio — sigue SKIP (geo_pending) |

Los precios están ahora correctos en raw y staging, pero Watson sigue excluido por `geocoding_status=pending` (sin ciudad ni provincia). **Impacto: mejora de datos pero no cambia el conteo de encolables.**

### Resumen de impacto del enrichment

| Métrica | Pre-enrichment | Post-enrichment | Delta |
|---|---|---|---|
| Encolables | 14 | 14 | 0 (mismo conteo) |
| Campos con título rico encolados | 0 (título genérico) | **4** | +4 calidad |
| Watson con precio en staging | 0 | 2 | +2 calidad (no encolados) |
| Datos correctos en raw | mejorado | mejorado | auditables |

---

## Análisis de los exclusiones restantes

### ¿Sigue faltando geocoding?

**Sí.** 10 de 24 props están excluidas por geocoding:
- 5 Innoacafayate geo_pending (calles específicas de Cafayate)
- 2 Innoacafayate geo_failed (Nominatim sin cobertura)
- 3 Watson geo_pending (sin ubicación en HTML/JSON-LD)

Solución posible: Google Maps API para Innoacafayate (7 props). Para Watson: sin datos de ubicación en la fuente → no hay API que ayude sin información base.

### ¿Sigue faltando precio?

**Sí, en 8 de las 14 encolables.** Esto es legítimo — son propiedades que no publican precio (consultar precio). No es un bug del scraper. Se pueden publicar igualmente.

### ¿Coordenadas disponibles?

Las 14 encolables tienen `geocoding_status=skipped` (Innoacafayate → coord ciudad=Cafayate aplicada por Fix A) o coordenadas directas. Sin coordenadas precisas de calle, pero con ciudad/provincia.

---

## Recomendación final

**Los 14 encolables son publicables tal como están.** Los títulos de Campos están ahora enriquecidos. Los precios de Watson están en raw/staging pero Watson no puede ser publicado aún sin ubicación.

Opciones para aumentar el conteo:

| Opción | Props ganables | Requiere |
|---|---|---|
| Google Maps API para Innoacafayate geo_pending | +5 (81036, 81038, 81041, 81042, 81044) | Autorización + API key |
| Resetear geo_failed → pending → re-geocodificar | +2 (81047, 81048) | Autorización + Google Maps API |
| Marcr Watson como geo=skipped (sin ubicación) | +2 (81057, 81059 — sí precio) o +3 | Decisión explícita: publicar sin ubicación |

**Sin acción adicional: 14 props listas para commit si se autoriza.**

---

## Estado de los controles

| Control | Estado |
|---|---|
| publish_queue commit | NO ejecutado |
| Supabase | NO tocado |
| publish_to_supabase.py | NO ejecutado |
| Frontend | NO tocado |
| .env | NO modificado |
| geocoding adicional | NO ejecutado |
| Nuevas importaciones | NO ejecutadas |
| Schema changes | NINGUNO |
| git push | NO ejecutado |

---

## FASE 5 — Freno activo

**STATUS: EN ESPERA DE AUTORIZACIÓN**

Todos los datos están correctos en raw y staging.  
14 props listas para publish_queue si se autoriza el commit.  
Reportes generados. Sin cambios en publish_queue.

---

*Dry-run: 2026-06-07 · post-enrichment-update · rama fix/scraping-diagnostics-batch · commit activo fe4ecd04*

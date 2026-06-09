# ETAPA 7C - Root fix agencia e imágenes

Fecha: 2026-06-09

## Resultado general

Se auditó el problema raíz antes de escalar a las 43 propiedades con warning fuerte.

No se ejecutó:

- `publish_to_supabase`
- `publish_queue`
- import
- geocoding
- SQL
- nuevas publicaciones
- updates masivos sobre propiedades publicadas

Se aplicó un fix de pipeline para futuras publicaciones:

- `scripts/image_quality.py`
- `scripts/publish_to_supabase.py`
- `scripts/test_image_quality.py`

Además se generó la propuesta no ejecutada:

- `reports/scraping_runs/import_controlado_20260608/etapa7c_vista_inmobiliaria_nombre_fix_proposal.md`

## Causa raíz inmobiliaria

Scope auditado: 41 propiedades publicadas.

| Dominio | Propiedades | ID publicado | Nombre correcto en `inmobiliarias_main` | Nombre en vista |
|---|---:|---:|---|---|
| `pagliaropropiedades.com.ar` | 29 | 4418 | Juan I. Pagliaro Propiedades | Re/Max Jardin |
| `svestudioinmobiliario.com.ar` | 10 | 6335 | SV Inmobiliaria | NULL |
| `inmobiliariamendocasa.com.ar` | 2 | 3532 | INMOBILIARIA & GESTORIA MENDOCASA LAVALLE | Agostina Garofalo Bienes Raices |

Hallazgo:

- `propiedades.inmobiliaria_id` coincide con `propiedades_staging.inmobiliaria_id`.
- `inmobiliarias_main` contiene los registros correctos para 4418, 6335 y 3532.
- `v_propiedades_frontend_mapa` devuelve nombres de otros registros o null.
- `pg_views` e `information_schema.views` no están expuestos por REST, y la definición SQL de la vista no está en el repo.

Conclusión:

El problema raíz está en la definición/resolución de `v_propiedades_frontend_mapa` o en una tabla auxiliar usada por esa vista. No se aplicó SQL porque no se pudo obtener la definición completa de la vista desde el entorno disponible.

## Propuesta de vista

Se generó:

`reports/scraping_runs/import_controlado_20260608/etapa7c_vista_inmobiliaria_nombre_fix_proposal.md`

Incluye:

- evidencia;
- consultas read-only para extraer `pg_views.definition`;
- validación esperada;
- fragmento conceptual de join a `inmobiliarias_main`;
- riesgos;
- rollback.

No incluye un `CREATE OR REPLACE VIEW` completo porque sería inventado sin la definición actual.

## Causa raíz imágenes

Problema observado:

- La vista podía exponer como `imagen_principal_real` un logo/branding.
- El array `imagenes` publicado venía encabezado por assets como:
  - `/imgs/inmobiliaria`
  - `inmobiliaria-`
  - `logo`
  - `footer`
  - `mascara-galeria`
  - `rounded-cds`
- Cuando había fotos reales más adelante, quedaban detrás del logo.

Causa en el flujo ETAPA 5/7:

- `publish_to_supabase.py` tomaba `staging.imagenes` tal cual.
- Si staging tenía logos al principio, se publicaban al principio.
- La vista/mapper podían corregir visualmente, pero la raíz seguía en el payload publicado.

## Fix aplicado en pipeline

Archivo nuevo:

- `scripts/image_quality.py`

Funciones:

- `is_branding_or_logo_image(value)`
- `normalize_property_images(values, max_images=60)`
- `has_real_property_image(values)`

Archivo modificado:

- `scripts/publish_to_supabase.py`

Cambio:

- `staging_to_prop()` ahora normaliza imágenes antes de armar el payload Supabase.
- Solo se envían imágenes reales limpias.
- Logos/branding/surface assets se descartan antes de publicar.
- Si solo hay logos, `imagenes` queda vacío para esa futura publicación; no se publica un logo como foto principal.

Archivo de tests:

- `scripts/test_image_quality.py`

Casos cubiertos:

- logo Pagliaro filtrado;
- logo SV filtrado;
- foto real preservada;
- array logo + fotos -> fotos primero;
- array solo logos -> sin imagen usable;
- URL normal no se filtra.

## Validación

Comandos:

```powershell
python -B -m unittest scripts.test_image_quality
python -B -m py_compile scripts/image_quality.py scripts/publish_to_supabase.py scripts/test_image_quality.py
```

Resultados:

- Unit tests: 6/6 OK.
- `py_compile`: OK.

Simulación local read-only sobre las 41 publicadas:

| Métrica | Resultado |
|---|---:|
| Scope simulado | 41 |
| Propiedades donde se descartaba/reordenaba la primera imagen | 39 |
| Imágenes limpias totales resultantes | 152 |
| Assets descartados totales | 146 |
| Propiedades que quedarían sin imagen usable | 5 |

Las 5 que quedarían sin imagen usable son SV:

- 81647
- 81650
- 81651
- 81653
- 81654

Esto es deseable como compuerta: antes de futuras publicaciones, esas propiedades deberían tratarse como warning de imagen y no publicarse con logo.

## Impacto esperado

Futuras publicaciones por `publish_to_supabase.py`:

- no enviarán logos/branding como primera imagen;
- no enviarán logos/branding como imágenes de propiedad;
- preservarán fotos reales;
- dejarán sin imágenes las filas que solo tienen logos, forzando revisión o warning.

No cambia propiedades ya publicadas.

## Qué queda pendiente antes de las 43 warning fuerte

1. Extraer definición real de `v_propiedades_frontend_mapa` desde Supabase SQL Editor.
2. Preparar y revisar migración para que `inmobiliaria_nombre` venga de la fuente canónica correcta.
3. Decidir política para propiedades sin imagen usable después del filtro:
   - excluir de publish queue;
   - o enriquecer imágenes antes de publicar.
4. Reauditar un subconjunto pequeño de las 43 warning fuerte con la nueva compuerta de imágenes, sin publish ni queue commit.

## Estado final

ETAPA 7C deja listo el root fix de imágenes para futuras publicaciones, pero no aplica todavía el fix raíz de vista porque falta la definición SQL real.

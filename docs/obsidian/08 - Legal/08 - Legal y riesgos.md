# Legal y riesgos

Ultima actualizacion: 2026-06-04

Esta nota ordena riesgos legales y criterios de cuidado. No reemplaza asesoramiento legal profesional.

## Regla principal

Antes de un lanzamiento publico amplio, consultar con un abogado.

## Riesgos principales

- Scraping y terminos de uso de sitios externos.
- Uso de imagenes.
- Datos personales.
- Informacion desactualizada.
- Confusion sobre responsabilidad comercial.
- Reclamos de inmobiliarias o desarrolladoras.
- Publicacion de datos incorrectos.

## Criterios de cuidado

- Mantener link a la publicacion original.
- No vender propiedades directamente.
- No presentarse como propietario ni inmobiliaria.
- No inventar datos faltantes.
- No publicar datos dudosos como si fueran verificados.
- No usar imagenes placeholder/logos como fotos reales.
- No ocultar fuente.
- Permitir correcciones o bajas si una inmobiliaria lo solicita.

## Estado actual

No se recomienda publicar masivamente todavia.

Motivos:

- Hay propiedades retenidas por calidad.
- Muchas requieren geocoding.
- Existen faltantes de ubicacion, precio e imagen real.
- Falta definir politica de duplicados.
- Falta revisar legalmente el lanzamiento publico.

## Publicacion controlada futura

Antes de publicar:

- Seleccionar solo propiedades de maxima calidad.
- Revisar trazabilidad y fuente.
- Validar que el frontend derive a la fuente original/inmobiliaria.
- Evitar textos que parezcan oferta comercial propia.
- Preparar terminos, privacidad y mecanismo de contacto/baja.

## Datos personales y contacto

Si se muestran telefono, email o WhatsApp:

- Usar solo informacion publicada por la fuente.
- No mezclar telefonos/emails con direccion.
- No inferir contactos.
- No publicar datos privados.

## Imagenes

Riesgo relevante:

- Las imagenes pueden tener derechos de terceros.

Criterios:

- Priorizar link a la publicacion original.
- No cachear o republicar masivamente imagenes sin evaluar riesgo.
- Descartar logos, placeholders, iconos y mapas como imagen real.

## Scraping

El scraping debe ser prudente:

- Workers bajos.
- Timeouts.
- No afectar sitios externos.
- Respetar bloqueos claros.
- Clasificar sitios caidos/bloqueados.
- No insistir infinitamente.

## Notas relacionadas

- [[05 - Scraping]]
- [[04 - Supabase y base de datos]]
- [[Politicas de calidad y publicacion]]
- [[10 - Decisiones importantes]]

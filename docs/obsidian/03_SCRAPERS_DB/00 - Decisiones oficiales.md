# Decisiones oficiales — Scrapers y Base de datos

Ultima actualizacion: 2026-06-09

Esta nota registra las decisiones oficiales del proyecto referidas a scraping, base de datos, pipeline, propiedades y datos.

---

## Alcance geografico del proyecto

**Oficial desde: 2026-06-09**

ERETZ Propiedades tiene alcance nacional: Argentina completa.

No es un proyecto limitado a una ciudad ni a una provincia.

- Todas las inmobiliarias ya cargadas en la base de datos forman parte del sistema.
- Santa Fe capital puede ser la primera ciudad fuerte en marketing, pero el producto debe contemplar todas las provincias desde el diseño.
- La cobertura se amplia gradualmente segun disponibilidad de datos y capacidad de scraping.

---

## Prioridad actual de desarrollo

**Oficial desde: 2026-06-09**

La prioridad absoluta es scrapers + base de datos.

Orden estricto:

1. Estabilizar el sistema de scraping y persistencia de datos.
2. Luego: frontend publico.
3. Luego: panel de inmobiliarias.
4. Luego: carga manual.
5. Luego: marketing y crecimiento.
6. Luego: monetizacion.

No avanzar fuerte con frontend, panel de inmobiliarias ni marketing hasta que el sistema de scraping y persistencia este estable.

---

## Regla principal de propiedades

**Oficial desde: 2026-06-09**

Todas las propiedades deben guardarse y publicarse aunque tengan datos incompletos.

Reglas:

- No descartar ninguna propiedad por falta de imagenes, precio, descripcion, coordenadas, operacion clara ni calidad de datos.
- Si no tiene precio: mostrar "Consultar precio".
- Si no se sabe si es venta o alquiler: mostrar "Consultar".
- Una propiedad puede ser venta y alquiler a la vez.
- Si no tiene coordenadas: aparecer en listado, no en mapa.
- Si no tiene imagenes: aparecer con imagen placeholder.

Esta regla contradice decisiones previas que priorizaban retener propiedades dudosas en staging. La nueva politica es: guardar y publicar todo, con indicadores de datos faltantes visibles.

---

## Estados posibles de una propiedad

**Oficial desde: 2026-06-09**

Ver nota: [[08 - Estados de propiedades]]

Estados:

- `activa`
- `reservada`
- `vendida`
- `alquilada`
- `no_detectada_en_ultimo_scraping`
- `consultar`
- `desconocida`

Regla sobre propiedades que desaparecen del sitio original:

- No se borran.
- Se conservan como historico.
- Se marcan como `no_detectada_en_ultimo_scraping`.
- Comercialmente pueden mostrarse como vendida/no disponible.
- Tecnicamente se conserva el estado exacto para evitar errores por fallas de scraping.
- Si la web original indica vendida, alquilada o reservada: registrar ese estado.
- Las propiedades vendidas, alquiladas o reservadas pueden seguir mostrándose con cartel correspondiente.

---

## Propiedades repetidas entre inmobiliarias

**Oficial desde: 2026-06-09**

Ver nota: [[07 - Deduplicacion]]

Si una misma propiedad aparece en varias inmobiliarias:

- Se muestra como publicaciones separadas.
- No se fusionan automaticamente en una unica publicacion.
- A futuro puede mostrarse que "tambien esta publicada por otras inmobiliarias".
- Por ahora se conservan separadas.

---

## Actualizacion diaria y batches

**Oficial desde: 2026-06-09**

El objetivo es actualizar informacion diariamente.

- No conviene hacer un unico scraping gigante.
- Se recomienda usar batches o cola de scraping.

Posibles divisiones de los batches:

- Por provincia.
- Por tipo de web.
- Por inmobiliaria.
- Por prioridad.
- Por ultimo scraping exitoso.
- Por cantidad de errores.

Logs y trazabilidad obligatorios:

- Registrar logs, errores, reintentos y fecha de ultima corrida.
- Cada batch debe tener ID, estado, inicio, fin y resultado.

---

## Notas relacionadas

- [[08 - Estados de propiedades]]
- [[07 - Deduplicacion]]
- [[03 - Modelo de datos propiedades]]
- [[10 - Decisiones importantes]]
- [[Roadmap 2026-06-09]]

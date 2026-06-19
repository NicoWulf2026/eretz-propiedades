# Batches diarios de scraping

Ultima actualizacion: 2026-06-09

---

## Objetivo

Actualizar informacion de propiedades diariamente de forma automatica y controlada.

No se hace un unico scraping gigante. Se usa un sistema de batches o cola de scraping.

---

## Estrategias de division de batches

Posibles criterios para dividir el scraping diario:

- Por provincia.
- Por tipo de web (WordPress, cdh, Webnode, PHP custom, etc.).
- Por inmobiliaria.
- Por prioridad (inmobiliarias activas, con mas propiedades, con scraping exitoso reciente).
- Por ultimo scraping exitoso (las que tienen mas tiempo sin actualizar van primero).
- Por cantidad de errores acumulados (las mas problematicas van al final o a un batch separado).

---

## Logs y trazabilidad

Cada corrida de scraping debe registrar:

- ID del batch.
- Fecha y hora de inicio.
- Fecha y hora de fin.
- Estado: exitoso, parcial, error, timeout.
- Cantidad de propiedades detectadas.
- Cantidad de propiedades nuevas.
- Cantidad de propiedades actualizadas.
- Cantidad de errores.
- Reintentos.

---

## Estado actual

Por implementar. El sistema de batches diarios automaticos no esta activo todavia.

Pendiente: definir cola de scraping, scheduler y sistema de logs.

---

## Notas relacionadas

- [[00 - Decisiones oficiales]]
- [[05 - Logs y errores]]

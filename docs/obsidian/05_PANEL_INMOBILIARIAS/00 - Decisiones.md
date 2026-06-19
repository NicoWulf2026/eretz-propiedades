# Panel de inmobiliarias — Decisiones oficiales

Ultima actualizacion: 2026-06-09

El panel de inmobiliarias se desarrolla DESPUES del frontend publico.

Ver orden de desarrollo: [[Roadmap 2026-06-09]]

---

## Funcion del panel

Las inmobiliarias podran:

- Reclamar y verificar su perfil.
- Editar propiedades scrapeadas de su web.
- Corregir datos incorrectos.
- Agregar imagenes.
- Marcar propiedades como vendida, alquilada o reservada.
- Cargar nuevas propiedades manualmente.

---

## Autenticacion

- Acceso con usuario y contrasena.
- El usuario puede ser el email oficial de la inmobiliaria.
- Es preferible enviar un link seguro para crear contrasena, no una contrasena fija.
- No hardcodear contrasenas iniciales.

---

## Reclamo de perfil

El proceso de verificacion de perfil debe:

- Confirmar que la persona que reclama el perfil representa a la inmobiliaria.
- Usar el email oficial de la inmobiliaria como canal de verificacion.
- Enviar un link de acceso con token de un solo uso.

---

## Carga manual — Inmobiliarias

Las inmobiliarias verificadas pueden cargar propiedades manualmente.

Sin campos obligatorios minimos definidos todavia. A definir en la fase de desarrollo.

---

## Carga manual — Particulares

Personas particulares tambien pueden cargar propiedades.

Campos minimos sugeridos para particulares:

- Tipo de operacion (venta / alquiler).
- Tipo de propiedad.
- Precio o marcar "consultar precio".
- Direccion aproximada o zona.
- Ciudad.
- Provincia.
- Descripcion minima.
- Superficie (si la sabe).
- Cantidad de ambientes (si aplica).
- Fotos obligatorias (minimo 1).
- Nombre de contacto.
- Telefono o email.

Las publicaciones de particulares deben pasar por revision antes de publicarse.

---

## Moderacion

- Las publicaciones de particulares requieren revision manual antes de publicarse.
- Las inmobiliarias verificadas no requieren revision para propiedades que ya estan en el sistema.
- Las propiedades nuevas cargadas por inmobiliarias pueden publicarse directamente o con revision segun política a definir.

---

## Notas relacionadas

- [[Roadmap 2026-06-09]]
- [[00 - Decisiones oficiales]]
- [[Reclamo de perfil]]
- [[Login inmobiliarias]]

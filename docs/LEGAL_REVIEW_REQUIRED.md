# ERETZ Propiedades — inventario para revisión legal

Fecha: 2026-08-27

## Qué es y qué no es este documento

**No es asesoramiento legal, y no lo escribió alguien habilitado para darlo.**

Es un inventario técnico: qué hace el sistema hoy, qué dicen hoy las páginas
legales, y dónde hay distancia entre las dos cosas. Cada punto está clasificado
para que quien lo revise sepa qué está mirando:

| Etiqueta | Significa |
| --- | --- |
| `TECHNICAL_FACT` | Cómo funciona el sistema. Verificable en el código o en la base. No es opinable. |
| `PRODUCT_POLICY` | Una decisión de producto ya tomada, o que hay que tomar. No requiere abogado. |
| `LEGAL_REVIEW_REQUIRED` | Requiere una persona habilitada. **No se resolvió acá.** |

Las páginas actuales están rotuladas *"Borrador para revisión legal · julio de
2026"*, lo cual es correcto: no afirman haber pasado por una revisión que no
pasaron. Ese rótulo debe seguir hasta que efectivamente la haya.

## Páginas existentes

| Ruta | Estado |
| --- | --- |
| `/terminos` | borrador, 5 secciones |
| `/privacidad` | borrador, 5 secciones |
| `/baja-o-correccion` | borrador, 3 secciones |
| `/contacto` | borrador, 3 secciones |

Las cuatro son `noindex`. Son honestas en lo que dicen —no prometen garantías
que el sistema no da, ni afirman controles que no existen—. Lo que sigue es lo
que **no** dicen.

---

## 1. Nombres de agentes publicados sin consentimiento

**`TECHNICAL_FACT`.** La base tiene `agente_nombre` con nombres de personas
extraídos de sitios de inmobiliarias, y esos nombres se muestran en las fichas.
Son personas reales que no fueron notificadas, no consintieron, y hoy no tienen
forma de pedir que se los quite salvo escribiendo al correo genérico.

**`TECHNICAL_FACT`.** El modelo de dominio ya separa identidad *inferida* de
*reclamada* (`domain/agent.ts`) y restringe la publicación de un **perfil** a
quien lo reclamó. Eso limita el problema hacia adelante; no resuelve que el
nombre ya aparece en las fichas.

**`LEGAL_REVIEW_REQUIRED`.** Si mostrar un nombre profesional que ya es público
en el sitio de su empleador requiere base legal propia, y cuál. Qué obligación
de información existe hacia esas personas. Cómo se articula con el derecho de
supresión.

Es el punto de mayor exposición del inventario y el que menos cubren las páginas
actuales: ni términos ni privacidad lo mencionan.

## 2. Fotos y textos de terceros

**`TECHNICAL_FACT`.** Se almacenan URLs de imágenes alojadas por las
inmobiliarias y se muestran desde el navegador de quien visita. Las
descripciones se copian y se guardan como texto.

**`PRODUCT_POLICY`.** Ya decidido: nunca se re-alojan imágenes ni se presentan
como propias.

**`LEGAL_REVIEW_REQUIRED`.** Si copiar y almacenar el texto descriptivo —a
diferencia de enlazar la imagen— requiere permiso. Qué régimen aplica a la base
de datos agregada. Qué corresponde ante un reclamo de titularidad.

Los términos dicen que la información "proviene de la publicación original",
que es cierto pero no aborda la titularidad.

## 3. La política de privacidad no contempla los formularios

**`TECHNICAL_FACT`.** `/privacidad` dice: *"Si escribís a nuestro correo… "*, y
describe sólo la vía de email.

**`TECHNICAL_FACT`.** Existen `/api/reports` y `/api/claims`, que reciben datos
por formulario web, no por correo. Hay una tabla preparada para reportes (hoy
con 0 filas y sin writer configurado, ver la matriz de capacidades). Cuando el
writer se active, habrá datos aportados por personas guardados en base.

**Distancia concreta:** la política describe un canal y el sistema tiene dos.

**`PRODUCT_POLICY`.** Actualizar la redacción para cubrir los formularios,
incluso mientras el writer siga apagado. Es lo que evita que activarlo genere
una divergencia silenciosa.

**`LEGAL_REVIEW_REQUIRED`.** Qué información hay que dar en el punto de
recolección y qué conservación corresponde.

## 4. Almacenamiento en el navegador

**`TECHNICAL_FACT`.** "Mi ERETZ" usa `localStorage` para favoritos, colecciones,
comparación, historial y búsquedas recientes (`lib/local-store.ts`). No son
cookies y **no salen del dispositivo**: no llegan a ningún servidor, ni al
nuestro ni a terceros.

**`TECHNICAL_FACT`.** No hay proveedor de analítica configurado.
`lib/analytics.ts` emite un `CustomEvent` local que nada escucha. La política
dice *"una capa técnica deshabilitada"*, y es exacto.

**`LEGAL_REVIEW_REQUIRED`.** Si almacenamiento local puramente funcional exige
aviso o consentimiento previo bajo la normativa aplicable. La respuesta cambia
el diseño de la interfaz, no sólo el texto.

## 5. Retención

**`TECHNICAL_FACT`.** No hay política de retención escrita ni implementada. Los
datos de scraping se conservan indefinidamente. Un reporte enviado se guardaría
sin plazo de borrado definido.

**`PRODUCT_POLICY`.** Definir plazos. No requiere abogado para proponerlos.

**`LEGAL_REVIEW_REQUIRED`.** Si hay plazos mínimos o máximos obligatorios.

## 6. Derecho de baja y corrección

**`TECHNICAL_FACT`.** `/baja-o-correccion` describe un procedimiento por correo.
No hay expediente, ni estados, ni plazo comprometido, ni forma de que la persona
sepa en qué quedó. `domain/reports.ts` modela eso pero no está persistido.

**`TECHNICAL_FACT`.** El dominio ya decide que solicitar una baja **no oculta
por sí solo** (`domain/overrides.ts`), porque el flujo podría usarse para borrar
competencia. Abre un caso.

**`LEGAL_REVIEW_REQUIRED`.** Qué plazo de respuesta corresponde y si esa demora
—entre la solicitud y la decisión— es admisible cuando el reclamo es de la
persona titular del dato.

## 7. Lo que todavía no existe

Nada de esto está construido, y **ninguna de las páginas legales lo menciona**.
Se listan ahora porque la revisión conviene hacerla una vez:

- **cuentas** (`domain/auth.ts`): registro, datos personales de usuarios;
- **publicación manual** (`domain/publishing.ts`): responsabilidad sobre lo que
  publica un particular, declaración de legitimidad —ya modelada como requisito—;
- **reclamación de inmobiliarias** (`domain/claim.ts`): verificación de
  identidad y consecuencias de un error de atribución;
- **analítica profesional** (`domain/professional-analytics.ts`): qué se le
  muestra a una inmobiliaria sobre quienes visitaron sus avisos. Ya está
  decidido que **no se guarda el texto de búsqueda** ni hay identificador de
  usuario, sólo sesión anónima;
- **alertas** (`domain/alerts.ts`): comunicaciones comerciales por email.

## 8. Marco aplicable

**`TECHNICAL_FACT`.** El servicio opera sobre inmuebles en Argentina y la
infraestructura está en `us-east-1` (Supabase). Es una transferencia
internacional de datos.

**`LEGAL_REVIEW_REQUIRED`.** Qué normativa aplica —la Ley 25.326 es la
referencia obvia, pero determinar su alcance sobre este caso no es una tarea
técnica—, qué exige la localización de la infraestructura, y si corresponde
alguna inscripción o designación.

---

## Resumen para quien revise

Tres cosas antes de beta pública, en orden de exposición:

1. **Nombres de personas** publicados sin consentimiento ni vía de contacto
   directa (punto 1).
2. **Titularidad del contenido** copiado de terceros (punto 2).
3. **Divergencia entre la política y el sistema** en los canales de recolección
   (punto 3) — la única que se puede cerrar sin abogado, sólo redactando.

Ninguna se resolvió acá. Beta **privada** puede continuar; el veredicto de beta
pública no cambia por este documento.

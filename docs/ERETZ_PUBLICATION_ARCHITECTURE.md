# ERETZ Propiedades — arquitectura de publicación

Fecha: 2026-08-28

## La frontera

```
  UI (wizard)
      ↓
  Application Service        lib/publication/service.ts
      ↓
  PublicationRepository      lib/publication/repository.ts   ← LA FRONTERA
      ↓
  (futuro adaptador de persistencia)
```

La UI no sabe qué hay del otro lado, y el contrato no lo menciona: no aparece
Supabase, ni PostgreSQL, ni tablas, ni SQL, ni un proveedor de archivos. Cuando
exista persistencia real se implementa esa interfaz y **no se toca ni el wizard
ni el servicio**.

El servicio no importa nada de React. Se prueba entero sin montar un
componente, y el mismo código serviría desde una ruta de API o una server
action.

La prueba de que la frontera es real es el adaptador en memoria: si el servicio
dependiera de algo de la base, ese adaptador no podría existir. Existe, y los 27
tests del servicio corren contra él.

## Estado de cada pieza

| Pieza | Estado | Nota |
| --- | --- | --- |
| Wizard de 8 pasos | `IMPLEMENTED` | Tras flag, sin enlazar |
| Validación | `IMPLEMENTED` | Reutiliza `domain/publishing.ts` |
| Precheck de moderación | `IMPLEMENTED` | Reutiliza `domain/moderation.ts` |
| Sugerencias de calidad | `IMPLEMENTED` | Sin mostrar el puntaje |
| Borrador y autosave | `LOCAL_ONLY` | `localStorage`, versionado |
| Permisos y tenancy | `IMPLEMENTED` | Reutiliza `domain/permissions.ts` |
| Idempotencia | `IMPLEMENTED` | Clave del cliente |
| Auditoría | `READY_FOR_BACKEND` | Contrato, sin guardar |
| Contrato de repositorio | `READY_FOR_BACKEND` | Con adaptador en memoria |
| Contrato de medios | `READY_FOR_BACKEND` | Sin proveedor elegido |
| Precheck de duplicados | `READY_FOR_BACKEND` | Reutiliza el scorer; falta pasarle candidatos |
| **Persistencia real** | `BLOCKED_BACKEND` | No existe |
| **Subida de imágenes** | `BLOCKED_BACKEND` | No existe |
| Base de datos | `DEFERRED_DB` | Sin cambios |

## Decisiones que conviene conocer

### El envío no existe, y no hay botón

La pantalla de revisión llega a "listo para publicar" y se detiene. **No hay
botón de publicar**, y no es un olvido: no existe dónde guardar, y un botón ahí
aceptaría el trabajo de alguien para perderlo.

Hay un test E2E que verifica que ese botón no exista en ninguna parte.

### Las imágenes no se suben ni se guardan

Se eligen, se previsualizan, se ordenan y se validan — todo en el dispositivo.
La vista previa usa `URL.createObjectURL`, que referencia el archivo ya en
memoria del navegador en vez de copiarlo, y se revoca al quitarla o al salir.

**No se guardan en el borrador local.** Un `localStorage` tiene unos pocos
megabytes y una sola foto de celular los llena: guardarlas en base64 rompería el
guardado de todo lo demás, y justo cuando más contenido hay. Se guardan los
nombres para poder decir "faltan volver a cargar las fotos".

El contrato futuro tiene cuatro pasos —`presign`, `upload`, `confirm`,
`attach`— y son cuatro porque **el archivo no pasa por nuestro servidor**: se
sube directo al proveedor con una URL firmada. Subirlo a través del servidor
haría que cada foto de 5 MB ocupara memoria y tiempo de una función.

### El borrador es de este dispositivo, y lo dice

La UI dice *"borrador en este dispositivo"* y nunca *"guardado en tu cuenta"*.
Hay un test que verifica las dos cosas.

Va versionado con `draftVersion`. Un borrador de otra versión del formulario
**se descarta**, no se migra a ciegas: restaurar a medias es peor que no
restaurar, porque parece que funcionó.

### La clave de idempotencia la genera el cliente

Si la generara el servidor, dos requests del mismo doble click traerían claves
distintas y crearían dos publicaciones — exactamente lo que la clave existe para
evitar. El cliente la genera al abrir el formulario y la conserva durante todo
el envío, reintentos incluidos.

`DUPLICATE_SUBMISSION` **no se muestra como error**: significa que el envío ya
se procesó. Mostrar un error haría que la persona lo intentara de nuevo.

### El tenant sale del actor cargado, nunca del cliente

Un `organizationId` que llega en el body es una afirmación, no una prueba. El
actor lo arma el servidor a partir de la sesión y las membresías cargadas, y el
motor de permisos existente decide. Hay un test que verifica que ser OWNER de
una organización no habilite publicar en otra.

### Moderación: acá sí se bloquea

Una carga manual con datos contradictorios **se bloquea**. Es la asimetría que
ya estaba en `domain/moderation.ts` y que acá se aplica del lado estricto:
rechazar una carga manual cuesta un minuto de quien la hizo; esconder una
scrapeada borra inventario que existe.

Esto **no es** el modo sombra del catálogo ni lo modifica. Son dos usos del
mismo motor sobre contenidos distintos.

### No se muestra el puntaje de calidad

Se calcula y se traduce en cosas que hacer: *"Agregá más fotos"*, *"Completá la
dirección"*. Un "82/100" invita a optimizar la métrica en vez de la publicación,
y no le dice a nadie qué hacer. Hay un test que verifica que no aparezca ningún
número de esa forma.

### Un posible duplicado no impide publicar

El caso más común de coincidencia parcial no es alguien duplicando: es una
inmobiliaria cargando a mano una propiedad que ya scrapeamos de su propio sitio.
Bloquearla sería impedirle publicar lo suyo. Se avisa y no se bloquea, y **una
carga manual nunca modifica una scrapeada**.

## Cómo se conecta la persistencia

Cuando exista, el trabajo es implementar `PublicationRepository`. Nada más.

Lo que ese adaptador tendrá que hacer atómico:

1. la fila de la publicación,
2. los metadatos de las imágenes y su orden,
3. la relación con el publicador (particular, agente u organización),
4. el evento de auditoría,
5. el estado de moderación inicial.

Si (1) entra y (2) falla, queda una publicación sin fotos que nadie sabe que
está incompleta. Si (4) falla, se pierde el registro de quién publicó qué.

Sobre la forma del borde HTTP: el repositorio no la impone. Server actions o
rutas de API, **una sola dirección**, y la decisión se toma cuando se implemente
—no ahora, y no las dos.

## Cómo probarlo

```
ERETZ_PUBLICATION_WIZARD_PREVIEW=true
```

Server-only, apagada por defecto, sin prefijo `NEXT_PUBLIC_`. Con la flag
apagada la ruta `/internal/publicar-preview` devuelve 404, que es lo mismo que
vería quien adivine la URL.

**No se activa en producción.**

## Lo que NO está expuesto

- ningún enlace en la navegación;
- ningún CTA en la home ni en los perfiles;
- la ruta es `noindex, nofollow` por su cuenta, además del `robots.ts` global;
- no hay botón de publicar.

Un test E2E verifica que no exista ningún enlace hacia el wizard desde la home.

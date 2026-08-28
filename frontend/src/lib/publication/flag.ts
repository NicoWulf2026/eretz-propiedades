import "server-only";

// Interruptor del wizard de publicación.
//
// Apagado por defecto y server-only. Sin prefijo `NEXT_PUBLIC_`: la decisión se
// toma en el servidor y la ruta devuelve 404 cuando está apagada, así que el
// wizard no llega ni siquiera al bundle del cliente en una build normal.
//
// Igual que el modo sombra: sólo el string exacto `"true"` enciende. No hay
// `!== "false"`, que es la forma habitual de que algo se encienda por accidente.
//
// **No se activa en producción.** El wizard no puede cumplir su promesa —no hay
// dónde guardar— y exponerlo sería aceptar el trabajo de alguien para perderlo.

export const VAR_WIZARD = "ERETZ_PUBLICATION_WIZARD_PREVIEW";

export function wizardHabilitado(env: NodeJS.ProcessEnv = process.env): boolean {
  return env[VAR_WIZARD] === "true";
}

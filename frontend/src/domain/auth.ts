// Contratos de autenticación, agnósticos del proveedor.
//
// No hay implementación acá, y no es una omisión: ERETZ todavía no tiene
// cuentas, y este archivo existe para que el día que las tenga no haya que
// elegir proveedor y reescribir la aplicación al mismo tiempo.
//
// Que sea agnóstico importa por una razón concreta: la Data API de Supabase
// está deliberadamente apagada para el navegador, y Supabase Auth es una
// biblioteca de cliente. Adoptarla sin una capa intermedia metería llamadas
// desde el browser a un servicio que hoy se mantiene server-only a propósito.
// La interfaz permite decidir eso después, y cambiarlo sin tocar la UI.
//
// ---------------------------------------------------------------------------
// ERETZ FUNCIONA SIN CUENTA, Y ESO NO CAMBIA
// ---------------------------------------------------------------------------
//
// Explorer, mapa, búsqueda, filtros, fichas, favoritos, comparación y
// colecciones funcionan hoy sin cuenta y tienen que seguir funcionando. La
// cuenta agrega sincronización entre dispositivos y capacidades profesionales;
// no es un peaje para mirar propiedades.
//
// Por eso `SessionState` tiene una variante anónima explícita en vez de
// `Session | null`: obliga a que cada consumidor decida qué hace con el
// anónimo, en lugar de tratarlo como un error o un estado de carga.

import type { UserId } from "./ids";

export type AuthMethod = "PASSWORD" | "OAUTH_GOOGLE" | "MAGIC_LINK";

/** Datos mínimos de una persona. Nada de esto es obligatorio para navegar. */
export type UserProfile = {
  userId: UserId;
  firstName: string | null;
  lastName: string | null;
  email: string;
  phone: string | null;
  emailVerified: boolean;
  createdAt: string;
};

export type Session = {
  userId: UserId;
  /** Cuándo expira. La UI no debe asumir sesiones eternas. */
  expiresAt: string;
  method: AuthMethod;
};

/**
 * Estado de sesión. Tres variantes, no dos.
 *
 * `UNKNOWN` es el intervalo antes de saber si hay sesión. Sin él, la UI trata
 * "todavía no sé" como "anónimo" y muestra por un instante el estado
 * equivocado —el parpadeo clásico de "iniciar sesión" a quien ya la tiene—.
 */
export type SessionState =
  | { kind: "UNKNOWN" }
  | { kind: "ANONYMOUS" }
  | { kind: "AUTHENTICATED"; session: Session; profile: UserProfile };

export function estaAutenticado(s: SessionState): s is Extract<SessionState, { kind: "AUTHENTICATED" }> {
  return s.kind === "AUTHENTICATED";
}

/** ¿Ya sabemos el estado? Lo que la UI necesita para no parpadear. */
export function sesionResuelta(s: SessionState): boolean {
  return s.kind !== "UNKNOWN";
}

// --- resultados ------------------------------------------------------------

/**
 * Motivos de fallo, como códigos y no como mensajes.
 *
 * El texto que ve la persona se decide en la UI, en su idioma. Y un detalle
 * que no es cosmético: `CREDENCIALES_INVALIDAS` no distingue entre "ese email
 * no existe" y "la contraseña está mal", a propósito. Distinguirlos convierte
 * el login en un oráculo para averiguar qué emails están registrados.
 */
export const AUTH_ERRORS = [
  "CREDENCIALES_INVALIDAS",
  "EMAIL_NO_VERIFICADO",
  "CUENTA_BLOQUEADA",
  "DEMASIADOS_INTENTOS",
  "TOKEN_INVALIDO",
  "TOKEN_EXPIRADO",
  "PROVEEDOR_NO_DISPONIBLE",
] as const;
export type AuthError = (typeof AUTH_ERRORS)[number];

export type AuthResult<T> = { ok: true; value: T } | { ok: false; error: AuthError };

// --- el puerto -------------------------------------------------------------

/**
 * Lo que ERETZ necesita de un proveedor de identidad.
 *
 * Deliberadamente chico. Cada método que se agregue acá es un método que todo
 * proveedor futuro tendrá que soportar.
 *
 * Ninguna operación devuelve tokens crudos: la sesión se maneja con cookies
 * HttpOnly del lado del servidor. Un token en JavaScript es un token que
 * cualquier XSS se lleva.
 */
export type AuthProvider = {
  obtenerSesion(): Promise<SessionState>;
  registrar(datos: {
    email: string;
    password: string;
    firstName?: string;
    lastName?: string;
  }): Promise<AuthResult<UserProfile>>;
  iniciarSesion(datos: { email: string; password: string }): Promise<AuthResult<Session>>;
  cerrarSesion(): Promise<void>;
  iniciarOAuth(proveedor: "google", redireccion: string): Promise<AuthResult<{ url: string }>>;
  solicitarRestablecimiento(email: string): Promise<AuthResult<void>>;
  restablecerPassword(token: string, nueva: string): Promise<AuthResult<void>>;
  solicitarVerificacionEmail(): Promise<AuthResult<void>>;
  verificarEmail(token: string): Promise<AuthResult<void>>;
};

/**
 * ¿La respuesta a un intento de login revela si el email existe?
 *
 * Existe como función para poder testear la propiedad, no sólo documentarla.
 * Un flujo de registro o de restablecimiento que responda distinto según si el
 * email está registrado permite enumerar usuarios.
 */
export function revelaExistenciaDeCuenta(error: AuthError): boolean {
  return error === "EMAIL_NO_VERIFICADO" || error === "CUENTA_BLOQUEADA";
}

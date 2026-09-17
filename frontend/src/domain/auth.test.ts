import { describe, expect, it } from "vitest";
import { userId } from "./ids";
import {
  AUTH_ERRORS,
  type SessionState,
  estaAutenticado,
  revelaExistenciaDeCuenta,
  sesionResuelta,
} from "./auth";

const AUTENTICADO: SessionState = {
  kind: "AUTHENTICATED",
  session: { userId: userId("u-1"), expiresAt: "2026-09-01", method: "PASSWORD" },
  profile: {
    userId: userId("u-1"),
    firstName: "Ana",
    lastName: null,
    email: "ana@ejemplo.com",
    phone: null,
    emailVerified: true,
    createdAt: "2026-08-01",
  },
};

describe("estado de sesión", () => {
  it("distingue no saber todavía de ser anónimo", () => {
    // Sin esa distinción la UI muestra "iniciar sesión" a quien ya la tiene,
    // por un instante, en cada carga.
    expect(sesionResuelta({ kind: "UNKNOWN" })).toBe(false);
    expect(sesionResuelta({ kind: "ANONYMOUS" })).toBe(true);
    expect(sesionResuelta(AUTENTICADO)).toBe(true);
  });

  it("sólo el autenticado tiene sesión y perfil", () => {
    expect(estaAutenticado(AUTENTICADO)).toBe(true);
    expect(estaAutenticado({ kind: "UNKNOWN" })).toBe(false);
    expect(estaAutenticado({ kind: "ANONYMOUS" })).toBe(false);
  });

  it("estrecha el tipo para poder acceder al perfil", () => {
    const s: SessionState = AUTENTICADO;
    if (estaAutenticado(s)) expect(s.profile.email).toBe("ana@ejemplo.com");
    else expect.unreachable("debería estar autenticado");
  });
});

describe("no filtrar qué cuentas existen", () => {
  it("credenciales inválidas no revela si el email está registrado", () => {
    // Distinguir "no existe" de "contraseña mal" convierte el login en un
    // oráculo para enumerar usuarios.
    expect(revelaExistenciaDeCuenta("CREDENCIALES_INVALIDAS")).toBe(false);
  });

  it("marca los errores que sí revelarían la existencia de una cuenta", () => {
    // No se prohíben: hay flujos donde son correctos (alguien ya autenticado).
    // Se marcan para que un login público no los devuelva sin pensarlo.
    expect(revelaExistenciaDeCuenta("EMAIL_NO_VERIFICADO")).toBe(true);
    expect(revelaExistenciaDeCuenta("CUENTA_BLOQUEADA")).toBe(true);
  });

  it("los errores genéricos son seguros", () => {
    for (const e of ["DEMASIADOS_INTENTOS", "TOKEN_INVALIDO", "TOKEN_EXPIRADO", "PROVEEDOR_NO_DISPONIBLE"] as const) {
      expect(revelaExistenciaDeCuenta(e)).toBe(false);
    }
  });

  it("todo error declarado está clasificado", () => {
    for (const e of AUTH_ERRORS) {
      expect(typeof revelaExistenciaDeCuenta(e)).toBe("boolean");
    }
  });
});

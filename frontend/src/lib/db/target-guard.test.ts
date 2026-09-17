import { describe, expect, it } from "vitest";
// La guarda vive en scripts/ y no en src/: es código de operación y no tiene por
// qué viajar en el bundle. Se importa por ruta relativa para poder testearla.
import {
  MOTIVOS,
  USUARIOS_PROHIBIDOS,
  evaluarDestino,
  exigirDestinoSeguro,
  identidadDeDsn,
  refDeProyecto,
} from "../../../scripts/db-target-guard.mjs";

const REF_PROD = "pggrvzyixyjkhfknpurg";
const REF_PREVIEW = "abcdefghijklmnopqrst";

const dsn = (usuario: string, host: string) =>
  `postgresql://${usuario}:cl4v3@${host}:5432/postgres`;

const prod = dsn("eretz_app", `db.${REF_PROD}.supabase.co`);
const preview = dsn("eretz_app", `db.${REF_PREVIEW}.supabase.co`);

describe("guarda de destino de base", () => {
  it("extrae identidad sin arrastrar la contraseña", () => {
    const id = identidadDeDsn(prod);
    expect(id).toMatchObject({ usuario: "eretz_app", host: `db.${REF_PROD}.supabase.co`, base: "postgres" });
    expect(JSON.stringify(id)).not.toContain("cl4v3");
  });

  it("reconoce el proyecto en el host y también en el usuario del pooler", () => {
    expect(refDeProyecto({ host: `db.${REF_PROD}.supabase.co` })).toBe(REF_PROD);
    // El pooler lleva el ref en el usuario, no en el host.
    expect(refDeProyecto({ host: "aws-0-sa-east-1.pooler.supabase.com", usuario: `postgres.${REF_PROD}` }))
      .toBe(REF_PROD);
  });

  // --- la regla central: hay que DEMOSTRAR el destino ----------------------

  it("aborta cuando no se declaró qué destino se espera", () => {
    // "Parece de preview" no es una comprobación. Sin expectativa no hay contra
    // qué comparar, así que no se corre.
    const v = evaluarDestino({ dsn: preview });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toBe(MOTIVOS.SIN_EXPECTATIVA);
  });

  it("aborta cuando el destino no se puede identificar", () => {
    const v = evaluarDestino({ dsn: dsn("eretz_app", "un.host.cualquiera"), esperado: REF_PREVIEW });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toBe(MOTIVOS.REF_DESCONOCIDA);
  });

  it("aborta sin DSN y con un DSN ilegible", () => {
    expect(evaluarDestino({ esperado: REF_PREVIEW }).motivo).toBe(MOTIVOS.SIN_DSN);
    expect(evaluarDestino({ dsn: "no-es-una-url", esperado: REF_PREVIEW }).motivo)
      .toBe(MOTIVOS.DSN_INVALIDO);
  });

  it("deja pasar el destino esperado", () => {
    const v = evaluarDestino({ dsn: preview, esperado: REF_PREVIEW, produccion: REF_PROD });
    expect(v.permitido).toBe(true);
  });

  // --- producción -----------------------------------------------------------

  it("rechaza producción aunque el resto esté bien", () => {
    const v = evaluarDestino({ dsn: prod, esperado: REF_PREVIEW, produccion: REF_PROD });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toBe(MOTIVOS.ES_PRODUCCION);
  });

  it("rechaza producción incluso si alguien la declara como destino esperado", () => {
    // Es el caso que esta guarda existe para atrapar: alguien que cree que
    // "Preview" es otra base y configura el ref real. Que esté declarado no lo
    // convierte en permiso: es un error de configuración.
    const v = evaluarDestino({ dsn: prod, esperado: REF_PROD, produccion: REF_PROD });
    expect(v.permitido).toBe(false);
    expect(v.motivo).toBe(MOTIVOS.ES_PRODUCCION);
  });

  it("rechaza un destino que no es el esperado", () => {
    const otro = dsn("eretz_app", "db.zzzzzzzzzzzzzzzzzzzz.supabase.co");
    const v = evaluarDestino({ dsn: otro, esperado: REF_PREVIEW, produccion: REF_PROD });
    expect(v.motivo).toBe(MOTIVOS.DESTINO_DISTINTO);
  });

  // --- privilegio -----------------------------------------------------------

  it("rechaza correr DDL como superusuario, aunque el host sea el correcto", () => {
    for (const usuario of USUARIOS_PROHIBIDOS) {
      const v = evaluarDestino({
        dsn: dsn(usuario, `db.${REF_PREVIEW}.supabase.co`),
        esperado: REF_PREVIEW,
        produccion: REF_PROD,
      });
      expect(v.permitido, usuario).toBe(false);
      expect(v.motivo).toBe(MOTIVOS.USUARIO_PROHIBIDO);
    }
  });

  it("permite ese mismo usuario cuando no se va a ejecutar DDL", () => {
    // Medir un EXPLAIN de sólo lectura no necesita el mismo recaudo.
    const v = evaluarDestino({
      dsn: dsn("postgres", `db.${REF_PREVIEW}.supabase.co`),
      esperado: REF_PREVIEW,
      produccion: REF_PROD,
      requiereDdl: false,
    });
    expect(v.permitido).toBe(true);
  });

  // --- no confiar en NODE_ENV ----------------------------------------------

  it("NODE_ENV no alcanza para autorizar nada", () => {
    // Es una variable de proceso que cualquiera fija, y no dice a qué host
    // apunta la conexión.
    expect(() =>
      exigirDestinoSeguro({ NODE_ENV: "development", SUPABASE_DATABASE_URL: prod }),
    ).toThrow(/no autorizado/i);
  });

  it("el mensaje de error dice host y usuario, nunca la contraseña", () => {
    let mensaje = "";
    try {
      exigirDestinoSeguro({
        SUPABASE_DATABASE_URL: prod,
        ERETZ_DB_TARGET_EXPECT: REF_PREVIEW,
        ERETZ_DB_PRODUCTION_REF: REF_PROD,
      });
    } catch (e) {
      mensaje = (e as Error).message;
    }
    expect(mensaje).toContain("db." + REF_PROD);
    expect(mensaje).toContain("eretz_app");
    expect(mensaje).not.toContain("cl4v3");
  });

  it("devuelve el detalle cuando el destino sí está demostrado", () => {
    const detalle = exigirDestinoSeguro({
      ERETZ_DB_TARGET_URL: preview,
      ERETZ_DB_TARGET_EXPECT: REF_PREVIEW,
      ERETZ_DB_PRODUCTION_REF: REF_PROD,
    });
    expect(detalle).toMatchObject({ ref: REF_PREVIEW, usuario: "eretz_app" });
  });
});

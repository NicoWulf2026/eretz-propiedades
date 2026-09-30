import { afterEach, describe, expect, it, vi } from "vitest";
import { frontendHealth } from "./health";

const respuesta = (status: number, body: unknown) =>
  vi.fn<typeof fetch>(async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));

afterEach(() => vi.unstubAllEnvs());

describe("salud del frontend contra la API v2", () => {
  it("lista: informa propiedades, si es sintetica y el commit, sin la URL", async () => {
    vi.stubEnv("VERCEL_GIT_COMMIT_SHA", "abc123");
    const fetchImpl = respuesta(200, { status: "ok", propiedades: 65028, sintetica: false, snapshot: "x" });
    const salud = await frontendHealth({ baseUrl: "https://api.invalid", fetchImpl });
    expect(salud).toEqual({ status: "ok", commit: "abc123",
      api: { configured: true, ready: true, error: null, propiedades: 65028, sintetica: false } });
    expect(JSON.stringify(salud)).not.toContain("api.invalid");
    expect(String(fetchImpl.mock.calls[0][0])).toBe("https://api.invalid/readyz");
  });

  it("sin configurar: lo dice y no llama a nadie", async () => {
    vi.stubEnv("ERETZ_API_V2_BASE_URL", "");
    const fetchImpl = respuesta(200, {});
    const salud = await frontendHealth({ fetchImpl });
    expect(salud.status).toBe("degraded");
    expect(salud.api).toMatchObject({ configured: false, ready: false, error: "UNCONFIGURED" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("API no lista (snapshot sintetica rechazada, 503): degradado", async () => {
    const salud = await frontendHealth({ baseUrl: "https://api.invalid", fetchImpl: respuesta(503, { status: "unavailable" }) });
    expect(salud.status).toBe("degraded");
    expect(salud.api).toMatchObject({ configured: true, ready: false, error: "SERVER_ERROR" });
  });

  it("API caida: error de red, sin romper", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new TypeError("fetch failed"); });
    const salud = await frontendHealth({ baseUrl: "https://api.invalid", fetchImpl });
    expect(salud.api).toMatchObject({ ready: false, error: "NETWORK_ERROR" });
  });
});

// @vitest-environment node
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

const bridge = vi.hoisted(() => ({
  isPreviewEnvironment: vi.fn(() => true), isConfigured: vi.fn(() => true),
  stats: vi.fn(async () => ({})), stagingPorFuente: vi.fn(async () => []),
  nombres: vi.fn(async () => []), preflight: vi.fn(async () => ({})),
  insertar: vi.fn(async () => ({})), safeError: vi.fn(() => "safe error"),
}));
vi.mock("@/lib/agency-bridge", () => bridge);
import { GET, POST } from "./route";

const request = (method = "GET", auth = "") => new Request("http://localhost/api/agency-bridge?op=stats", {
  method, headers: auth ? { authorization: auth } : {},
  ...(method === "POST" ? { body: JSON.stringify({ filas: [] }) } : {}),
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv("AGENCY_BRIDGE_ENABLED", "true");
  vi.stubEnv("AGENCY_BRIDGE_TOKEN", "test-only-not-a-secret-credential-1234");
  bridge.isPreviewEnvironment.mockReturnValue(true);
});
afterEach(() => vi.unstubAllEnvs());

describe("operator bridge", () => {
  it("is inert unless explicitly enabled", async () => {
    vi.stubEnv("AGENCY_BRIDGE_ENABLED", "");
    expect((await GET(request())).status).toBe(404);
    expect(bridge.isConfigured).not.toHaveBeenCalled();
  });
  it("cannot run in production, even with a credential", async () => {
    bridge.isPreviewEnvironment.mockReturnValue(false);
    expect((await POST(request("POST", `Bearer ${process.env.AGENCY_BRIDGE_TOKEN}`))).status).toBe(404);
    expect(bridge.insertar).not.toHaveBeenCalled();
  });
  it.each(["", "Bearer wrong", "Bearer test-only-not-a-secret-credential-123X"])("rejects missing/invalid credentials: %s", async (auth) => {
    expect((await POST(request("POST", auth))).status).toBe(401);
    expect(bridge.stats).not.toHaveBeenCalled();
    expect(bridge.insertar).not.toHaveBeenCalled();
  });
  it("does not accept a credential in the URL", async () => {
    const req = new Request(`http://localhost/api/agency-bridge?token=${process.env.AGENCY_BRIDGE_TOKEN}`);
    expect((await GET(req)).status).toBe(401);
  });
  it("rejects insecure operator configuration", async () => {
    vi.stubEnv("AGENCY_BRIDGE_TOKEN", "short");
    expect((await GET(request())).status).toBe(503);
  });
  it("allows explicitly authenticated preview operations", async () => {
    expect((await GET(request("GET", `Bearer ${process.env.AGENCY_BRIDGE_TOKEN}`))).status).toBe(200);
    expect(bridge.stats).toHaveBeenCalledOnce();
  });
});

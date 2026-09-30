import "server-only";

import { fetchApiV2Json, type ApiV2ClientOptions } from "./client";

// Salud del frontend para la beta (P16 #7 y #8): ¿este deploy habla con una API v2
// lista, y con cuál snapshot? No expone la URL de la API ni ningún secreto: solo si
// está configurada, si responde `/readyz` y el SHA del código desplegado.
export type FrontendHealth = {
  status: "ok" | "degraded";
  commit: string | null;
  api: {
    configured: boolean;
    ready: boolean;
    error: string | null;
    propiedades: number | null;
    sintetica: boolean | null;
  };
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function frontendHealth(options: ApiV2ClientOptions = {}): Promise<FrontendHealth> {
  const commit = process.env.VERCEL_GIT_COMMIT_SHA?.trim() || null;
  const response = await fetchApiV2Json("/readyz", null, { timeoutMs: 3_000, ...options });
  if (response.status === "FAILURE") {
    const configured = response.error.kind !== "UNCONFIGURED";
    return {
      status: "degraded",
      commit,
      api: { configured, ready: false, error: response.error.kind, propiedades: null, sintetica: null },
    };
  }
  const data = record(response.data) ? response.data : {};
  const ready = data.status === "ok";
  return {
    status: ready ? "ok" : "degraded",
    commit,
    api: {
      configured: true,
      ready,
      error: ready ? null : "NOT_READY",
      propiedades: typeof data.propiedades === "number" ? data.propiedades : null,
      sintetica: typeof data.sintetica === "boolean" ? data.sintetica : null,
    },
  };
}

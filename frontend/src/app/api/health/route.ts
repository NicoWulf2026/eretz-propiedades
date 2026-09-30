import { NextResponse } from "next/server";
import { frontendHealth } from "@/lib/api-v2/health";
import { withObservability } from "@/lib/observability/route";

export const dynamic = "force-dynamic";

async function handleGET() {
  const health = await frontendHealth();
  return NextResponse.json(health, {
    status: health.status === "ok" ? 200 : 503,
    headers: { "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" },
  });
}

export const GET = withObservability("/api/health", handleGET);

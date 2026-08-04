import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { safeExternalUrl, phoneLinks } from "@/lib/safe-url";

describe("public frontend security", () => {
  it("accepts only HTTP external URLs", () => {
    expect(safeExternalUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("data:text/html,test")).toBeNull();
  });

  it("normalizes contact links without exposing the message to ERETZ", () => {
    expect(phoneLinks("11 5555-5555")).toEqual({
      whatsapp: "https://wa.me/541155555555",
      telephone: "tel:+541155555555",
    });
    expect(phoneLinks("123")).toEqual({ whatsapp: null, telephone: null });
  });

  it("keeps the database adapter server-only and out of browser bundles", () => {
    const service = readFileSync(join(process.cwd(), "src/lib/property-db-service.ts"), "utf8");
    const config = readFileSync(join(process.cwd(), "next.config.ts"), "utf8");
    const envTemplate = readFileSync(join(process.cwd(), ".env.local.example"), "utf8");
    expect(service.startsWith('import "server-only"')).toBe(true);
    expect(service).not.toMatch(/service[_-]?role|NEXT_PUBLIC_|SUPABASE_ANON/i);
    expect(service).not.toMatch(/rpc\s*\(/i);
    expect(config).toContain('"connect-src \'self\'"');
    expect(envTemplate).not.toMatch(/NEXT_PUBLIC_(SUPABASE|DATABASE)/);
  });
});

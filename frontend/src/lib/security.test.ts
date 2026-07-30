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

  it("does not reference private backend credentials or RPCs", () => {
    const service = readFileSync(join(process.cwd(), "src/lib/property-supabase-service.ts"), "utf8");
    expect(service).not.toMatch(/service[_-]?role|DATABASE_URL|SUPABASE_SERVICE/i);
    expect(service).not.toMatch(/rpc\s*\(/i);
  });
});


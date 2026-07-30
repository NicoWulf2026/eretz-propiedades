import { describe, expect, it } from "vitest";
import { resolveSiteUrl } from "@/lib/site-url";

describe("site URL", () => {
  it("allows the localhost fallback only outside production deployments", () => {
    expect(resolveSiteUrl(undefined, false)).toBe("http://localhost:3000");
    expect(() => resolveSiteUrl(undefined, true)).toThrow();
    expect(() => resolveSiteUrl("http://localhost:3000", true)).toThrow();
  });

  it("requires HTTPS for production canonical URLs", () => {
    expect(resolveSiteUrl("https://eretz.example/", true)).toBe("https://eretz.example");
    expect(() => resolveSiteUrl("http://eretz.example", true)).toThrow();
  });
});


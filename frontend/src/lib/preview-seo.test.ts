import { describe, expect, it } from "vitest";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";

describe("private preview SEO controls", () => {
  it("disallows all crawlers without a runtime escape hatch", () => {
    process.env.NEXT_PUBLIC_SITE_INDEXING = "true";
    expect(robots()).toEqual({ rules: { userAgent: "*", disallow: "/" } });
  });

  it("fails closed for an absent indexing flag", () => {
    expect(robots().rules).toEqual({ userAgent: "*", disallow: "/" });
  });

  it("keeps the sitemap route prepared without submitting private URLs", () => {
    expect(sitemap()).toEqual([]);
  });
});

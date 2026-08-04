import { afterEach, describe, expect, it } from "vitest";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";

const originalIndexing = process.env.NEXT_PUBLIC_SITE_INDEXING;

afterEach(() => {
  if (originalIndexing === undefined) delete process.env.NEXT_PUBLIC_SITE_INDEXING;
  else process.env.NEXT_PUBLIC_SITE_INDEXING = originalIndexing;
});

describe("private preview SEO controls", () => {
  it("disallows all crawlers and omits the sitemap when indexing is disabled", () => {
    process.env.NEXT_PUBLIC_SITE_INDEXING = "false";
    expect(robots()).toEqual({ rules: { userAgent: "*", disallow: "/" }, sitemap: undefined });
  });

  it("fails closed for an absent indexing flag", () => {
    delete process.env.NEXT_PUBLIC_SITE_INDEXING;
    expect(robots().rules).toEqual({ userAgent: "*", disallow: "/" });
  });

  it("never emits property detail URLs from the static sitemap", () => {
    expect(sitemap().every((entry) => !new URL(entry.url).pathname.startsWith("/propiedad/"))).toBe(true);
  });
});

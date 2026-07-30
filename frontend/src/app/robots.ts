import type { MetadataRoute } from "next";
export default function robots(): MetadataRoute.Robots {
  const allow = process.env.NEXT_PUBLIC_SITE_INDEXING === "true";
  return { rules: allow ? { userAgent: "*", allow: "/" } : { userAgent: "*", disallow: "/" }, sitemap: allow ? `${process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"}/sitemap.xml` : undefined };
}


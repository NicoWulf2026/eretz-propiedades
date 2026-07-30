import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/site-url";
export default function robots(): MetadataRoute.Robots {
  const allow = process.env.NEXT_PUBLIC_SITE_INDEXING === "true";
  return { rules: allow ? { userAgent: "*", allow: "/" } : { userAgent: "*", disallow: "/" }, sitemap: allow ? `${siteUrl}/sitemap.xml` : undefined };
}

import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/site-url";
export default function sitemap(): MetadataRoute.Sitemap {
  return ["/", "/propiedades", "/contacto", "/terminos", "/privacidad", "/baja-o-correccion"].map((path) => ({ url: `${siteUrl}${path}`, changeFrequency: path === "/" ? "daily" as const : "monthly" as const, priority: path === "/" ? 1 : 0.5 }));
}

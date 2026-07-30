import type { MetadataRoute } from "next";
export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  return ["/", "/propiedades", "/contacto", "/terminos", "/privacidad", "/baja-o-correccion"].map((path) => ({ url: `${base}${path}`, changeFrequency: path === "/" ? "daily" as const : "monthly" as const, priority: path === "/" ? 1 : 0.5 }));
}


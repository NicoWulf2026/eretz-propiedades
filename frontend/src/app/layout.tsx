import type { Metadata, Viewport } from "next";
import { siteUrl } from "@/lib/site-url";
import "./globals.css";

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#071d35" };

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "ERETZ Propiedades | Inmuebles en Argentina", template: "%s | ERETZ Propiedades" },
  description: "Buscá propiedades de toda Argentina y contactá directamente a la inmobiliaria o responsable del aviso.",
  applicationName: "ERETZ Propiedades",
  alternates: { canonical: "/" },
  icons: { icon: "/favicon.ico" },
  robots: { index: false, follow: false, nocache: true, noarchive: true, nosnippet: true },
  openGraph: {
    title: "ERETZ Propiedades",
    description: "Encontrá propiedades en Argentina con búsqueda real y contacto directo.",
    url: "/",
    siteName: "ERETZ Propiedades",
    locale: "es_AR",
    type: "website",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "ERETZ Propiedades" }],
  },
  twitter: { card: "summary_large_image", title: "ERETZ Propiedades", description: "Propiedades en toda Argentina.", images: ["/opengraph-image"] },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es-AR"><body>{children}</body></html>;
}

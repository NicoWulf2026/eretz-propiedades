import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const SITE_TITLE = "ERETZ Propiedades | Búsqueda inmobiliaria en Argentina";
const SITE_DESCRIPTION =
  "Mapa, filtros y listado de propiedades para comprar, alquilar o invertir en Argentina.";

// Beta: por defecto NO indexar (noindex, nofollow). Solo se indexa si
// NEXT_PUBLIC_SITE_INDEXING === "true" (producción pública). Cualquier otro valor o ausencia -> noindex.
const allowIndexing = process.env.NEXT_PUBLIC_SITE_INDEXING === "true";

export const metadata: Metadata = {
  title: SITE_TITLE,
  description: SITE_DESCRIPTION,
  robots: allowIndexing ? undefined : { index: false, follow: false },
  openGraph: {
    title: SITE_TITLE,
    description: SITE_DESCRIPTION,
    siteName: "ERETZ Propiedades",
    locale: "es_AR",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es-AR"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">{children}</body>
    </html>
  );
}

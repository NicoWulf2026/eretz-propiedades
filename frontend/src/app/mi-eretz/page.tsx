import type { Metadata } from "next";
import { Suspense } from "react";
import { SiteShell } from "@/components/layout/SiteShell";
import { MiEretzClient } from "@/components/local/MiEretzClient";

export const metadata: Metadata = { title: "Mi ERETZ", robots: { index: false, follow: false } };

export default function Page() {
  return <SiteShell><Suspense fallback={<div className="container py-8"><div className="skeleton h-52 rounded-2xl" /></div>}><MiEretzClient /></Suspense></SiteShell>;
}

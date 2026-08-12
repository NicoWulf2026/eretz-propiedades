import type { Metadata } from "next";
import { SiteShell } from "@/components/layout/SiteShell";
import { CompareClient } from "@/components/local/CompareClient";

export const metadata: Metadata = {
  title: "Comparar propiedades",
  robots: { index: false, follow: false },
};

export default function Page() {
  return (
    <SiteShell>
      <CompareClient />
    </SiteShell>
  );
}

import type { Metadata } from "next";
import { SiteShell } from "@/components/layout/SiteShell";
import { CollectionsClient } from "@/components/local/CollectionsClient";

export const metadata: Metadata = {
  title: "Colecciones",
  robots: { index: false, follow: false },
};

export default function Page() {
  return (
    <SiteShell>
      <CollectionsClient />
    </SiteShell>
  );
}

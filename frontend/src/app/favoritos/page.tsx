import type { Metadata } from "next";
import { SiteShell } from "@/components/layout/SiteShell";
import { FavoritesClient } from "@/components/local/FavoritesClient";

export const metadata: Metadata = {
  title: "Mi actividad",
  robots: { index: false, follow: false },
};

export default function Page() {
  return (
    <SiteShell>
      <FavoritesClient />
    </SiteShell>
  );
}

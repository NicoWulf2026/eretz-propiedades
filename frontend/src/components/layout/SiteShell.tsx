import type { ReactNode } from "react";
import { Footer } from "@/components/layout/Footer";
import { Navbar } from "@/components/layout/Navbar";
import { OfflineNotice } from "@/components/system/OfflineNotice";

export function SiteShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <OfflineNotice />
      <Navbar />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}


import { SiteShell } from "@/components/layout/SiteShell";

export default function Loading() {
  return <SiteShell><div className="container py-12"><div className="skeleton h-10 w-72" /><div className="skeleton mt-6 h-48 w-full" /><div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <div key={i} className="skeleton h-96" />)}</div></div></SiteShell>;
}


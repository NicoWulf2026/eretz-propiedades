import { SiteShell } from "@/components/layout/SiteShell";
export default function Loading() { return <SiteShell><div className="container py-10"><div className="skeleton h-10 w-3/4" /><div className="mt-8 grid gap-8 lg:grid-cols-[1.6fr_.7fr]"><div className="skeleton aspect-[16/10]" /><div className="skeleton h-80" /></div></div></SiteShell>; }


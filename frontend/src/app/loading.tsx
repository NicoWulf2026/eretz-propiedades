import { PropertyCardSkeleton } from "@/components/property/PropertyCardSkeleton";

export default function Loading() {
  return (
    <div className="min-h-screen bg-[#f6f8fb]">
      {/* Navbar */}
      <div className="sticky top-0 z-40 h-16 border-b border-white/10 bg-ink-950/96 backdrop-blur-xl" />

      {/* Hero skeleton */}
      <div className="relative overflow-hidden bg-ink-950 px-4 py-6 sm:px-5 sm:py-8 lg:px-6 lg:py-10">
        <div className="mx-auto w-full max-w-[1480px]">
          {/* Tagline */}
          <div className="mb-2 h-2.5 w-40 rounded bg-white/10 animate-pulse sm:mb-3" />
          {/* H1 */}
          <div className="mb-5 space-y-2 sm:mb-6">
            <div className="h-7 w-72 rounded-md bg-white/10 animate-pulse sm:h-9" />
            <div className="hidden h-7 w-56 rounded-md bg-white/8 animate-pulse sm:block sm:h-9" />
          </div>
          {/* SearchBar skeleton — input + button */}
          <div className="overflow-hidden rounded-2xl border border-white/14 bg-white shadow-[0_16px_48px_rgba(6,21,40,0.38)]">
            <div className="flex gap-2 p-2.5 sm:p-3">
              <div className="h-12 flex-1 rounded-xl bg-ink-950/6 animate-pulse" />
              <div className="h-12 w-24 shrink-0 rounded-xl bg-ink-950/10 animate-pulse" />
            </div>
          </div>
          {/* Stats row */}
          <div className="mt-3.5 flex items-center gap-4">
            <div className="h-3 w-24 rounded bg-white/8 animate-pulse" />
            <div className="h-3 w-px bg-white/10" />
            <div className="h-3 w-16 rounded bg-white/8 animate-pulse" />
          </div>
        </div>
      </div>

      {/* Filter strip skeleton */}
      <div className="border-b border-ink-950/8 bg-white">
        <div className="mx-auto w-full max-w-[1480px] px-4 py-3 sm:px-5 lg:px-6">
          <div className="flex gap-2 overflow-hidden">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-9 w-20 shrink-0 rounded-md bg-ink-950/6 animate-pulse" />
            ))}
          </div>
        </div>
      </div>

      {/* Main content skeleton */}
      <section className="mx-auto grid w-full max-w-[1480px] gap-4 px-4 pb-24 pt-3 sm:px-5 lg:grid-cols-[360px_minmax(0,1fr)] lg:px-6 lg:pt-4 xl:grid-cols-[380px_minmax(0,1fr)]">
        {/* List skeleton */}
        <div className="min-w-0 rounded-lg border border-ink-950/10 bg-white/72 p-3 shadow-sm">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="h-3.5 w-36 rounded bg-ink-950/10 animate-pulse" />
            <div className="h-9 w-28 shrink-0 rounded-md border border-ink-950/10 bg-white animate-pulse" />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <PropertyCardSkeleton key={i} />
            ))}
          </div>
        </div>

        {/* Map skeleton */}
        <div className="min-h-[480px] overflow-hidden rounded-lg border border-ink-950/10 bg-[#eef3f8] shadow-lift lg:sticky lg:top-20 lg:h-[calc(100vh-5.5rem)] lg:min-h-[720px]">
          <div className="flex h-full min-h-[480px] flex-col">
            <div className="flex items-center justify-between gap-3 border-b border-ink-950/10 bg-white/92 px-4 py-3">
              <div className="h-3.5 w-36 rounded bg-ink-950/10 animate-pulse" />
            </div>
            <div className="flex-1 animate-pulse bg-[#eef3f8]" />
          </div>
        </div>
      </section>
    </div>
  );
}

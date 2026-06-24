export function PropertyCardSkeleton() {
  return (
    <article className="overflow-hidden rounded-lg border border-ink-950/10 bg-white shadow-sm">
      <div className="aspect-[16/10] animate-pulse bg-ink-950/10" />
      <div className="p-4">
        <div className="h-4 w-3/4 rounded bg-ink-950/10 animate-pulse" />
        <div className="mt-2 h-3 w-1/2 rounded animate-pulse bg-ink-950/[0.06]" />
        <div className="mt-4 h-6 w-1/3 rounded animate-pulse bg-ink-950/10" />
        <div className="mt-3 flex gap-2">
          <div className="h-6 w-16 rounded animate-pulse bg-ink-950/[0.06]" />
          <div className="h-6 w-20 rounded animate-pulse bg-ink-950/[0.06]" />
          <div className="h-6 w-14 rounded animate-pulse bg-ink-950/[0.06]" />
        </div>
      </div>
    </article>
  );
}

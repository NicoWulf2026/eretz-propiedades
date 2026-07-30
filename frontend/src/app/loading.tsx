export default function Loading() {
  return (
    <main className="container py-12" aria-busy="true" aria-label="Cargando">
      <div className="skeleton h-12 w-3/4" />
      <div className="skeleton mt-8 h-44 w-full" />
      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, index) => <div key={index} className="skeleton h-96" />)}
      </div>
    </main>
  );
}

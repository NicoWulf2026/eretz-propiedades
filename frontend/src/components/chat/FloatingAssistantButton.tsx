export function FloatingAssistantButton() {
  return (
    <button
      className="fixed bottom-5 right-5 z-50 flex h-14 items-center gap-3 rounded-lg bg-ink-950 px-4 text-sm font-semibold text-white shadow-soft transition hover:-translate-y-0.5 hover:bg-ink-800 focus:outline-none focus:ring-4 focus:ring-gold-500/30"
      type="button"
      aria-label="Abrir asistente IA"
    >
      <span className="grid size-8 place-items-center rounded-md bg-gold-500 text-ink-950">
        IA
      </span>
      <span className="hidden sm:inline">Asistente IA</span>
    </button>
  );
}

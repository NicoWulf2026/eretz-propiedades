import type { ExplorerMode } from "@/types/property";

const views: Array<{ mode: ExplorerMode; label: string; icon: "split" | "grid" | "map" }> = [
  { mode: "balanced", label: "Mapa + propiedades", icon: "split" },
  { mode: "results_only", label: "Solo propiedades", icon: "grid" },
  { mode: "map_only", label: "Solo mapa", icon: "map" },
];

function ViewIcon({ kind }: { kind: "split" | "grid" | "map" }) {
  if (kind === "split") {
    return <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2" y="3" width="9" height="14" rx="1.5" /><rect x="13" y="3" width="5" height="6" rx="1" /><rect x="13" y="11" width="5" height="6" rx="1" /></svg>;
  }
  if (kind === "grid") {
    return <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="2" y="3" width="7" height="6" rx="1" /><rect x="11" y="3" width="7" height="6" rx="1" /><rect x="2" y="11" width="7" height="6" rx="1" /><rect x="11" y="11" width="7" height="6" rx="1" /></svg>;
  }
  return <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 18s5-4.8 5-9a5 5 0 1 0-10 0c0 4.2 5 9 5 9Z" /><circle cx="10" cy="9" r="1.8" /></svg>;
}

export function ViewModeSelector({ mode, onChange }: { mode: ExplorerMode; onChange: (mode: ExplorerMode) => void }) {
  return (
    <div className="view-mode-tabs" role="group" aria-label="Vista del explorador">
      {views.map((view) => (
        <button
          key={view.mode}
          type="button"
          className={mode === view.mode ? "is-active" : ""}
          aria-label={view.label}
          aria-pressed={mode === view.mode}
          data-tooltip={view.label}
          title={view.label}
          onClick={() => onChange(view.mode)}
        >
          <ViewIcon kind={view.icon} />
          <span className="sr-only">{view.label}</span>
        </button>
      ))}
    </div>
  );
}

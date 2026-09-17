"use client";

import { useState } from "react";

const MOTIVOS = [
  { value: "no_disponible", label: "Ya no está disponible" },
  { value: "precio_incorrecto", label: "El precio es incorrecto" },
  { value: "duplicada", label: "Está duplicada" },
  { value: "datos_erroneos", label: "Tiene datos erróneos" },
  { value: "otro", label: "Otro" },
];

// Reportar un problema en la publicación. Sin cuenta. El reporte es una señal:
// no modifica ni oculta la publicación.
export function ReportButton({ propertyId }: { propertyId: string }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "ok" | "error">("idle");
  const [error, setError] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setState("sending");
    setError("");
    try {
      const response = await fetch("/api/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          propiedadId: propertyId,
          motivo: form.get("motivo"),
          detalle: form.get("detalle"),
          email: form.get("email"),
        }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { error?: string };
        setState("error");
        setError(data.error ?? "No pudimos registrar el reporte.");
        return;
      }
      setState("ok");
    } catch {
      setState("error");
      setError("No pudimos registrar el reporte.");
    }
  }

  if (state === "ok") {
    return <p role="status" className="text-sm font-semibold text-green-700">Gracias, recibimos tu reporte. Lo revisará una persona.</p>;
  }

  if (!open) {
    return (
      <button type="button" className="inline-action text-sm font-semibold u-text-faint underline hover:u-text" onClick={() => setOpen(true)}>
        Reportar un problema
      </button>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-2 grid gap-3 rounded-xl border u-border p-4">
      <label className="field"><span>Motivo</span>
        <select name="motivo" required defaultValue="">
          <option value="" disabled>Elegí un motivo</option>
          {MOTIVOS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </label>
      <label className="field"><span>Detalle (opcional)</span><textarea name="detalle" maxLength={1000} rows={3} /></label>
      <label className="field"><span>Tu email (opcional, por si necesitamos más datos)</span><input name="email" type="email" maxLength={160} /></label>
      {state === "error" ? <p role="alert" className="text-sm font-semibold u-bad-text">{error}</p> : null}
      <p className="text-xs u-text-faint">Tu reporte es una señal para revisión humana; no modifica ni oculta la publicación.</p>
      <div className="flex gap-2">
        <button type="submit" className="primary-button" disabled={state === "sending"}>{state === "sending" ? "Enviando…" : "Enviar reporte"}</button>
        <button type="button" className="secondary-button" onClick={() => setOpen(false)}>Cancelar</button>
      </div>
    </form>
  );
}

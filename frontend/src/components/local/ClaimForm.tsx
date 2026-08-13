"use client";

import { useState } from "react";

// Formulario de reclamo de perfil. Sin cuenta. No auto-aprueba: al enviar, el
// reclamo queda como "pendiente"/"en revisión" para verificación humana.
export function ClaimForm({ tipo, entidadId, entidadNombre }: { tipo: "inmobiliaria" | "agente"; entidadId: string; entidadNombre: string }) {
  const [state, setState] = useState<"idle" | "sending" | "ok" | "review" | "error">("idle");
  const [message, setMessage] = useState("");

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setState("sending");
    setMessage("");
    try {
      const response = await fetch("/api/claims", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo,
          entidadId,
          nombre: form.get("nombre"),
          email: form.get("email"),
          telefono: form.get("telefono"),
          rol: form.get("rol"),
          mensaje: form.get("mensaje"),
        }),
      });
      if (!response.ok) {
        const data = (await response.json().catch(() => ({}))) as { error?: string };
        setState("error");
        setMessage(data.error ?? "No pudimos registrar el reclamo. Reintentá en unos minutos.");
        return;
      }
      const data = (await response.json()) as { status: string };
      setState(data.status === "needs_review" ? "review" : "ok");
    } catch {
      setState("error");
      setMessage("No pudimos registrar el reclamo. Reintentá en unos minutos.");
    }
  }

  if (state === "ok" || state === "review") {
    return (
      <div role="status" className="rounded-xl border border-green-200 bg-green-50 p-6 text-sm text-green-900">
        <p className="font-bold">Recibimos tu reclamo de {entidadNombre}.</p>
        <p className="mt-1">
          Queda {state === "review" ? "en revisión" : "pendiente"} de verificación. No se aprueba
          automáticamente ni se modifica el perfil hasta confirmar la titularidad.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="grid max-w-xl gap-4">
      <label className="field"><span>Nombre y apellido *</span><input name="nombre" required maxLength={120} /></label>
      <label className="field"><span>Email de contacto *</span><input name="email" type="email" required maxLength={160} /></label>
      <label className="field"><span>Teléfono</span><input name="telefono" type="tel" maxLength={40} /></label>
      <label className="field"><span>Tu rol en la inmobiliaria</span><input name="rol" maxLength={80} placeholder="Titular, responsable, agente…" /></label>
      <label className="field"><span>Mensaje (opcional)</span><textarea name="mensaje" maxLength={1000} rows={4} /></label>
      {state === "error" ? <p role="alert" className="text-sm font-semibold u-bad-text">{message}</p> : null}
      <p className="text-xs u-text-faint">
        Al enviar, tu solicitud queda pendiente de verificación humana. ERETZ no comparte estos datos
        con terceros y los usa sólo para validar el reclamo.
      </p>
      <button type="submit" className="primary-button justify-self-start" disabled={state === "sending"}>
        {state === "sending" ? "Enviando…" : "Enviar reclamo"}
      </button>
    </form>
  );
}

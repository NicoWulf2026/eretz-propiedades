"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";
import { phoneLinks } from "@/lib/safe-url";
import type { Property } from "@/types/property";

export function ContactActions({ property, canonical }: { property: Property; canonical: string }) {
  const [copied, setCopied] = useState(false);
  const { whatsapp, telephone } = phoneLinks(property.agentPhone);
  const message = encodeURIComponent(`Hola, consulto por “${property.title}” en ERETZ Propiedades: ${canonical}`);
  const whatsappHref = whatsapp ? `${whatsapp}?text=${message}` : null;
  const shareHref = `https://wa.me/?text=${encodeURIComponent(`${property.title} — ${canonical}`)}`;
  async function copy() {
    await navigator.clipboard.writeText(canonical);
    setCopied(true);
    track("share_clicked", { method: "copy" });
  }
  return (
    <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#2166a5]">Contacto directo</p>
      <h2 className="mt-2 text-xl font-black text-[#0b2748]">{property.agentName ?? "Responsable de la publicación"}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">ERETZ no recibe ni almacena tu consulta. Te conectamos con la publicación original.</p>
      <div className="mt-5 grid gap-2">
        {whatsappHref && <a className="primary-button justify-center bg-emerald-700 hover:bg-emerald-800" href={whatsappHref} target="_blank" rel="noopener noreferrer" onClick={() => track("whatsapp_clicked", { property_id: property.id })}>Consultar por WhatsApp</a>}
        {telephone && <a className="secondary-button justify-center" href={telephone} onClick={() => track("phone_clicked", { property_id: property.id })}>Llamar por teléfono</a>}
        {property.sourceUrl && <a className="secondary-button justify-center" href={property.sourceUrl} target="_blank" rel="noopener noreferrer" onClick={() => track("original_listing_clicked", { property_id: property.id })}>Ver publicación original ↗</a>}
      </div>
      {!whatsappHref && !telephone && !property.sourceUrl && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Esta publicación no incluye un contacto público válido.</p>}
      <div className="mt-5 flex gap-2 border-t border-slate-100 pt-4">
        <a className="text-sm font-bold text-[#2166a5]" href={shareHref} target="_blank" rel="noopener noreferrer" onClick={() => track("share_clicked", { method: "whatsapp" })}>Compartir</a>
        <button className="text-sm font-bold text-[#2166a5]" type="button" onClick={copy}>{copied ? "Enlace copiado" : "Copiar enlace"}</button>
      </div>
    </aside>
  );
}


"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";
import { phoneLinks } from "@/lib/safe-url";
import { contactMessage, propertyShareMessage } from "@/lib/property-share";
import type { Property } from "@/types/property";

export function ContactActions({ property, canonical }: { property: Property; canonical: string }) {
  const [copied, setCopied] = useState(false);
  const contact = property.publisher;
  const { whatsapp, telephone } = phoneLinks(contact?.phone ?? property.agentPhone);
  const message = encodeURIComponent(contactMessage(property, canonical));
  const whatsappHref = whatsapp ? `${whatsapp}?text=${message}` : null;
  const shareMessage = propertyShareMessage(property, canonical);
  const shareHref = `https://wa.me/?text=${encodeURIComponent(shareMessage)}`;
  const emailHref = `mailto:${contact?.email ?? ""}?subject=${encodeURIComponent(`Consulta por ${property.title}`)}&body=${message}`;
  async function copy() {
    try {
      await navigator.clipboard.writeText(canonical);
      setCopied(true);
      track("share_clicked", { method: "copy" });
    } catch {
      window.prompt("Copiá este enlace", canonical);
    }
  }
  async function webShare() {
    if (!navigator.share) {
      await copy();
      return;
    }
    try {
      await navigator.share({ title: property.title, text: shareMessage, url: canonical });
      track("share_clicked", { method: "web_share" });
    } catch {
      // The user can cancel the native share sheet without creating an error state.
    }
  }
  return (
    <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#2166a5]">Contacto directo</p>
      <h2 className="mt-2 text-xl font-black text-[#0b2748]">{contact?.name ?? property.agentName ?? "Responsable de la publicación"}</h2>
      {contact?.verified ? <p className="mt-1 text-xs font-bold text-emerald-700">Identidad verificada en ERETZ</p> : null}
      <p className="mt-2 text-sm leading-6 text-slate-600">ERETZ no recibe ni almacena tu consulta. Te conectamos con la publicación original.</p>
      <div className="mt-5 grid gap-2">
        {whatsappHref && <a className="primary-button justify-center bg-emerald-700 hover:bg-emerald-800" href={whatsappHref} target="_blank" rel="noopener noreferrer" onClick={() => track("whatsapp_clicked", { property_id: property.id })}>Consultar por WhatsApp</a>}
        {telephone && <a className="secondary-button justify-center" href={telephone} onClick={() => track("phone_clicked", { property_id: property.id })}>Llamar por teléfono</a>}
        {contact?.email && <a className="secondary-button justify-center" href={emailHref} onClick={() => track("email_clicked", { property_id: property.id })}>Enviar correo</a>}
        {contact?.website && <a className="secondary-button justify-center" href={contact.website} target="_blank" rel="noopener noreferrer">Sitio del publicador ↗</a>}
        {property.sourceUrl && <a className="secondary-button justify-center" href={property.sourceUrl} target="_blank" rel="noopener noreferrer" onClick={() => track("original_listing_clicked", { property_id: property.id })}>Ver publicación original ↗</a>}
      </div>
      {!whatsappHref && !telephone && !contact?.email && !contact?.website && !property.sourceUrl && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Esta publicación no incluye un contacto público válido.</p>}
      <div className="mt-5 flex flex-wrap gap-3 border-t border-slate-100 pt-4">
        <a className="text-sm font-bold text-[#2166a5]" href={shareHref} target="_blank" rel="noopener noreferrer" onClick={() => track("share_clicked", { method: "whatsapp" })}>WhatsApp</a>
        <a className="text-sm font-bold text-[#2166a5]" href={`mailto:?subject=${encodeURIComponent(property.title)}&body=${encodeURIComponent(shareMessage)}`} onClick={() => track("share_clicked", { method: "email" })}>Correo</a>
        <button className="text-sm font-bold text-[#2166a5]" type="button" onClick={webShare}>Compartir</button>
        <button className="text-sm font-bold text-[#2166a5]" type="button" onClick={copy}>{copied ? "Enlace copiado" : "Copiar enlace"}</button>
      </div>
    </aside>
  );
}

"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";
import { phoneLinks } from "@/lib/safe-url";
import { CONTACT_TOPICS, contactMessage, contactMessageWithTopics, contactTopicLabel, propertyShareMessage, type ContactTopicId } from "@/lib/property-share";
import type { Property } from "@/types/property";

export function ContactActions({ property, canonical }: { property: Property; canonical: string }) {
  const [copied, setCopied] = useState(false);
  const [topics, setTopics] = useState<ContactTopicId[]>([]);
  const [freeText, setFreeText] = useState("");
  const contact = property.publisher;
  const { whatsapp, telephone } = phoneLinks(contact?.phone ?? property.agentPhone);
  const toggleTopic = (id: ContactTopicId) =>
    setTopics((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  const composed = topics.length || freeText.trim()
    ? contactMessageWithTopics(property, canonical, topics, freeText)
    : contactMessage(property, canonical);
  const message = encodeURIComponent(composed);
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
    <aside className="detail-panel rounded-2xl border p-5">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[color:var(--brand)]">Contacto directo</p>
      <h2 className="mt-2 text-xl font-black text-[color:var(--ink)]">{contact?.name ?? property.agentName ?? "Responsable de la publicación"}</h2>
      {contact?.verified ? <p className="mt-1 text-xs font-bold text-emerald-700">Identidad verificada en ERETZ</p> : null}
      <p className="mt-2 text-sm leading-6 text-slate-600">ERETZ no recibe ni almacena tu consulta. Te conectamos con la publicación original.</p>
      {(whatsapp || contact?.email) ? (
        <fieldset className="mt-4 rounded-xl border border-slate-200 p-3">
          <legend className="px-1 text-xs font-bold text-slate-600">¿Sobre qué querés consultar? (opcional)</legend>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1.5">
            {CONTACT_TOPICS.map((t) => (
              <label key={t.id} className="check-label inline-flex items-center gap-1.5 text-sm text-slate-700">
                <input className="form-check" type="checkbox" checked={topics.includes(t.id)} onChange={() => toggleTopic(t.id)} />
                {contactTopicLabel(t.id)}
              </label>
            ))}
          </div>
          <label className="mt-2 block">
            <span className="sr-only">Mensaje adicional</span>
            <textarea value={freeText} onChange={(e) => setFreeText(e.target.value)} maxLength={400} rows={2} placeholder="Agregá algo más (opcional)" className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
          </label>
          <p className="mt-1 text-xs text-slate-500">Se arma un mensaje sólo con lo que elijas. Vos lo revisás antes de enviarlo.</p>
        </fieldset>
      ) : null}
      <div className="mt-5 grid gap-2">
        {whatsappHref && <a className="primary-button justify-center bg-emerald-700 hover:bg-emerald-800" href={whatsappHref} target="_blank" rel="noopener noreferrer" onClick={() => track("whatsapp_clicked", { property_id: property.id })}>Consultar por WhatsApp</a>}
        {telephone && <a className="secondary-button justify-center" href={telephone} onClick={() => track("phone_clicked", { property_id: property.id })}>Llamar por teléfono</a>}
        {contact?.email && <a className="secondary-button justify-center" href={emailHref} onClick={() => track("email_clicked", { property_id: property.id })}>Enviar correo</a>}
        {contact?.website && <a className="secondary-button justify-center" href={contact.website} target="_blank" rel="noopener noreferrer">Sitio del publicador ↗</a>}
        {property.sourceUrl && <a className="secondary-button justify-center" href={property.sourceUrl} target="_blank" rel="noopener noreferrer" onClick={() => track("original_listing_clicked", { property_id: property.id })}>Ver publicación original ↗</a>}
      </div>
      {!whatsappHref && !telephone && !contact?.email && !contact?.website && !property.sourceUrl && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">Esta publicación no incluye un contacto público válido.</p>}
      <div className="mt-5 flex flex-wrap gap-3 border-t border-slate-100 pt-4">
        <a className="inline-action text-sm font-bold text-[color:var(--brand)]" href={shareHref} target="_blank" rel="noopener noreferrer" onClick={() => track("share_clicked", { method: "whatsapp" })}>WhatsApp</a>
        <a className="inline-action text-sm font-bold text-[color:var(--brand)]" href={`mailto:?subject=${encodeURIComponent(property.title)}&body=${encodeURIComponent(shareMessage)}`} onClick={() => track("share_clicked", { method: "email" })}>Correo</a>
        <button className="inline-action text-sm font-bold text-[color:var(--brand)]" type="button" onClick={webShare}>Compartir</button>
        <button className="inline-action text-sm font-bold text-[color:var(--brand)]" type="button" onClick={copy}>{copied ? "Enlace copiado" : "Copiar enlace"}</button>
      </div>
    </aside>
  );
}

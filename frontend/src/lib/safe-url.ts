export function safeExternalUrl(value: unknown): string | null {
  if (typeof value !== "string" || value.length > 2048) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function phoneLinks(value: string | null) {
  if (!value) return { whatsapp: null, telephone: null };
  const digits = value.replace(/\D/g, "");
  if (digits.length < 8 || digits.length > 15) return { whatsapp: null, telephone: null };
  const international = digits.startsWith("54") ? digits : `54${digits.replace(/^0/, "")}`;
  return {
    whatsapp: `https://wa.me/${international}`,
    telephone: `tel:+${international}`,
  };
}


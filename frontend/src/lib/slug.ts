// Slugs estables para perfiles públicos (inmobiliarias, agentes). El slug es
// legible pero lleva el id real al final para resolverlo sin ambigüedad, incluso
// si dos perfiles comparten nombre.

export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60) || "perfil";
}

// `${slugify(nombre)}-${id}` — p. ej. "inmobiliaria-acme-1234".
export function entitySlug(id: string | number, name: string | null | undefined): string {
  return `${slugify(name ?? "")}-${id}`;
}

// Extrae el id numérico del final del slug. Devuelve "" si no hay id válido.
export function idFromSlug(slug: string): string {
  const match = /(\d+)$/.exec(slug ?? "");
  return match ? match[1] : "";
}

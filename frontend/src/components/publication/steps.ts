// Los pasos del wizard y qué campo mira cada uno.
//
// La lista vive aparte del componente para que el orden, los títulos y la
// pertenencia campo→paso sean datos y no estructura de JSX. Eso permite, entre
// otras cosas, mandar a la persona al paso correcto cuando la revisión final
// encuentra un error: sin este mapa habría que buscarlo a mano.

import type { BorradorDePublicacion } from "@/domain/publishing";

export type PasoId =
  | "operacion"
  | "ubicacion"
  | "precio"
  | "caracteristicas"
  | "descripcion"
  | "imagenes"
  | "contacto"
  | "revision";

export type Paso = {
  id: PasoId;
  titulo: string;
  /** Qué se decide en este paso, en una línea. */
  ayuda: string;
  /** Campos del borrador que se completan acá. */
  campos: readonly string[];
};

export const PASOS: readonly Paso[] = Object.freeze([
  {
    id: "operacion",
    titulo: "Qué publicás",
    ayuda: "Empezamos por lo básico: qué tipo de propiedad es y qué querés hacer con ella.",
    campos: ["operation", "propertyType"],
  },
  {
    id: "ubicacion",
    titulo: "Dónde está",
    ayuda: "La ubicación es lo primero que filtra la gente que busca.",
    campos: ["province", "city", "neighborhood", "address"],
  },
  {
    id: "precio",
    titulo: "Precio",
    ayuda: "Podés poner un monto o dejarlo a consultar.",
    campos: ["precio", "expenses"],
  },
  {
    id: "caracteristicas",
    titulo: "Características",
    ayuda: "Ambientes, superficie y demás. Lo que no sepas, dejalo vacío.",
    campos: ["rooms", "bedrooms", "bathrooms", "totalArea", "coveredArea"],
  },
  {
    id: "descripcion",
    titulo: "Descripción",
    ayuda: "Contá lo que no se ve en las fotos ni en los números.",
    campos: ["title", "description"],
  },
  {
    id: "imagenes",
    titulo: "Fotos",
    ayuda: "La primera es la portada. Podés reordenarlas.",
    campos: ["images"],
  },
  {
    id: "contacto",
    titulo: "Contacto",
    ayuda: "Cómo te van a escribir quienes se interesen.",
    campos: ["contactPhone", "contactEmail", "legitimacyAccepted"],
  },
  {
    id: "revision",
    titulo: "Revisión",
    ayuda: "Mirá que esté todo bien antes de publicar.",
    campos: [],
  },
]);

export function indiceDePaso(id: PasoId): number {
  return PASOS.findIndex((p) => p.id === id);
}

/** En qué paso se completa un campo. `null` si no pertenece a ninguno. */
export function pasoDelCampo(campo: string): PasoId | null {
  return PASOS.find((p) => p.campos.includes(campo))?.id ?? null;
}

/** Un borrador vacío. Todo en `null`: nada se presume. */
export function borradorVacio(
  authorUserId: BorradorDePublicacion["authorUserId"],
): BorradorDePublicacion {
  return {
    publisherType: "INDIVIDUAL",
    authorUserId,
    organizationId: null,
    agentId: null,
    operation: null,
    propertyType: null,
    precio: null,
    expenses: null,
    province: null,
    city: null,
    neighborhood: null,
    address: null,
    title: null,
    description: null,
    rooms: null,
    bedrooms: null,
    bathrooms: null,
    totalArea: null,
    coveredArea: null,
    images: [],
    contactPhone: null,
    contactEmail: null,
    legitimacyAccepted: false,
  };
}

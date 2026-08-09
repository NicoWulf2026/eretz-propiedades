"use client";

import { useEffect } from "react";
import { addRecentView } from "@/lib/local-store";

// Registra la ficha visitada en "vistas recientes" (localStorage). Sin efecto en
// el servidor ni impacto en el render; sólo guarda un snapshot liviano.
export function RecentViewTracker({ id, title, price }: { id: string; title: string; price: string | null }) {
  useEffect(() => {
    addRecentView({ id, title, price });
  }, [id, title, price]);
  return null;
}

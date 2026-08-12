"use client";

import { useEffect, useRef, useState } from "react";
import { CHANGE_EVENT } from "@/lib/local-store";

// Suscribe un lector del local-store a los cambios (mismo tab vía CHANGE_EVENT,
// otros tabs vía `storage`). El valor inicial es el del servidor para evitar
// mismatches de hidratación; el valor real se aplica en un efecto tras montar.
export function useLocalValue<T>(read: () => T, initial: T): T {
  const [value, setValue] = useState<T>(initial);
  const readRef = useRef(read);
  useEffect(() => {
    readRef.current = read;
  });
  useEffect(() => {
    const update = () => setValue(readRef.current());
    update();
    window.addEventListener(CHANGE_EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(CHANGE_EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return value;
}

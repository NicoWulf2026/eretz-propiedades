import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Aísla cada test: desmonta el DOM montado para evitar coincidencias múltiples.
afterEach(() => cleanup());


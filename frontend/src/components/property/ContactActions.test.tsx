import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContactActions } from "./ContactActions";
import { mapSupabasePropertyToProperty } from "@/lib/property-mapper";
import { completeRow } from "@/test/fixtures";

describe("ContactActions", () => {
  it("uses the real source publication when the agency has no public contact channels", () => {
    const property = {
      ...mapSupabasePropertyToProperty(completeRow),
      sourceUrl: "https://example.com/aviso/123",
      agentPhone: null,
      publisher: {
        id: "roomix:agency",
        name: "Agencia real",
        phone: null,
        email: null,
        website: null,
        verified: false,
      },
    };

    render(<ContactActions property={property} canonical="https://eretz.example/propiedad/123" />);

    expect(screen.getByRole("link", { name: "Ver publicación original ↗" })).toHaveAttribute("href", property.sourceUrl);
    expect(screen.queryByRole("link", { name: "Consultar por WhatsApp" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compartir por WhatsApp" })).toBeInTheDocument();
  });
});

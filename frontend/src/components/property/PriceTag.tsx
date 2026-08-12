import type { Property } from "@/types/property";
import { propertyPrice } from "@/lib/property-presenter";

// Tratamiento ERETZ del precio: la moneda va delante, en versalita atenuada, y
// el monto en cifras tabulares. Es el mismo componente en tarjeta, ficha,
// comparador y mapa, así que un precio siempre se lee igual en todo el producto.
// El texto renderizado es exactamente el de `propertyPrice`: sólo cambia el
// marcado, nunca el contenido ni el formato de los números.
export function PriceTag({
  property,
  className = "",
}: {
  property: Pick<Property, "price" | "currency">;
  className?: string;
}) {
  const text = propertyPrice(property);
  if (!property.price || !property.currency) {
    return <p className={`price price-consult ${className}`.trim()}>{text}</p>;
  }
  const amount = text.slice(property.currency.length).trim();
  return (
    <p className={`price ${className}`.trim()}>
      <span className="price-currency">{property.currency}</span>{" "}
      <span className="price-amount">{amount}</span>
    </p>
  );
}

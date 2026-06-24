import type { ExchangeRate } from "@/types/exchange-rate";
import type { Property, PropertyCurrency } from "@/types/property";

type AnalysisConversionResult = {
  ars: number;
  usd: number;
  exchangeRate: ExchangeRate;
};

const priceFormatter = new Intl.NumberFormat("es-AR", {
  maximumFractionDigits: 0,
});

function isValidPrice(price: number) {
  return Number.isFinite(price) && price > 0;
}

export function convertPriceForAnalysis(
  price: number,
  currency: PropertyCurrency,
  exchangeRate: ExchangeRate,
): AnalysisConversionResult | null {
  if (!isValidPrice(price) || !isValidPrice(exchangeRate.value)) {
    return null;
  }

  if (currency === "USD") {
    return {
      ars: Math.round(price * exchangeRate.value),
      usd: price,
      exchangeRate,
    };
  }

  return {
    ars: price,
    usd: Math.round(price / exchangeRate.value),
    exchangeRate,
  };
}

export function getOriginalPublishedPriceLabel(property: Property) {
  if (!isValidPrice(property.price)) {
    return "Consultar precio";
  }

  return `${property.currency} ${priceFormatter.format(property.price)}`;
}

export type ExchangeRateType = "oficial" | "blue" | "mep" | "ccl" | "custom";

export type ExchangeRate = {
  type: ExchangeRateType;
  value: number;
  source: string;
  updatedAt: string;
};

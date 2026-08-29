import type { AssetConfig, AssetSymbol } from "@/types";

export const ASSET_CONFIGS: Record<AssetSymbol, AssetConfig> = {
  XAUUSD: {
    symbol: "XAUUSD",
    displayName: "XAU/USD",
    shortName: "Gold",
    pipDecimal: 2,
    contextFactors: ["USD strength (DXY)", "Gold volatility regime", "US economic news", "London / New York session"],
    sessions: ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
  EURUSD: {
    symbol: "EURUSD",
    displayName: "EUR/USD",
    shortName: "Euro",
    pipDecimal: 4,
    contextFactors: ["USD news", "EUR news", "London session", "New York session"],
    sessions: ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
  GBPUSD: {
    symbol: "GBPUSD",
    displayName: "GBP/USD",
    shortName: "Cable",
    pipDecimal: 4,
    contextFactors: ["GBP news", "USD news", "London session", "Volatility regime"],
    sessions: ["LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
};

export const ASSET_LIST: AssetSymbol[] = ["XAUUSD", "EURUSD", "GBPUSD"];

export const BASE_PRICES: Record<AssetSymbol, number> = {
  XAUUSD: 2418.35,
  EURUSD: 1.0842,
  GBPUSD: 1.2671,
};

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
  // Crypto trades continuously on real exchanges, so these are the only
  // assets here with genuine weekend coverage. Sessions are still listed
  // because volume/volatility do follow them, but the market never closes.
  BTCUSD: {
    symbol: "BTCUSD",
    displayName: "BTC/USD",
    shortName: "Bitcoin",
    pipDecimal: 2,
    contextFactors: ["Trades 24/7", "US macro (rates, CPI)", "Crypto-wide risk sentiment", "High volatility regime"],
    sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
  ETHUSD: {
    symbol: "ETHUSD",
    displayName: "ETH/USD",
    shortName: "Ethereum",
    pipDecimal: 2,
    contextFactors: ["Trades 24/7", "US macro (rates, CPI)", "Correlated to BTC", "High volatility regime"],
    sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
};

export const ASSET_LIST: AssetSymbol[] = ["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD"];

/** Assets that trade continuously (no weekend close). Mirrors CRYPTO_SYMBOLS in apps/api/app/instruments.py. */
export const ALWAYS_OPEN_ASSETS: AssetSymbol[] = ["BTCUSD", "ETHUSD"];

export function tradesAroundTheClock(asset: AssetSymbol): boolean {
  return ALWAYS_OPEN_ASSETS.includes(asset);
}

export const BASE_PRICES: Record<AssetSymbol, number> = {
  XAUUSD: 2418.35,
  EURUSD: 1.0842,
  GBPUSD: 1.2671,
  BTCUSD: 50000,
  ETHUSD: 3000,
};

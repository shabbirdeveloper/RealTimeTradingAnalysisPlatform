import type { AssetConfig, AssetSymbol, MarketAssetSymbol, OtcAssetSymbol } from "@/types";

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
  // Deriv synthetic indices. The number is that index's nominal annualised
  // volatility, which is the whole basis for choosing between them: V25 and
  // V75 are the same generator at very different speeds.
  DERIV_V75: {
    symbol: "DERIV_V75",
    displayName: "Volatility 75",
    shortName: "V75 · Deriv",
    pipDecimal: 4,
    contextFactors: ["Broker-generated, not a real market", "Trades 24/7 including weekends", "High nominal volatility", "No news impact"],
    sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
  DERIV_V50: {
    symbol: "DERIV_V50",
    displayName: "Volatility 50",
    shortName: "V50 · Deriv",
    pipDecimal: 4,
    contextFactors: ["Broker-generated, not a real market", "Trades 24/7 including weekends", "Moderate nominal volatility", "No news impact"],
    sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
  DERIV_V25: {
    symbol: "DERIV_V25",
    displayName: "Volatility 25",
    shortName: "V25 · Deriv",
    pipDecimal: 4,
    contextFactors: ["Broker-generated, not a real market", "Trades 24/7 including weekends", "Low nominal volatility", "No news impact"],
    sessions: ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"],
  },
};

/**
 * Real-market instruments the platform currently RUNS. Drives the main
 * dashboard grid, the analyzer, the history filters and every "is this a
 * symbol we know" check.
 *
 * Three, and each one is here for a reason that can be stated. XAU/USD is
 * the instrument being measured. BTC and ETH are here to answer one
 * question: a broker quotes its own weekend "OTC" gold 83 dollars from the
 * real market, but crypto trades continuously on real exchanges, so a
 * broker has a genuine 24/7 reference to quote against. Whether it does is
 * unchecked -- these cards exist so the price can be compared against a
 * broker's own screen in ten seconds.
 *
 * What is NOT here: an instrument nobody is analysing. A card that goes
 * permanently stale is not a fourth instrument, it is furniture, and a
 * visitor cannot tell the difference.
 *
 * MIRRORS apps/api/app/otc/config.py MARKET_SYMBOLS. The two must be
 * changed together: this list decides what the site renders, that one
 * decides what the engine analyses, and nothing checks them against each
 * other. A symbol here but not there is a permanently stale card.
 */
export const ASSET_LIST: MarketAssetSymbol[] = ["XAUUSD", "BTCUSD", "ETHUSD"];

/**
 * Broker-generated instruments the platform currently RUNS, rendered in
 * their own section. Appending them to ASSET_LIST would put a synthetic
 * series into every real-market total on the page — exactly what spec
 * section 72 forbids, and invisible once it happened.
 *
 * V75 is here because it is the only broker-generated series this platform
 * can price honestly. A broker's OTC instrument runs at weekends, ignores
 * news and is priced by the broker — and Deriv publishes the tick stream it
 * settles its own contracts against, so analysis and outcome read the same
 * series. Quotex's OTC pairs are the same kind of object with no permitted
 * way to read their prices; see claude/quotex-otc-audit.md.
 *
 * MIRRORS OTC_SYMBOLS in apps/api/app/otc/config.py.
 */
export const OTC_ASSET_LIST: OtcAssetSymbol[] = ["DERIV_V75"];

/**
 * Every broker-generated symbol this codebase knows about, enabled or not.
 *
 * Separate from OTC_ASSET_LIST because the two answer different questions.
 * That one asks "what should this page render"; this one asks "is this
 * symbol a real market" -- and the second answer must not change when an
 * instrument is switched off. A stored DERIV_V75 decision still has to be
 * labelled synthetic wherever it surfaces, or spec section 72's rule
 * against mixing generated prices with market ones is broken by omission.
 */
export const SYNTHETIC_SYMBOLS: OtcAssetSymbol[] = ["DERIV_V75", "DERIV_V50", "DERIV_V25"];

/** Assets that trade continuously (no weekend close). Mirrors CRYPTO_SYMBOLS in apps/api/app/instruments.py. */
export const ALWAYS_OPEN_ASSETS: AssetSymbol[] = ["BTCUSD", "ETHUSD"];

export function tradesAroundTheClock(asset: AssetSymbol): boolean {
  // Broker-generated instruments never close: their generator does not stop.
  if (OTC_ASSET_LIST.includes(asset as OtcAssetSymbol)) return true;
  return ALWAYS_OPEN_ASSETS.includes(asset as MarketAssetSymbol);
}

// Demo-engine seed prices, real-market only. A synthetic index has no
// meaningful base price to seed, and it never uses this path.
export const BASE_PRICES: Record<MarketAssetSymbol, number> = {
  XAUUSD: 2418.35,
  EURUSD: 1.0842,
  GBPUSD: 1.2671,
  BTCUSD: 50000,
  ETHUSD: 3000,
};

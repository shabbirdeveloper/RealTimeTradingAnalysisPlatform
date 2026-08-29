// DEMO DATA ENGINE
// ------------------------------------------------------------------
// Everything generated here is clearly-marked synthetic demo data for
// UI development, per project rule: "Absolutely No Fake Data in
// Production". It stands in for the real Market Data Collector ->
// Feature Engine -> Regime Engine -> Multi-Timeframe Engine -> Signal
// Engine -> Meta Model -> Calibration pipeline described in the spec.
// Nothing here is a real accuracy claim.
// ------------------------------------------------------------------
import type {
  AssetSymbol, Direction, ExpiryCandidate, ExpiryMinutes, MarketRegime,
  MarketSnapshot, Signal, SignalGrade, SessionName, Timeframe, TimeframeBias,
} from "@/types";
import { ASSET_LIST, BASE_PRICES } from "./assets";
import { pick, seededRandom, range } from "./rng";

export const IS_DEMO_DATA = true;

const TIMEFRAMES: Timeframe[] = ["H4", "H1", "M15", "M5"];
const EXPIRIES: ExpiryMinutes[] = [15, 30, 60];

function timeBucket(now: Date, minutes: number): number {
  return Math.floor(now.getTime() / (minutes * 60000));
}

export function sessionForTime(now: Date): SessionName {
  const h = now.getUTCHours();
  const london = h >= 7 && h < 16;
  const ny = h >= 12 && h < 21;
  if (london && ny) return "LONDON_NY_OVERLAP";
  if (london) return "LONDON";
  if (ny) return "NEW_YORK";
  return "ASIAN";
}

function gradeFromConfidence(confidence: number | null, technicalScore: number): SignalGrade {
  const score = confidence ?? technicalScore;
  if (confidence === null) {
    // Without a calibrated model probability we never claim A-tier.
    return technicalScore >= 78 ? "B" : "REJECTED";
  }
  if (score >= 90) return "A++";
  if (score >= 85) return "A+";
  if (score >= 80) return "A";
  if (score >= 70) return "B";
  return "REJECTED";
}

function biasLabel(rand: () => number, driftBias: -1 | 0 | 1): "BULLISH" | "BEARISH" | "NEUTRAL" {
  const r = rand();
  if (driftBias === 1) return r < 0.7 ? "BULLISH" : r < 0.9 ? "NEUTRAL" : "BEARISH";
  if (driftBias === -1) return r < 0.7 ? "BEARISH" : r < 0.9 ? "NEUTRAL" : "BULLISH";
  return r < 0.4 ? "BULLISH" : r < 0.8 ? "BEARISH" : "NEUTRAL";
}

export function generateTimeframes(asset: AssetSymbol, now: Date): TimeframeBias[] {
  const bucket = timeBucket(now, 5);
  const rand = seededRandom(asset, bucket, "timeframes");
  // A slow-moving "macro drift" so H4/H1 usually agree more than M5/M15.
  const macroDrift = rand() < 0.55 ? 1 : rand() < 0.5 ? -1 : 0;

  return TIMEFRAMES.map((tf) => {
    const tfRand = seededRandom(asset, bucket, "tf", tf);
    const align = tf === "H4" || tf === "H1" ? macroDrift : (tfRand() < 0.65 ? macroDrift : 0);
    const bias = biasLabel(tfRand, align as -1 | 0 | 1);
    const strength = Math.round(range(tfRand, bias === "NEUTRAL" ? 20 : 45, bias === "NEUTRAL" ? 55 : 95));
    const notesPool =
      bias === "BULLISH"
        ? ["Price above EMA20/50", "Higher-high structure", "RSI trending up", "MACD histogram expanding"]
        : bias === "BEARISH"
        ? ["Price below EMA20/50", "Lower-low structure", "RSI trending down", "MACD histogram contracting"]
        : ["Range-bound between S/R", "EMAs flat / crossing", "RSI mid-range", "No clear structure break"];
    const notes = [notesPool[Math.floor(tfRand() * notesPool.length)] ?? notesPool[0]!];
    return { timeframe: tf, bias, strength, notes };
  });
}

export function deriveRegime(timeframes: TimeframeBias[], rand: () => number): MarketRegime {
  const h4 = timeframes.find((t) => t.timeframe === "H4")!;
  const h1 = timeframes.find((t) => t.timeframe === "H1")!;
  const m15 = timeframes.find((t) => t.timeframe === "M15")!;
  const volRoll = rand();

  if (volRoll < 0.06) return "NEWS_MODE";
  if (volRoll < 0.11) return "UNSTABLE";
  if (volRoll < 0.2) return "HIGH_VOLATILITY";
  if (volRoll > 0.94) return "LOW_VOLATILITY";

  if (h4.bias === h1.bias && h1.bias === m15.bias && h4.bias !== "NEUTRAL") {
    return h4.bias === "BULLISH" ? "TRENDING_UP" : "TRENDING_DOWN";
  }
  return "RANGING";
}

export function generateMarketSnapshot(asset: AssetSymbol, now: Date): MarketSnapshot {
  const bucket = timeBucket(now, 5);
  const rand = seededRandom(asset, bucket, "snapshot");
  const timeframes = generateTimeframes(asset, now);
  const regime = deriveRegime(timeframes, seededRandom(asset, bucket, "regime"));
  const base = BASE_PRICES[asset];
  const driftPct = range(rand, -0.9, 0.9);
  const price = base * (1 + driftPct / 100);
  const h4 = timeframes.find((t) => t.timeframe === "H4")!;
  const bias = h4.bias;

  return {
    asset,
    price,
    change24hPct: driftPct,
    bias,
    regime,
    dataStatus: "LIVE",
    lastUpdated: now.toISOString(),
    session: sessionForTime(now),
    timeframes,
  };
}

function expiryCandidateFor(asset: AssetSymbol, now: Date, expiry: ExpiryMinutes, timeframes: TimeframeBias[], regime: MarketRegime, direction: Direction): ExpiryCandidate {
  const bucket = timeBucket(now, 5);
  const rand = seededRandom(asset, bucket, "expiry", expiry);

  const alignedCount = timeframes.filter((t) => t.bias === direction || (direction === "NO_TRADE")).length;
  const avgStrength = timeframes.reduce((s, t) => s + t.strength, 0) / timeframes.length;

  let technicalScore = Math.round(
    avgStrength * 0.55 +
      alignedCount * 6 +
      range(rand, -6, 8) +
      (regime === "TRENDING_UP" || regime === "TRENDING_DOWN" ? 6 : 0) -
      (regime === "RANGING" ? 8 : 0) -
      (regime === "HIGH_VOLATILITY" || regime === "UNSTABLE" || regime === "NEWS_MODE" ? 14 : 0)
  );
  technicalScore = Math.max(5, Math.min(99, technicalScore));

  // Simulated model lifecycle: not every asset/expiry model is trained yet.
  const modelReadyRoll = seededRandom(asset, expiry, "model-lifecycle")();
  const modelStatus: "READY" | "MODEL_NOT_READY" = modelReadyRoll < 0.82 ? "READY" : "MODEL_NOT_READY";

  let modelConfidence: number | null = null;
  if (modelStatus === "READY") {
    const calibrationNoise = range(rand, -5, 5);
    modelConfidence = Math.max(1, Math.min(99, Math.round(technicalScore * 0.78 + calibrationNoise + alignedCount * 3)));
  }

  const metaRoll = rand();
  const metaDecision: "TAKE" | "REJECT" | null =
    modelStatus === "READY" ? ((modelConfidence ?? 0) >= 68 && metaRoll > 0.15 ? "TAKE" : "REJECT") : null;

  const grade = gradeFromConfidence(modelConfidence, technicalScore);

  return {
    expiryMinutes: expiry,
    direction,
    technicalScore,
    modelConfidence,
    modelStatus,
    metaDecision,
    grade,
  };
}

const GRADE_RANK: Record<SignalGrade, number> = { "A++": 4, "A+": 3, A: 2, B: 1, REJECTED: 0 };

export function generateSignal(asset: AssetSymbol, now: Date): Signal {
  const bucket = timeBucket(now, 5);
  const snapshot = generateMarketSnapshot(asset, now);
  const { timeframes, regime } = snapshot;
  const rand = seededRandom(asset, bucket, "direction");

  const h4 = timeframes.find((t) => t.timeframe === "H4")!;
  const h1 = timeframes.find((t) => t.timeframe === "H1")!;
  const m15 = timeframes.find((t) => t.timeframe === "M15")!;
  const m5 = timeframes.find((t) => t.timeframe === "M5")!;

  const bullVotes = [h4, h1, m15, m5].filter((t) => t.bias === "BULLISH").length;
  const bearVotes = [h4, h1, m15, m5].filter((t) => t.bias === "BEARISH").length;

  let proposedDirection: Direction = "NO_TRADE";
  if (bullVotes >= 3) proposedDirection = "CALL";
  else if (bearVotes >= 3) proposedDirection = "PUT";

  const newsBlackout = regime === "NEWS_MODE";
  const unstable = regime === "UNSTABLE";

  const reasons: string[] = [];
  const warnings: string[] = [];

  if (proposedDirection === "NO_TRADE" || newsBlackout || unstable) {
    if (newsBlackout) warnings.push("High-impact news window active — signal generation paused.");
    if (unstable) warnings.push("Market regime classified UNSTABLE — conditions too erratic to score reliably.");
    if (proposedDirection === "NO_TRADE" && !newsBlackout && !unstable) {
      warnings.push(`Timeframes conflicting: H4 ${h4.bias.toLowerCase()}, H1 ${h1.bias.toLowerCase()}, M15 ${m15.bias.toLowerCase()}, M5 ${m5.bias.toLowerCase()}.`);
    }
    return {
      id: `${asset}-${bucket}-notrade`,
      asset,
      direction: "NO_TRADE",
      confidence: null,
      technicalScore: 0,
      grade: "REJECTED",
      expiryMinutes: null,
      marketRegime: regime,
      generatedAt: now.toISOString(),
      entryPrice: null,
      validUntil: null,
      reasons: reasons.length ? reasons : ["Market conditions not strong enough for a high-quality setup."],
      warnings,
      status: "REJECTED",
      modelVersion: null,
      timeframes,
      session: snapshot.session,
    };
  }

  const candidates = EXPIRIES.map((exp) => expiryCandidateFor(asset, now, exp, timeframes, regime, proposedDirection));

  const eligible = candidates.filter((c) => c.metaDecision !== "REJECT" && GRADE_RANK[c.grade] >= GRADE_RANK.B);
  const best = eligible.length
    ? eligible.reduce((a, b) => ((b.modelConfidence ?? b.technicalScore) > (a.modelConfidence ?? a.technicalScore) ? b : a))
    : null;

  if (!best) {
    return {
      id: `${asset}-${bucket}-notrade`,
      asset,
      direction: "NO_TRADE",
      confidence: null,
      technicalScore: Math.max(...candidates.map((c) => c.technicalScore)),
      grade: "REJECTED",
      expiryMinutes: null,
      marketRegime: regime,
      generatedAt: now.toISOString(),
      entryPrice: null,
      validUntil: null,
      reasons: ["No expiry cleared the meta-model TAKE threshold."],
      warnings: ["All expiry candidates rejected by meta trade/no-trade model or below B-grade threshold."],
      status: "REJECTED",
      modelVersion: null,
      timeframes,
      session: snapshot.session,
    };
  }

  if (h4.bias === h1.bias && h1.bias === proposedDirectionBias(proposedDirection)) {
    reasons.push(`H4 and H1 both ${h4.bias.toLowerCase()} — trend alignment confirmed.`);
  }
  reasons.push(`${bullVotes >= 3 ? bullVotes : bearVotes}/4 timeframes aligned ${proposedDirection === "CALL" ? "bullish" : "bearish"}.`);
  reasons.push(`Market regime: ${regime.replace("_", " ").toLowerCase()}.`);
  if (best.modelStatus === "MODEL_NOT_READY") {
    warnings.push("Calibrated model not yet available for this expiry — grade capped, technical score shown separately.");
  }
  if (candidates.some((c) => c.metaDecision === "REJECT")) {
    warnings.push("One or more expiries rejected by meta model despite directional agreement.");
  }

  const validUntilMs = now.getTime() + best.expiryMinutes * 60000;

  return {
    id: `${asset}-${bucket}-${best.expiryMinutes}`,
    asset,
    direction: proposedDirection,
    confidence: best.modelConfidence,
    technicalScore: best.technicalScore,
    grade: best.grade,
    expiryMinutes: best.expiryMinutes,
    marketRegime: regime,
    generatedAt: now.toISOString(),
    entryPrice: snapshot.price,
    validUntil: new Date(validUntilMs).toISOString(),
    reasons,
    warnings,
    status: "ACTIVE",
    modelVersion: best.modelStatus === "READY" ? `${asset.toLowerCase()}-${best.expiryMinutes}m-xgb-v1.4.2` : null,
    timeframes,
    session: snapshot.session,
    candidates,
  };
}

function proposedDirectionBias(direction: Direction): "BULLISH" | "BEARISH" | "NEUTRAL" {
  if (direction === "CALL") return "BULLISH";
  if (direction === "PUT") return "BEARISH";
  return "NEUTRAL";
}

export function generateAllSignals(now: Date): Signal[] {
  return ASSET_LIST.map((a) => generateSignal(a, now));
}

// ------------------------------------------------------------------
// Technical + structure detail generators (Markets pages, Analyzer)
// ------------------------------------------------------------------
export interface TechnicalMetrics {
  rsi: number;
  rsiSlope: "RISING" | "FALLING" | "FLAT";
  macdHistogram: number;
  macdTrend: "EXPANDING" | "CONTRACTING";
  ema20: number;
  ema50: number;
  ema200: number;
  priceVsEma: "ABOVE_ALL" | "BELOW_ALL" | "MIXED";
  atr: number;
  atrPercentile: number;
  bollingerWidth: number;
}

export function generateTechnicalMetrics(asset: AssetSymbol, now: Date): TechnicalMetrics {
  const bucket = timeBucket(now, 5);
  const rand = seededRandom(asset, bucket, "technical");
  const base = BASE_PRICES[asset];
  const rsi = Math.round(range(rand, 28, 78));
  const ema20 = base * (1 + range(rand, -0.4, 0.4) / 100);
  const ema50 = base * (1 + range(rand, -0.6, 0.6) / 100);
  const ema200 = base * (1 + range(rand, -1, 1) / 100);
  const priceVsEma = ema20 > ema50 && ema50 > ema200 ? "ABOVE_ALL" : ema20 < ema50 && ema50 < ema200 ? "BELOW_ALL" : "MIXED";

  return {
    rsi,
    rsiSlope: rsi > 55 ? "RISING" : rsi < 45 ? "FALLING" : "FLAT",
    macdHistogram: Math.round(range(rand, -1.2, 1.2) * 100) / 100,
    macdTrend: rand() > 0.5 ? "EXPANDING" : "CONTRACTING",
    ema20, ema50, ema200, priceVsEma,
    atr: base * range(rand, 0.003, 0.012),
    atrPercentile: Math.round(range(rand, 10, 95)),
    bollingerWidth: Math.round(range(rand, 8, 60) * 10) / 10,
  };
}

export function generateStructureNotes(asset: AssetSymbol, now: Date): string[] {
  const bucket = timeBucket(now, 5);
  const rand = seededRandom(asset, bucket, "structure");
  const pool = [
    "Higher-high / higher-low sequence intact on H1.",
    "Break of structure confirmed above prior swing high.",
    "Change of character detected — momentum shifting on M15.",
    "Price retesting broken resistance as new support.",
    "False breakout rejected at London high.",
    "Consolidating inside prior day's range.",
    "Approaching untested previous-day high.",
    "Support holding at Asian session low.",
    "Lower-high forming below H4 resistance.",
    "Liquidity sweep below Asian low, reclaiming range.",
  ];
  const count = 3 + Math.floor(rand() * 2);
  const chosen = new Set<string>();
  while (chosen.size < count) chosen.add(pool[Math.floor(rand() * pool.length)]!);
  return Array.from(chosen);
}

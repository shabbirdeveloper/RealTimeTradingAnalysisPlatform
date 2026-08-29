// DEMO DATA — static, fixed-seed historical records for history tables,
// performance dashboards, admin views, calendar, model registry and
// backtests. Uses a fixed anchor date (not Date.now()) so server and
// client render identically and no hydration mismatch occurs.
import type {
  BacktestResult, Direction, EconomicEvent, ExpiryMinutes, ModelInfo, ModelStatus,
  PerformanceBucket, PerformanceSummary, RejectedOpportunity, Signal, SignalGrade,
  SystemComponentHealth, SessionName, MarketRegime, AssetSymbol,
} from "@/types";
import { ASSET_LIST, BASE_PRICES } from "./assets";
import { seededRandom, pick, range } from "./rng";
import { generateTimeframes } from "./engine";

export const ANCHOR_DATE = new Date("2026-08-29T09:00:00.000Z");

const GRADES: SignalGrade[] = ["A++", "A+", "A", "B"];
const EXPIRIES: ExpiryMinutes[] = [15, 30, 60];
const SESSIONS: SessionName[] = ["ASIAN", "LONDON", "NEW_YORK", "LONDON_NY_OVERLAP"];
const REGIMES: MarketRegime[] = ["TRENDING_UP", "TRENDING_DOWN", "RANGING", "HIGH_VOLATILITY", "LOW_VOLATILITY"];

// Grade -> approximate win probability used only to shape realistic-looking
// DEMO history. Real win rates must come from actual resolved trades.
const GRADE_WIN_PROB: Record<SignalGrade, number> = { "A++": 0.91, "A+": 0.83, A: 0.76, B: 0.63, REJECTED: 0 };

function gradeWeightedPick(rand: () => number): SignalGrade {
  const r = rand();
  if (r < 0.17) return "A++";
  if (r < 0.4) return "A+";
  if (r < 0.68) return "A";
  return "B";
}

export const HISTORICAL_SIGNALS: Signal[] = (() => {
  const out: Signal[] = [];
  const count = 420;
  for (let i = 0; i < count; i++) {
    const rand = seededRandom("history", i);
    const asset = pick(rand, ASSET_LIST);
    const direction: Direction = rand() < 0.51 ? "CALL" : "PUT";
    const grade = gradeWeightedPick(rand);
    const expiryMinutes = pick(rand, EXPIRIES);
    const session = pick(rand, SESSIONS);
    const regime = pick(rand, REGIMES);
    const confidence =
      grade === "A++" ? Math.round(range(rand, 90, 97))
      : grade === "A+" ? Math.round(range(rand, 85, 89))
      : grade === "A" ? Math.round(range(rand, 80, 84))
      : Math.round(range(rand, 70, 79));
    const technicalScore = Math.min(99, confidence + Math.round(range(rand, -6, 6)));
    const minutesAgo = Math.round(range(rand, 20, 60 * 24 * 30));
    const generatedAt = new Date(ANCHOR_DATE.getTime() - minutesAgo * 60000);
    const resolvedAt = new Date(generatedAt.getTime() + expiryMinutes * 60000);
    const base = BASE_PRICES[asset];
    const entryPrice = base * (1 + range(rand, -1.2, 1.2) / 100);
    const won = rand() < GRADE_WIN_PROB[grade];
    const isDraw = !won && rand() < 0.03;
    const moveSize = entryPrice * range(rand, 0.0005, 0.006);
    let closingPrice: number;
    let result: "WON" | "LOST" | "DRAW";
    if (isDraw) {
      closingPrice = entryPrice;
      result = "DRAW";
    } else if (won) {
      closingPrice = direction === "CALL" ? entryPrice + moveSize : entryPrice - moveSize;
      result = "WON";
    } else {
      closingPrice = direction === "CALL" ? entryPrice - moveSize : entryPrice + moveSize;
      result = "LOST";
    }

    out.push({
      id: `hist-${asset}-${i}`,
      asset,
      direction,
      confidence,
      technicalScore,
      grade,
      expiryMinutes,
      marketRegime: regime,
      generatedAt: generatedAt.toISOString(),
      entryPrice,
      validUntil: resolvedAt.toISOString(),
      reasons: [],
      warnings: [],
      status: result,
      result,
      closingPrice,
      resolvedAt: resolvedAt.toISOString(),
      modelVersion: `${asset.toLowerCase()}-${expiryMinutes}m-xgb-v1.4.2`,
      timeframes: generateTimeframes(asset, generatedAt),
      session,
    });
  }
  return out.sort((a, b) => new Date(b.generatedAt).getTime() - new Date(a.generatedAt).getTime());
})();

export const REJECTED_OPPORTUNITIES: RejectedOpportunity[] = (() => {
  const out: RejectedOpportunity[] = [];
  const reasonsPool = [
    "Below A++ confidence threshold",
    "Meta model returned REJECT despite directional agreement",
    "Timeframes conflicting (H4 vs M15)",
    "High-impact news window within blackout period",
    "Regime classified UNSTABLE",
    "ATR percentile too extreme for reliable scoring",
    "Model confidence unavailable — MODEL_NOT_READY",
  ];
  for (let i = 0; i < 60; i++) {
    const rand = seededRandom("rejected", i);
    const asset = pick(rand, ASSET_LIST);
    const potentialDirection: "CALL" | "PUT" = rand() < 0.5 ? "CALL" : "PUT";
    const hasConfidence = rand() > 0.25;
    const minutesAgo = Math.round(range(rand, 10, 60 * 24 * 20));
    out.push({
      id: `rej-${asset}-${i}`,
      asset,
      potentialDirection,
      confidence: hasConfidence ? Math.round(range(rand, 55, 88)) : null,
      reason: pick(rand, reasonsPool),
      generatedAt: new Date(ANCHOR_DATE.getTime() - minutesAgo * 60000).toISOString(),
    });
  }
  return out.sort((a, b) => new Date(b.generatedAt).getTime() - new Date(a.generatedAt).getTime());
})();

function bucketFrom(label: string, signals: Signal[]): PerformanceBucket {
  const resolved = signals.filter((s) => s.result);
  const wins = resolved.filter((s) => s.result === "WON").length;
  const losses = resolved.filter((s) => s.result === "LOST").length;
  const draws = resolved.filter((s) => s.result === "DRAW").length;
  const decided = wins + losses;
  return {
    label,
    signals: resolved.length,
    wins,
    losses,
    draws,
    accuracy: decided > 0 ? Math.round((wins / decided) * 1000) / 10 : 0,
  };
}

export function computePerformanceSummary(signals: Signal[]): PerformanceSummary {
  const resolved = [...signals].filter((s) => s.result).sort((a, b) => new Date(a.generatedAt).getTime() - new Date(b.generatedAt).getTime());
  const wins = resolved.filter((s) => s.result === "WON").length;
  const losses = resolved.filter((s) => s.result === "LOST").length;
  const draws = resolved.filter((s) => s.result === "DRAW").length;
  const decided = wins + losses;

  const aPlusPlus = resolved.filter((s) => s.grade === "A++");
  const aPlusPlusDecided = aPlusPlus.filter((s) => s.result === "WON" || s.result === "LOST");
  const aPlusPlusWins = aPlusPlus.filter((s) => s.result === "WON").length;

  let curType: "WIN" | "LOSS" | "NONE" = "NONE";
  let curCount = 0;
  for (let i = resolved.length - 1; i >= 0; i--) {
    const r = resolved[i]!.result;
    if (r === "DRAW") continue;
    const t = r === "WON" ? "WIN" : "LOSS";
    if (curType === "NONE") { curType = t; curCount = 1; }
    else if (t === curType) curCount++;
    else break;
  }

  let maxWin = 0, maxLoss = 0, runWin = 0, runLoss = 0;
  for (const s of resolved) {
    if (s.result === "WON") { runWin++; runLoss = 0; maxWin = Math.max(maxWin, runWin); }
    else if (s.result === "LOST") { runLoss++; runWin = 0; maxLoss = Math.max(maxLoss, runLoss); }
  }

  const byAsset = ASSET_LIST.map((a) => bucketFrom(a, resolved.filter((s) => s.asset === a)));
  const byExpiry = ([15, 30, 60] as ExpiryMinutes[]).map((e) => bucketFrom(`${e}m`, resolved.filter((s) => s.expiryMinutes === e)));
  const bySession = SESSIONS.map((s) => bucketFrom(s.replace("_", " "), resolved.filter((sig) => sig.session === s)));
  const byRegime = REGIMES.map((r) => bucketFrom(r.replace("_", " "), resolved.filter((s) => s.marketRegime === r)));
  const confBuckets: [string, number, number][] = [["70-79%", 70, 80], ["80-84%", 80, 85], ["85-89%", 85, 90], ["90-100%", 90, 101]];
  const byConfidenceBucket = confBuckets.map(([label, lo, hi]) =>
    bucketFrom(label as string, resolved.filter((s) => (s.confidence ?? 0) >= (lo as number) && (s.confidence ?? 0) < (hi as number)))
  );

  const byDay = new Map<string, Signal[]>();
  for (const s of resolved) {
    const day = s.generatedAt.slice(0, 10);
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day)!.push(s);
  }
  const days = Array.from(byDay.keys()).sort();
  let cumW = 0, cumL = 0;
  const accuracyOverTime = days.map((day) => {
    const daySignals = byDay.get(day)!;
    const dWins = daySignals.filter((s) => s.result === "WON").length;
    const dDecided = daySignals.filter((s) => s.result === "WON" || s.result === "LOST").length;
    return { date: day, accuracy: dDecided > 0 ? Math.round((dWins / dDecided) * 1000) / 10 : 0, signals: daySignals.length };
  });
  const cumulative = days.map((day) => {
    const daySignals = byDay.get(day)!;
    cumW += daySignals.filter((s) => s.result === "WON").length;
    cumL += daySignals.filter((s) => s.result === "LOST").length;
    return { date: day, wins: cumW, losses: cumL };
  });

  return {
    totalSignals: resolved.length,
    wins, losses, draws,
    overallAccuracy: decided > 0 ? Math.round((wins / decided) * 1000) / 10 : 0,
    aPlusPlusSignals: aPlusPlus.length,
    aPlusPlusAccuracy: aPlusPlusDecided.length > 0 ? Math.round((aPlusPlusWins / aPlusPlusDecided.length) * 1000) / 10 : 0,
    currentStreak: { type: curType, count: curCount },
    maxWinStreak: maxWin,
    maxLossStreak: maxLoss,
    byAsset, byExpiry, bySession, byRegime, byConfidenceBucket,
    accuracyOverTime, cumulative,
  };
}

export const PERFORMANCE_SUMMARY: PerformanceSummary = computePerformanceSummary(HISTORICAL_SIGNALS);

export const ECONOMIC_EVENTS: EconomicEvent[] = [
  { id: "ev-1", event: "US Non-Farm Payrolls", currency: "USD", impact: "HIGH", previous: "187K", forecast: "195K", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 26 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
  { id: "ev-2", event: "FOMC Rate Decision", currency: "USD", impact: "HIGH", previous: "5.25%", forecast: "5.25%", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 3 * 24 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
  { id: "ev-3", event: "US CPI y/y", currency: "USD", impact: "HIGH", previous: "3.1%", forecast: "3.0%", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 5 * 24 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
  { id: "ev-4", event: "ECB Press Conference", currency: "EUR", impact: "HIGH", previous: "-", forecast: "-", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 6 * 24 * 3600000).toISOString(), affectsAssets: ["EURUSD"] },
  { id: "ev-5", event: "BoE Rate Decision", currency: "GBP", impact: "HIGH", previous: "5.00%", forecast: "5.00%", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 7 * 24 * 3600000).toISOString(), affectsAssets: ["GBPUSD"] },
  { id: "ev-6", event: "US PPI m/m", currency: "USD", impact: "MEDIUM", previous: "0.2%", forecast: "0.2%", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 2 * 24 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
  { id: "ev-7", event: "US Unemployment Claims", currency: "USD", impact: "MEDIUM", previous: "218K", forecast: "220K", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 12 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
  { id: "ev-8", event: "German ZEW Sentiment", currency: "EUR", impact: "LOW", previous: "12.8", forecast: "14.0", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 4 * 24 * 3600000).toISOString(), affectsAssets: ["EURUSD"] },
  { id: "ev-9", event: "UK Retail Sales m/m", currency: "GBP", impact: "MEDIUM", previous: "0.3%", forecast: "0.1%", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 1 * 24 * 3600000).toISOString(), affectsAssets: ["GBPUSD"] },
  { id: "ev-10", event: "Powell Speech", currency: "USD", impact: "HIGH", previous: "-", forecast: "-", actual: null, dateTime: new Date(ANCHOR_DATE.getTime() + 8 * 3600000).toISOString(), affectsAssets: ["XAUUSD", "EURUSD", "GBPUSD"] },
];

export const MODELS: ModelInfo[] = ASSET_LIST.flatMap((asset) =>
  ([15, 30, 60] as ExpiryMinutes[]).map((expiry, idx) => {
    const rand = seededRandom("model", asset, expiry);
    const statusRoll = rand();
    const status: ModelStatus = statusRoll < 0.55 ? "ACTIVE" : statusRoll < 0.75 ? "READY" : statusRoll < 0.88 ? "VALIDATING" : statusRoll < 0.97 ? "TRAINING" : "ARCHIVED";
    const testAcc = status === "TRAINING" ? null : Math.round(range(rand, 66, 74) * 10) / 10;
    const aAcc = status === "TRAINING" ? null : Math.round(range(rand, 87, 93) * 10) / 10;
    return {
      id: `${asset.toLowerCase()}-${expiry}m`,
      name: `${asset} ${expiry}m XGBoost`,
      asset,
      expiryMinutes: expiry,
      version: `v1.${idx + 3}.${Math.floor(range(rand, 0, 9))}`,
      trainingDate: new Date(ANCHOR_DATE.getTime() - Math.round(range(rand, 5, 60)) * 86400000).toISOString(),
      trainingPeriod: "2023-01-01 → 2026-06-30",
      testAccuracy: testAcc,
      aPlusPlusAccuracy: aAcc,
      signalCoverage: status === "TRAINING" ? null : Math.round(range(rand, 3, 9) * 10) / 10,
      status,
    };
  })
);

export const SYSTEM_HEALTH: SystemComponentHealth[] = [
  { name: "Frontend", status: "Healthy" },
  { name: "API", status: "Healthy", latencyMs: 84 },
  { name: "Database", status: "Healthy", latencyMs: 12 },
  { name: "Market Data", status: "Healthy", latencyMs: 210 },
  { name: "Feature Engine", status: "Healthy" },
  { name: "Signal Engine", status: "Healthy" },
  { name: "ML Engine", status: "Warning", detail: "2 of 9 expiry models still TRAINING" },
  { name: "News API", status: "Healthy", latencyMs: 340 },
  { name: "Notifications", status: "Healthy" },
  { name: "WebSockets", status: "Healthy", latencyMs: 45 },
];

export function buildDemoBacktest(params: {
  asset: AssetSymbol | "ALL";
  expiryMinutes: ExpiryMinutes | "ALL";
  startDate: string;
  endDate: string;
  minConfidence: number;
}): BacktestResult {
  const pool = HISTORICAL_SIGNALS.filter((s) => {
    const t = new Date(s.generatedAt).getTime();
    const inRange = t >= new Date(params.startDate).getTime() && t <= new Date(params.endDate).getTime();
    const assetMatch = params.asset === "ALL" || s.asset === params.asset;
    const expiryMatch = params.expiryMinutes === "ALL" || s.expiryMinutes === params.expiryMinutes;
    const confMatch = (s.confidence ?? 0) >= params.minConfidence;
    return inRange && assetMatch && expiryMatch && confMatch;
  });
  const totalOpportunities = Math.round(pool.length * 3.4);
  const accepted = pool.length;
  const rejected = totalOpportunities - accepted;
  const wins = pool.filter((s) => s.result === "WON").length;
  const losses = pool.filter((s) => s.result === "LOST").length;
  const draws = pool.filter((s) => s.result === "DRAW").length;
  const decided = wins + losses;

  let maxWin = 0, maxLoss = 0, runWin = 0, runLoss = 0;
  for (const s of [...pool].sort((a, b) => new Date(a.generatedAt).getTime() - new Date(b.generatedAt).getTime())) {
    if (s.result === "WON") { runWin++; runLoss = 0; maxWin = Math.max(maxWin, runWin); }
    else if (s.result === "LOST") { runLoss++; runWin = 0; maxLoss = Math.max(maxLoss, runLoss); }
  }

  return {
    id: `bt-${Date.now()}`,
    asset: params.asset,
    expiryMinutes: params.expiryMinutes,
    startDate: params.startDate,
    endDate: params.endDate,
    minConfidence: params.minConfidence,
    modelVersion: "xgb-v1.4.2",
    totalOpportunities,
    accepted,
    rejected,
    wins, losses, draws,
    winRate: decided > 0 ? Math.round((wins / decided) * 1000) / 10 : 0,
    maxWinStreak: maxWin,
    maxLossStreak: maxLoss,
    byAsset: ASSET_LIST.map((a) => bucketFrom(a, pool.filter((s) => s.asset === a))),
    byExpiry: ([15, 30, 60] as ExpiryMinutes[]).map((e) => bucketFrom(`${e}m`, pool.filter((s) => s.expiryMinutes === e))),
    bySession: SESSIONS.map((s) => bucketFrom(s.replace("_", " "), pool.filter((sig) => sig.session === s))),
    byRegime: REGIMES.map((r) => bucketFrom(r.replace("_", " "), pool.filter((s) => s.marketRegime === r))),
    byConfidenceBucket: [["70-79%", 70, 80], ["80-84%", 80, 85], ["85-89%", 85, 90], ["90-100%", 90, 101]].map(([label, lo, hi]) =>
      bucketFrom(label as string, pool.filter((s) => (s.confidence ?? 0) >= (lo as number) && (s.confidence ?? 0) < (hi as number)))
    ),
    createdAt: ANCHOR_DATE.toISOString(),
  };
}

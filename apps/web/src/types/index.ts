// Core domain types for the NorthFXTrade signal platform.
// These mirror the signal engine output contract defined in the project spec.

export type AssetSymbol = "XAUUSD" | "EURUSD" | "GBPUSD" | "BTCUSD" | "ETHUSD";

export type Direction = "CALL" | "PUT" | "NO_TRADE";

export type SignalGrade = "A++" | "A+" | "A" | "B" | "REJECTED";

export type ExpiryMinutes = 15 | 30 | 60;

export type Timeframe = "M5" | "M15" | "H1" | "H4";

export type MarketRegime =
  | "TRENDING_UP"
  | "TRENDING_DOWN"
  | "RANGING"
  | "HIGH_VOLATILITY"
  | "LOW_VOLATILITY"
  | "NEWS_MODE"
  | "UNSTABLE";

export type DataStatus = "LIVE" | "DELAYED" | "STALE" | "OFFLINE";

export type SignalStatus =
  | "CANDIDATE"
  | "REJECTED"
  | "ACTIVE"
  | "EXPIRED"
  | "WON"
  | "LOST"
  | "DRAW"
  | "INVALIDATED";

export type ModelStatus = "TRAINING" | "VALIDATING" | "READY" | "ACTIVE" | "ARCHIVED" | "FAILED";

export type SessionName = "ASIAN" | "LONDON" | "NEW_YORK" | "LONDON_NY_OVERLAP";

export type NewsImpact = "HIGH" | "MEDIUM" | "LOW";

export interface TimeframeBias {
  timeframe: Timeframe;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  strength: number; // 0-100
  notes: string[];
}

export interface AssetConfig {
  symbol: AssetSymbol;
  displayName: string;
  shortName: string;
  pipDecimal: number;
  contextFactors: string[];
  sessions: SessionName[];
}

export interface MarketSnapshot {
  asset: AssetSymbol;
  price: number;
  change24hPct: number;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
  regime: MarketRegime;
  dataStatus: DataStatus;
  lastUpdated: string; // ISO
  session: SessionName;
  timeframes: TimeframeBias[];
}

export interface SignalReasonSet {
  reasons: string[];
  warnings: string[];
}

/** One gate a setup was put through (spec Phase 26). Recorded for every
 *  decision, so a NO TRADE can say which check stopped it and how close it
 *  came, instead of only that it happened. */
export interface DecisionCheck {
  name: string;
  passed: boolean;
  detail: string;
  value: string | null;
  required: string | null;
}

export interface ExpiryCandidate {
  expiryMinutes: ExpiryMinutes;
  expirySeconds?: number | null;
  direction: Direction;
  technicalScore: number; // 0-100, always computed (technical scoring never depends on ML readiness)
  modelConfidence: number | null; // 0-100, null if MODEL_NOT_READY
  modelStatus: "READY" | "MODEL_NOT_READY";
  metaDecision: "TAKE" | "REJECT" | null;
  grade: SignalGrade;
}

export interface Signal {
  id: string;
  asset: AssetSymbol;
  direction: Direction;
  confidence: number | null;
  technicalScore: number;
  grade: SignalGrade;
  expiryMinutes: ExpiryMinutes | null;
  /** Authoritative horizon in seconds. Broker-OTC trades 15-180s, which
   *  expiryMinutes cannot express; it is null for those signals. */
  expirySeconds: number | null;
  marketRegime: MarketRegime;
  checks?: DecisionCheck[];
  generatedAt: string; // ISO
  /**
   * When the engine last re-confirmed this decision. Dedup keeps ONE row
   * per standing decision (a NO_TRADE that holds all day is one decision,
   * not 144), so `generatedAt` stops moving while the engine keeps running.
   * Showing only that made a working engine look dead. This is the field
   * that answers "is it still alive?".
   */
  lastEvaluatedAt?: string | null; // ISO
  entryPrice: number | null;
  validUntil: string | null; // ISO
  expiresInMs?: number;
  reasons: string[];
  warnings: string[];
  status: SignalStatus;
  result?: "WON" | "LOST" | "DRAW";
  closingPrice?: number | null;
  resolvedAt?: string | null;
  modelVersion: string | null;
  timeframes: TimeframeBias[];
  session: SessionName;
  candidates?: ExpiryCandidate[];
}

export interface RejectedOpportunity {
  id: string;
  asset: AssetSymbol;
  potentialDirection: "CALL" | "PUT";
  confidence: number | null;
  reason: string;
  generatedAt: string;
}

export interface EconomicEvent {
  id: string;
  event: string;
  currency: "USD" | "EUR" | "GBP" | string;
  dateTime: string; // ISO
  impact: NewsImpact;
  previous: string | null;
  forecast: string | null;
  actual: string | null;
  affectsAssets: AssetSymbol[];
}

export interface PerformanceBucket {
  label: string;
  signals: number;
  wins: number;
  losses: number;
  draws: number;
  accuracy: number; // 0-100
}

export interface PerformanceSummary {
  totalSignals: number;
  wins: number;
  losses: number;
  draws: number;
  overallAccuracy: number;
  aPlusPlusSignals: number;
  aPlusPlusAccuracy: number;
  currentStreak: { type: "WIN" | "LOSS" | "NONE"; count: number };
  maxWinStreak: number;
  maxLossStreak: number;
  byAsset: PerformanceBucket[];
  byExpiry: PerformanceBucket[];
  bySession: PerformanceBucket[];
  byRegime: PerformanceBucket[];
  byConfidenceBucket: PerformanceBucket[];
  accuracyOverTime: { date: string; accuracy: number; signals: number }[];
  cumulative: { date: string; wins: number; losses: number }[];
}

export interface ModelInfo {
  id: string;
  name: string;
  asset: AssetSymbol;
  expiryMinutes: ExpiryMinutes;
  version: string;
  trainingDate: string;
  trainingPeriod: string;
  testAccuracy: number | null;
  aPlusPlusAccuracy: number | null;
  signalCoverage: number | null;
  status: ModelStatus;
}

export interface BacktestResult {
  id: string;
  asset: AssetSymbol | "ALL";
  expiryMinutes: ExpiryMinutes | "ALL";
  startDate: string;
  endDate: string;
  minConfidence: number;
  modelVersion: string;
  totalOpportunities: number;
  accepted: number;
  rejected: number;
  wins: number;
  losses: number;
  draws: number;
  winRate: number;
  maxWinStreak: number;
  maxLossStreak: number;
  byAsset: PerformanceBucket[];
  byExpiry: PerformanceBucket[];
  bySession: PerformanceBucket[];
  byRegime: PerformanceBucket[];
  byConfidenceBucket: PerformanceBucket[];
  createdAt: string;
}

export interface SystemComponentHealth {
  name: string;
  status: "Healthy" | "Warning" | "Offline";
  detail?: string;
  latencyMs?: number;
}

import { createClient } from "@/lib/supabase/server";
import type { AssetSymbol, DataStatus, MarketAssetSymbol } from "@/types";
import { ASSET_LIST } from "@/data/assets";

export interface AssetPriceSnapshot {
  asset: AssetSymbol;
  price: number;
  change24hPct: number;
  dataStatus: DataStatus;
  lastUpdated: string; // ISO
}

const LIVE_MAX_AGE_MS = 10 * 60 * 1000; // 10 minutes
const DELAYED_MAX_AGE_MS = 30 * 60 * 1000; // 30 minutes
const STALE_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

function classifyDataStatus(lastCandleTime: Date, now: Date): DataStatus {
  const ageMs = now.getTime() - lastCandleTime.getTime();
  if (ageMs <= LIVE_MAX_AGE_MS) return "LIVE";
  if (ageMs <= DELAYED_MAX_AGE_MS) return "DELAYED";
  if (ageMs <= STALE_MAX_AGE_MS) return "STALE";
  return "OFFLINE";
}

type SupabaseServerClient = Awaited<ReturnType<typeof createClient>>;

async function fetchSnapshotForAssetId(
  supabase: SupabaseServerClient,
  assetId: string,
  symbol: AssetSymbol,
  now: Date
): Promise<AssetPriceSnapshot | null> {
  const [latestResult, oldestResult] = await Promise.all([
    supabase
      .from("candles")
      .select("close, open_time")
      .eq("asset_id", assetId)
      .eq("timeframe", "M5")
      .order("open_time", { ascending: false })
      .limit(1),
    supabase
      .from("candles")
      .select("close, open_time")
      .eq("asset_id", assetId)
      .eq("timeframe", "M5")
      .order("open_time", { ascending: true })
      .limit(1),
  ]);

  const latest = latestResult.data?.[0] as { close: string; open_time: string } | undefined;
  const oldest = oldestResult.data?.[0] as { close: string; open_time: string } | undefined;
  if (!latest) return null; // no data for this asset yet

  const price = Number(latest.close);
  const baseline = oldest ? Number(oldest.close) : price;
  const change24hPct = baseline !== 0 ? ((price - baseline) / baseline) * 100 : 0;
  const lastCandleTime = new Date(latest.open_time);

  return {
    asset: symbol,
    price,
    change24hPct,
    dataStatus: classifyDataStatus(lastCandleTime, now),
    lastUpdated: lastCandleTime.toISOString(),
  };
}

/**
 * Reads real M5 candles from Supabase for each configured asset and
 * derives a price snapshot. An asset with no candles yet (collector
 * hasn't reached it, migrations not run, Supabase not configured) comes
 * back as `null` in the result -- never a fabricated number. Spec
 * section 50: no fake prices, ever, in any state.
 *
 * change24hPct is computed against the OLDEST M5 candle currently
 * stored, not a fixed "24h ago" timestamp -- while the collector is
 * still building up history that may be less than 24 hours' worth. It's
 * still a real, honestly-computed number from real data; it converges to
 * a true 24h figure as history accumulates.
 *
 * Never throws -- any failure (Supabase not configured, network error,
 * RLS denial) results in every asset coming back null, so the caller can
 * render an honest "no data" state instead of the page crashing.
 */
/**
 * Why a snapshot is missing. "No candle has ever been stored" and "the
 * query was refused" both produce null, and they call for opposite
 * responses — start the collector, versus fix access. Rendering them
 * identically is how an outage gets diagnosed as an empty database.
 */
export type SnapshotFailure = { reason: string } | null;

export interface SnapshotResult {
  snapshots: Record<AssetSymbol, AssetPriceSnapshot | null>;
  failure: SnapshotFailure;
}

export async function getAssetPriceSnapshotsWithReason(): Promise<SnapshotResult> {
  const snapshots = await getAssetPriceSnapshots();
  if (Object.values(snapshots).some((s) => s !== null)) {
    return { snapshots, failure: null };
  }

  let failure: SnapshotFailure = null;
  try {
    const supabase = await createClient();

    // Order matters. A row-level policy that filters everything out returns
    // an EMPTY SET, not an error -- so an error probe alone cannot tell
    // "you may not see these rows" from "there are no rows", which is the
    // exact confusion this function exists to end. Ask about access first,
    // explicitly, and only then about content.
    // Ask the database what IT thinks, and ask the app what it thinks, and
    // print both. is_approved() returning false while the profiles row says
    // APPROVED is a completely different bug from the row not being
    // approved, and one message cannot stand for both.
    const { data: approved, error: approvalError } = await supabase.rpc("is_approved");
    const { data: auth } = await supabase.auth.getUser();
    const uid = auth?.user?.id ?? null;

    let rowStatus: string | null = null;
    let rowError: string | null = null;
    if (uid) {
      const { data: profile, error: profileError } = await supabase
        .from("profiles")
        .select("access_status, role")
        .eq("id", uid)
        .maybeSingle();
      rowStatus = (profile as { access_status?: string; role?: string } | null)
        ? `${(profile as { access_status?: string }).access_status ?? "?"} / ${(profile as { role?: string }).role ?? "?"}`
        : null;
      if (profileError) rowError = profileError.message;
    }

    if (approvalError) {
      failure = {
        reason:
          `The approval check itself failed: ${approvalError.message}. ` +
          "That usually means migration 18 has not been applied to this database.",
      };
      return { snapshots, failure };
    }

    if (approved === false) {
      const seen = rowStatus
        ? `Your profile row says ${rowStatus}.`
        : rowError
          ? `Your profile row could not be read: ${rowError}.`
          : "No profile row was found for your account.";

      failure = {
        reason:
          `The database's approval check returned false for user ${uid ?? "(none)"}. ${seen} ` +
          (rowStatus?.startsWith("APPROVED")
            // The two disagree. Not a data problem -- the check itself is
            // wrong, and telling the reader to approve an already-approved
            // account would send them round the loop again.
            ? "These disagree, so the check is at fault rather than your account. " +
              "is_approved() is SECURITY DEFINER and calls auth.uid(); if its search_path " +
              "does not include the auth schema, that call cannot resolve for the caller."
            : "Fix in the Supabase SQL editor: update profiles set access_status = 'APPROVED', " +
              "role = 'admin' where id = (select id from auth.users where email = 'your@email');"),
      };
      return { snapshots, failure };
    }

    // The asset list is read before any candle is. If THAT query fails,
    // every asset comes back null having never looked at a candle, and
    // blaming the candles table would send the reader to the wrong place.
    const { error: assetsError } = await supabase.from("assets").select("id").limit(1);
    if (assetsError) {
      failure = { reason: `The assets table could not be read: ${assetsError.message}` };
      return { snapshots, failure };
    }

    const { error: candlesError } = await supabase.from("candles").select("id").limit(1);
    if (candlesError) failure = { reason: candlesError.message };
  } catch (err) {
    failure = { reason: err instanceof Error ? err.message : "Could not reach the database." };
  }
  return { snapshots, failure };
}

export async function getAssetPriceSnapshots(): Promise<
  Record<AssetSymbol, AssetPriceSnapshot | null>
> {
  // Built from ASSET_LIST rather than written out, so adding an asset can
  // never silently leave a key missing here.
  const result = Object.fromEntries(
    ASSET_LIST.map((asset) => [asset, null])
  ) as Record<AssetSymbol, AssetPriceSnapshot | null>;

  try {
    const supabase = await createClient();
    const now = new Date();

    // One round trip, not eleven. This used to be an assets query plus two
    // candle queries per asset, each a separate hop from Vercel to
    // Supabase -- which is where the page's seconds were going.
    const { data, error } = await supabase.rpc("dashboard_prices");
    if (error || !data) return result;

    for (const row of data as Array<{
      symbol: string;
      latest_close: string | number | null;
      latest_time: string | null;
      oldest_close: string | number | null;
    }>) {
      const symbol = row.symbol as MarketAssetSymbol;
      if (!ASSET_LIST.includes(symbol) || row.latest_close === null || !row.latest_time) continue;

      const price = Number(row.latest_close);
      const baseline = row.oldest_close === null ? price : Number(row.oldest_close);
      const lastCandleTime = new Date(row.latest_time);

      result[symbol] = {
        asset: symbol,
        price,
        change24hPct: baseline !== 0 ? ((price - baseline) / baseline) * 100 : 0,
        dataStatus: classifyDataStatus(lastCandleTime, now),
        lastUpdated: lastCandleTime.toISOString(),
      };
    }
  } catch {
    // Leave everything null -- see docstring above.
  }

  return result;
}


/**
 * Same as getAssetPriceSnapshots() but for a single asset -- used by
 * per-market detail pages so they don't fetch all three assets' candles
 * just to show one. Returns null under the same conditions (no data yet,
 * Supabase not configured, any failure) -- never throws, never fakes.
 */
export async function getAssetPriceSnapshot(
  asset: AssetSymbol
): Promise<AssetPriceSnapshot | null> {
  try {
    const supabase = await createClient();
    const now = new Date();

    const { data: assetRow, error: assetError } = await supabase
      .from("assets")
      .select("id, symbol")
      .eq("symbol", asset)
      .maybeSingle();

    if (assetError || !assetRow) return null;

    return await fetchSnapshotForAssetId(
      supabase,
      (assetRow as { id: string }).id,
      asset,
      now
    );
  } catch {
    return null;
  }
}

import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

/**
 * Proxies an on-demand evaluation to the Python engine.
 *
 * Server-side rather than a direct browser call, for three reasons: the
 * engine's address stays out of the bundle, there is no CORS to configure,
 * and the caller can be checked against the session before anything runs.
 *
 * The engine usually runs on the operator's own machine and is not
 * reachable from the public internet. That is a normal state, not a fault,
 * so an unreachable engine returns a plain explanation rather than a 500 --
 * "the engine is not reachable from here" and "the engine crashed" need
 * different responses from whoever reads it.
 *
 * And a third state, which the first message used to be wrong about: this
 * route running in a DEPLOYED site with no ENGINE_API_URL set. The default
 * address is 127.0.0.1, which on Vercel means Vercel's own container --
 * never the operator's PC. Telling that reader to "start the collector"
 * sends them to restart something that is already running and cannot help,
 * which is the same wrong diagnosis this project has paid for repeatedly.
 * Starting the engine only fixes this when the site is running on the same
 * machine as the engine.
 */

export const dynamic = "force-dynamic";

const ENGINE_URL = process.env.ENGINE_API_URL ?? "http://127.0.0.1:8000";
const TIMEOUT_MS = 25_000;

/** Deployed, with no address configured: the loopback default can only ever
 *  reach this server, so no local engine is reachable however healthy it is. */
function unreachableBecauseDeployed(): boolean {
  return !process.env.ENGINE_API_URL && Boolean(process.env.VERCEL);
}

export async function POST(request: Request) {
  // Signed in, or nothing runs. This endpoint causes real provider
  // requests against a metered quota, so it is not anonymous.
  let userId: string | null = null;
  try {
    const supabase = await createClient();
    const { data } = await supabase.auth.getUser();
    userId = data.user?.id ?? null;
  } catch {
    userId = null;
  }
  if (!userId) {
    return NextResponse.json({ error: "Sign in to run an evaluation." }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const symbol = (searchParams.get("symbol") ?? "").toUpperCase();
  if (!/^[A-Z0-9_]{3,20}$/.test(symbol)) {
    return NextResponse.json({ error: "A valid symbol is required." }, { status: 400 });
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${ENGINE_URL}/api/signals/evaluate?symbol=${encodeURIComponent(symbol)}`,
      { method: "POST", signal: controller.signal, cache: "no-store" }
    );
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      return NextResponse.json(
        { error: body?.detail ?? `The engine refused the request (${response.status}).` },
        { status: 502 }
      );
    }
    return NextResponse.json(body);
  } catch (e) {
    const aborted = e instanceof Error && e.name === "AbortError";
    return NextResponse.json(
      {
        error: aborted
          ? "The engine did not answer within 25 seconds. It may be fetching candles — try again shortly."
          : unreachableBecauseDeployed()
            ? "This is the deployed site, and the engine runs on your own machine — the two cannot reach each other. Nothing is broken and starting the collector will not change it. The scheduler keeps analysing every cycle and those results appear below; on-demand analysis needs the engine reachable over the network (set ENGINE_API_URL), or run the site locally."
            : "The engine is not reachable from here. It runs alongside the collector on this machine; start it, or set ENGINE_API_URL if it runs elsewhere.",
      },
      { status: 503 }
    );
  } finally {
    clearTimeout(timer);
  }
}

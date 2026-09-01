"""
Where is the signal pipeline stuck?

Run this any time signals are not appearing. It walks the pipeline in order
and stops at the FIRST broken stage, because a later stage failing is usually
just an echo of an earlier one -- reporting all of them at once is how you end
up fixing the wrong thing.

    .venv\\Scripts\\python.exe diagnose.py         (Windows)
    .venv/bin/python diagnose.py                  (macOS / Linux)

Read-only. It writes nothing, changes nothing, and never prints a secret --
credentials are reported as present/absent only.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

OK, WARN, BAD, INFO = "  OK ", " WARN", " STOP", "     "


def line(tag: str, text: str) -> None:
    print(f"[{tag}] {text}")


def head(title: str) -> None:
    print(f"\n{title}\n" + "-" * len(title))


def halt(reason: str, fix: str) -> None:
    print()
    print("=" * 68)
    print(f"PIPELINE STOPS HERE: {reason}")
    print("=" * 68)
    print(f"\nWhat to do:\n{fix}\n")
    sys.exit(1)


def age(ts: datetime, now: datetime) -> str:
    secs = int((now - ts).total_seconds())
    if secs < 90:
        return f"{secs}s ago"
    if secs < 5400:
        return f"{secs // 60}m ago"
    return f"{secs // 3600}h {(secs % 3600) // 60}m ago"


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ---------------------------------------------------------------- 1. config
head("1. Configuration")
try:
    from app.config import get_settings
except Exception as exc:  # noqa: BLE001
    halt(
        f"the app will not import: {exc}",
        "Dependencies are probably not installed. From apps/api:\n"
        "    py -3 -m venv .venv\n"
        "    .venv\\Scripts\\python.exe -m pip install -r requirements.txt",
    )

settings = get_settings()
line(OK if settings.has_supabase else BAD, f"Supabase credentials: {'set' if settings.has_supabase else 'MISSING'}")
line(
    OK if settings.has_real_provider else WARN,
    f"Twelve Data key: {'set' if settings.has_real_provider else 'NOT set — running the DEMO provider'}",
)
line(INFO, f"Poll interval: {settings.poll_interval_seconds}s   Bars per poll: {settings.poll_outputsize}")

if not settings.has_supabase:
    halt(
        "no database credentials",
        "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in apps/api/.env",
    )

if not settings.has_real_provider:
    halt(
        "no market-data key, so the demo provider is active",
        "The demo provider stores placeholder candles and the engine deliberately\n"
        "SKIPS signal generation for them — placeholder prices are not market prices.\n"
        "Set TWELVE_DATA_API_KEY in apps/api/.env, then restart the API.",
    )

# ------------------------------------------------------------ 2. connection
head("2. Database connection")
try:
    from app.storage.supabase_client import get_service_client

    client = get_service_client()
    assets = client.table("assets").select("id, symbol, is_active, market_type").execute().data or []
    line(OK, f"connected — {len(assets)} instruments registered")
except Exception as exc:  # noqa: BLE001
    halt(f"cannot reach the database: {exc}", "Check SUPABASE_URL and that the project is running.")

by_id = {a["id"]: a["symbol"] for a in assets}
active = [a for a in assets if a.get("is_active")]
line(INFO, f"active: {', '.join(sorted(a['symbol'] for a in active)) or 'none'}")
inactive = [a["symbol"] for a in assets if not a.get("is_active")]
if inactive:
    line(INFO, f"inactive (will not be polled): {', '.join(sorted(inactive))}")

# ------------------------------------------------------------- 3. migrations
head("3. Schema / migrations")

# Each probe is a cheap read that only succeeds once its migration has run.
# Probing per-migration rather than per-column matters: migrations can be
# applied OUT OF ORDER, and then "some columns exist" tells you nothing about
# which file still needs running.
def has_column(table: str, column: str) -> bool:
    try:
        client.table(table).select(column).limit(1).execute()
        return True
    except Exception:  # noqa: BLE001
        return False


def has_function(name: str) -> bool:
    try:
        client.rpc(name, {}).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        # A permission or argument error still proves the function exists;
        # only "does not exist" means the migration has not run.
        return "does not exist" not in str(exc).lower()


PROBES = [
    ("20260830000011_seed_crypto_assets",
     lambda: any(a["symbol"] == "BTCUSD" for a in assets)),
    ("20260830000012_notification_prefs_crypto",
     lambda: has_column("notification_preferences", "btcusd_enabled")),
    ("20260830000013_admin_list_users",
     lambda: has_function("admin_list_users")),
    ("20260830000014_dedup_and_shadow_resolution",
     lambda: has_column("signals", "last_evaluated_at") and has_column("signals", "shadow_result")),
    ("20260830000015_strategy_configs",
     lambda: has_column("strategy_configs", "min_technical_score")),
    ("20260830000016_otc_instruments_and_provenance",
     lambda: has_column("signals", "data_source") and has_column("assets", "market_type")),
    ("20260830000017_expiry_seconds",
     lambda: has_column("strategy_configs", "expiry_seconds")),
]

pending: list[str] = []
for name, probe in PROBES:
    try:
        applied = probe()
    except Exception:  # noqa: BLE001
        applied = False
    line(OK if applied else BAD, f"{name}  {'applied' if applied else 'NOT APPLIED'}")
    if not applied:
        pending.append(name)

# 10 adds a constraint, which PostgREST cannot see. Named as unverifiable
# rather than assumed either way -- it is safe to re-run regardless.
line(INFO, "20260830000010_economic_events_unique  (constraint — cannot verify from here; safe to re-run)")

if pending:
    numbered = "\n".join(f"    {i}. {name}.sql" for i, name in enumerate(pending, 1))
    halt(
        f"{len(pending)} migration(s) not applied",
        "Every signal write fails on a missing column, which looks exactly like\n"
        "'no signals'. Run these files from supabase/migrations/, IN THIS ORDER,\n"
        "in the Supabase SQL editor:\n\n"
        f"{numbered}\n\n"
        "Run each file as a SEPARATE query — paste one, run it, then the next.\n"
        "(A migration already applied is safe to re-run; they are written to be\n"
        "idempotent. Order still matters: later files depend on earlier tables.)\n\n"
        "Then restart the API.",
    )

# ---------------------------------------------------------------- 4. candles
head("4. Candles (is the collector actually running?)")
now = datetime.now(timezone.utc)
WARMUP = 250
newest_overall: datetime | None = None
ready: list[str] = []
warming: list[str] = []

for asset in sorted(active, key=lambda a: a["symbol"]):
    for tf in ("M5", "M15", "H1", "H4"):
        rows = (
            client.table("candles")
            .select("open_time", count="exact")
            .eq("asset_id", asset["id"]).eq("timeframe", tf)
            .order("open_time", desc=True).limit(1).execute()
        )
        total = rows.count or 0
        newest = parse(rows.data[0]["open_time"]) if rows.data else None
        if newest and (newest_overall is None or newest > newest_overall):
            newest_overall = newest
        label = f"{asset['symbol']:<11} {tf:<4} {total:>6} bars"
        if total == 0:
            line(BAD, f"{label}   — none")
        elif total < WARMUP:
            warming.append(f"{asset['symbol']}/{tf}")
            line(WARN, f"{label}   newest {age(newest, now)}  (needs {WARMUP} to analyse)")
        else:
            ready.append(f"{asset['symbol']}/{tf}")
            line(OK, f"{label}   newest {age(newest, now)}")

if newest_overall is None:
    halt(
        "no candles at all",
        "The collector has never successfully stored data. Start it and leave it running:\n"
        "    .venv\\Scripts\\python.exe -m uvicorn app.main:app\n"
        "Then check http://127.0.0.1:8000/health",
    )

stale_minutes = (now - newest_overall).total_seconds() / 60
if stale_minutes > 20:
    line(BAD, f"newest candle anywhere is {age(newest_overall, now)}")
    halt(
        "candle data has stopped arriving",
        "The collector is not running, or its polls are failing. The engine refuses\n"
        "to analyse stale data on purpose, so no signals will be produced until this\n"
        "is fixed. Restart it and watch the console for errors:\n"
        "    .venv\\Scripts\\python.exe -m uvicorn app.main:app",
    )
line(OK, f"data is fresh — newest candle {age(newest_overall, now)}")

# ------------------------------------------------------------ 5. warm-up
head("5. History warm-up")
if warming:
    line(WARN, f"{len(warming)} timeframe(s) below {WARMUP} bars: {', '.join(warming[:8])}")
    line(INFO, "Until a timeframe has enough history the engine reports 'insufficient")
    line(INFO, "history' and returns NO_TRADE. That is correct behaviour, not a fault.")
    line(INFO, "M5 fills in ~21h of continuous running; H4 takes about 6 weeks.")
else:
    line(OK, f"every active timeframe has {WARMUP}+ bars")

# ------------------------------------------------------------- 6. decisions
head("6. Decisions")
sig = (
    client.table("signals")
    .select("generated_at, last_evaluated_at, direction, grade, status, technical_score, "
            "expiry_seconds, expiry_minutes, market_regime, asset_id, reasons, warnings, "
            "strategy_version, result")
    .order("generated_at", desc=True).limit(8).execute().data or []
)

if not sig:
    if warming:
        halt(
            "no decisions recorded yet, and history is still warming up",
            "This is the expected state early on. Leave the collector running and\n"
            "re-run this script in a few hours.",
        )
    halt(
        "candles are arriving but no decision has ever been recorded",
        "The analysis step is failing. Check the uvicorn console for a traceback,\n"
        "and section 7 below for recorded failures.",
    )

newest_decision = parse(sig[0]["last_evaluated_at"] or sig[0]["generated_at"])
line(OK, f"{len(sig)} recent decision(s); last evaluated {age(newest_decision, now)}")
if (now - newest_decision).total_seconds() > settings.poll_interval_seconds * 3:
    line(WARN, "the engine has not re-evaluated recently — is the collector still running?")

print()
for row in sig:
    symbol = by_id.get(row["asset_id"], "?")
    when = parse(row["generated_at"]).strftime("%m-%d %H:%M")
    horizon = row.get("expiry_seconds") or ((row.get("expiry_minutes") or 0) * 60)
    horizon_text = f"{horizon}s" if horizon and horizon < 60 else (f"{horizon // 60}m" if horizon else "—")
    verdict = row.get("result") or row["status"]
    print(f"  {when}  {symbol:<11} {row['direction']:<8} {row['grade']:<9} "
          f"score {row['technical_score']:<3} {horizon_text:<5} {row['market_regime']:<16} {verdict}")
    note = (row.get("warnings") or row.get("reasons") or [""])[0]
    if note:
        print(f"             why: {note[:96]}")

counts: dict[str, int] = {}
for row in client.table("signals").select("direction").limit(5000).execute().data or []:
    counts[row["direction"]] = counts.get(row["direction"], 0) + 1
print()
line(INFO, "all decisions so far: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"))
line(INFO, f"strategy version in use: {sig[0].get('strategy_version') or 'unstamped'}")

# --------------------------------------------------------------- 7. failures
head("7. Recorded failures (last 24h)")
since = (now - timedelta(days=1)).isoformat()
fails = (
    client.table("audit_logs")
    .select("created_at, action, target_id, metadata")
    .in_("action", ["analysis.failed", "market_data.failed"])
    .gte("created_at", since).order("created_at", desc=True).limit(10).execute().data or []
)
if not fails:
    line(OK, "none")
else:
    for f in fails:
        when = parse(f["created_at"]).strftime("%m-%d %H:%M")
        err = str((f.get("metadata") or {}).get("error", ""))[:90]
        line(BAD, f"{when}  {f['action']:<20} {f.get('target_id', '')}  {err}")

# ------------------------------------------------------------ 8. resolution
head("8. Resolution (are outcomes being scored?)")
resolved = client.table("signals").select("result", count="exact").not_.is_("result", "null").execute()
pending = (
    client.table("signals").select("expiry_at", count="exact")
    .eq("status", "ACTIVE").in_("direction", ["CALL", "PUT"])
    .lt("expiry_at", now.isoformat()).execute()
)
line(OK if (resolved.count or 0) else INFO, f"resolved outcomes: {resolved.count or 0}")
overdue = pending.count or 0
if overdue:
    line(WARN, f"{overdue} signal(s) past expiry but still unresolved — the resolution job may not be running")
else:
    line(OK, "nothing overdue")

# ----------------------------------------------------------------- verdict
print()
print("=" * 68)
if not ready:
    print("VERDICT: collecting data, not yet analysing. Warm-up in progress.")
elif counts.get("CALL", 0) + counts.get("PUT", 0) == 0:
    print("VERDICT: the engine is running and evaluating, but has not yet found a")
    print("         setup it considers tradeable. NO_TRADE is a real result — see")
    print("         the 'why' lines above for what it is rejecting.")
else:
    print("VERDICT: the pipeline is working end to end.")
print("=" * 68)

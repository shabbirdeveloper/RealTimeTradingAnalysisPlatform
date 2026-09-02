"""
A once-a-day "the collector is alive" message.

Rationale: this engine is designed to reject most opportunities, so a
quiet Telegram channel is the *expected* state, not a broken one. But
silence from a working system and silence from a dead one look identical
from the outside -- and the reasonable response to that ambiguity is to
lower the threshold until messages appear, which is exactly the wrong
move. This message makes the silence legible: how many decisions ran,
how close the best one came to the bar, and whether the data is fresh.

Deliberately reports only stored facts. It never estimates, never
projects, and refuses to print a win rate until enough trades have
resolved for one to mean anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Below this many resolved trades a win rate is noise. 20 is not a
# statistical threshold so much as a floor of decency: at n=10, one trade
# swings the number by ten points, and printing "60%" invites a decision
# nobody should be making on that evidence.
MIN_RESOLVED_FOR_RATE = 20


@dataclass(frozen=True)
class AssetLine:
    asset: str
    decisions: int = 0
    signals: int = 0
    best_score: int | None = None
    candle_age_minutes: float | None = None


@dataclass(frozen=True)
class HeartbeatSummary:
    window_hours: int
    generated_at: datetime
    decisions: int = 0
    signals: int = 0
    rejected: int = 0
    best_score: int | None = None
    best_asset: str | None = None
    threshold: int | None = None
    wins: int = 0
    losses: int = 0
    assets: list[AssetLine] = field(default_factory=list)
    note: str | None = None

    @property
    def resolved(self) -> int:
        return self.wins + self.losses


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _age_text(minutes: float | None) -> str:
    if minutes is None:
        return "no data"
    if minutes < 60:
        return f"{minutes:.0f}m ago"
    return f"{minutes / 60:.1f}h ago"


def format_heartbeat(summary: HeartbeatSummary) -> str:
    """Pure formatting, so it can be tested without a database."""
    stamp = summary.generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"<b>Daily report — {stamp}</b>",
        f"<i>Last {summary.window_hours}h</i>",
        "",
        f"Decisions    {summary.decisions}",
        f"Signals      {summary.signals}",
        f"Rejected     {summary.rejected}",
    ]

    if summary.best_score is not None:
        bar = f" (bar is {summary.threshold})" if summary.threshold is not None else ""
        who = f" on {_escape(summary.best_asset)}" if summary.best_asset else ""
        lines.append(f"Best score   {summary.best_score}{who}{bar}")

    if summary.assets:
        lines += ["", "<b>Per asset</b>"]
        for a in summary.assets:
            best = "—" if a.best_score is None else str(a.best_score)
            lines.append(
                f"• {_escape(a.asset)}  {a.decisions} decisions, "
                f"best {best}, data {_age_text(a.candle_age_minutes)}"
            )

    lines += ["", "<b>Resolved in window</b>"]
    if summary.resolved == 0:
        lines.append("Nothing resolved yet.")
    elif summary.resolved < MIN_RESOLVED_FOR_RATE:
        lines.append(
            f"{summary.wins}W / {summary.losses}L — too few to quote a rate."
        )
    else:
        rate = 100.0 * summary.wins / summary.resolved
        lines.append(f"{summary.wins}W / {summary.losses}L — {rate:.1f}%")
        # Break-even at a typical 80% binary payout. Printing a win rate
        # without it invites reading 53% as "winning".
        lines.append("<i>Break-even at an 80% payout is 55.6%.</i>")

    if summary.signals == 0:
        lines += [
            "",
            "<i>No signals is a normal result — the engine rejects setups "
            "that do not clear the bar. This message means it ran.</i>",
        ]

    if summary.note:
        lines += ["", f"<i>{_escape(summary.note)}</i>"]

    return "\n".join(lines)


def collect_summary(*, window_hours: int = 24, now: datetime | None = None) -> HeartbeatSummary:
    """Reads the last `window_hours` of stored decisions. Stored facts only."""
    from app.storage.candle_repository import _asset_id_map
    from app.storage.supabase_client import get_service_client

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = now - timedelta(hours=window_hours)
    client = get_service_client()

    id_to_asset = {v: k.value for k, v in _asset_id_map().items()}

    rows = (
        client.table("signals")
        .select("asset_id,direction,status,result,technical_score,generated_at")
        .gte("generated_at", since.isoformat())
        .execute()
        .data
        or []
    )

    per_asset: dict[str, dict] = {
        name: {"decisions": 0, "signals": 0, "best": None} for name in id_to_asset.values()
    }
    signals = rejected = wins = losses = 0
    best_score: int | None = None
    best_asset: str | None = None

    for row in rows:
        name = id_to_asset.get(row.get("asset_id"), "?")
        bucket = per_asset.setdefault(name, {"decisions": 0, "signals": 0, "best": None})
        bucket["decisions"] += 1

        status = row.get("status")
        if status == "REJECTED":
            rejected += 1
        elif row.get("direction") in ("CALL", "PUT"):
            signals += 1
            bucket["signals"] += 1

        if row.get("result") == "WON":
            wins += 1
        elif row.get("result") == "LOST":
            losses += 1

        score = row.get("technical_score")
        if score is not None:
            score = int(score)
            if bucket["best"] is None or score > bucket["best"]:
                bucket["best"] = score
            if best_score is None or score > best_score:
                best_score, best_asset = score, name

    # Data freshness, per asset, from the candles actually stored. A report
    # that says "0 signals" while the feed has been dead for six hours is
    # worse than no report -- it reads as a market judgement.
    ages: dict[str, float | None] = {}
    for asset, asset_id in _asset_id_map().items():
        newest = (
            client.table("candles")
            .select("open_time")
            .eq("asset_id", asset_id)
            .order("open_time", desc=True)
            .limit(1)
            .execute()
            .data
        )
        if newest:
            open_time = datetime.fromisoformat(newest[0]["open_time"].replace("Z", "+00:00"))
            ages[asset.value] = (now - open_time).total_seconds() / 60.0
        else:
            ages[asset.value] = None

    lines = [
        AssetLine(
            asset=name,
            decisions=data["decisions"],
            signals=data["signals"],
            best_score=data["best"],
            candle_age_minutes=ages.get(name),
        )
        for name, data in sorted(per_asset.items())
        if data["decisions"] or ages.get(name) is not None
    ]

    stale = [a.asset for a in lines if a.candle_age_minutes is None or a.candle_age_minutes > 90]
    note = None
    if stale:
        note = "Stale or missing data: " + ", ".join(stale) + ". Signals are paused for those."

    return HeartbeatSummary(
        window_hours=window_hours,
        generated_at=now,
        decisions=len(rows),
        signals=signals,
        rejected=rejected,
        best_score=best_score,
        best_asset=best_asset,
        threshold=_default_threshold(),
        wins=wins,
        losses=losses,
        assets=lines,
        note=note,
    )


def _default_threshold() -> int | None:
    try:
        from app.features.strategy import DEFAULT_MIN_TECHNICAL_SCORE

        return int(DEFAULT_MIN_TECHNICAL_SCORE)
    except Exception:  # noqa: BLE001 -- the report is worth sending without it
        return None


def send_heartbeat(*, window_hours: int = 24, now: datetime | None = None) -> bool:
    from app.notifications.telegram import build_notifier

    notifier = build_notifier()
    if not notifier.is_configured:
        logger.debug("heartbeat skipped -- Telegram not configured")
        return False
    summary = collect_summary(window_hours=window_hours, now=now)
    sent = notifier.send(format_heartbeat(summary))
    logger.info(
        "daily heartbeat %s (%d decisions, %d signals)",
        "sent" if sent else "FAILED",
        summary.decisions, summary.signals,
    )
    return sent


if __name__ == "__main__":  # pragma: no cover -- manual "send it now" path
    import argparse

    from app.logging_setup import configure

    parser = argparse.ArgumentParser(description="Send the daily report now.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="build and print the report without sending it",
    )
    args = parser.parse_args()

    configure()
    if args.print_only:
        print(format_heartbeat(collect_summary(window_hours=args.hours)))
    else:
        ok = send_heartbeat(window_hours=args.hours)
        print("sent" if ok else "NOT sent -- Telegram not configured, or delivery failed")

"""
Push a new signal to Telegram.

WHY TELEGRAM RATHER THAN BROWSER PUSH
-------------------------------------
This engine is built to stay quiet. It rejects most cycles by design, which
means a signal is rare -- and a rare signal you don't see is worth exactly
nothing. Until now a firing signal produced a database row and a log line,
so a setup at 03:00 was a setup you missed.

Browser notifications need a tab open on a machine you are at. Telegram
reaches a phone. For one trader watching a handful of instruments that is
the whole difference between a system that works and one that technically
functions.

WHAT IT WILL NOT DO
-------------------
* Alert on NO_TRADE. Most cycles are NO_TRADE; alerting on them trains you
  to ignore the channel, which costs you the one message that mattered.
* Alert on a re-confirmed signal. A setup lasting an hour is ONE
  opportunity, not six. Only a newly created row alerts.
* Alert on rejected opportunities. Those are analysis, not instructions.
* Block or break the poll cycle. A messaging failure must never cost a
  candle -- market data is the irreplaceable part, an alert is not.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.features.signal_engine import SignalDecision
from app.features.strategy import format_expiry

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"


@dataclass(frozen=True)
class TelegramNotifier:
    bot_token: str | None
    chat_id: str | None
    timeout_seconds: float = 10.0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, text: str) -> bool:
        """True if delivered. Never raises: see the module docstring on why a
        messaging failure must not be able to interrupt collection."""
        if not self.is_configured:
            return False

        # Imported here rather than at module scope so message formatting and
        # the configuration rules stay unit-testable without the HTTP stack
        # installed. Transport is the only part that needs it.
        import httpx

        try:
            response = httpx.post(
                f"{_API}/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            # str(exc) on an httpx error can carry the request URL, and the
            # bot token lives in that path. Log the type only.
            logger.warning("telegram send failed: %s", type(exc).__name__)
            return False

        if response.status_code != 200:
            # Body, not URL: Telegram's error bodies explain the problem
            # ("chat not found") and contain no token.
            logger.warning(
                "telegram rejected the message: HTTP %s %s",
                response.status_code, response.text[:200],
            )
            return False
        return True


def build_notifier() -> TelegramNotifier:
    # Settings pull pydantic in. Imported at call time so message formatting
    # and the configuration rules stay testable without the whole settings
    # stack -- the same reason httpx is deferred inside send().
    from app.config import get_settings

    settings = get_settings()
    return TelegramNotifier(
        bot_token=getattr(settings, "telegram_bot_token", None),
        chat_id=getattr(settings, "telegram_chat_id", None),
    )


def _escape(value: str) -> str:
    """Telegram HTML mode. Unescaped market text would break the message, and
    a broken message is a missed signal."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_signal(asset: str, decision: SignalDecision, *, is_otc: bool = False) -> str:
    arrow = "↑" if decision.direction == "CALL" else "↓"
    lines = [
        f"<b>{_escape(asset)} — {decision.direction} {arrow}</b>",
        "",
        f"Grade        {decision.grade}",
        f"Score        {decision.technical_score}/100",
        f"Expiry       {format_expiry(decision.expiry_seconds) if decision.expiry_seconds else '—'}",
        f"Entry        {decision.entry_price}",
        f"Regime       {_escape(decision.market_regime.replace('_', ' ').lower())}",
        f"Session      {_escape(decision.session.replace('_', ' ').title())}",
    ]

    if decision.reasons:
        lines += ["", "<b>Why</b>"]
        lines += [f"• {_escape(r)}" for r in decision.reasons[:4]]

    # The grade cap is not decoration. Until a calibrated model exists the
    # engine cannot express a confidence, and a message that quietly omitted
    # that would read as more certain than the system is.
    lines += [
        "",
        "<i>Technical score only — no calibrated ML confidence exists yet, "
        "so grades are capped at B. Place manually; this platform never trades "
        "for you.</i>",
    ]

    if not is_otc:
        lines += [
            "<i>Computed from real exchange prices. Do NOT place this on a "
            "broker's OTC pair — that is a different, broker-generated price "
            "series.</i>",
        ]
    return "\n".join(lines)


def notify_new_signal(asset: str, decision: SignalDecision, *, is_otc: bool = False) -> bool:
    notifier = build_notifier()
    if not notifier.is_configured:
        return False
    return notifier.send(format_signal(asset, decision, is_otc=is_otc))


def format_otc_signal(decision) -> str:
    """The 5-minute engine's own message.

    A separate formatter rather than an adapter onto SignalDecision,
    because the two engines carry different evidence and squeezing one
    into the other's shape would have meant inventing the fields it does
    not have -- a grade it cannot justify, a session it does not use.
    What this engine knows is the CALL/PUT pair and which strategy fired,
    so that is what the message says.
    """
    from app.otc.config import TIMEFRAME_SECONDS  # noqa: F401  (kept for symmetry)

    arrow = "↑" if decision.direction.value == "CALL" else "↓"
    minutes = decision.expiry_seconds // 60
    lines = [
        f"<b>{_escape(decision.symbol)} — {decision.direction.value} {arrow}</b>",
        "",
        f"Expiry       {minutes} min",
        f"Entry        {decision.price}",
        f"Score        {decision.score}/100",
        f"CALL / PUT   {decision.call_score} / {decision.put_score}",
        f"Regime       {_escape(decision.regime.replace('_', ' ').lower())}",
        f"Strategy     {_escape((decision.strategy or '—').replace('_', ' '))}",
    ]

    if decision.reasons:
        lines += ["", "<b>Why</b>"]
        lines += [f"• {_escape(r)}" for r in decision.reasons[:4]]

    if decision.warnings:
        lines += ["", "<b>Warnings</b>"]
        lines += [f"! {_escape(w)}" for w in decision.warnings[:3]]

    lines += [
        "",
        "<i>Technical score only — no calibrated ML confidence exists yet, so "
        "this is not a probability. Place manually; this platform never trades "
        "for you.</i>",
    ]

    # Which SERIES this was computed from, every time. A broker-generated
    # index and a real pair can carry similar names, and a message that did
    # not say which one it meant would eventually be placed on the wrong
    # instrument -- the exact confusion the provenance work exists to stop.
    if decision.broker == "MARKET":
        lines += [
            "<i>Computed from real exchange prices. Do NOT place this on a "
            "broker's OTC pair — that is a different, broker-generated series.</i>",
        ]
    else:
        lines += [
            f"<i>Computed from {_escape(decision.broker)}'s own generated series, "
            "not from any market. It is not interchangeable with a real pair or "
            "with another broker's instrument of a similar name.</i>",
        ]
    return "\n".join(lines)


def notify_otc_signal(decision) -> bool:
    """Send one 5-minute decision. Returns False when Telegram is not
    configured, which is a normal state and not an error."""
    notifier = build_notifier()
    if not notifier.is_configured:
        return False
    return notifier.send(format_otc_signal(decision))

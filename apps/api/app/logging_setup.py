"""
Logging that survives the process.

WHY
---
Logging went to the console only. The collector runs in a terminal window,
so closing that window destroyed both the process AND every record of what
it had been doing. It died twice with no evidence left behind, and the only
way to tell was noticing that decisions had stopped moving hours later.

A crash you cannot read is a crash you cannot fix.

SECRETS
-------
The Twelve Data API key travels as a URL query parameter, so any log line
carrying a request URL carries the key. Console logging got away with
suppressing httpx's INFO logger; a file on disk is a durable artifact that
may get attached to a bug report or a chat, so it also runs a redaction
filter over every record. Belt and braces on purpose: the suppression is
one library's log level away from failing open.
"""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

# Query parameters whose values must never reach disk. Matched on the
# parameter name so a rotated key, or a different provider's, is covered
# without anyone remembering to update a list of literal secrets.
_SECRET_PARAMS = ("apikey", "api_key", "token", "key", "password", "secret")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(" + "|".join(_SECRET_PARAMS) + r")=([^&\s\"']+)"
)


class RedactSecrets(logging.Filter):
    """Rewrites `apikey=abc123` to `apikey=***` in any formatted message."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 -- a broken record must not kill logging
            return True
        if "=" in message:
            redacted = _SECRET_PATTERN.sub(r"\1=***", message)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        return True


def configure(log_dir: Path | None = None, level: int = logging.INFO) -> Path | None:
    """Console + rotating file. Returns the log path, or None if a file
    could not be opened.

    A read-only or full disk must not stop the collector: losing the log is
    bad, losing the market data is worse. So a file failure degrades to
    console-only with a warning rather than raising.
    """
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    redactor = RedactSecrets()

    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
               for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.addFilter(redactor)
        root.addHandler(console)

    log_dir = log_dir or Path(__file__).resolve().parents[1] / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "collector.log"
        # 5 files x 2MB. Enough to cover a long weekend of polling at a
        # 10-minute interval, bounded so an unattended collector cannot
        # quietly fill the disk it depends on.
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(fmt)
        handler.addFilter(redactor)
        root.addHandler(handler)
    except OSError as exc:
        root.warning("could not open a log file (%s) — logging to console only", exc)
        return None

    # httpx logs each request URL at INFO, which is where the API key rides.
    # The redaction filter above covers it too; this keeps the noise down.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return path

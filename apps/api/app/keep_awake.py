"""
Ask Windows not to sleep while the collector is running.

WHY
---
The collector must run continuously: it accumulates candle history and
resolves signals when they reach expiry. A sleeping machine collects
nothing, and unlike a crash this leaves no error behind -- you find out
days later from a gap in the data.

The gaps are also not recoverable. Prices can be backfilled; the DECISIONS
the engine would have made in that window cannot, because a decision
depends on what was knowable at that moment. Every sleep permanently
removes evidence from the accuracy measurement this project exists to
produce.

HOW
---
SetThreadExecutionState is the documented Windows API for exactly this --
what a media player uses so a film doesn't pause halfway. ES_SYSTEM_REQUIRED
keeps the machine awake; ES_DISPLAY_REQUIRED is deliberately NOT set, so the
screen still turns off normally. Keeping a monitor lit all night to collect
candles would be a poor trade.

WHAT IT CANNOT DO
-----------------
* Closing a laptop lid still sleeps the machine on most power profiles.
* Hibernate, and a user choosing Sleep from the Start menu, still win.
* It does nothing on macOS or Linux, where it is a silent no-op.

So this narrows the gap rather than closing it. The honest fix for
continuous operation is a machine that does not sleep at all.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

# winbase.h
ES_CONTINUOUS = 0x80000000        # the state persists until cleared
ES_SYSTEM_REQUIRED = 0x00000001   # do not sleep the machine
# ES_DISPLAY_REQUIRED is intentionally unused -- see the docstring.

_active = False


def prevent_sleep() -> bool:
    """True if Windows accepted the request. False on any other platform, or
    if the call failed -- collection is far more important than this, so a
    failure is logged and stepped over, never raised."""
    global _active
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        result = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not request sleep prevention: %s", type(exc).__name__)
        return False

    if result == 0:
        logger.warning("Windows declined the sleep-prevention request")
        return False

    _active = True
    return True


def allow_sleep() -> None:
    """Hand normal power management back. Called on shutdown so stopping the
    collector does not leave the machine permanently awake -- a background
    process that quietly disables sleep forever is a bad neighbour."""
    global _active
    if not _active or not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except Exception:  # noqa: BLE001
        pass
    _active = False


def is_active() -> bool:
    return _active

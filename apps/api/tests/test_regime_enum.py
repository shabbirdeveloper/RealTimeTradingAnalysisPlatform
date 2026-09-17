"""
Every regime the engine can return must exist in the database enum.

WHY THIS TEST EXISTS
--------------------
It did not, and four regimes were missing for weeks. BREAKOUT, PULLBACK,
CHOPPY and UNKNOWN were absent from market_regime_type, so every decision
classified into one of them failed to insert:

    invalid input value for enum market_regime_type: "CHOPPY"

The collector logged a WARNING and carried on. Nothing looked broken --
the engine kept scoring, the log kept printing decisions -- and the rows
simply never arrived. DERIV_V75 evaluated every minute for days and
appeared nowhere on the dashboard.

Worse than the loss: CHOPPY and UNKNOWN are the two NO_TRADE regimes, so
what went missing was disproportionately REJECTIONS -- the records spec
section 30 calls "extremely important" for asking later whether the
filters helped or hurt.

This reads the migrations rather than the live database on purpose. A
test needing credentials would be skipped in exactly the situation where
it matters, and the migration is what any new environment gets anyway.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def enum_members(type_name: str) -> set[str]:
    """Every value the migrations ever add to one enum: the CREATE TYPE
    body plus every later ADD VALUE."""
    members: set[str] = set()
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")

        created = re.search(
            rf"create type {type_name} as enum\s*\((.*?)\)", sql, re.S | re.I
        )
        if created:
            members |= set(re.findall(r"'([^']+)'", created.group(1)))

        for added in re.finditer(
            rf"alter type {type_name} add value(?: if not exists)? '([^']+)'", sql, re.I
        ):
            members.add(added.group(1))
    return members


class RegimeEnumTests(unittest.TestCase):
    def test_migrations_exist(self):
        self.assertTrue(MIGRATIONS.is_dir(), f"no migrations directory at {MIGRATIONS}")

    def test_every_engine_regime_is_storable(self):
        from app.otc import regime

        engine_regimes = {
            value
            for name, value in vars(regime).items()
            if name.isupper() and isinstance(value, str) and name == value
        }
        self.assertGreaterEqual(len(engine_regimes), 9, "regime constants not found")

        stored = enum_members("market_regime_type")
        missing = sorted(engine_regimes - stored)
        self.assertEqual(
            missing, [],
            f"market_regime_type cannot store {missing}. A decision in one of "
            "these regimes fails to insert, logs a warning, and vanishes -- add "
            "them in a migration.",
        )

    def test_no_trade_regimes_are_storable(self):
        """The ones that must never be lost: a rejected setup is the record
        that later says whether the filter was worth having."""
        from app.otc.regime import NO_TRADE_REGIMES

        stored = enum_members("market_regime_type")
        self.assertEqual(sorted(set(NO_TRADE_REGIMES) - stored), [])


if __name__ == "__main__":
    unittest.main()

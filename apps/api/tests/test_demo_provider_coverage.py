"""
Guards a real outage path rather than the demo prices themselves.

When the crypto pairs were added, the demo provider's _BASE_PRICE map was
extended and _STEP_PCT was not. `_STEP_PCT[asset]` then raised KeyError --
not a MarketDataError, so it escaped run_poll_cycle's handler, aborted
run_all_assets mid-loop, and took signal resolution down with it. Anyone
running without an API key stopped resolving signals entirely, and it
presented as "no results yet" rather than as an error.

The module is parsed rather than imported because pydantic (via
schemas.candle) is not installed in every environment this suite runs in,
and a coverage check should not require the whole storage stack.
"""
import ast
import pathlib
import unittest

_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "app" / "market_data" / "demo_provider.py"


def _dict_keys(tree: ast.Module, name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
            return [ast.unparse(k) for k in node.value.keys]
    raise AssertionError(f"{name} not found in {_SOURCE.name}")


class EveryAssetIsCoveredByEveryMap(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))

    def test_step_pct_covers_every_base_price_asset(self):
        base = _dict_keys(self.tree, "_BASE_PRICE")
        step = _dict_keys(self.tree, "_STEP_PCT")
        self.assertEqual(
            [a for a in base if a not in step],
            [],
            "an asset with a base price but no volatility step raises KeyError at poll time",
        )

    def test_the_asset_enum_is_fully_covered(self):
        """Catches the next addition to the enum, not just the last one."""
        enum_source = (_SOURCE.parents[1] / "schemas" / "candle.py").read_text(encoding="utf-8")
        enum_tree = ast.parse(enum_source)
        members: list[str] = []
        for node in ast.walk(enum_tree):
            if isinstance(node, ast.ClassDef) and node.name == "Asset":
                members = [
                    f"Asset.{stmt.targets[0].id}"
                    for stmt in node.body
                    if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name)
                ]
        self.assertTrue(members, "could not read the Asset enum")

        for map_name in ("_BASE_PRICE", "_STEP_PCT"):
            missing = [m for m in members if m not in _dict_keys(self.tree, map_name)]
            self.assertEqual(missing, [], f"{map_name} is missing {missing}")


if __name__ == "__main__":
    unittest.main()

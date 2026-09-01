"""
Which provider errors are worth retrying.

Grounded in a real incident: "Quota API is not available" arrived on all five
assets at 06:23 and again at 06:33, then cleared. That is Twelve Data's quota
SERVICE being down, not the account being out of credits -- but it came back
in a 200 body, and only 5xx responses were retried, so every asset silently
lost its cycle to something one retry would very likely have survived.

The distinction matters in both directions. Retrying genuine credit
exhaustion spends the very credits it is complaining about.
"""
import ast
import pathlib
import unittest

_SOURCE = pathlib.Path(__file__).resolve().parents[1] / "app" / "market_data" / "twelve_data_provider.py"


def _load_classifier():
    """Loaded from source: the module imports httpx, which is not installed
    everywhere this suite runs, and the classifier itself has no dependencies."""
    src = _SOURCE.read_text(encoding="utf-8")
    tail = src[src.index("_SERVICE_OUTAGE_PHRASES"):]
    namespace: dict = {}
    exec(compile(ast.parse(tail), str(_SOURCE), "exec"), namespace)
    return namespace["_is_service_outage"]


is_outage = _load_classifier()


class ProviderOutagesAreRetried(unittest.TestCase):
    def test_the_error_that_actually_happened(self):
        self.assertTrue(is_outage("Quota API is not available"))

    def test_other_service_outage_phrasings(self):
        for message in (
            "Service temporarily unavailable",
            "Internal error, please try again later",
            "Data API is not available right now",
        ):
            self.assertTrue(is_outage(message), message)


class QuotaComplaintsAreNotRetried(unittest.TestCase):
    """Retrying these spends the credits being complained about, and turns a
    throttle into an outage."""

    def test_credit_exhaustion_is_not_an_outage(self):
        for message in (
            "You have run out of API credits for the current minute",
            "You have reached the API calls limit for the day",
            "Upgrade your plan to increase the limit",
        ):
            self.assertFalse(is_outage(message), message)

    def test_a_quota_word_beats_an_outage_word(self):
        """'limit ... try again' contains both. The quota reading must win, or
        the narrow outage rule quietly swallows every throttle message."""
        self.assertFalse(is_outage("API credits limit reached, try again tomorrow"))


class PermanentErrorsAreNotRetried(unittest.TestCase):
    def test_configuration_and_symbol_errors_stay_permanent(self):
        for message in ("Invalid API key", "**symbol** not found", "", "HTTP 404"):
            self.assertFalse(is_outage(message), repr(message))

    def test_none_is_handled(self):
        self.assertFalse(is_outage(None))


if __name__ == "__main__":
    unittest.main()

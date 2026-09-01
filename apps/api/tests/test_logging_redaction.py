import logging
import unittest

from app.logging_setup import RedactSecrets


def redact(message: str, *args) -> str:
    """Run one record through the filter and return what would be written."""
    record = logging.LogRecord("t", logging.INFO, __file__, 1, message, args, None)
    RedactSecrets().filter(record)
    return record.getMessage()


class SecretsNeverReachDisk(unittest.TestCase):
    """The Twelve Data key travels as a URL query parameter, so any log line
    carrying a request URL carries the key. A console log scrolls away; a
    file is a durable artifact that gets attached to bug reports."""

    def test_api_key_in_a_url_is_redacted(self):
        out = redact("GET https://api.twelvedata.com/time_series?symbol=EUR/USD&apikey=SECRET123")
        self.assertNotIn("SECRET123", out)
        self.assertIn("apikey=***", out)

    def test_redaction_survives_lazy_formatting(self):
        """Logging formats args at emit time, so filtering the template alone
        would miss a secret that arrives as an argument."""
        out = redact("calling %s", "https://x/y?api_key=SECRET456&z=1")
        self.assertNotIn("SECRET456", out)

    def test_common_secret_parameter_names_are_covered(self):
        for name, value in (
            ("apikey", "AAA"), ("api_key", "BBB"), ("token", "CCC"),
            ("key", "DDD"), ("password", "EEE"), ("secret", "FFF"),
        ):
            out = redact(f"x?{name}={value}&next=1")
            self.assertNotIn(value, out, name)

    def test_matching_is_case_insensitive(self):
        self.assertNotIn("GGG", redact("x?APIKEY=GGG"))
        self.assertNotIn("HHH", redact("x?ApiKey=HHH"))

    def test_the_rest_of_the_line_survives(self):
        out = redact("GET https://api.twelvedata.com/time_series?symbol=EUR/USD&apikey=S&interval=5min")
        self.assertIn("symbol=EUR/USD", out)
        self.assertIn("interval=5min", out)

    def test_redaction_stops_at_the_value_boundary(self):
        """A greedy match would swallow the rest of the query string and hide
        the very context that makes a log line useful."""
        out = redact("a?apikey=SECRET&symbol=XAUUSD&interval=5min")
        self.assertIn("symbol=XAUUSD", out)
        self.assertIn("interval=5min", out)

    def test_ordinary_lines_are_untouched(self):
        for message in (
            "market data fetch failed for EURUSD",
            "signal generation paused — stale data",
            "score = 87",
        ):
            self.assertEqual(redact(message), message)

    def test_a_record_that_cannot_format_does_not_kill_logging(self):
        """A broken log call is a bug, but losing every subsequent log line to
        it would be a much worse one."""
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "%d", ("not-an-int",), None)
        self.assertTrue(RedactSecrets().filter(record))


if __name__ == "__main__":
    unittest.main()

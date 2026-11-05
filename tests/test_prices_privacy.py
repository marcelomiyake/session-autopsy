from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from session_autopsy.adapters.local import PrivateEvidenceStore, cache_directory, private_write
from session_autopsy.adapters.network import FixedRedirects, fetch_document
from session_autopsy.adapters.prices import OfficialPrices, dollars, parse_claude, parse_openai, validate_snapshot
from tests.test_accounting import catalog

CLAUDE = '''## Model pricing
| Model | Base input tokens | 5m cache writes | 1h cache writes | Cache hits | Output tokens |
| Claude Haiku 5.5 | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| Claude Haiku 5.5 (over 100,000 tokens) | $0.50 | $0.625 | $1 | $0.05 | $2.50 |
| Claude Sonnet 5.5 | $2 | $2.5 | $4 | $0.10 | $10 |
## Other
| Claude Opus 5.5 | $4 | $5 | $8 | $0.2 | $20 |
'''
OPENAI = '''### Standard pricing data
| Model | Short input | Short output | Short read | Short 30m | Short 12h | Long input | Long output | Long read | Long 30m | Long 12h |
| gpt-test | $1 | $10 | $0.1 | $1.25 | $2.5 | $2 | $15 | $0.2 | $2.5 | $5 |
### Fast pricing data
| gpt-test | $2 | $20 | $0.2 | $2.5 | $5 | - | - | - | - | - |
'''


class PricePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"XDG_CACHE_HOME": self.temp.name});self.env.start();self.addCleanup(self.env.stop)

    def test_markdown_tables(self):
        self.assertEqual(dollars("$1,000.25 / MTok"), "1000.25")
        self.assertIsNone(dollars("-"))
        self.assertEqual(len(parse_claude(CLAUDE)), 3)
        self.assertEqual(parse_claude(CLAUDE)[1]["context"], "long")
        self.assertEqual(len(parse_openai(OPENAI)), 3)
        self.assertEqual(parse_openai(OPENAI)[-1]["tier"], "fast")

    def test_snapshot_validation(self):
        for bad in ({}, {"schema_version": 1, "retrieved_at": "now", "rates": []}):
            with self.assertRaises(ValueError):validate_snapshot(bad)
        data = catalog();data["rates"][0]["input"] = "-1"
        with self.assertRaises(ValueError):validate_snapshot(data)
        self.assertEqual(validate_snapshot(catalog())["schema_version"], 1)

    def test_private_files(self):
        root = cache_directory()
        path = PrivateEvidenceStore().save("private")
        self.assertEqual(path.read_text(), "private")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        private_write(path, "replacement")
        self.assertEqual(path.read_text(), "replacement")

    def test_egress_denies_arbitrary_urls_and_redirects(self):
        with self.assertRaises(ValueError):fetch_document("https://example.com/private")
        with self.assertRaises(ValueError):FixedRedirects().redirect_request(None, None, 302, "", {}, "https://example.com")
        response = MagicMock();response.__enter__.return_value.read.return_value = b"public"
        opener = MagicMock();opener.open.return_value = response
        with patch("session_autopsy.adapters.network.build_opener", return_value=opener):
            self.assertEqual(fetch_document("openai-prices"), "public")
            request = opener.open.call_args.args[0]
            self.assertIsNone(request.data)
            self.assertFalse(request.has_header("Authorization"))
            response.__enter__.return_value.read.return_value = b"x" * 2_000_001
            with self.assertRaises(ValueError):fetch_document("openai-prices")

    def test_offline_refresh_and_last_good(self):
        path = Path(self.temp.name) / "custom.json";path.write_text(json.dumps(catalog()))
        self.assertEqual(OfficialPrices(path).load()["rates"], catalog()["rates"])
        prices = OfficialPrices()
        with patch("session_autopsy.adapters.prices.fetch_document", side_effect=AssertionError("network forbidden")):
            self.assertTrue(prices.load(offline=True)["rates"])
        with patch.object(prices, "refresh", return_value=catalog()):
            self.assertEqual(prices.load(refresh=True)["rates"], catalog()["rates"])
        with patch.object(prices, "refresh", side_effect=ValueError("layout")):
            self.assertTrue(prices.load(refresh=True)["rates"])
            self.assertTrue(prices.warnings)
        with patch("session_autopsy.adapters.prices.fetch_document", side_effect=[CLAUDE, OPENAI]):
            self.assertGreaterEqual(len(prices.refresh()["rates"]), 6)
        with patch("session_autopsy.adapters.prices.fetch_document", return_value="layout changed"):
            with self.assertRaises(ValueError):prices.refresh()

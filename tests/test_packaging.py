"""Plugin manifests for both hosts must agree with the package and skill layout."""
import json
from pathlib import Path
import subprocess
import sys
import struct
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/session-autopsy"


def manifest(path):
    return json.loads((ROOT / path).read_text())


class PackagingTests(unittest.TestCase):
    def test_plugin_manifests_match_project(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        claude, codex = manifest(".claude-plugin/plugin.json"), manifest(".codex-plugin/plugin.json")
        for plugin in (claude, codex):
            self.assertEqual((plugin["name"], plugin["version"], plugin["license"]),
                             (project["name"], project["version"], project["license"]))
        self.assertEqual((ROOT / codex["skills"]).resolve(), SKILL.parent)
        self.assertIn("name: session-autopsy\n", (SKILL / "SKILL.md").read_text())

    def test_icons_exist_and_meet_listing_limits(self):
        claude, codex = manifest(".claude-plugin/plugin.json"), manifest(".codex-plugin/plugin.json")
        icon = ROOT / claude["icon"]
        header = icon.read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", header[16:24])
        self.assertTrue(width == height and 512 <= width <= 2048)
        self.assertLess(icon.stat().st_size, 2_000_000)
        for key in ("composerIcon", "logo"):
            self.assertTrue((ROOT / codex["interface"][key]).is_file(), key)

    def test_marketplaces_list_this_plugin_from_repository_root(self):
        for path in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
            catalog = manifest(path)
            self.assertEqual(catalog["name"], "session-autopsy")
            self.assertEqual([(p["name"], p["source"]) for p in catalog["plugins"]], [("session-autopsy", "./")])

    def test_skill_launcher_runs_from_skill_directory(self):
        result = subprocess.run([sys.executable, str(SKILL / "scripts/autopsy.py"), "--help"],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local session accounting", result.stdout)

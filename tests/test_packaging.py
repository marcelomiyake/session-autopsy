"""Plugin manifests for both hosts must agree with the package and skill layout."""
import json
import re
from pathlib import Path
import subprocess
import sys
import struct
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/session-autopsy"
SKILL = PLUGIN / "skills/session-autopsy"
DEVELOPMENT_ONLY = {".github", "tests", "pyproject.toml", "uv.lock", "sonar-project.properties", "AGENTS.md"}
MARKDOWN_CODE = re.compile(r"^```.*?^```|`[^`\n]+`", re.MULTILINE | re.DOTALL)
BUNDLED_ASSET = re.compile(r"\.(?:png|jpe?g|gif|webp|svg|ttf|otf|woff2?)\b", re.IGNORECASE)


def manifest(path, root=PLUGIN):
    return json.loads((root / path).read_text())


class PackagingTests(unittest.TestCase):
    def test_plugin_manifests_match_project(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        claude, codex = manifest(".claude-plugin/plugin.json"), manifest(".codex-plugin/plugin.json")
        for plugin in (claude, codex):
            self.assertEqual((plugin["name"], plugin["version"], plugin["license"]),
                             (project["name"], project["version"], project["license"]))
        self.assertEqual((PLUGIN / codex["skills"]).resolve(), SKILL.parent)
        self.assertIn("name: session-autopsy\n", (SKILL / "SKILL.md").read_text())

    def test_icons_exist_and_meet_listing_limits(self):
        claude, codex = manifest(".claude-plugin/plugin.json"), manifest(".codex-plugin/plugin.json")
        icon = PLUGIN / claude["icon"]
        header = icon.read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", header[16:24])
        self.assertTrue(width == height and 512 <= width <= 2048)
        self.assertLess(icon.stat().st_size, 2_000_000)
        for key in ("composerIcon", "logo"):
            self.assertTrue((PLUGIN / codex["interface"][key]).is_file(), key)

    def test_marketplaces_list_this_plugin_from_its_folder(self):
        for path in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
            catalog = manifest(path, ROOT)
            self.assertEqual(catalog["name"], "session-autopsy")
            self.assertEqual([(p["name"], p["source"]) for p in catalog["plugins"]],
                             [("session-autopsy", "./plugins/session-autopsy")])

    def test_plugin_folder_ships_only_runtime_files(self):
        self.assertEqual(DEVELOPMENT_ONLY & {entry.name for entry in PLUGIN.iterdir()}, set())
        self.assertEqual((PLUGIN / "LICENSE").read_text(), (ROOT / "LICENSE").read_text())
        self.assertGreaterEqual(len((PLUGIN / "README.md").read_text().split()), 40)

    def test_plugin_docs_show_bundled_images_only_as_markdown_images(self):
        for path in PLUGIN.rglob("*.md"):
            for code in MARKDOWN_CODE.findall(path.read_text()):
                self.assertIsNone(BUNDLED_ASSET.search(code), str(path))

    def test_skill_launcher_runs_from_skill_directory(self):
        result = subprocess.run([sys.executable, str(SKILL / "scripts/autopsy.py"), "--help"],
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Local session accounting", result.stdout)

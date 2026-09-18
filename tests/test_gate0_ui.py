"""Gate 0 UI tests — JS syntax, allowlist sync, static sink audit, behavior harness.

Covers task items 7-10 (JS/browser). Browser flows run in node:vm with a
fake DOM (tests/ui_harness.cjs); no real browser needed for the gate signal.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_PATH = REPO_ROOT / "codebase"
if str(CODEBASE_PATH) not in sys.path:
    sys.path.insert(0, str(CODEBASE_PATH))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

UI_PATH = CODEBASE_PATH / "ui.html"
HARNESS_PATH = Path(__file__).resolve().parent / "ui_harness.cjs"
NODE = shutil.which("node")


def _script() -> str:
    html = UI_PATH.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    return scripts[-1]


class TestUISyntax(unittest.TestCase):
    @unittest.skipUnless(NODE, "node not available")
    def test_node_check_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            js = Path(tmp) / "ui_check.js"
            js.write_text(_script(), encoding="utf-8")
            proc = subprocess.run(
                [NODE, "--check", str(js)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[-2000:])


class TestAllowlistSync(unittest.TestCase):
    def test_js_allowlist_matches_backend(self):
        from codebase import app as appmod

        m = re.search(r"const PUBLISH_ALLOWLIST = new Set\((\[.*?\])\);", _script(), re.S)
        self.assertIsNotNone(m, "PUBLISH_ALLOWLIST not found in ui.html")
        js_set = set(json.loads(m.group(1)))
        self.assertEqual(js_set, set(appmod.ALLOWLIST_PUBLIC_PATHS))

    def test_no_fake_verified_sha(self):
        self.assertNotIn("verified-sha256", UI_PATH.read_text(encoding="utf-8"))


class TestStaticSinkAudit(unittest.TestCase):
    def test_no_dynamic_innerhtml_or_inline_handlers_in_script(self):
        script = _script()
        for i, line in enumerate(script.splitlines(), 1):
            s = line.strip()
            code = s.split("//", 1)[0]
            if ".innerHTML" in code:
                # Allowed: single static round description, and the copy
                # button's own static label save/restore.
                self.assertTrue(
                    "round-desc" in code or "btn.innerHTML" in code,
                    f"line {i}: unexpected innerHTML sink: {s[:160]}",
                )
            if "onclick" in code.lower():
                self.fail(f"line {i}: inline handler in script: {s[:160]}")


@unittest.skipUnless(NODE, "node not available")
class TestUIHarness(unittest.TestCase):
    def test_harness_scenarios_all_pass(self):
        proc = subprocess.run(
            [NODE, str(HARNESS_PATH), str(UI_PATH)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(proc.returncode, 0, msg=(proc.stderr or "")[-2000:])
        try:
            report = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.fail(f"harness produced no JSON: {(proc.stdout or '')[-2000:]}")
        self.assertNotIn("harness_error", report, msg=report.get("harness_error"))
        scenarios = report.get("scenarios", {})
        expected = {
            "init_no_errors",
            "xss_chat",
            "xss_prov",
            "xss_code",
            "xss_chips",
            "flows",
            "qa_ok",
            "api_error_no_fake_ai",
            "badge_honesty",
            "no_exec_sink",
            "no_console_errors",
        }
        self.assertTrue(
            expected <= set(scenarios),
            f"missing scenarios: {expected - set(scenarios)}",
        )
        failed = {k: v for k, v in scenarios.items() if not v.get("pass")}
        self.assertEqual(failed, {})


if __name__ == "__main__":
    unittest.main()

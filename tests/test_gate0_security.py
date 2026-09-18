"""Gate 0 security tests — publish allowlist, traversal/symlink denial, SHA binding.

Uses fake fixtures only (no real secrets, no real API keys, no live LLM calls).
Written BEFORE the fix (red-first); implementation lives in codebase/app.py.
"""

import hashlib
import http.client
import json
import os
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEBASE_PATH = REPO_ROOT / "codebase"
if str(CODEBASE_PATH) not in sys.path:
    sys.path.insert(0, str(CODEBASE_PATH))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from codebase import app as appmod  # noqa: E402


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Gate0FixtureMixin:
    """Builds a fake lab dir + manifest + chunks; monkeypatches app module globals."""

    ALLOW = {"docs/OK.md", "src/ok.py", "stale.md"}

    def _build_fixture(self, tmp: Path):
        lab = tmp / "lab"
        (lab / "docs").mkdir(parents=True)
        (lab / "src").mkdir(parents=True)
        (lab / "sub").mkdir(parents=True)

        ok_md = b"# public doc\nline2\n"
        ok_py = b"def hello():\n    return 1\n"
        (lab / "docs" / "OK.md").write_bytes(ok_md)
        (lab / "src" / "ok.py").write_bytes(ok_py)
        (lab / ".env").write_bytes(b"FAKE_KEY=not-real-fixture\n")
        (lab / ".env.example").write_bytes(b"FAKE_KEY=placeholder-fixture\n")
        (lab / "app.log").write_bytes(b"log line fixture\n")
        (lab / "answer_key.json").write_bytes(b'{"a": 1}')
        (lab / "secret.txt").write_bytes(b"fake secret fixture\n")
        (lab / "stale.md").write_bytes(b"version TWO fixture\n")
        (lab / "sub" / "inner.md").write_bytes(b"inner fixture\n")
        (tmp / "outside.txt").write_bytes(b"outside fixture\n")

        manifest = {
            "lab_id": "day03",
            "source_manifest_sha256": "fixture",
            "files": [
                {
                    "path": "docs/OK.md",
                    "sha256": _sha_bytes(ok_md),
                    "size_bytes": len(ok_md),
                    "total_lines": 2,
                    "source_kind": "instruction",
                    "symbols": [],
                    "symbols_count": 0,
                },
                {
                    "path": "src/ok.py",
                    "sha256": _sha_bytes(ok_py),
                    "size_bytes": len(ok_py),
                    "total_lines": 2,
                    "source_kind": "code",
                    "symbols": [
                        {"name": "hello", "kind": "function", "line": 1, "end_line": 2}
                    ],
                    "symbols_count": 1,
                },
                # Denied even though present in manifest with correct hash.
                {
                    "path": ".env",
                    "sha256": _sha_bytes(b"FAKE_KEY=not-real-fixture\n"),
                    "size_bytes": 1,
                    "total_lines": 1,
                    "source_kind": "reported",
                    "symbols": [],
                    "symbols_count": 0,
                },
                # Hash in manifest is for v1, file on disk is v2 -> must refuse.
                {
                    "path": "stale.md",
                    "sha256": _sha_bytes(b"version ONE fixture\n"),
                    "size_bytes": 1,
                    "total_lines": 1,
                    "source_kind": "reported",
                    "symbols": [],
                    "symbols_count": 0,
                },
            ],
            "skipped": [{"path": ".env", "reason": "credential_pattern_detected"}],
        }
        manifest_path = tmp / "source_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        chunks = [
            {
                "chunk_id": "docs/OK.md:1-2",
                "lab_id": "day03",
                "path": "docs/OK.md",
                "start_line": 1,
                "end_line": 2,
                "sha256": "c1",
                "file_sha256": _sha_bytes(ok_md),
                "text": "# public doc\nline2\n",
                "source_kind": "instruction",
            },
            {
                # Stale binding: file_sha256 does not match manifest -> filtered.
                "chunk_id": "stale.md:1-1",
                "lab_id": "day03",
                "path": "stale.md",
                "start_line": 1,
                "end_line": 1,
                "sha256": "c2",
                "file_sha256": "deadbeef",
                "text": "version TWO fixture\n",
                "source_kind": "reported",
            },
            {
                # Blocked path must never leak via chunks.
                "chunk_id": ".env:1-1",
                "lab_id": "day03",
                "path": ".env",
                "start_line": 1,
                "end_line": 1,
                "sha256": "c3",
                "file_sha256": _sha_bytes(b"FAKE_KEY=not-real-fixture\n"),
                "text": "FAKE_KEY=not-real-fixture\n",
                "source_kind": "reported",
            },
        ]
        chunks_path = tmp / "source_chunks.jsonl"
        chunks_path.write_text(
            "\n".join(json.dumps(c) for c in chunks), encoding="utf-8"
        )

        # Symlinks (may fail without privilege on Windows -> tests skip then).
        self.symlink_ok = True
        try:
            os.symlink(str(tmp / "outside.txt"), str(lab / "link_outside"))
            os.symlink(str(lab / ".env"), str(lab / "link_secret"))
        except (OSError, NotImplementedError):
            self.symlink_ok = False
        return lab, manifest_path, chunks_path

    def _patch_app(self, lab: Path, manifest_path: Path, chunks_path: Path):
        self._saved = {
            "PUBLIC_LAB_DIR": appmod.PUBLIC_LAB_DIR,
            "QA_MANIFEST_PATH": appmod.QA_MANIFEST_PATH,
            "QA_CHUNKS_PATH": appmod.QA_CHUNKS_PATH,
            "ALLOWLIST_PUBLIC_PATHS": appmod.ALLOWLIST_PUBLIC_PATHS,
        }
        appmod.PUBLIC_LAB_DIR = lab
        appmod.QA_MANIFEST_PATH = manifest_path
        appmod.QA_CHUNKS_PATH = chunks_path
        appmod.ALLOWLIST_PUBLIC_PATHS = frozenset(self.ALLOW)
        appmod._reset_publish_caches()

    def _unpatch_app(self):
        for k, v in self._saved.items():
            setattr(appmod, k, v)
        appmod._reset_publish_caches()


class TestPublishPolicyUnit(Gate0FixtureMixin, unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        lab, mp, cp = self._build_fixture(Path(self._tmp.name))
        self._patch_app(lab, mp, cp)

    def tearDown(self):
        self._unpatch_app()
        self._tmp.cleanup()

    def test_approved_public_file_resolves_and_hash_matches(self):
        target, content, reason = appmod.resolve_publishable_file("docs/OK.md")
        self.assertEqual(reason, "")
        self.assertIsNotNone(target)
        self.assertTrue(target.is_file())
        self.assertIn(b"public doc", content)

    def test_env_files_denied_even_when_in_manifest(self):
        for p in (".env", ".env.example", "app.log", "answer_key.json", "secret.txt"):
            with self.subTest(path=p):
                ok, _ = appmod.is_publishable(p)
                self.assertFalse(ok)
                target, _, _ = appmod.resolve_publishable_file(p)
                self.assertIsNone(target)

    def test_traversal_absolute_and_empty_rejected(self):
        for p in ("../outside.txt", "..", "/etc/passwd", "C:/Windows/x", "", "sub/../../docs/OK.md"):
            with self.subTest(path=p):
                self.assertIsNone(appmod.normalize_rel_path(p))

    def test_symlinks_rejected(self):
        if not self.symlink_ok:
            self.skipTest("symlink creation not permitted on this machine")
        for p in ("link_outside", "link_secret", "sub"):
            target, _, _ = appmod.resolve_publishable_file(p)
            # 'sub' is a dir (not a file) and not allowlisted either.
            self.assertIsNone(target)

    def test_stale_sha_refused(self):
        target, _, reason = appmod.resolve_publishable_file("stale.md")
        self.assertIsNone(target)
        self.assertIn("stale", reason)


class Gate0HTTPMixin(Gate0FixtureMixin):
    def _start_server(self):
        self._httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0), appmod.PrototypeWebHandler
        )
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def _stop_server(self):
        self._httpd.shutdown()
        self._thread.join(timeout=5)
        self._httpd.server_close()

    def _get(self, path, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        if host is None:
            conn.request("GET", path)
        else:
            conn.putrequest("GET", path, skip_host=True)
            conn.putheader("Host", host)
            conn.endheaders()
        resp = conn.getresponse()
        body = resp.read()
        headers = dict(resp.getheaders())
        conn.close()
        return resp.status, headers, body


class TestPublishPolicyHTTP(Gate0HTTPMixin, unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        lab, mp, cp = self._build_fixture(Path(self._tmp.name))
        self._patch_app(lab, mp, cp)
        self._start_server()

    def tearDown(self):
        self._stop_server()
        self._unpatch_app()
        self._tmp.cleanup()

    def test_public_file_readable_with_manifest_hash(self):
        from urllib.parse import quote

        status, headers, body = self._get("/api/file?path=" + quote("docs/OK.md"))
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        data = json.loads(body.decode("utf-8"))
        manifest = json.loads(appmod.QA_MANIFEST_PATH.read_text(encoding="utf-8"))
        expected = next(f for f in manifest["files"] if f["path"] == "docs/OK.md")
        self.assertEqual(data["sha256"], expected["sha256"])
        self.assertIn("public doc", data["content"])

    def test_secret_paths_return_generic_404_without_leak(self):
        from urllib.parse import quote

        for p in (".env", ".env.example", "app.log", "answer_key.json",
                  "secret.txt", "../outside.txt", "/etc/passwd"):
            with self.subTest(path=p):
                status, _, body = self._get("/api/file?path=" + quote(p))
                self.assertIn(status, (400, 403, 404))
                text = body.decode("utf-8", errors="ignore")
                self.assertNotIn(str(self._tmp.name), text)
                self.assertNotIn("Traceback", text)
                self.assertNotIn("FAKE_KEY", text)

    def test_symlink_paths_rejected_over_http(self):
        if not self.symlink_ok:
            self.skipTest("symlink creation not permitted on this machine")
        for p in ("link_outside", "link_secret"):
            with self.subTest(path=p):
                status, _, _ = self._get("/api/file?path=" + p)
                self.assertIn(status, (400, 403, 404))

    def test_stale_file_not_served_as_valid(self):
        status, _, _ = self._get("/api/file?path=stale.md")
        self.assertEqual(status, 409)

    def test_chunks_never_leaks_blocked_content(self):
        from urllib.parse import quote

        # Un-normalizable secret path -> 400, no content.
        status, _, body = self._get("/api/chunks?path=" + quote(".env"))
        self.assertEqual(status, 400)
        # Well-formed but blocked chunk selector -> 200 with empty list.
        status, _, body = self._get("/api/chunks?chunk_id=" + quote(".env:1-1"))
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        items = data if isinstance(data, list) else [data]
        self.assertEqual(items, [])
        self.assertNotIn("FAKE_KEY", body.decode("utf-8"))
        # Public chunk served, stale-bound chunk filtered out.
        status, _, body = self._get("/api/chunks?path=" + quote("docs/OK.md"))
        self.assertEqual(status, 200)
        self.assertIn("public doc", body.decode("utf-8"))
        status, _, body = self._get("/api/chunks?path=stale.md")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8")), [])
        # Bulk dump without selector is refused.
        status, _, _ = self._get("/api/chunks")
        self.assertEqual(status, 400)

    def test_manifest_lists_only_publishable_without_skipped_or_text(self):
        status, headers, body = self._get("/api/manifest")
        self.assertEqual(status, 200)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        data = json.loads(body.decode("utf-8"))
        paths = {f["path"] for f in data["files"]}
        self.assertTrue(paths <= self.ALLOW)
        self.assertIn("docs/OK.md", paths)
        self.assertNotIn("skipped", data)
        self.assertNotIn("FAKE_KEY", body.decode("utf-8"))

    def test_spoofed_host_rejected_on_api(self):
        status, _, _ = self._get("/api/manifest", host="evil.example")
        self.assertEqual(status, 403)

    def test_no_wildcard_cors_anywhere(self):
        for path in ("/", "/api/manifest", "/api/provider-status"):
            with self.subTest(path=path):
                _, headers, _ = self._get(path)
                self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_error_bodies_generic(self):
        status, _, body = self._get("/api/file")
        self.assertEqual(status, 400)
        self.assertNotIn("Traceback", body.decode("utf-8", errors="ignore"))


class TestServerBinding(unittest.TestCase):
    def test_run_web_binds_loopback_only(self):
        captured = {}

        class FakeServer:
            def __init__(self, addr, handler):
                captured["addr"] = addr

            def serve_forever(self):
                captured["served"] = True

            def server_close(self):
                pass

        with mock.patch.object(appmod, "ThreadingHTTPServer", FakeServer):
            appmod.run_web(port=8129)
        self.assertEqual(captured.get("addr", (None,))[0], "127.0.0.1")
        self.assertTrue(captured.get("served"))


class TestAgentTLS(unittest.TestCase):
    def test_no_unverified_context_and_default_tls_used(self):
        from codebase import agent as agentmod

        src = Path(agentmod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_create_unverified_context", src)

        client = agentmod.LLMClient(api_key="DUMMY-FIXTURE-KEY-NOT-REAL")
        captured = {}

        class FakeResp:
            def read(self):
                return json.dumps(
                    {"choices": [{"message": {"content": "hi"}}]}
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=30, **kwargs):
            captured["kwargs"] = kwargs
            return FakeResp()

        with mock.patch.object(
            agentmod.urllib.request, "urlopen", side_effect=fake_urlopen
        ):
            msg = client.chat_completion([{"role": "user", "content": "hi"}])
        self.assertEqual(msg.get("content"), "hi")
        # Default verification: no custom unverified context may be passed.
        self.assertNotIn("context", captured["kwargs"])


class TestNoShellInRoutes(unittest.TestCase):
    def test_app_routes_do_not_reference_shell_exec(self):
        src = Path(CODEBASE_PATH / "app.py").read_text(encoding="utf-8")
        for token in ("run_command", "subprocess", "os.system", "eval("):
            self.assertNotIn(token, src)


if __name__ == "__main__":
    unittest.main()

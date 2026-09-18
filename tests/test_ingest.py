import json
import tempfile
import unittest
from pathlib import Path

from labsim.ingest import scan_sources


class TestIngest(unittest.TestCase):
    def test_scan_is_scoped_and_skips_secrets(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src = tmp_path / "input"
            src.mkdir()
            (src / "README.md").write_text("# Lab\nTool call returns an observation.\n", encoding="utf-8")
            (src / ".env").write_text("API_KEY=DO_NOT_EXPORT", encoding="utf-8")
            out = tmp_path / "output"
            manifest = scan_sources(src, "day03", out)
            self.assertEqual(manifest["lab_id"], "day03")
            self.assertEqual(manifest["files"][0]["path"], "README.md")
            data = (out / "source_chunks.jsonl").read_text(encoding="utf-8")
            self.assertIn("observation", data)
            self.assertNotIn("DO_NOT_EXPORT", data)
            self.assertIn('"start_line": 1', data)

    def test_line_chunking_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            src = tmp_path / "input"
            src.mkdir()
            lines = [f"line {i}\n" for i in range(1, 101)]
            (src / "code.py").write_text("".join(lines), encoding="utf-8")
            out = tmp_path / "output"
            
            manifest = scan_sources(src, "day03", out, chunk_size=40, chunk_overlap=5)
            self.assertEqual(manifest["files"][0]["source_kind"], "code")
            
            chunks_text = (out / "source_chunks.jsonl").read_text(encoding="utf-8").strip().split("\n")
            chunks = [json.loads(c) for c in chunks_text]
            self.assertGreater(len(chunks), 1)
            self.assertEqual(chunks[0]["start_line"], 1)
            self.assertEqual(chunks[0]["end_line"], 40)
            self.assertEqual(chunks[1]["start_line"], 36)
            self.assertEqual(chunks[0]["source_kind"], "code")


def test_scan_is_scoped_and_skips_secrets(tmp_path: Path):
    src = tmp_path / "input"
    src.mkdir()
    (src / "README.md").write_text("# Lab\nTool call returns an observation.\n", encoding="utf-8")
    (src / ".env").write_text("API_KEY=DO_NOT_EXPORT", encoding="utf-8")
    out = tmp_path / "output"
    manifest = scan_sources(src, "day03", out)
    assert manifest["lab_id"] == "day03"
    assert manifest["files"][0]["path"] == "README.md"
    data = (out / "source_chunks.jsonl").read_text(encoding="utf-8")
    assert "observation" in data and "DO_NOT_EXPORT" not in data
    assert '"start_line": 1' in data


if __name__ == "__main__":
    unittest.main()

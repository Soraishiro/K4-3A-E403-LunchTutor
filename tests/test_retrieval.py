import json
import tempfile
import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from labsim.retrieval import (
    get_chunk_by_id,
    get_manifest_file_outline,
    load_chunk_index,
    search_sources,
)


class TestRetrieval(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)
        
        # Create dummy chunks
        self.chunks_file = self.tmp_path / "source_chunks.jsonl"
        chunks = [
            {
                "chunk_id": "docs/CODELAB.md:1-40",
                "lab_id": "day03",
                "path": "docs/CODELAB.md",
                "start_line": 1,
                "end_line": 40,
                "sha256": "hash1",
                "file_sha256": "fhash1",
                "text": "Task 1.1: Define tools and schemas for academic query.",
                "source_kind": "instruction"
            },
            {
                "chunk_id": "src/tools.py:1-40",
                "lab_id": "day03",
                "path": "src/tools.py",
                "start_line": 1,
                "end_line": 40,
                "sha256": "hash2",
                "file_sha256": "fhash2",
                "text": "def academic_query(student_id: str): return {'gpa': 3.8}",
                "source_kind": "code"
            },
            {
                "chunk_id": "src/mcp_server.py:1-40",
                "lab_id": "day03",
                "path": "src/mcp_server.py",
                "start_line": 1,
                "end_line": 40,
                "sha256": "hash3",
                "file_sha256": "fhash3",
                "text": "class MCPAcademicServer: def call_tool(self, name, args): pass",
                "source_kind": "code"
            }
        ]
        with open(self.chunks_file, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")
                
        # Create dummy manifest
        self.manifest_file = self.tmp_path / "source_manifest.json"
        manifest = {
            "lab_id": "day03",
            "files": [
                {
                    "path": "src/tools.py",
                    "sha256": "fhash2",
                    "size_bytes": 120,
                    "total_lines": 40,
                    "source_kind": "code",
                    "symbols": [{"name": "academic_query", "kind": "function", "line": 1, "end_line": 5}]
                }
            ]
        }
        self.manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_search_sources_ranking(self):
        index = load_chunk_index(self.chunks_file)
        results = search_sources(index, "day03", "academic_query", top_k=2)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["path"], "src/tools.py")
        self.assertIn("gpa", results[0]["text"])

    def test_get_chunk_by_id(self):
        index = load_chunk_index(self.chunks_file)
        chunk = get_chunk_by_id(index, "src/mcp_server.py:1-40")
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk["path"], "src/mcp_server.py")
        self.assertIn("MCPAcademicServer", chunk["text"])

    def test_get_manifest_file_outline(self):
        outline = get_manifest_file_outline(self.manifest_file, "src/tools.py")
        self.assertIsNotNone(outline)
        self.assertEqual(len(outline["symbols"]), 1)
        self.assertEqual(outline["symbols"][0]["name"], "academic_query")


if __name__ == "__main__":
    unittest.main()

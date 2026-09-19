import json
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

try:
    from codebase.agent import LabSimAgent
    from codebase.tools import (
        ToolRegistry,
        get_chunk_by_id,
        get_manifest_file_outline,
        load_chunk_index,
        search_sources,
    )
except ImportError:
    from agent import LabSimAgent
    from tools import (
        ToolRegistry,
        get_chunk_by_id,
        get_manifest_file_outline,
        load_chunk_index,
        search_sources,
    )


class DummyLLMClient:
    def __init__(self):
        self.call_count = 0

    def chat_completion(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search_sources",
                            "arguments": json.dumps({"query": "academic_query", "top_k": 1})
                        }
                    }
                ]
            }
        else:
            return {
                "role": "assistant",
                "content": "Found academic_query in src/tools.py at lines 1-10.",
                "tool_calls": []
            }


class TestToolsAndAgent(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.chunks = [
            {
                "chunk_id": "src/tools.py:1-40",
                "lab_id": "day03",
                "path": "src/tools.py",
                "start_line": 1,
                "end_line": 40,
                "sha256": "h1",
                "file_sha256": "fh1",
                "text": "def academic_query(student_id: str): pass",
                "source_kind": "code"
            },
            {
                "chunk_id": "docs/CODELAB.md:1-40",
                "lab_id": "day03",
                "path": "docs/CODELAB.md",
                "start_line": 1,
                "end_line": 40,
                "sha256": "h2",
                "file_sha256": "fh2",
                "text": "Task 1.1: Setup academic tools and test queries.",
                "source_kind": "instruction"
            }
        ]
        self.manifest = {
            "lab_id": "day03",
            "files": [
                {
                    "path": "src/tools.py",
                    "sha256": "fh1",
                    "size_bytes": 100,
                    "total_lines": 40,
                    "source_kind": "code",
                    "symbols": [{"name": "academic_query", "kind": "function", "line": 1, "end_line": 5}],
                    "symbols_count": 1
                }
            ]
        }
        self.chunks_path = self.tmp_path / "source_chunks.jsonl"
        self.chunks_path.write_text("\n".join(json.dumps(c) for c in self.chunks), encoding="utf-8")
        self.manifest_path = self.tmp_path / "source_manifest.json"
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_search_sources_ranking(self):
        index = load_chunk_index(self.chunks_path)
        results = search_sources(index, "day03", "academic_query", top_k=2)
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["path"], "src/tools.py")

    def test_get_chunk_by_id(self):
        index = load_chunk_index(self.chunks_path)
        chunk = get_chunk_by_id(index, "docs/CODELAB.md:1-40")
        self.assertIsNotNone(chunk)
        self.assertEqual(chunk["path"], "docs/CODELAB.md")

    def test_get_manifest_file_outline(self):
        outline = get_manifest_file_outline(self.manifest_path, "src/tools.py")
        self.assertIsNotNone(outline)
        self.assertEqual(len(outline["symbols"]), 1)
        self.assertEqual(outline["symbols"][0]["name"], "academic_query")

    def test_tool_registry_execution(self):
        registry = ToolRegistry(self.tmp_path, "day03")
        res = registry.execute("search_sources", {"query": "academic_query"})
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["path"], "src/tools.py")

        outline = registry.execute("get_file_outline", {"path": "src/tools.py"})
        self.assertEqual(outline["total_lines"], 40)
        self.assertEqual(len(outline["symbols"]), 1)

    def test_agent_react_loop(self):
        registry = ToolRegistry(self.tmp_path, "day03")
        dummy_llm = DummyLLMClient()
        log_file = self.tmp_path / "traces.jsonl"
        agent = LabSimAgent(registry, dummy_llm, trace_log_path=log_file)

        result = agent.run("Where is academic_query defined?")
        self.assertEqual(result["iterations"], 2)
        self.assertIn("Found academic_query", result["final_answer"])
        self.assertEqual(len(result["traces"]), 1)
        self.assertEqual(result["traces"][0]["tool"], "search_sources")
        self.assertTrue(log_file.exists())


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from labsim.agent import LabSimAgent, ToolRegistry


class DummyLLMClient:
    def __init__(self):
        self.call_count = 0

    def chat_completion(self, messages, tools=None):
        self.call_count += 1
        if self.call_count == 1:
            # First turn: call search_sources tool
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
            # Second turn: produce final grounded answer
            return {
                "role": "assistant",
                "content": "Found academic_query in src/tools.py at lines 1-10.",
                "tool_calls": []
            }


class TestAgent(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        # Create dummy artifacts
        chunks = [
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
            }
        ]
        manifest = {
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
        (self.tmp_path / "source_chunks.jsonl").write_text(
            "\n".join(json.dumps(c) for c in chunks), encoding="utf-8"
        )
        (self.tmp_path / "source_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

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

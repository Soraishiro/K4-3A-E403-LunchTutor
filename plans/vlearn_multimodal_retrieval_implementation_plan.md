# VLearn Multimodal Retrieval MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CPU-only local evidence retrieval for VLearn PDF slides and cleaned transcripts, with RAGFlow as ingestion/reference and fully independent, evaluable BM25 + multilingual-E5 retrieval.

**Architecture:** Keep original materials read-only; construct an immutable page/segment-level evidence snapshot. RAGFlow Docker gives a native ingestion/UI reference, while a compact Python retrieval lab indexes the same canonical snapshot with independent lexical and dense methods. Expose evidence, anchors and metrics through a small API/UI. No answer-generating LLM, VLM, video processing or graph required for acceptance.

**Tech Stack:** Windows x86-64 / Docker Desktop WSL2; RAGFlow pinned stable release + Ollama `bge-m3` for its **own** index; Python 3.13 **if using current RAGFlow SDK version** (inspect pinned SDK's `requires-python`); PyMuPDF, `bm25s`, `sentence-transformers`, `intfloat/multilingual-e5-small`, NumPy, FastAPI, Streamlit, pytest. Use a single package lock generated after resolving versions; do not assume RAGFlow image includes model weights.

**Spec:** [`vlearn_multimodal_retrieval_spec.md`](./vlearn_multimodal_retrieval_spec.md) (install both docs together at `docs/superpowers/specs/2026-09-16-vlearn-multimodal-retrieval-design.md` and `docs/superpowers/plans/2026-09-16-vlearn-multimodal-retrieval.md` inside the project repo).

## Global constraints

- Input materials are restricted to the hackathon; no raw files, chatlog, `.env`, gold annotations or derived artifacts in git or external model APIs. Use localhost inference only.
- On Windows, CPU ≥4 x86 cores, RAM ≥16 GB, free disk ≥50 GB before starting RAGFlow. Stop and report blocker otherwise; no silent plan change.
- Commit exact RAGFlow stable tag/image digest, SDK version, Ollama model digest and E5 revision in a run manifest after resolving them. Pin runtime dependencies with a lockfile. No `nightly` in final baseline.
- Gold from manually verified slide pages/transcript segments only; `tutor_reply`, `has_citation`, `rating` must not be treated as ground truth.
- `course_id + lecture_code` is the course key; `lecture_code` alone is not unique. Keep original `[Txx-NNN]` segment IDs and 1-based slide page anchors.
- Independent `bm25`, `e5_dense`, `rrf` all use one evidence snapshot. Native RAGFlow retrieval is a **different** labeled baseline and must not be passed off as independently controlled BM25 or E5.
- Raw text is untrusted; escape for UI, no prompt execution. VLM/video/equation-image semantic retrieval is out of scope.

## Repository layout (create only paths needed by an accepted task)

```text
docs/superpowers/specs/2026-09-16-vlearn-multimodal-retrieval-design.md
docs/superpowers/plans/2026-09-16-vlearn-multimodal-retrieval.md
README.md                         # local setup, commands and known coverage limitations
.gitignore                        # raw + derived restricted data, secrets, model caches
pyproject.toml, uv.lock            # locked Python environment
.env.example                      # names only, never real tokens
configs/retrieval.yaml            # baseline depths, weights, index/model identifiers
configs/it_glossary.yaml          # reviewed aliases; no automatic unverified translations
src/vlearn/evidence.py            # immutable record schema, hashing/manifest validation
src/vlearn/ingest.py              # transcript parser, PDF page extractor/renderer
src/vlearn/ragflow_adapter.py     # only module importing the RAGFlow SDK
src/vlearn/index.py               # BM25 + CPU E5 building/loading
src/vlearn/retrieve.py            # retrieval contracts, filtering, deterministic RRF
src/vlearn/evaluate.py            # gold validation, metrics, per-query artifacts
src/vlearn/api.py                 # small FastAPI wrapper (not a proxy for RAGFlow DB)
src/vlearn/ui.py                  # Streamlit source viewer
scripts/preflight.py
scripts/build_evidence.py
scripts/build_indexes.py
scripts/run_eval.py
tests/test_evidence.py
tests/test_ingest.py
tests/test_ragflow_adapter.py
tests/test_retrieve.py
tests/test_evaluate.py
tests/test_api.py
data/raw/                        # local restricted inputs; gitignored
data/derived/snapshots/<hash>/   # evidence.jsonl, assets/, manifest.json; gitignored
data/derived/indexes/<hash>/     # bm25s + E5 vectors/meta; gitignored
data/local_gold/                 # verified questions, gitignored
artifacts/runs/                  # rankings/metrics/manifests; gitignored
```

### Task 1: Preflight, data privacy and upstream version lock

**Files:** `scripts/preflight.py`, `.gitignore`, `.env.example`, `README.md`, `pyproject.toml`, `uv.lock`, `tests/test_evidence.py` (preflight-specific test can be `tests/test_preflight.py` if preferred). Do not modify upstream RAGFlow files.

**Interfaces:** `preflight() -> dict[str, object]`, raises `RuntimeError` explaining **which** minimum was missed; config values are read from `.env` only for local URLs/keys, never copied into manifests. `runtime_manifest() -> dict` includes pinned non-secret versions/digests.

- [ ] Confirm the repo exists and inspect current project layout (`git status --short`, `ls`, `find ... -maxdepth 2`); **adapt paths if an existing convention already exists** and record any deviation in the docs before implementation.
- [ ] Read [RAGFlow quickstart](https://github.com/infiniflow/ragflow/blob/main/docs/quickstart.mdx), [Docker configuration](https://github.com/infiniflow/ragflow/blob/main/docs/administrator/configurations/configurations.md), [local model instructions](https://github.com/infiniflow/ragflow/blob/main/docs/guides/models/deploy_local_llm.mdx), and [SDK package metadata](https://github.com/infiniflow/ragflow/blob/main/sdk/python/pyproject.toml). Resolve matching **stable** tag, image digest, SDK compatibility and Python requirements; record exact versions in README and lock file.
- [ ] Write a failing test: fake CPU=2/RAM=8 GiB/disk=20 GiB inputs cause explicit error; fake CPU=4/RAM=16 GiB/disk=50 GiB inputs pass. Test .gitignore patterns via `git check-ignore data/raw/example.pdf .env artifacts/runs/example.json`.
- [ ] Run `python -m pytest tests/test_preflight.py -q`; check expected failure before implementation.
- [ ] Implement a minimal preflight using `os.cpu_count()`, `psutil.virtual_memory().total`, `shutil.disk_usage()` and a Docker/WSL2 capability check, with a dependency-injected hardware probe for tests; print free disk in GiB and do not claim machine compliance without testing on the user's host. Add secret-safe `.env.example` containing `RAGFLOW_BASE_URL=http://127.0.0.1`, `RAGFLOW_API_KEY=`, `OLLAMA_BASE_URL=http://host.docker.internal:11434` as a **candidate endpoint**, not a verified address.
- [ ] Run tests and `git diff --check`. Commit only configuration/docs/tests; never commit copied data, model weights or actual credentials. **Deliverable:** reproducible preflight and pinned deployment recipe.

**Manual host check (Windows PowerShell):** `wsl --status`; `docker version`; `docker compose version`; inspect RAM and free disk; run `docker info`. If deploying Elastic-backed RAGFlow on WSL2, follow RF-02 `vm.max_map_count=262144` guidance for this Docker Desktop version; check with `wsl -d docker-desktop -u root -- sysctl vm.max_map_count` where supported. Stop if preflight fails.

### Task 2: Deterministic evidence snapshot, *independent of* RAGFlow

**Files:** `src/vlearn/evidence.py`, `src/vlearn/ingest.py`, `scripts/build_evidence.py`, `tests/test_evidence.py`, `tests/test_ingest.py`. **This task must succeed without Docker, Ollama, network or API keys.**

**Interfaces:**

```python
@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    source_id: str
    source_path: str
    source_type: str
    modality: str
    content: str
    title: str | None
    course_id: str | None
    lecture_code: str | None
    page_1based: int | None
    segment_ids: tuple[str, ...]
    start_ms: int | None
    end_ms: int | None
    asset_path: str | None
    content_sha256: str


def build_snapshot(raw_dir: Path, out_root: Path) -> Path: ...
def load_snapshot(snapshot_dir: Path) -> list[Evidence]: ...
```

- [ ] Write fixtures with a two-page synthetic PDF, transcript containing `**[T06-130]**` and `**[T06-131]**`, plus malformed/duplicate segment IDs. Expected: two page evidence records and two transcript records, deterministic page numbers 1/2 and exact segment anchors; duplicate segment IDs fail. Include a PDF page with image but no extractable text: it keeps an image asset and extraction status, without hallucinating a caption.
- [ ] Run `python -m pytest tests/test_evidence.py tests/test_ingest.py -q` and observe test failure before implementation.
- [ ] Implement transcript parsing by explicit `^\*\*\[(T\d{2}-\d{3})\]\*\*` multiline regex; capture text from segment marker until the next marker, preserve section heading as metadata, and exclude front matter from searchable segments. Error if duplicate IDs occur within a source. A markdown segment that embeds `[không nghe rõ]` retains it unchanged.
- [ ] Implement PDF page rendering/extraction using documented [PyMuPDF `Page.get_text/get_pixmap`](https://pymupdf.readthedocs.io/en/latest/page.html); set `dpi=120, alpha=False`; output `assets/<source-hash>/page-0001.png` and `page_1based=page.number+1`. If text extraction returns empty, create a valid evidence record with `content=""` and an extraction-status field in the **manifest**; index builder must skip empty text while preserving image/anchor. Do **not** invoke OCR silently. This local extractor is a separate deterministic fallback, *not* claimed as RAGFlow parser output.
- [ ] Normalize only Unicode NFKC and whitespace; avoid translating or altering `C++`, `RRF`, `Q/K/V`, LaTeX operators. Compute SHA-256 from source bytes and canonical locator/content; write sorted JSONL and manifest atomically via temporary directory + rename. Print the resulting snapshot directory and write its absolute path to gitignored `data/derived/current_snapshot.txt` for subsequent CLI commands. Validate relative paths remain under `data/raw` and derived assets under snapshot root.
- [ ] Rebuild from identical fixtures twice; assert equal JSONL bytes and source/evidence counts. Mutating one source byte changes its snapshot ID. Check `load_snapshot` rejects mismatched hashes. Run tests + `git diff --check`; commit. **Deliverable:** immutable canonical evidence with exact clickable human anchors.

**Runtime source mapping:** Place attached PDFs, six transcript markdown files and dictionary/README under `data/raw/` without renaming their contents. README counts are an expected *audit reference*, not hard-coded validity for unrelated fixtures. Print actual page/segment counts and investigate any differences. Do not ingest `tutor_turns.csv` into the knowledge index.

### Task 3: RAGFlow Docker, local model and adapter (reference track)

**Files:** `src/vlearn/ragflow_adapter.py`, `tests/test_ragflow_adapter.py`, `README.md`, `configs/retrieval.yaml`. Use upstream `docker/docker-compose.yml` and its `.env` in a **separately checked out pinned RAGFlow repository**; do not copy its Compose file into our repo unless a documented required override exists.

**Interfaces:**

```python
class RagflowAdapter:
    def __init__(self, sdk_client: object, dataset_ids: list[str]): ...
    def retrieve(self, question: str, page_size: int = 50) -> list[dict]: ...
    def list_document_chunks(self, dataset_id: str, document_id: str) -> list[dict]: ...
```

- [ ] Read [RF-06](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/configure_knowledge_base.md), [SDK `retrieve`](https://github.com/infiniflow/ragflow/blob/main/sdk/python/ragflow_sdk/ragflow.py), [dataset SDK](https://github.com/infiniflow/ragflow/blob/main/sdk/python/ragflow_sdk/modules/dataset.py) and [chunk example](https://github.com/infiniflow/ragflow/blob/main/example/http/chunk_example.sh) **at the chosen release tag**. Confirm names (`dataset_ids`, `document_ids`, `page`, `page_size`) rather than copying older docs with `datasets`/`documents`/`offset` variants.
- [ ] Write a fake SDK test expecting `retrieve(dataset_ids=..., question=..., page=1, page_size=50, top_k=1024, similarity_threshold=0.0, vector_similarity_weight=0.3, rerank_id=None, keyword=False, use_kg=False)`. Test nonzero error, timeout and an unmapped chunk returns `mapping_status="unresolved"`; do not invent page metadata.
- [ ] Run `python -m pytest tests/test_ragflow_adapter.py -q` to observe failure. Implement adapter using SDK methods, page through `Document.list_chunks` (verify signature on pinned version), preserve raw `ragflow_chunk_id`, dataset/document IDs, raw scores and fields. No direct DB reads or upstream code edits.
- [ ] Deploy pinned RAGFlow with official Docker Compose on a verified ≥16GB machine. Install Ollama locally and `ollama pull bge-m3`; check `curl http://localhost:11434/api/embed -d '{"model":"bge-m3","input":"attention mechanism"}'` from a compatible shell and ensure embedding length is 1024. For a host Ollama + containerized RAGFlow, check container access to `http://host.docker.internal:11434/` per RF-04 before provider configuration. The model download is a local-model setup step, not a remote content-upload exception.
- [ ] In RAGFlow UI: add Ollama embedding provider, create a dataset **with BGE-M3 selected before parsing**, choose `Presentation` for PDFs and `General` for MD where available; upload and parse only the 8 learning-content files. Verify parsing reaches terminal success per document, inspect image/formula-heavy pages manually, and log any unsupported parsing behavior. For API-based import, use the pinned SDK's `DataSet.upload_documents` and `async_parse_documents`, not guessed REST methods.
- [ ] Run one bilingual query through SDK and save raw response and mapping table locally. Assert retrieval errors are reported and successful results remain source-traceable when possible. Run tests; commit adapter and setup docs only. **Deliverable:** stable RAGFlow native reference, no hidden dependency in the canonical builder.

**Caveat:** The RAGFlow parser's chunks do not necessarily align to PDF pages/transcript `[Txx-NNN]` segments. Build a verified mapping for any scored native hits; if no reliable locator exists, mark unresolved and do not score as a match. Keep the standalone canonical pipeline working even if RAGFlow's API or ingestion is temporarily unavailable.

### Task 4: Independent CPU indexes and deterministic retrieval

**Files:** `src/vlearn/index.py`, `src/vlearn/retrieve.py`, `scripts/build_indexes.py`, `configs/retrieval.yaml`, `configs/it_glossary.yaml`, `tests/test_retrieve.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class RankedEvidence:
    evidence_id: str
    rank: int
    score: float
    source_ranks: dict[str, int]
    source_scores: dict[str, float]


def build_indexes(snapshot_dir: Path, index_dir: Path, model_id: str) -> None: ...
def retrieve(query: str, method: str, top_k: int, filters: dict[str, str] | None = None) -> list[RankedEvidence]: ...
def weighted_rrf(bm25_ids: list[str], dense_ids: list[str], k: int, w_bm25: float, w_dense: float) -> list[RankedEvidence]: ...
```

- [ ] Write failing tests: `query: ` / `passage: ` prefixes applied exactly once; E5 vector dimension 384; stable cosine sort; lexical tokenizer retains `C++`, `RRF`, `Q/K/V`, `self-attention`; a duplicated evidence ID contributes only once per source; missing candidate contributes zero; tie-break by evidence ID. Validate depth and weights (nonnegative; weights sum to 1; `k>0`; `top_k>0`).
- [ ] Run `python -m pytest tests/test_retrieve.py -q` and verify failure.
- [ ] Implement BM25 with [bm25s public API](https://github.com/xhluca/bm25s): `bm25s.tokenize(texts, ...)`, `.index`, `.retrieve(..., k=...)`; persist **the ordered evidence-ID mapping** next to BM25 arrays. Do not use English-only stemming or English stopwords on mixed-language documents. Implement a narrow regex tokenizer preserving IT tokens and use it consistently for indexing and queries; write the regex directly into the unit tests.
- [ ] Implement CPU E5 with [model card](https://huggingface.co/intfloat/multilingual-e5-small/blob/main/README.md): `SentenceTransformer(model_id, device="cpu")`; encode passages with `passage: ` and queries with `query: ` and `normalize_embeddings=True`; `np.float32` saved arrays; cosine = matrix dot product after normalization; verify dim=384. For long page/segment evidence, tokenizer-window into 448 content tokens with 64-token overlap, keep each prefixed window <=512 positions, index `(evidence_id, window_idx)`, aggregate dense score with maximum window similarity before final ranking, and retain every original page/segment as the gold evaluation unit. Never silently truncate long evidence. Keep a stable separate dense index directory keyed by model revision + snapshot hash.
- [ ] Implement filters before ranking for both branches. Fusion 1-based ranks: `w_bm25/(k+r_bm25) + w_dense/(k+r_dense)`, `k=60`, `w_bm25=w_dense=0.5`, retrieval depth=50/branch by default. Deduplicate by canonical ID and save per-source rank and score. Never mix BM25 and dense raw scores directly.
- [ ] Build fixture snapshot indexes, run `bm25`, `e5_dense`, `rrf` twice; assert ranking byte-identical for fixed fixtures. A corrupt snapshot hash, changed model revision, wrong dimension or stale BM25 ID mapping must error. Run tests + `git diff --check`; commit. **Deliverable:** transparent, replaceable CPU retrievers independent of RAGFlow internals.

**Avoid premature features:** no separate Qdrant server at this corpus size; if index throughput actually becomes a bottleneck, document measured latency/memory first. Do not claim Ollama BGE-M3 dense embeddings and local E5 vectors occupy one embedding space.

### Task 5: Human-verified evaluation and experiment runner

**Files:** `src/vlearn/evaluate.py`, `scripts/run_eval.py`, `tests/test_evaluate.py`, `README.md`. Store real `gold.jsonl` under gitignored `data/local_gold/`; commit only a fabricated sample schema.

**Interfaces:**

```python
def validate_gold(rows: list[dict], evidence_ids: set[str]) -> tuple[list[dict], dict]: ...
def metrics_for_query(gold_ids: set[str], ranked_ids: list[str]) -> dict[str, float]: ...
def evaluate(gold_path: Path, method: str, out_dir: Path) -> dict[str, object]: ...
```

- [ ] Write failing metric tests: gold `{a,b}`, top5 `[x,a,y,b]` gives `Recall@5=1.0`, `MRR@10=0.5`; top5 `[x,a,y]` gives `Recall@5=0.5`; no matching top10 gives MRR=0; unlabeled query excluded from denominators; `gold_evidence_ids=[]` handled as abstention, never zero-divide. Test duplicate predictions cannot inflate recall.
- [ ] Run `python -m pytest tests/test_evaluate.py -q` to see failure. Implement query-level metrics and macro averaging with explicit `n_verified`, `n_unlabeled`, `n_unanswerable`, `n_failed`. Report `candidate_coverage@50` and provenance resolution independently. Measure wall-clock latency with `time.perf_counter()` for the actual retrieval call; percentile interpolation documented in metrics manifest.
- [ ] Curate 50–100 queries from `student_question` locally. Use `turn_id` in local annotation logs; separate preset questions, split multilingual/IT and image/formula-location categories. Verify gold page/segment manually against originals; **do not** fill gold by copying `tutor_reply`. Split development and held-out query IDs before trying weight grids. If there are no verified labels, runner must output `status="unscored"` rather than invented accuracy.
- [ ] Output `artifacts/runs/<run_id>/ranked.jsonl`, `metrics.json`, `manifest.json`; include input snapshot hash, gold hash, source filters, model revision, weights, candidate depth, tokenizer/glossary version, hardware and timings. Reject direct metric comparisons if hashes or query partitions differ.
- [ ] Run a synthetic fully labeled evaluation fixture and independently recompute two expected scores by hand. Run tests + `git diff --check`; commit. **Deliverable:** honest, auditable retrieval comparison with no held-out leakage.

### Task 6: Minimal API/UI, source navigation and final verification

**Files:** `src/vlearn/api.py`, `src/vlearn/ui.py`, `tests/test_api.py`, `README.md`. API and UI are optional conveniences **only after** the CLI retrieval and evaluation are correct.

**Interfaces:**

```json
POST /search {"query":"attention là gì?","method":"rrf","top_k":5,"filters":{}}
200 {"snapshot_id":"...","latency_ms":12.3,"results":[{"evidence_id":"...","page_1based":5,"segment_ids":[],"modality":"text","source_path":"...","score":0.01,"asset_url":"/assets/..."}]}
```

- [ ] Write failing FastAPI TestClient tests: blank query -> HTTP 422/400; illegal method -> 422; unknown evidence ID -> 404; asset path traversal -> 403/404; valid evidence returns source info and never leaks absolute host filesystem paths or unescaped user text. Test that an empty extracted slide page still has a viewable image and is explicitly marked not semantically searchable.
- [ ] Run `python -m pytest tests/test_api.py -q` to observe failure. Implement routes `GET /health`, `POST /search`, `GET /evidence/{evidence_id}`, `GET /assets/{asset_id}` using allowlisted manifest assets and validated path containment. UI: query input, method selector, ranked cards, page image/segment link and `provenance_unresolved` label. No answer-generation chatbox or unverifiable visual-match language.
- [ ] Run `python -m pytest -q`, `python -m compileall -q src scripts`, `git diff --check` and a local smoke test of **all three independent methods**. Run native RAGFlow test only if hardware prerequisite and local service are available; otherwise report blocked/not-run, never mark native integration as passing. For any failures, correct the root cause and rerun the complete check.
- [ ] Verify restricted data exclusion: `git status --short`; `git check-ignore data/raw/example.pdf data/derived/example.json artifacts/runs/example.json .env`; scan staged paths for raw packs, tokens and gold. Inspect the saved `manifest.json` for exact source and model hashes. Commit code/tests/docs only.
- [ ] Produce a handoff note with commands, hardware specs, source coverage counts, accuracy denominators, measured CPU latency, known parser failure pages, missing gold categories and explicitly deferred video/visual semantic retrieval. **Deliverable:** reproducible CPU MVP, not an unverified production claim.

## Commands to expose in README (names are project-defined contracts)

```powershell
# From Windows PowerShell after Python/uv/Docker prerequisites are installed:
uv sync --frozen
uv run python scripts/preflight.py
uv run python scripts/build_evidence.py --raw-dir data/raw --out-dir data/derived/snapshots
$snapshot = (Get-Content data/derived/current_snapshot.txt -Raw).Trim()
uv run python scripts/build_indexes.py --snapshot-dir "$snapshot" --out-dir data/derived/indexes
uv run python scripts/run_eval.py --gold data/local_gold/gold.jsonl --method bm25
uv run python scripts/run_eval.py --gold data/local_gold/gold.jsonl --method e5_dense
uv run python scripts/run_eval.py --gold data/local_gold/gold.jsonl --method rrf
uv run pytest -q
```

`scripts/build_evidence.py` must print the created snapshot directory and write `data/derived/current_snapshot.txt`. The PowerShell invocation reads that exact path rather than guessing a hash. If the checked-out app uses different command conventions, update the README **and tests together** so there is exactly one documented entrypoint per action.

## Implementation review checklist

- [ ] Requirement trace: spec Gates A–D each have a passing test or an explicitly recorded blocked/manual check.
- [ ] Contradiction audit: RAGFlow uses BGE-M3 while independent dense uses E5; two indexes, no mixed vector space.
- [ ] Provenance audit: page/segment IDs verified; failed extraction surfaced; no false visual-retrieval claims.
- [ ] Experiment audit: immutable snapshot, stable IDs, fair filters, correct macro metrics, held-out untouched.
- [ ] Privacy audit: no raw uploads, public repos, source content in logs or external APIs.
- [ ] Status audit: distinguish tests actually run, manual checks, missing hardware and future features.

**Execution boundary:** This file is an agent-ready plan, not evidence that Docker, parsers, model downloads or retrieval tests have already run on the user's PC. Begin with Task 1 and report any blocker before proceeding.

# Lab Simulator — Unified Workflow MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, honest Lab Simulator demo: choose an available lab, proceed through human-reviewed learning checkpoints, explore evidence, receive one real AI coaching response, complete a deterministic quiz, see contextual tips, and optionally self-report real-lab completion.

**Architecture:** A single FastAPI/Python application serves a small HTML/JavaScript client. An **offline, human-approved, versioned lab bundle** separates source evidence and private answer keys from public checkpoint content. Runtime is a session state machine with read-only evidence/retrieval, a single bounded AI coach call, a rule grader, a contextual tip selector, and a self-report recorder. It never runs the learner's code or changes their repository.

**Tech Stack:** Python **3.11**, FastAPI, Pydantic **2**, Uvicorn, pytest, httpx, Google GenAI SDK (`google-genai`) for a configurable real model; Python stdlib for hashing, JSON, pathlib, regex, `random`. Plain HTML/JavaScript; no vector database, GPU, browser build chain, agent framework, MCP execution, or mandatory embeddings. If the actual team's repository already has an equivalent stack, **inspect first and adapt the path map in a reviewed plan revision**; do not blindly replace its code.

**Spec:** `docs/superpowers/specs/2026-09-18-labsim-unified-workflow-design.md` (approved), with `docs/superpowers/specs/2026-09-18-labsim-design-divergence.md` for decisions explicitly rejected or deferred. Do **not** execute the older scenario-generation or Case Detective-only plans.

## Global Constraints

- One learner workflow, **no** “Học hiểu/Thử sức” mode switch. Choose Lab → chronological checkpoints, flexible exploration *within* a checkpoint. **Load/resume from checkpoint is pending**, not an MVP API or UI claim.
- Demonstrate **one Lab 3 bundle**, ideally **two reviewed learning checkpoints**, at least one with interactive evidence, **one real AI coach call**, and a **reviewed answer-key quiz**. If only one checkpoint is verified, show only one and disclose that scope.
- A *learning checkpoint* is not an official VLearn *CHECKPOINT 1/2/3*; store an optional mapping but never equate Simulator completion with completing the actual lab.
- Pure simulation: **no terminal, repo writes, GitHub/VLearn access, real tool execution, code fixes, automatic submission, or verified real-lab completion**. Action/evidence IDs only resolve human-approved observations.
- Source facts, scenario consequences, quiz answers, and tips are **human curated, version-bound, and source-linked**. AI must not invent evidence. `answer_key`, `reference_explanation`, unopened evidence and raw secrets never reach the coach request or public checkpoint response.
- VLearn Day 03 `Pasted text(1).txt` and the attached MCP-enhanced `CODELAB.md` disagree over Task 2.1 (`src/tools.py` dispatcher vs `src/mcp_server.py` MCP dispatch). Record a conflict and **do not publish a definitive fact/quiz about that file until a reviewer establishes the target cohort/version**.
- Textual VLearn quizzes include single/multi-select, matching and ordering, but their pasted text does **not** contain complete verified keys. Implement single/multi-select only, publish only questions with separately reviewed keys, and establish reproduction rights before redistributing VLearn text.
- `trace_waterfall.json` contains mock output/empty observation; `trace_eval.md` may contain template/report content. Neither proves an actual successful run. Source classification is mandatory; do not publish reports as verified observations.
- A deterministic first-attempt quiz score measures that specific quiz only; AI explanation feedback is **qualitative**, event counts do not prove learning, and real-lab completion is **self-reported** with skip allowed.
- Retain the CP4 quality bar from `labsim_submission/spec.md` (§7, proposed ≥16/20 plus specified zero-violation hard bars) without post-hoc threshold changes. The old set evaluates a different AI task: create a *new, labeled coach-specific golden set* and report non-comparability; do not claim old tests passed.
- Content permission and privacy gate: never commit raw VLearn exports, unapproved copies, chatlog, `.env`, personal data, secret-bearing traces, or private bundles to public Git. Do not send these to model APIs. A human must explicitly approve the material and its allowed display.
- Source provenance includes version + path/locator + hash; citations are validated by application code. UI explicitly labels *source instruction*, *code*, *report*, *verified observation*, and *hypothetical*.
- **Timebox:** two hours is a target, not a guarantee. Cut extra checkpoints, optional lexical search UI, matching/ordering, extra Labs and extra agent calls before cutting content integrity, real-AI demonstration, correct grading, self-report provenance or tests.
- **Workspace caveat:** provided materials are loose files under `/mnt/data`, not an established runnable Lab Simulator Git checkout. The target tree below is relative to the **team's actual app repo root**, not the original Lab 3 repo. Verify its location before creating files; do not `git init` in `/mnt/data`, claim commits that did not happen, or write into the original lab's `src/`.

## Execution setup and file map

First, in the team's **actual app repository**, locate `README`, app entrypoint, package files, tests and `.git`. Preserve any existing working components. If none exists, create the following *new app* layout there. The original Lab 3 code is **read-only input**, not a destination for changes.

```text
<app-repo>/
  docs/superpowers/specs/2026-09-18-labsim-unified-workflow-design.md
  docs/superpowers/specs/2026-09-18-labsim-design-divergence.md
  docs/superpowers/plans/2026-09-18-labsim-unified-mvp-implementation.md
  pyproject.toml                  # dependencies, pytest settings and editable installation
  .gitignore                      # private/generated data, .env, local sessions
  src/labsim/__init__.py
  src/labsim/models.py            # Pydantic public/private bundle types and enums
  src/labsim/ingest.py            # offline allowlisted source scan/chunk/hash; CLI
  src/labsim/catalog.py           # approved bundle validation, safe public projections
  src/labsim/retrieval.py         # read-only scoped lexical lookup; optional UI integration
  src/labsim/sessions.py          # one-process fresh sessions, state/events, checkpoint order
  src/labsim/quiz.py              # fixed-key grading and first/latest attempts
  src/labsim/coach.py             # model port, Gemini adapter, context and output checks
  src/labsim/tips.py              # seeded contextual tip scheduler
  src/labsim/api.py               # FastAPI composition; endpoints and static UI
  src/labsim/eval_runner.py       # testable golden-set result aggregation
  src/labsim/static/index.html    # single-page native HTML/JS demo
  scripts/validate_bundle.py      # publish-time entrypoint, no runtime generation
  content/day03/README.md        # contributor instructions only; no unapproved raw content
  tests/conftest.py              # synthetic *approved-like* data factory, fake provider
  tests/test_ingest.py
  tests/test_catalog.py
  tests/test_retrieval.py
  tests/test_sessions.py
  tests/test_quiz.py
  tests/test_coach.py
  tests/test_tips.py
  tests/test_api.py
  eval/coach_golden.jsonl        # sanitized, human-reviewed cases only
  eval/run_coach_golden.py       # records real results + reviewer fields; no fake passes
  data/private/                  # gitignored: permitted original documents, reviewed bundle
  data/generated/                # gitignored: source index and runtime artifacts
```

**Contracts to keep consistent across tasks (use these names everywhere):**

```python
# models.py — Pydantic 2 models; these are signatures, not code already implemented.
class SourceRef(BaseModel):
    source_id: str; path: str; start_line: int; end_line: int; sha256: str
class Evidence(BaseModel):
    evidence_id: str; title: str; excerpt: str; source: SourceRef
    epistemic_label: Literal["instruction", "code", "reported", "verified_observation", "hypothetical"]
    review_status: Literal["approved", "draft", "conflict"]
    reviewed_by: str
class Question(BaseModel):
    question_id: str; kind: Literal["single_select", "multi_select"]
    prompt: str; options: dict[str, str]; answer_key: list[str]
    explanation: str; source_ids: list[str]; review_status: Literal["approved", "draft", "conflict"]
    reviewed_by: str
class Tip(BaseModel):
    tip_id: str; text: str; checkpoint_ids: list[str]
    source_ids: list[str]; spoiler_for: list[str]
    review_status: Literal["approved", "draft", "conflict"]
    reviewed_by: str
class Checkpoint(BaseModel):
    checkpoint_id: str; title: str; objective: str; briefing: str
    evidence_ids: list[str]; question_ids: list[str]; tip_ids: list[str]
    official_milestone_id: str | None = None
class LabBundle(BaseModel):
    lab_id: str; title: str; bundle_version: str; source_manifest_sha256: str
    status: Literal["approved", "draft", "conflict"]
    checkpoints: list[Checkpoint]; evidence: list[Evidence]
    questions: list[Question]; tips: list[Tip]
    reference_explanations: dict[str, str]  # private: keyed by checkpoint_id
class CoachFeedback(BaseModel):
    observation_acknowledged: str; unsupported_inference: str
    next_question: str; cited_evidence_ids: list[str]; uncertainty: str

# ingest.py
# scan_sources(source_dir: Path, lab_id: str, out_dir: Path) -> dict
# catalog.py
# load_approved_bundle(path: Path, source_manifest: dict) -> LabBundle
# public_checkpoint(bundle: LabBundle, checkpoint_id: str) -> dict
# retrieval.py
# search_sources(index: list[dict], lab_id: str, query: str, top_k: int = 5) -> list[dict]
# sessions.py
# class SessionStore: create(bundle: LabBundle) -> dict; get(session_id: str) -> dict
#   reveal(session_id: str, evidence_id: str, bundle: LabBundle) -> Evidence
#   hypothesize(session_id: str, text: str) -> dict
#   advance(session_id: str, bundle: LabBundle) -> dict
#   self_report(session_id: str, value: str | None) -> dict
# quiz.py
# grade(question: Question, selected: list[str]) -> bool
# record_attempt(session: dict, question: Question, selected: list[str]) -> dict
# coach.py
# class ModelPort(Protocol): generate(self, payload: dict) -> str
# coach_feedback(session: dict, bundle: LabBundle, model: ModelPort, hint_level: int) -> CoachFeedback
# tips.py
# select_tip(bundle: LabBundle, session: dict, event: str, rng: random.Random) -> Tip | None
# api.py
# create_app(bundle_path: Path, manifest_path: Path, model: ModelPort | None = None) -> FastAPI
```

**Review/commit policy for every task:** create focused failing tests → run targeted tests and inspect the *actual* failure → implement minimal change → run targeted plus prior tests → review for source leakage and scope creep → `git add`/`git commit` **only in an existing repo**. Commit commands below are execution instructions, **not claims that commits already exist**.

---

### Task 1: Offline source ingestion with traceable provenance

**Files:** Create `pyproject.toml`, `.gitignore`, `src/labsim/__init__.py`, `src/labsim/ingest.py`, `tests/test_ingest.py`; use `data/private/day03/` as an externally supplied, permitted read-only source folder. Do not copy unapproved VLearn content into tracked files.

**Interfaces:** Consumes `source_dir: Path`, `lab_id: str`, `out_dir: Path`; produces an inventory dict and `data/generated/day03/source_manifest.json`, `source_chunks.jsonl`. `scan_sources()` is offline and never calls a model. Each chunk binds a path, exact 1-based line range, source hash and epistemic source-kind; the inventory hash binds the source snapshot.

- [ ] **Step 1 — write a failing test** in `tests/test_ingest.py`:

```python
from pathlib import Path
from labsim.ingest import scan_sources

def test_scan_is_scoped_and_skips_secrets(tmp_path: Path):
    src = tmp_path / "input"; src.mkdir()
    (src / "README.md").write_text("# Lab\nTool call returns an observation.\n", encoding="utf-8")
    (src / ".env").write_text("API_KEY=DO_NOT_EXPORT", encoding="utf-8")
    out = tmp_path / "output"
    manifest = scan_sources(src, "day03", out)
    assert manifest["lab_id"] == "day03"
    assert manifest["files"][0]["path"] == "README.md"
    data = (out / "source_chunks.jsonl").read_text(encoding="utf-8")
    assert "observation" in data and "DO_NOT_EXPORT" not in data
    assert '"start_line": 1' in data
```

- [ ] **Step 2 — verify RED:** `python -m pytest tests/test_ingest.py -v` → import/function missing, not a silent skip.
- [ ] **Step 3 — minimal implementation:** use `Path.rglob`, an allowlist `{.md,.txt,.py,.json,.yaml,.yml}`, reject symlinks and hidden folders, exclude `.env*`, `tutor_turns*.csv`, `transcript*`, `data/private` recursion, any credential-pattern files and file size >1 MiB; decode UTF-8 strictly. Hash raw file bytes with `hashlib.sha256`, split line chunks (e.g. 40 lines with 5-line overlap), produce deterministic JSONL ordered by normalized relative path and line start. `source_kind` must be assigned from a **reviewed inventory** (unknown defaults to `reported`/unverified, never `verified_observation`); skip secret-looking content and report skipped paths without their bytes. `source_manifest_sha256` is SHA-256 of canonical sorted inventory JSON. Explicitly reject `..` paths and disallow overwriting source folder. Keep all output in the gitignored generated path. Configure minimal package metadata and pytest in `pyproject.toml` (`pythonpath=["src"]`).
- [ ] **Step 4 — GREEN/regression:** `python -m pytest tests/test_ingest.py -v`; add test for stable re-ingestion hash, symlink exclusion and a source containing a fake instruction/prompt injection (stored only as source text, never treated as runtime policy).
- [ ] **Step 5 — source audit:** compare selected chunk text and line numbers to original `README.md` and `CODELAB.md` *without choosing between their conflicting versions*. If a real source file is unavailable, record `blocked: missing permitted source` rather than substituting an invented one.
- [ ] **Step 6 — commit if repo exists:** `git add pyproject.toml .gitignore src/labsim/__init__.py src/labsim/ingest.py tests/test_ingest.py && git commit -m "feat: index reviewed lab sources with provenance"`.

**Acceptance:** deterministic manifest/chunks, no secrets indexed, no lab-code execution, no misleading observed-run labels.

### Task 2: Human curation and published bundle gate

**Files:** Create `src/labsim/models.py`, `src/labsim/catalog.py`, `scripts/validate_bundle.py`, `tests/conftest.py`, `tests/test_catalog.py`, `content/day03/README.md`. Reviewed bundle lives at `data/private/published/day03.json` (gitignored) until permission to redistribute any part is confirmed.

**Interfaces:** Consumes `source_manifest.json` plus a human-authored JSON bundle; produces `LabBundle` or explicit validation errors. `public_checkpoint()` strips private key/solution and unopened evidence. Define the exact models in the shared-contract block above; `Checkpoint` IDs must be unique and ordered by array position (no unexplained ordinal gaps).

- [ ] **Step 1 — failing tests**:

```python
import json
import pytest
from labsim.catalog import load_approved_bundle, public_checkpoint

def test_bundle_blocks_conflict_and_private_answer(tmp_path, approved_bundle_dict, source_manifest):
    src = tmp_path / "bundle.json"
    src.write_text(json.dumps(approved_bundle_dict, ensure_ascii=False), encoding="utf-8")
    lab = load_approved_bundle(src, source_manifest)
    public = public_checkpoint(lab, lab.checkpoints[0].checkpoint_id)
    assert "answer_key" not in str(public)
    assert "reference_explanations" not in str(public)
    bad = dict(approved_bundle_dict, status="conflict")
    src.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="approved"):
        load_approved_bundle(src, source_manifest)
```

`tests/conftest.py` must define `approved_bundle_dict`, `source_manifest`, and parsed `approved_bundle` as **synthetic** fixtures with two short learning checkpoints, three fake evidence cards, a single-select question, a multi-select question, one safe tip and matching source refs/hashes. Mark text clearly `SYNTHETIC TEST FIXTURE` and **never** show it as a real Day 03 achievement.
- [ ] **Step 2 — RED:** `python -m pytest tests/test_catalog.py -v` → missing models/catalog.
- [ ] **Step 3 — implementation:** implement Pydantic types; in `load_approved_bundle`, check `status==approved`, source-manifest hash match, all IDs unique, all referenced IDs exist, question kind/key option IDs consistent, `answer_key` nonempty, `review_status==approved` for every visible evidence/question/tip, source refs path + hash + line range resolve to the scanned manifest, every question has `source_ids` and a nonempty `reviewed_by` on each evidence, question and tip. Reject `reported`/`hypothetical` evidence as proof of actual observed test outcomes. Refuse unreviewed Task 2.1 file-location claims and incomplete VLearn answer keys. Return public projections via an explicit allowlist; keep `reference_explanations`, `answer_key`, and unopened evidence on server only. Run `scripts/validate_bundle.py --bundle ... --manifest ...` with nonzero exit on failure.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_catalog.py -v`; tests for cross-bundle source mismatch, broken citation, absent quiz key, duplicate ID, and spoiler-tip rejection by human review gate.
- [ ] **Step 5 — actual Day 03 content gate (human, not coding agent):** group designates **one version/cohort** (VLearn vs MCP-enhanced CODELAB); obtains permission for displayed passages; annotates every source `instruction/code/report/observed/hypothetical`; reviews **at least one** meaningful scenario and **one** keyed quiz, with optional second checkpoint. Verify line refs manually. If cannot resolve Task 2.1 conflict, exclude that fact and use a different, version-independent case. If cannot verify any quiz key, **stop launch**, do not guess answers from marks such as “Your answer”.
- [ ] **Step 6 — commit code/tests only:** `git add src/labsim/models.py src/labsim/catalog.py scripts/validate_bundle.py tests/conftest.py tests/test_catalog.py content/day03/README.md && git commit -m "feat: validate human-approved lab bundles"`.

**Acceptance:** an approved bundle loads, unapproved/conflicting content fails closed; only safe public fields are exposed. **Human sign-off is a real dependency, not an AI-generated checkbox.**

### Task 3: Scoped read-only lexical retrieval (support tool, never ground truth)

**Files:** Create `src/labsim/retrieval.py`, `tests/test_retrieval.py`; use Task 1 `source_chunks.jsonl`. This is the only search component needed; **BM25 or vector search is not mandatory** for MVP.

**Interfaces:** `search_sources(index: list[dict], lab_id: str, query: str, top_k: int = 5) -> list[dict]`; returns source refs and text, never answer keys. Core scenario evidence is selected by explicit ID, **not** by retrieval ranking.

- [ ] **Step 1 — failing test**:

```python
from labsim.retrieval import search_sources

def test_retrieval_never_crosses_lab():
    index = [
        {"lab_id": "day03", "text": "dispatcher observation", "source_id": "s1"},
        {"lab_id": "day04", "text": "dispatcher observation", "source_id": "s2"},
    ]
    assert [h["source_id"] for h in search_sources(index, "day03", "dispatcher")] == ["s1"]
    assert search_sources(index, "day03", "not_in_sources") == []
```

- [ ] **Step 2 — RED:** `python -m pytest tests/test_retrieval.py -v`.
- [ ] **Step 3 — implementation:** Unicode-aware lowercase `re.findall(r"\w+", query.lower())`, reject empty query, match only rows whose `lab_id` equals target, rank by number of matched query tokens and stable `source_id`, filter out unapproved/private source kinds, return up to `top_k` with locator/path/hash. This is simple lexical retrieval, **not BM25**: label it honestly. Never append a retrieved chunk to `viewed_evidence_ids` until the learner explicitly opens it; never let ad-hoc hits override curated case truth.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_retrieval.py -v`; also test stable ranking and a zero-hit query (“không tìm thấy”, no hallucinated snippet).
- [ ] **Step 5 — commit if repo exists:** `git add src/labsim/retrieval.py tests/test_retrieval.py && git commit -m "feat: add lab-scoped read-only source lookup"`.

**Acceptance:** same-bundle, source-linked results; no false claim that retrieval is grounded if source/index missing. **Timebox cut:** backend helper can exist without a search UI; core scenario continues using direct evidence IDs.

### Task 4: Fresh-session state machine and evidence explorer

**Files:** Create `src/labsim/sessions.py`, `tests/test_sessions.py`.

**Interfaces:** `SessionStore.create/get/reveal/hypothesize/advance/self_report` exactly as the shared contracts. Store **in memory within one server process**, no checkpoint resume/recovery after refresh or restart; `get` is used for the current session, not a promise of durable resume. `phase` values: `exploring`, `debrief`, `summary`. Store `checkpoint_id`, `viewed_evidence_ids`, versioned hypotheses, `hint_level`, attempt records, `tips_seen`, `tips_disabled`, and `lab_completion_self_reported`.

- [ ] **Step 1 — failing tests**:

```python
import pytest
from labsim.sessions import SessionStore

def test_reveal_is_id_scoped_and_never_runs_code(approved_bundle):
    store = SessionStore()
    state = store.create(approved_bundle)
    ev_id = approved_bundle.checkpoints[0].evidence_ids[0]
    ev = store.reveal(state["session_id"], ev_id, approved_bundle)
    assert ev.evidence_id == ev_id
    assert ev_id in store.get(state["session_id"])["viewed_evidence_ids"]
    with pytest.raises(ValueError):
        store.reveal(state["session_id"], "foreign-lab-evidence", approved_bundle)

def test_advance_is_ordered_and_not_a_resume_feature(approved_bundle):
    store = SessionStore(); state = store.create(approved_bundle)
    result = store.advance(state["session_id"], approved_bundle)
    assert result["current_checkpoint_id"] == approved_bundle.checkpoints[1].checkpoint_id
```

- [ ] **Step 2 — RED:** `python -m pytest tests/test_sessions.py -v`.
- [ ] **Step 3 — implement:** UUID4 session ID, lock around in-memory dictionary mutations if app can process concurrent requests, enforce bundle version and current-checkpoint membership, copy approved evidence on `reveal` (do not mutate bundle), append timestamped events; store hypothesis versions without interpreting user text as instructions. `advance` returns next checkpoint in manifest order or `phase=summary`; **no skip/restore endpoint**. `self_report` only accepts `completed`, `in_progress`, `not_started`, `prefer_not_to_say` or `None` (skip), and only in `phase=summary` (otherwise raises `ValueError` mapped to HTTP 409). It stores timestamp and never creates a `verified` field.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_sessions.py -v`; add tests for empty hypothesis, correct initial hypothesis retained, modified hypothesis versioning, unauthorized evidence, invalid self-report, and completed/skip remaining distinct. When debrief opens, record explicit event; do not gate progression on correct quiz answers.
- [ ] **Step 5 — commit:** `git add src/labsim/sessions.py tests/test_sessions.py && git commit -m "feat: track simulated checkpoint sessions"`.

**Acceptance:** chronological checkpoints, non-linear evidence opening, no real-lab state claims, no durable resume promise.

### Task 5: Deterministic single/multi-select grading and reveal policy

**Files:** Create `src/labsim/quiz.py`, `tests/test_quiz.py`; use Question model and in-memory `Session` attempt records.

**Interfaces:** `grade(question, selected)` returns exact Boolean; `record_attempt(session, question, selected)` mutates one session's attempt history and returns public `{question_id, correct, attempt_number, post_reveal}`. Grader reads a server-private bundle, not question/answer data sent by the browser.

- [ ] **Step 1 — failing tests**:

```python
import pytest
from labsim.quiz import grade, record_attempt

def test_multi_select_set_match_not_text_fuzzy(approved_bundle):
    q = next(x for x in approved_bundle.questions if x.kind == "multi_select")
    assert grade(q, list(reversed(q.answer_key))) is True
    assert grade(q, [q.answer_key[0]]) is False
    with pytest.raises(ValueError):
        grade(q, ["unknown-option"])

def test_first_attempt_immutable_after_retry(approved_bundle):
    q = approved_bundle.questions[0]; session = {"attempts": []}
    record_attempt(session, q, ["wrong-id"] if "wrong-id" in q.options else [next(k for k in q.options if k not in q.answer_key)])
    record_attempt(session, q, q.answer_key)
    assert session["attempts"][0]["correct"] is False
    assert session["attempts"][1]["correct"] is True
```

- [ ] **Step 2 — RED:** `python -m pytest tests/test_quiz.py -v`.
- [ ] **Step 3 — implementation:** validate option IDs, refuse duplicate choices, single-select length exactly one, multi-select normalized set equality, reject question lacking approved key; `record_attempt` stores first attempt unchanged and appends later attempts. Mark `post_reveal=True` if the reference answer was already shown; expose correctness only at submission and explanation **only after an explicit end/debrief**, per spec. No LLM grader and no knowledge percentage.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_quiz.py -v`; test invalid/empty IDs, reorder invariance, post-reveal retakes, and question from another checkpoint rejected in API (Task 8).
- [ ] **Step 5 — commit:** `git add src/labsim/quiz.py tests/test_quiz.py && git commit -m "feat: grade reviewed checkpoint quizzes deterministically"`.

**Acceptance:** same approved key + answer always gives same result; no score claimed as measured knowledge gain.

### Task 6: Grounded AI hypothesis coach with a *real* provider and fake-model tests

**Files:** Create `src/labsim/coach.py`, `tests/test_coach.py`. Avoid reusing the original Lab 3 `providers(1).py`: it is lab code with a silent mock-fallback behavior inappropriate for claiming a real AI call in the Simulator.

**Interfaces:** `ModelPort.generate(payload: dict) -> str` returns JSON string; `coach_feedback(session, bundle, model, hint_level) -> CoachFeedback`. `GeminiCoach.generate` is the production adapter and must require a configured API key; model name comes from `GEMINI_MODEL`, with a documented tested default selected by the team. No writable application tools are exposed to the model.

- [ ] **Step 1 — failing test**:

```python
import json
import pytest
from labsim.coach import coach_feedback

class CaptureModel:
    def __init__(self, answer): self.answer = answer; self.payload = None
    def generate(self, payload): self.payload = payload; return json.dumps(self.answer)

def test_coach_sees_only_opened_evidence_and_no_key(approved_bundle):
    e = approved_bundle.evidence[0]
    session = {"lab_id": approved_bundle.lab_id,
               "current_checkpoint_id": approved_bundle.checkpoints[0].checkpoint_id,
               "viewed_evidence_ids": [e.evidence_id],
               "hypothesis_versions": [{"text": "I suspect the wrong boundary"}],
               "hint_level": 0}
    model = CaptureModel({"observation_acknowledged": "The shown trace has one call.",
                          "unsupported_inference": "The cause is not yet established.",
                          "next_question": "Which observation could distinguish the alternatives?",
                          "cited_evidence_ids": [e.evidence_id], "uncertainty": "Insufficient evidence"})
    result = coach_feedback(session, approved_bundle, model, hint_level=0)
    assert result.cited_evidence_ids == [e.evidence_id]
    text = json.dumps(model.payload)
    assert "answer_key" not in text and "reference_explanations" not in text
    assert all(x.evidence_id == e.evidence_id or x.excerpt not in text
               for x in approved_bundle.evidence)
```

- [ ] **Step 2 — RED:** `python -m pytest tests/test_coach.py -v`.
- [ ] **Step 3 — implement context builder:** only objective, hypothesis text, already-viewed approved evidence excerpts+IDs+source locator, explicit hint level, and a brief boundary policy; no unviewed excerpt, source document dump, raw answer key/reference solution or secret. Treat learner/evidence text as **quoted data**, not a system instruction. Hint level `0` question, `1` reasoning gap, `2` diagnostic check; refuse an escalation unless the server observes a learner-requested hint event. For no evidence, return a bounded request to choose a source **without presenting a fabricated factual diagnosis**; this is an application rule, not a fake model response.
- [ ] **Step 4 — real adapter + output validation:** use `google.genai.Client(api_key=...)` and `client.models.generate_content(model=..., contents=..., config=types.GenerateContentConfig(response_mime_type="application/json"))`; parse `response.text` through `CoachFeedback.model_validate_json`, reject cited IDs outside `viewed_evidence_ids`, non-JSON, empty next question, provider error/timeouts or unsupported assertions detectable through deterministic source-ID checks. Log model name, latency, status and redacted ID-level metadata only, **not learner secrets**. A regex cannot guarantee semantic non-leakage; require human-reviewed golden cases for semantic leaks. Missing API key → explicit `503 coach_unavailable`, **never** silently swap in mock output.
- [ ] **Step 5 — negative tests:** `python -m pytest tests/test_coach.py -v`; add fake output with nonexistent citation, an unopened ID, malformed JSON, missing key, and an injection string inside learner hypothesis that attempts to reveal solution; assert no key or hidden text entered `model.payload`. Use mock fake **only for tests**; real demo must log an actual API result.
- [ ] **Step 6 — live acceptance (manual, credentials held by team):** set `GEMINI_API_KEY` in environment outside Git; run app, request feedback with one evidence opened, verify provider result and a cited source ID; record whether the call succeeded. If API is unavailable, mark this acceptance **blocked**, not passed.
- [ ] **Step 7 — commit:** `git add src/labsim/coach.py tests/test_coach.py && git commit -m "feat: add bounded evidence-only AI coach"`.

**Acceptance:** proof of one real call (or an honest blocked report), no key/unseen evidence in prompt, no fabricated citations, user-controlled hints.

### Task 7: Contextual tip scheduler and real-lab self-report

**Files:** Create `src/labsim/tips.py`, `tests/test_tips.py`; `SessionStore.self_report` already exists from Task 4 and will be exercised by API in Task 8.

**Interfaces:** `select_tip(bundle, session, event, rng) -> Tip | None` using injectable `random.Random(seed)`; session `tips_seen`, `tips_disabled`, `hint_level` and current checkpoint govern eligibility. No runtime model call.

- [ ] **Step 1 — failing test**:

```python
import random
from labsim.tips import select_tip

def test_tip_is_contextual_seeded_and_non_spoiler(approved_bundle):
    cp = approved_bundle.checkpoints[0]
    session = {"current_checkpoint_id": cp.checkpoint_id,
               "tips_seen": [], "tips_disabled": False, "session_phase": "exploring"}
    t1 = select_tip(approved_bundle, session, "checkpoint_opened", random.Random(9))
    t2 = select_tip(approved_bundle, session, "checkpoint_opened", random.Random(9))
    assert t1 is None or t1.tip_id == t2.tip_id
    assert t1 is None or cp.checkpoint_id in t1.checkpoint_ids
    assert t1 is None or cp.checkpoint_id not in t1.spoiler_for
    session["tips_disabled"] = True
    assert select_tip(approved_bundle, session, "checkpoint_opened", random.Random(9)) is None
```

- [ ] **Step 2 — RED:** `python -m pytest tests/test_tips.py -v`.
- [ ] **Step 3 — implementation:** trigger only on `checkpoint_opened`/`evidence_viewed` (not each keystroke), filter approved tips by checkpoint, `spoiler_for`, already shown IDs and enabled state; cap at one tip per checkpoint. Inject `rng` so tests can reproduce selection. Return a nonblocking dismissible card with source link in Task 8; do not use JavaScript `alert()`.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_tips.py -v`; include no-eligible-tip and repeated-event tests, and a self-report unit test verifying skip `None` stays distinct from `not_started`.
- [ ] **Step 5 — commit:** `git add src/labsim/tips.py tests/test_tips.py && git commit -m "feat: surface safe contextual facts and self-report"`.

**Acceptance:** deterministic when seeded, varied when seed varies and multiple eligible tips exist; no spoiler or forced interruption; self-report never marked verified.

### Task 8: Thin API and complete five-minute demo UI

**Files:** Create `src/labsim/api.py`, `src/labsim/static/index.html`, `tests/test_api.py`. Reuse earlier domain modules; never duplicate answer-key or session logic in JS. App configuration defaults to **no published bundle**, not synthetic content masquerading as Day 03.

**Interfaces:** `create_app(bundle_path, manifest_path, model=None)` loads the approved bundle at startup if both paths exist; when absent it exposes an explicit empty catalog without synthetic demo data. Routes below are *implementation decisions* for this plan and should stay stable across tests/UI:

| Method | Path | Purpose / important response rule |
|---|---|---|
| GET | `/api/labs` | Only published, approved labs. Empty list if no approved content. |
| POST | `/api/sessions` | `{lab_id}` → fresh `session_id`, checkpoint ID; no resume ID. |
| GET | `/api/sessions/{id}/checkpoint` | Public briefing, question prompts/options, **no key, reference solution, unopened evidence**. |
| POST | `/api/sessions/{id}/evidence` | `{evidence_id}` → approved excerpt + source/epistemic label; validate current checkpoint. |
| POST | `/api/sessions/{id}/hypothesis` | `{text}` → versioned hypothesis metadata, not a judgement. |
| POST | `/api/sessions/{id}/coach` | `{hint_level}` → validated AI feedback or 503; no mock-as-real. |
| POST | `/api/sessions/{id}/quiz` | `{question_id, selected:[...]}` → deterministic result and first/latest metadata. |
| POST | `/api/sessions/{id}/debrief` | Explicitly finish checkpoint → approved reference explanation, then advance permission. |
| POST | `/api/sessions/{id}/next` | Move to next ordinal checkpoint or summary; no load-from-checkpoint endpoint. |
| POST | `/api/sessions/{id}/tip` | `{event}` → eligible approved tip or null; store shown ID. |
| POST | `/api/sessions/{id}/self-report` | `{value|null}` → unverified learner answer; summary remains accessible on skip. |

- [ ] **Step 1 — failing API test**:

```python
from fastapi.testclient import TestClient
from labsim.api import create_app

def test_public_api_hides_answers_and_keeps_self_report_unverified(
        approved_bundle_file, source_manifest_file, fake_model):
    app = create_app(approved_bundle_file, source_manifest_file, model=fake_model)
    client = TestClient(app)
    r = client.post("/api/sessions", json={"lab_id": "day03"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    p = client.get(f"/api/sessions/{sid}/checkpoint").json()
    assert "answer_key" not in str(p)
    assert "reference_explanations" not in str(p)
    # Self-report is allowed only after the final checkpoint summary.
    assert client.post(f"/api/sessions/{sid}/self-report",
                       json={"value": "completed"}).status_code == 409
    for step in range(2):
        assert client.post(f"/api/sessions/{sid}/debrief").status_code == 200
        assert client.post(f"/api/sessions/{sid}/next").status_code == 200
    response = client.post(f"/api/sessions/{sid}/self-report",
                           json={"value": "completed"})
    assert response.status_code == 200
    assert response.json()["lab_completion_self_reported"] == "completed"
    assert "verified" not in response.text
```

`tests/conftest.py` must also write `approved_bundle_file`, `source_manifest_file` to `tmp_path` from the same synthetic fixture and define `fake_model` (used only for tests). The fixture contains exactly two ordered checkpoints so tests can finish both before self-report.
- [ ] **Step 2 — RED:** `python -m pytest tests/test_api.py -v`.
- [ ] **Step 3 — API implementation:** compose `SessionStore`, catalog, grader, coach, tips and optional source index. Use Pydantic request bodies and explicit 400/403/404/409/503 errors. Validate session ID, checkpoint relation, question membership and lab bundle version on each call. Return only data required by the UI. Avoid exposing `data/private` through static serving or error messages. Do not add resume/load-from-checkpoint route.
- [ ] **Step 4 — UI implementation:** native one-page UI: Lab picker (one real Lab), “pure simulation” label, current checkpoint/briefing, evidence cards with neutral titles, editable hypothesis, button “Nhận phản hồi AI”, separately activated “Xin gợi ý thêm”, quiz with radio/checkbox, debrief, next checkpoint, contextual dismissible tip card with “Tắt tips”, summary and skippable real-lab completion popup. Show visible states for provider unavailable and missing approved content; never pretend a call succeeded. Display source locator and epistemic label next to evidence/feedback.
- [ ] **Step 5 — end-to-end route tests:** `python -m pytest tests/test_api.py -v`; test unavailable bundle → empty-state; cross-checkpoint evidence → 403; unopened evidence not leaked by coach/public GET; no hypothesis → bounded error; provider down → 503, quiz still functions; first attempt retained after retry; skip self-report works; no `/api/sessions/{id}/resume` route.
- [ ] **Step 6 — run smoke locally:** `python -m uvicorn labsim.api:app --host 127.0.0.1 --port 8000`; implement module-level `app = create_app(...)` using `LABSIM_BUNDLE_PATH` and `LABSIM_MANIFEST_PATH` environment variables, with `None` for either missing path so `/api/labs` returns an empty catalog instead of crashing or showing fake content. Keep `create_app` directly injectable for tests. Visit `http://127.0.0.1:8000` and perform the complete demo. Missing approved bundle → empty-state instead of a fake demo.
- [ ] **Step 7 — commit:** `git add src/labsim/api.py src/labsim/static/index.html tests/test_api.py && git commit -m "feat: expose single-workflow simulator demo"`.

**Acceptance:** a real learner can reach summary through one workflow; interactive code/evidence is safely labeled; no answer key in public API.

### Task 9: Evaluations, release gate and handoff to team

**Files:** Create `eval/coach_golden.jsonl`, `eval/run_coach_golden.py`, `tests/test_eval_runner.py`, `content/day03/README.md` update with actual content instructions; amend `pyproject.toml` if needed to provide `pytest`/launch scripts. Do **not** modify the original CP4 §7 bar.

**Interfaces:** Golden rows contain `case_id`, `lab_id`, `checkpoint_id`, `hypothesis`, `viewed_evidence_ids`, `hint_level`, `risk_class`, `expected_behavior`, `source_turn_id` (nullable), `observed_output` (populated only after a real run), `reviewer`, `pass` (nullable before review). Runner reports total/passed/failed/blocked plus separate hard-bar counts and model/prompt/bundle hash; never fills results with synthetic outputs.

- [ ] **Step 1 — failing test**:

```python
import json
from labsim.eval_runner import summarize_results

def test_blocked_is_not_pass():
    rows = [{"case_id": "c1", "pass": True},
            {"case_id": "c2", "pass": False},
            {"case_id": "c3", "pass": None}]
    assert summarize_results(rows) == {"total": 3, "passed": 1, "failed": 1, "blocked": 1}
```

For this test, put the implementation in `src/labsim/eval_runner.py` and make `eval/run_coach_golden.py` a thin import/CLI entrypoint; add `src/labsim/eval_runner.py` to Task 9's file map.
- [ ] **Step 2 — RED:** `python -m pytest tests/test_eval_runner.py -v`.
- [ ] **Step 3 — implementation:** `summarize_results(rows)` must preserve nulls as blocked. Runner reads a **human-reviewed, sanitized ≥20-case** set with ≥2 cases per each of 4 risk classes, and ≥10 mapped/developed from true chat turns only if source IDs and use permissions verified; otherwise report the unmet challenge requirement plainly. Each record runs against the *real* coach adapter when available, validates schema and citations automatically, exports redacted outputs for human judgement of source support/semantic spoiler and a separate trace of hard-bar violations. Pin model, prompt version, bundle hash, run time, denominator; do not treat deterministic schema validation alone as full grounding evaluation. Do not secretly substitute canned outputs for provider errors.
- [ ] **Step 4 — GREEN:** `python -m pytest tests/test_eval_runner.py -v`; test malformed golden row, duplicate case IDs, unreviewed source turn IDs and a provider error counted as blocked/failed rather than passed.
- [ ] **Step 5 — release checklist:** run `python -m pytest -q`; `python scripts/validate_bundle.py --bundle data/private/published/day03.json --manifest data/generated/day03/source_manifest.json`; inspect `/api/labs` and `/api/sessions/{id}/checkpoint` for absence of keys and raw source dumps; manually test happy, insufficient evidence, unsupported action, correction, injection, timeout, quiz retry, tip spoiler and self-report skip. Record *actual* outcomes, including failures. Check that at least one coach response was produced by a configured real API and backed by opened evidence; if not, release is **not “working AI”**.
- [ ] **Step 6 — handoff:** document which source/version and reviewer approved each Day 03 question, which features remain pending (resume, extra Lab, optional search UI, matching/ordering, free-action consequence engine, multi-agent/prompt chaining), and whether content permission is sufficient for the intended demo audience. Update §4 and §9 of `spec.md` **only after explicit owner approval**; preserve historical CP4 submission and §7 threshold.
- [ ] **Step 7 — commit if repo exists:** `git add src/labsim/eval_runner.py eval/run_coach_golden.py tests/test_eval_runner.py content/day03/README.md && git commit -m "test: measure grounded coach and document release gates"`. Add `eval/coach_golden.jsonl` only if its content is approved for the destination repo.

**Acceptance:** release outcome is evidence-backed, with separate functional, AI-quality, provenance and learning-quiz measures; blocked/untested items cannot be represented as passing.

---

## Two-hour prioritization and stop conditions

1. **Preflight outside the two-hour coding clock:** team confirms repo, runtime secrets and permitted **reviewed Day 03 bundle/key**. If this is absent, the critical path is **human content review first**, not more code. Review and legal permission are not made free by a coding assistant.
2. **Core build path:** Tasks **2 → 4 → 5 → 6 → 7 → 8** using a previously reviewed bundle; Task 1 ingestion is needed if approved source inventory is not already available. Task 3 retrieval helper is **optional for the demo** and may run after the first working end-to-end path. Task 9 is required before claiming quality bar or readiness to submit.
3. **Scope-cut rule:** at 60 minutes, no vetted key → stop auto-graded demo claim; at 90 minutes, no working coach call → prioritize fixing that over a second checkpoint or search; at 120 minutes, report built/blocked/untested honestly. These timestamps are planning gates, not results.
4. **Definition of done for *demo*:** one real source-reviewed Lab appears, interactive checkpoint supports evidence exploration, feedback from **real** model is observably conditional on user hypothesis/viewed evidence, single/multi-select quiz grades from a verified key, contextual nonspoiler tip can appear, summary separates Simulator results from a skippable self-report. Full golden-set pass and real learner benefit remain separate validation claims.

## Execution handoff

Use `superpowers:subagent-driven-development` (fresh agent per task, two-stage review) **if the coding environment supports subagents**; otherwise `superpowers:executing-plans` with batches and checkpoints in the team's actual repo. The attached files in `/mnt/data` are reference inputs; do not mistake them for an application Git repository. Do not start execution on the historical plan that generates consequence/scenario at runtime.

# VLearn Multimodal Retrieval MVP — Architecture & Product Specification

**Date:** 2026-09-16  
**Status:** Implementation-ready design proposal; not an implemented or benchmarked system  
**Environment:** Windows x86-64 + Docker Desktop (WSL2), CPU only  
**Primary objective:** Retrieve verifiable evidence from Vietnamese/English course materials, with source navigation and reproducible retrieval experiments.

## 0. Read this first: architectural decision and source of truth

**Primary framework is RAGFlow**, as explicitly requested in the latest handoff. The prior conversation proposed RAG-Anything; that is **not** a hidden dependency of this spec. Keep RAG-Anything as a later **alternative parser / multimodal-ingestion spike**, not a second framework in the MVP. RAGFlow handles document ingestion, user-facing document inspection, and a built-in retrieval reference. A small **independent retrieval lab** operates over an immutable canonical evidence export so that BM25, dense embeddings, candidate depth and fusion can be changed and evaluated without forking RAGFlow. Avoid a duplicate Qdrant server or a second app backend at MVP scale.

This is a deliberately **staged multimodal** MVP: searchable text from PDFs, transcript segments and discoverable page images first; native image-to-image or image-to-text retrieval and video *semantic* indexing are explicitly outside MVP acceptance. Storing a page screenshot and retrieving the associated text does **not** constitute visual-content retrieval. Formulas are searchable only if extracted accurately as text/LaTeX; otherwise show the original page and flag coverage as missing. No CPU-only VLM quality/performance claims.

### Verified upstream references (research starts here, not with a broad search)

| ID | Authoritative reference | What the agent needs from it |
|---|---|---|
| RF-01 | [RAGFlow official repository](https://github.com/infiniflow/ragflow) | Framework ownership, release/tag, Docker layout. |
| RF-02 | [Official quickstart](https://github.com/infiniflow/ragflow/blob/main/docs/quickstart.mdx) | x86 CPU support; ≥4 cores, ≥16 GB RAM, ≥50 GB disk; WSL2 `vm.max_map_count`; dataset and chunk inspection; embedding model lock after indexing. |
| RF-03 | [Docker configurations](https://github.com/infiniflow/ragflow/blob/main/docs/administrator/configurations/configurations.md) and [docker README](https://github.com/infiniflow/ragflow/blob/main/docker/README.md) | `.env`, Compose, internal services, runtime ports, image and embedding service settings. |
| RF-04 | [Deploy local models](https://github.com/infiniflow/ragflow/blob/main/docs/guides/models/deploy_local_llm.mdx) | RAGFlow ↔ Ollama provider, `bge-m3` example, `host.docker.internal` networking. |
| RF-05 | [Model provider configuration](https://github.com/infiniflow/ragflow/blob/main/docs/guides/models/llm_api_key_setup.md) | Configure and verify model types; local models, defaults. |
| RF-06 | [Dataset configuration](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/configure_knowledge_base.md) | General/Presentation parsing, ingestion choices, fixed embedding per dataset, retrieval testing, chunk edits. |
| RF-07 | [Python SDK `RAGFlow.retrieve`](https://github.com/infiniflow/ragflow/blob/main/sdk/python/ragflow_sdk/ragflow.py) | Verified Python retrieval call parameters and response handling; prefer SDK over invented REST payloads. |
| RF-08 | [Official chunk HTTP example](https://github.com/infiniflow/ragflow/blob/main/example/http/chunk_example.sh) and [Python Document SDK](https://github.com/infiniflow/ragflow/blob/main/sdk/python/ragflow_sdk/modules/document.py) | Upload, list/add/update chunks; exact dataset/document/chunk API routes. |
| RF-09 | [RAGFlow retrieval implementation](https://github.com/infiniflow/ragflow/blob/main/rag/nlp/search.py) | Inspect internal fusion behavior **only if** API experiments require it; do not assume `vector_similarity_weight=0/1` isolates candidate generation. |
| M-01 | [BAAI/bge-m3 model card](https://huggingface.co/BAAI/bge-m3/blob/main/README.md) and [Ollama package](https://ollama.com/library/bge-m3) | Multilingual BGE-M3, dense embedding; Ollama package ≈1.2 GB. Model capability for sparse/multi-vector does NOT imply the Ollama embedding endpoint exposes those representations. |
| M-02 | [intfloat/multilingual-e5-small model card](https://huggingface.co/intfloat/multilingual-e5-small/blob/main/README.md) and [config](https://huggingface.co/intfloat/multilingual-e5-small/blob/main/config.json) | 384-dimensional embeddings, `query: ` / `passage: ` prefixes even for non-English text; max 512 input positions; independent CPU experiment model, NOT a drop-in replacement for the BGE-M3 dataset. |
| M-03 | [BAAI/bge-reranker-v2-m3 model card](https://huggingface.co/BAAI/bge-reranker-v2-m3/blob/main/README.md) | Optional later multilingual cross-encoder, not in mandatory CPU MVP. |
| ENG-01 | [bm25s repo / usage](https://github.com/xhluca/bm25s) | Minimal reproducible local BM25 index/retrieval. |
| ENG-02 | [Sentence Transformers encoding API](https://github.com/huggingface/sentence-transformers/blob/main/sentence_transformers/sentence_transformer/model.py) | `device="cpu"`, `normalize_embeddings=True`; confirm supported options in installed version. |
| ALT-01 | [RAG-Anything official repository](https://github.com/HKUDS/RAG-Anything) | Optional phase: Docling/MinerU, content-list insertion and VLM-driven modalities; do not install it during MVP. |

**Version policy:** Source URLs above are discovery/documentation anchors, not immutable release pins. Before installing, record one **stable RAGFlow release tag + image digest**, one Python dependency lock and model revisions/digests in `artifacts/manifest.json`. Do not ship `nightly` or unpinned `main`; if a documented API differs at the pinned version, use the pinned tag's matching SDK/docs, note the discrepancy, and adapt only the integration adapter. Never invent a version number or model revision before testing. On Windows, first verify the Docker Desktop/WSL2 prerequisites; if RAM <16 GB or available disk <50 GB, **stop the RAGFlow deployment** and report hardware blocker, rather than silently switch architecture.

## 1. User journeys, non-goals and acceptance

**User stories.** A learner asks a Vietnamese, English or mixed-language IT question; sees five relevant evidence cards, each with content, course context and a source anchor; opens the exact transcript segment or slide page. An engineer changes only a config file to compare lexical, dense and RRF retrieval on identical evidence and an identical gold set. A curator inspects extracted page text beside its screenshot and marks equations/diagrams as not yet covered when extraction misses them.

**Acceptance contract (functional):**

1. The two supplied PDF decks and six cleaned transcripts are ingestible and a query returns ranked evidence **without invoking a generative answer LLM**. Each result has a canonical ID, source path, type, and either 1-based PDF page or transcript segment ID. Source opening must land on that location; absent anchors display an explicit `unresolved` state rather than a fabricated page.
2. Every PDF page has a locally rendered image asset tied to `doc_id/page`, with OCR/parser text separately attributed. A diagram-only or equation-image query may return no semantic match; UI must not claim otherwise.
3. Independently runnable `bm25`, `e5_dense`, and `rrf` experiments use the **same immutable canonical evidence snapshot**; a RAGFlow-native retrieval run is a separately labeled reference, not an interchangeable BM25/E5 run.
4. The CPU-only system has a repeatable offline evaluation command that writes per-query rankings, aggregate Recall@5, Recall@10, MRR@10, p50/p95 wall-clock latency, run configuration and failure counts. No target quality threshold is asserted before gold labels exist.
5. No raw learner chatlog leaves the machine; no proprietary VLearn data enters git, hosted inference, external logging, or a public issue. Only minimal anonymized examples may be shared when permitted by the hackathon policy.

**Non-goals:** answer-generation quality, agent reasoning, fine-tuning, knowledge graph, Qdrant server, 13,494 answers as gold labels, full video indexing, audio transcription, image-vector retrieval, claim of accuracy on diagrams/formulas without annotations, production auth/multi-tenant support, automatic hyperparameter optimization on a test set.

## 2. Source inventory & source-derived limitations

The provided VLearn README reports **13,494 tutor turns**, **six cleaned transcripts** (~700 coded segments), **two 29-page slide PDF decks**. The dictionary states `turn_id`, `student_question`, `tutor_reply`, `course_id`, `lecture_code`, `is_preset` and citation fields; `lecture_code` is **not unique across courses**. The transcript README maps files `01..06` to sessions and marks ASR uncertainty `[không nghe rõ]`. These counts and relationships are **from the supplied pack, not validated runtime results**.

| Input | Canonical identity / processing | Gold-label policy |
|---|---|---|
| `d1-slide-hackathon.pdf`, `d2-slide-hackathon.pdf` | Source SHA-256 + stable PDF page number; keep page images and parsed text, link any formula to source page. | Gold may be document+page; page-level evidence must remain evaluable even if parser changes. |
| `transcript-01-clean.md` through `transcript-06-clean.md` | Preserve `[T01-001]` etc. as stable span anchors; source SHA-256, section title and sequence. | Gold is exact segment ID (or explicit set of IDs for multi-hop). |
| `tutor_turns.csv` | Local query candidate pool only. Split `is_preset`; `course_id + lecture_code` for context; `turn_id` for audit. | `tutor_reply`, `has_citation`, `rating` are **not** verified correct evidence labels. Manually assign source/page/segment, otherwise omit from scoring. |
| Future video files | No video is present in this delivery; allow schema fields `start_ms/end_ms` only. | No indexing/evaluation commitment until actual files and permissions arrive. |

**Data handling:** source pack permits hackathon-only use and prohibits publicly uploading complete files; learner input includes prompt-injection-like text and is always untrusted data. Sanitize path traversal, never execute material as prompts or commands, and prevent repository inclusion with `.gitignore` and a staged-file check. Report suspected residual personal information privately through organizer channels.

## 3. Architecture and ownership boundaries

```text
raw VLearn files (read-only; local, gitignored)
  ├─> RAGFlow (Docker): native PDF/MD dataset parsing + UI + optional baseline retrieval
  │       └─ SDK chunks + dataset/document IDs ─┐
  ├─> deterministic transcript segment parser ──┼─> canonical evidence.jsonl + assets/
  └─> deterministic per-page PDF renderer ──────┘        (hash-bound, immutable snapshot)
                                                          │
                                 ┌────────────────────────┴───────────────────────┐
                                 │                                                │
                           bm25s lexical                              multilingual-E5-small CPU
                                 │                                                │
                                 └────────────── canonical-ID RRF ────────────────┘
                                                          │
                                               ranked.jsonl / metrics.json
                                                          │
                                            small FastAPI + Streamlit UI
```

**Why two retrieval tracks?** RAGFlow's native retrieval provides a ready UI and a useful reference, but internal weighted fusion and candidate generation are not the same as independently controlled BM25 and E5 branches. The experiment lab indexes **one canonical snapshot** and allows correct ablation without patching upstream. The application code must never confuse its local index with the RAGFlow-native index.

**Canonical evidence store** is a local JSONL file plus assets and manifest, *not* a database dependency. Evidence fields:

```json
{
  "evidence_id": "sha256:...", "source_id": "sha256:...", "source_path": "slides/d1-slide-hackathon.pdf",
  "source_type": "pdf", "modality": "text", "content": "...", "title": "AI & LLM Foundation",
  "course_id": null, "lecture_code": "D01", "page_1based": 5, "segment_ids": [],
  "start_ms": null, "end_ms": null, "asset_path": "assets/<source-id>/page-0005.png",
  "ragflow_dataset_id": "...", "ragflow_document_id": "...", "ragflow_chunk_ids": ["..."],
  "parser_id": "ragflow:<pinned-version>:presentation", "content_sha256": "sha256:..."
}
```

`evidence_id` is `sha256(source_id + canonical locator + content_sha256 + normalization_schema_version)`; `source_id` hashes source bytes; `content_sha256` hashes normalized *content*, not the index model. IDs change deterministically when content changes; original transcript ID and page location remain independent human anchors. For page evidence use `locator = page:<1based>`; for transcript use `locator = segment:<Txx-NNN>`. Store supplementary RAGFlow chunk IDs in a **mapping file** if a single exported chunk spans pages/segments; never guess a page from a RAGFlow chunk. When page provenance is missing from chunk metadata, canonical PDF-page text is produced from a deterministic local extractor and labeled with its extractor ID; RAGFlow chunk becomes a separate unmapped reference until resolved. `null` means unknown, not zero.

**Export rules:** no auto-intermix of RAGFlow chunks with canonical segments; one PDF page / one transcript-coded segment is the initial retrieval unit. Output `evidence.jsonl` sorted by source path and locator, and `manifest.json` with input byte hashes, tool versions, parser config, normalization version and export count. Indexes must refuse to run on mismatched evidence/manifest hashes. A new parser version creates a new snapshot, never edits one in place.

## 4. CPU-only model and infra decisions

**RAGFlow reference index:** Official local-model guide demonstrates Ollama with `bge-m3`. Install Ollama **locally** (Windows host or Docker) and verify an `/api/embed` request before configuring it as RAGFlow's embedding provider. If RAGFlow is in Docker and Ollama runs on Windows host, use `http://host.docker.internal:11434` *only after verifying reachability from the RAGFlow container*. Set the dataset embedding model **before parsing**: RAGFlow docs say it cannot be swapped after chunks exist without deleting/rebuilding. BGE-M3 is multilingual and emits 1024-dimensional dense embeddings per its model card; its sparse/multi-vector capabilities are not automatically used merely because Ollama exposes the model.

**Independent dense experiment:** `intfloat/multilingual-e5-small` via Sentence Transformers on `device="cpu"`, normalized embeddings, `query: ` prepended to queries and `passage: ` prepended to evidence **even in Vietnamese**. Its model card reports 384 dimensions and a 512-position model limit. **Do not truncate page-level evidence**: split long evidence into deterministic tokenizer-aware windows (initial budget 448 content tokens, 64-token overlap, with the `passage: ` prefix and special tokens kept within 512 positions). Store `(evidence_id, window_index)` for every vector, use the maximum window similarity as the evidence-level dense score, and deduplicate to canonical evidence IDs before fusion. Record window counts and any extraction loss; the PDF page/transcript segment stays the evaluation unit. CPU performance is an unknown to measure, not a promised SLA. This model **does not replace** the BGE-M3 embedding used inside an already-indexed RAGFlow dataset.

**Independent sparse experiment:** `bm25s` with a deterministic tokenizer. Begin with Unicode NFKC + lowercase + whitespace/punctuation splitting that preserves terms such as `QKV`, `BM25`, `RRF`, `C++`, `GPT-4`, `self-attention` and `Q/K/V`; explicitly unit-test these. This is a provisional IT-term tokenizer, not a claim of optimal Vietnamese word segmentation. Keep a versioned, curated alias glossary (`self-attention` ↔ `cơ chế tự chú ý`, etc.), containing only validated equivalences. Preserve the unmodified original query; expansion is an optional, logged branch. No translation API or silent query rewriting.

If the pinned RAGFlow release requires a default chat model even for document processing, configure a verified **local-only** lightweight Ollama chat model solely to satisfy that dependency; disable optional LLM-driven enrichment and do not use it for answer generation or silently connect a cloud provider. Record any memory impact and stop if CPU/RAM budget cannot accommodate it.

**No GPU-driven mandatory components:** VLM captioning, ColPali, BGE reranker, MinerU GPU parsing, Whisper and full video processing are disabled by default. The optional reranker card is included to make later experiments straightforward; implementing it is not an MVP acceptance condition.

## 5. Retrieval contracts and scoring

`retrieve(query, method, top_k, filters, snapshot_id) -> list[RankedEvidence]`. Methods: `bm25`, `e5_dense`, `rrf`, `ragflow_native`. The first three read the exact same canonical snapshot. `ragflow_native` returns RAGFlow chunk IDs with mapping status; evaluate only mapped evidence at matching granularity, and report unmapped results separately.

For lexical and dense run depths initially use **K=50** each (configuration, not a presumed optimum); sort ties by `evidence_id` ascending. Deduplicate by `evidence_id` **before** fusion; use canonical IDs, never raw string equality or arbitrary source-row indexes. Weighted RRF for a present candidate `d`:

`RRF(d) = w_bm25/(k + rank_bm25(d)) + w_dense/(k + rank_dense(d))`

Ranks are 1-based and absent candidates contribute zero. Defaults: `w_bm25=0.5`, `w_dense=0.5`, `k=60`; these are **starting values**, not fitted values. Retain source ranks, raw scores and fusion contributions in each result. Test candidate pool membership separately from top-k final ranking; never call one a model-quality metric for another.

RAGFlow-native SDK settings initially: `page=1, page_size=50, top_k=1024, similarity_threshold=0.0, vector_similarity_weight=0.3, keyword=False, rerank_id=None, use_kg=False`. Verify actual semantics, response fields and resource costs on the pinned release; `top_k` is *not* the number of final output chunks. `page_size` may affect candidate recall in some versions, so fix it across native comparisons; `vector_similarity_weight=0` or `1` is **not guaranteed to create independent BM25-only/dense-only candidate pools**. No native results are fused with E5 in a single uncalibrated score space.

**Filter and mapping:** `source_type`, `course_id`, `lecture_code`, `source_id` filters are applied consistently to all three independent methods **before candidate ranking**. Document code alone is never a unique lesson identifier; if lesson mapping to PDFs/transcripts cannot be validated, do not enforce a fabricated course filter. Multiple relevant evidence items for one query are allowed; `top_k` output is ordered evidence, not generated prose.

## 6. Evaluation protocol

Gold input `gold.jsonl` is manually curated, each line:

```json
{"query_id":"Q0001","query":"...","query_language":"vi_en","course_id":null,
 "gold_evidence_ids":["sha256:..."],"gold_source_anchors":["transcript-06-clean.md#T06-130"],
 "evidence_type":"text","annotation_status":"verified","annotator_note":"source checked"}
```

A query without a verified label is **excluded** from retrieval accuracy denominators and counted in `unlabeled_count`. Propose 50–100 queries initially, stratified by Vietnamese / English / mixed IT terms / slide-specific formula or diagram / multi-source. The transcript and PDF anchors are manually checked before turning `gold_source_anchors` into evidence IDs. Do not train/tune on the held-out evaluation queries; use development queries for a small declared grid over fusion weights and `k`, pick once, then evaluate once on held-out set. If too few labels for a meaningful split, report descriptive baseline only and refrain from optimization claims.

For each verified query with gold set G and predicted top-k set P: `Recall@k = |G ∩ P| / |G|` (macro-averaged across queries); `MRR@10 = 1/rank(first relevant result)` else zero. Report both page-level and segment-level when applicable; never score a PDF page as a matching transcript segment. Report `candidate_coverage@50`, retrieval failure rate, provenance resolution rate and p50/p95 latency on same machine. For zero-gold valid questions (intentional unanswerable cases), report abstention separately, not Recall@k. Save per-query rank lists so metrics can be recomputed independently.

**Comparability gate:** Run manifests must match `snapshot_sha256`, `gold_sha256`, filter settings, query set, tokenizer/embedding version and hardware profile for fair comparisons. A changed embedding entails rebuilding its own index; a changed parser entails a new evidence snapshot and a separately labeled experiment group. A tokenizer or glossary change creates a new lexical index version. No automatic best-score tuning on the held-out gold.

## 7. UX, API, failure modes and security

**UI minimum:** query input; method selector; top-k cards showing canonical ID, modality, score/source-rank breakdown, source/anchor, excerpt, original PDF page image for page evidence, and explicit `provenance_unresolved` badge. UI must label `text-linked page image` rather than `visual semantic match` when no image encoder is used. No chat-answer generation is necessary.

**App endpoints (our own, not claims about RAGFlow):** `GET /health`; `POST /search` `{query, method, top_k, filters}` -> `{snapshot_id, results, latency_ms}`; `GET /evidence/{evidence_id}` -> metadata and local asset route; optional `GET /runs/{run_id}` -> metric artifact. Never accept arbitrary filesystem paths from the client; evidence IDs are looked up in the manifest and asset paths must be resolved under `data/derived/assets`.

**Failure behavior:** missing Ollama / RAGFlow: show reference-index unavailable while local BM25/E5 can still work if prebuilt; missing parser text: keep page image and `extraction_status=failed`, never invent a caption; GPU-only dependency accidentally selected: fail-fast with explanatory error; duplicate document import: detect SHA-256 and reuse source; API timeout: bounded retry only for idempotent reads, preserve error; model download blocked: error with exact local prerequisite, never switch to hosted provider; model/index dimension or hash mismatch: halt; untrusted tutor text: display escaped, do not follow any instructions embedded in it.

**Repo exclusions:** ignore `data/raw/`, `data/derived/`, `artifacts/runs/`, `models/`, `.env`, auth tokens, and raw gold content when derived from restricted pack. Keep only empty examples/schemas in git. Keep all inference local; optional hosted service requires explicit organizer permission and a separate privacy review.

## 8. Delivery gates

**Gate A — environmental readiness:** actual RAM/disk/CPU and WSL2 capability checked; stable tag and image digest pinned; local embedding returns expected dimension; no remote provider or data egress.

**Gate B — provenance:** two PDF originals and six transcripts accounted for; page count and segment coverage printed; source link resolves for every scored evidence; JSONL/manifest hash validation passes.

**Gate C — reproducible retrieval:** `bm25`, `e5_dense`, `rrf` run end-to-end on CPU and write deterministic rankings for fixed artifacts; RAGFlow reference is available only if Gate A resources support it.

**Gate D — measurement:** frozen verified labels, correct denominators, per-query results, independent metric recomputation, representative bilingual IT queries and explicit multimodal *coverage limitations*.

**Scope stop:** do not start video/VLM/GraphRAG/LLM answer-generation until Gates A–D are reviewed. If Gate A fails (<16 GB RAM / <50 GB disk), record a blocker and request an explicit decision on a lean local-only retrieval fallback; do not relabel fallback as a RAGFlow deployment.
